from django.core.management.base import BaseCommand, CommandError

from crm.models import VisitReport
from crm.services.transcription import TranscriptionError, transcribe_visit_report


class Command(BaseCommand):
    help = 'Transcribe voice audio on one or more visit reports using Whisper.'

    def add_arguments(self, parser):
        parser.add_argument('report_ids', nargs='*', type=int, help='VisitReport ID(s) to transcribe')
        parser.add_argument(
            '--all-pending',
            action='store_true',
            help='Transcribe all reports with audio that are not yet transcribed.',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Re-transcribe even if a transcript already exists.',
        )

    def handle(self, *args, **options):
        reports = VisitReport.objects.none()

        if options['all_pending']:
            reports = VisitReport.objects.exclude(audio_file='').filter(
                processing_status=VisitReport.ProcessingStatus.PENDING,
            )
        elif options['report_ids']:
            reports = VisitReport.objects.filter(pk__in=options['report_ids'])
        else:
            raise CommandError('Provide report ID(s) or use --all-pending.')

        if not reports.exists():
            raise CommandError('No matching visit reports found.')

        success = 0
        for report in reports:
            self.stdout.write(f'Transcribing report #{report.pk} ({report.sales_rep.name})...')
            try:
                transcript = transcribe_visit_report(report, force=options['force'])
            except TranscriptionError as exc:
                self.stdout.write(self.style.ERROR(f'  Failed: {exc}'))
                continue

            success += 1
            preview = transcript[:200] + ('...' if len(transcript) > 200 else '')
            self.stdout.write(self.style.SUCCESS(f'  Done ({len(transcript)} chars)'))
            try:
                self.stdout.write(f'  Preview: {preview}')
            except UnicodeEncodeError:
                self.stdout.write('  Preview: (non-ASCII text - see Admin)')

        self.stdout.write(self.style.SUCCESS(f'\nTranscribed {success}/{reports.count()} report(s).'))
