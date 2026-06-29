from django.core.management.base import BaseCommand, CommandError

from crm.models import VisitReport
from crm.services.extraction import ExtractionError, extract_visit_report


class Command(BaseCommand):
    help = 'Extract structured store visits from transcribed visit reports using AI.'

    def add_arguments(self, parser):
        parser.add_argument('report_ids', nargs='*', type=int, help='VisitReport ID(s) to extract')
        parser.add_argument(
            '--all-transcribed',
            action='store_true',
            help='Extract all reports with status TRANSCRIBED.',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Re-extract even if visits already exist (removes prior auto-created visits).',
        )

    def handle(self, *args, **options):
        reports = VisitReport.objects.none()

        if options['all_transcribed']:
            reports = VisitReport.objects.filter(
                processing_status=VisitReport.ProcessingStatus.TRANSCRIBED,
            ).exclude(transcript='').exclude(transcript__isnull=True)
        elif options['report_ids']:
            reports = VisitReport.objects.filter(pk__in=options['report_ids'])
        else:
            raise CommandError('Provide report ID(s) or use --all-transcribed.')

        if not reports.exists():
            raise CommandError('No matching visit reports found.')

        success = 0
        for report in reports:
            self.stdout.write(f'Extracting report #{report.pk} ({report.sales_rep.name})...')
            try:
                payload = extract_visit_report(report, force=options['force'])
            except ExtractionError as exc:
                self.stdout.write(self.style.ERROR(f'  Failed: {exc}'))
                continue

            created = len(payload.get('created_visit_ids', []))
            review = len(payload.get('needs_review', []))
            self.stdout.write(self.style.SUCCESS(
                f'  Done: {created} store visit(s) created, {review} need review.'
            ))
            if review:
                for item in payload['needs_review']:
                    reason = item.get('reason', 'Needs review')
                    self.stdout.write(f'    - {reason}')
            success += 1

        self.stdout.write(self.style.SUCCESS(f'\nExtracted {success}/{reports.count()} report(s).'))
