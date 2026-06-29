import json
import logging
from datetime import date
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction

from crm.models import StoreVisit, VisitReport
from crm.services.store_matching import find_store, get_or_create_store, match_store

logger = logging.getLogger(__name__)

VALID_STATUSES = {choice.value for choice in StoreVisit.VisitStatus}

EXTRACTION_SYSTEM_PROMPT = """You extract structured sales visit data from field-rep voice note transcripts.
The rep may speak Urdu, English, or a mix. Return ONLY valid JSON matching this schema:

{
  "visits": [
    {
      "store_name": "string or null",
      "owner_name": "string or null",
      "area": "string or null",
      "visit_date": "YYYY-MM-DD or null",
      "status": "PENDING | ORDER_CONFIRMED | FOLLOW_UP_NEEDED | NO_REQUIREMENT | NOT_INTERESTED",
      "quantity_requested": integer or null,
      "rate_offered": number or null,
      "needed_by_date": "YYYY-MM-DD or null",
      "follow_up_required": boolean,
      "follow_up_date": "YYYY-MM-DD or null",
      "remarks": "string or null"
    }
  ]
}

Rules:
- One voice note may mention multiple stores; return one object per store visit.
- Default visit_date to the report date when not mentioned.
- Use null for unknown fields; never invent store owner or area.
- Map Urdu numbers to integers (e.g. دو -> 2).
- Resolve relative dates (next week, tomorrow) using the report date.
- status ORDER_CONFIRMED when bags are ordered; FOLLOW_UP_NEEDED when a future visit or sample is planned.
- follow_up_required true when the rep must return later.
- remarks: brief summary of what was discussed."""


class ExtractionError(Exception):
    """Raised when transcript cannot be extracted."""


def _build_user_prompt(transcript: str, report_date: date) -> str:
    return (
        f'Report date: {report_date.isoformat()}\n\n'
        f'Transcript:\n{transcript}'
    )


def _parse_llm_json(text: str) -> dict:
    text = (text or '').strip()
    if not text:
        raise ExtractionError('LLM returned empty response.')

    if text.startswith('```'):
        lines = text.splitlines()
        if lines and lines[0].startswith('```'):
            lines = lines[1:]
        if lines and lines[-1].strip() == '```':
            lines = lines[:-1]
        text = '\n'.join(lines).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ExtractionError(f'Invalid JSON from LLM: {exc}') from exc

    if not isinstance(data, dict) or 'visits' not in data:
        raise ExtractionError('LLM JSON must contain a "visits" array.')
    if not isinstance(data['visits'], list):
        raise ExtractionError('"visits" must be a JSON array.')

    return data


def extract_with_gemini(transcript: str, report_date: date) -> dict:
    api_key = getattr(settings, 'GEMINI_API_KEY', '') or ''
    if not api_key:
        raise ExtractionError('GEMINI_API_KEY is not set in environment.')

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    model = getattr(settings, 'GEMINI_MODEL', 'gemini-2.0-flash')

    response = client.models.generate_content(
        model=model,
        contents=[
            types.Content(
                role='user',
                parts=[
                    types.Part(text=EXTRACTION_SYSTEM_PROMPT),
                    types.Part(text=_build_user_prompt(transcript, report_date)),
                ],
            ),
        ],
        config=types.GenerateContentConfig(
            response_mime_type='application/json',
            temperature=0.1,
        ),
    )

    return _parse_llm_json(response.text)


def extract_with_openai(transcript: str, report_date: date) -> dict:
    api_key = getattr(settings, 'OPENAI_API_KEY', '') or ''
    if not api_key:
        raise ExtractionError('OPENAI_API_KEY is not set in environment.')

    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    model = getattr(settings, 'OPENAI_EXTRACTION_MODEL', 'gpt-4o-mini')

    response = client.chat.completions.create(
        model=model,
        temperature=0.1,
        response_format={'type': 'json_object'},
        messages=[
            {'role': 'system', 'content': EXTRACTION_SYSTEM_PROMPT},
            {'role': 'user', 'content': _build_user_prompt(transcript, report_date)},
        ],
    )
    content = response.choices[0].message.content or ''
    return _parse_llm_json(content)


def extract_transcript(transcript: str, report_date: date) -> dict:
    backend = getattr(settings, 'EXTRACTION_BACKEND', 'gemini').lower()
    if backend == 'openai':
        return extract_with_openai(transcript, report_date)
    return extract_with_gemini(transcript, report_date)


def _parse_date(value, default: date | None = None) -> date | None:
    if value is None or value == '':
        return default
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return default


def _parse_int(value) -> int | None:
    if value is None or value == '':
        return None
    try:
        parsed = int(value)
        return parsed if parsed >= 0 else None
    except (TypeError, ValueError):
        return None


def _parse_decimal(value) -> Decimal | None:
    if value is None or value == '':
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _normalize_visit(raw: dict, report_date: date) -> dict:
    status = (raw.get('status') or StoreVisit.VisitStatus.PENDING).upper()
    if status not in VALID_STATUSES:
        status = StoreVisit.VisitStatus.PENDING

    follow_up_required = bool(raw.get('follow_up_required', False))
    if status == StoreVisit.VisitStatus.FOLLOW_UP_NEEDED:
        follow_up_required = True

    return {
        'store_name': (raw.get('store_name') or '').strip(),
        'owner_name': (raw.get('owner_name') or '').strip(),
        'area': (raw.get('area') or '').strip(),
        'visit_date': _parse_date(raw.get('visit_date'), default=report_date),
        'status': status,
        'quantity_requested': _parse_int(raw.get('quantity_requested')),
        'rate_offered': _parse_decimal(raw.get('rate_offered')),
        'needed_by_date': _parse_date(raw.get('needed_by_date')),
        'follow_up_required': follow_up_required,
        'follow_up_date': _parse_date(raw.get('follow_up_date')),
        'remarks': (raw.get('remarks') or '').strip() or None,
    }


def _resolve_store(visit_data: dict):
    store_name = visit_data['store_name']
    owner_name = visit_data['owner_name']
    area = visit_data['area']

    if not store_name:
        return None, {
            'visit': visit_data,
            'reason': 'Store name is missing.',
            'candidate_store_ids': [],
        }

    if owner_name and area:
        store = find_store(store_name, owner_name, area)
        if store:
            return store, None
        store, _created = get_or_create_store(store_name, owner_name, area)
        return store, None

    result = match_store(store_name, owner_name, area)
    return None, {
        'visit': visit_data,
        'reason': result.reason,
        'candidate_store_ids': [s.pk for s in result.candidates],
    }


def _create_store_visit(visit_report: VisitReport, store, visit_data: dict) -> StoreVisit:
    return StoreVisit.objects.create(
        visit_report=visit_report,
        store=store,
        visit_date=visit_data['visit_date'] or visit_report.report_date,
        status=visit_data['status'],
        quantity_requested=visit_data['quantity_requested'],
        rate_offered=visit_data['rate_offered'],
        needed_by_date=visit_data['needed_by_date'],
        follow_up_required=visit_data['follow_up_required'],
        follow_up_date=visit_data['follow_up_date'],
        remarks=visit_data['remarks'],
    )


def _json_safe(value):
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _clear_prior_extraction(visit_report: VisitReport):
    payload = visit_report.extraction_payload or {}
    visit_ids = payload.get('created_visit_ids') or []
    if visit_ids:
        StoreVisit.objects.filter(pk__in=visit_ids, visit_report=visit_report).delete()


@transaction.atomic
def _apply_extraction(visit_report: VisitReport, llm_data: dict, backend: str) -> dict:
    created_visit_ids = []
    needs_review = []

    for raw in llm_data.get('visits', []):
        visit_data = _normalize_visit(raw, visit_report.report_date)
        store, review_item = _resolve_store(visit_data)
        if review_item:
            needs_review.append(review_item)
            continue
        store_visit = _create_store_visit(visit_report, store, visit_data)
        created_visit_ids.append(store_visit.pk)

    payload = _json_safe({
        'backend': backend,
        'raw_visits': llm_data.get('visits', []),
        'created_visit_ids': created_visit_ids,
        'needs_review': needs_review,
    })

    visit_report.extraction_payload = payload
    visit_report.processing_status = VisitReport.ProcessingStatus.EXTRACTED
    visit_report.save(update_fields=['extraction_payload', 'processing_status'])
    return payload


def extract_visit_report(visit_report: VisitReport, *, force: bool = False) -> dict:
    if not visit_report.transcript:
        raise ExtractionError(f'VisitReport #{visit_report.pk} has no transcript.')

    if (
        visit_report.processing_status == VisitReport.ProcessingStatus.EXTRACTED
        and visit_report.store_visits.exists()
        and not force
    ):
        return visit_report.extraction_payload or {}

    if force:
        _clear_prior_extraction(visit_report)

    try:
        llm_data = extract_transcript(visit_report.transcript, visit_report.report_date)
        backend = getattr(settings, 'EXTRACTION_BACKEND', 'gemini').lower()
        payload = _apply_extraction(visit_report, llm_data, backend)
        logger.info(
            'Extracted VisitReport #%s: %s visits, %s need review',
            visit_report.pk,
            len(payload['created_visit_ids']),
            len(payload['needs_review']),
        )
        return payload
    except ExtractionError:
        visit_report.processing_status = VisitReport.ProcessingStatus.FAILED
        visit_report.save(update_fields=['processing_status'])
        raise
    except Exception as exc:
        visit_report.processing_status = VisitReport.ProcessingStatus.FAILED
        visit_report.save(update_fields=['processing_status'])
        logger.exception('Failed to extract VisitReport #%s', visit_report.pk)
        raise ExtractionError(str(exc)) from exc
