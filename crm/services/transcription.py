import logging
from functools import lru_cache

from django.conf import settings

from crm.models import VisitReport

logger = logging.getLogger(__name__)


class TranscriptionError(Exception):
    """Raised when audio cannot be transcribed."""


@lru_cache(maxsize=1)
def _get_whisper_model():
    from faster_whisper import WhisperModel

    model_size = getattr(settings, 'WHISPER_MODEL_SIZE', 'small')
    device = getattr(settings, 'WHISPER_DEVICE', 'cpu')
    compute_type = getattr(settings, 'WHISPER_COMPUTE_TYPE', 'int8')

    return WhisperModel(model_size, device=device, compute_type=compute_type)


def transcribe_with_faster_whisper(audio_path: str) -> str:
    model = _get_whisper_model()
    segments, _info = model.transcribe(audio_path, language=None)
    text = ' '.join(segment.text.strip() for segment in segments if segment.text.strip())
    if not text:
        raise TranscriptionError('Transcription returned empty text.')
    return text


def transcribe_with_openai(audio_path: str) -> str:
    api_key = getattr(settings, 'OPENAI_API_KEY', '') or ''
    if not api_key:
        raise TranscriptionError('OPENAI_API_KEY is not set in environment.')

    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    with open(audio_path, 'rb') as audio_file:
        response = client.audio.transcriptions.create(
            model=getattr(settings, 'OPENAI_WHISPER_MODEL', 'whisper-1'),
            file=audio_file,
        )
    text = (response.text or '').strip()
    if not text:
        raise TranscriptionError('OpenAI transcription returned empty text.')
    return text


def transcribe_audio_file(audio_path: str) -> str:
    backend = getattr(settings, 'TRANSCRIPTION_BACKEND', 'local').lower()
    if backend == 'openai':
        return transcribe_with_openai(audio_path)
    return transcribe_with_faster_whisper(audio_path)


def transcribe_visit_report(visit_report: VisitReport, *, force: bool = False) -> str:
    if not visit_report.has_audio:
        raise TranscriptionError(f'VisitReport #{visit_report.pk} has no audio file.')

    if (
        visit_report.transcript
        and visit_report.processing_status == VisitReport.ProcessingStatus.TRANSCRIBED
        and not force
    ):
        return visit_report.transcript

    audio_path = visit_report.audio_file.path
    try:
        transcript = transcribe_audio_file(audio_path)
        visit_report.transcript = transcript
        visit_report.processing_status = VisitReport.ProcessingStatus.TRANSCRIBED
        visit_report.save(update_fields=['transcript', 'processing_status'])
        logger.info('Transcribed VisitReport #%s', visit_report.pk)
        return transcript
    except Exception as exc:
        visit_report.processing_status = VisitReport.ProcessingStatus.FAILED
        visit_report.save(update_fields=['processing_status'])
        logger.exception('Failed to transcribe VisitReport #%s', visit_report.pk)
        raise TranscriptionError(str(exc)) from exc
