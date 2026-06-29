from django.core.management.base import BaseCommand, CommandError

from crm.models import SalesRep
from crm.services.analytics import get_rep_month_summary, get_store_history_summary
from crm.services.store_matching import find_store, find_store_candidates


class Command(BaseCommand):
    help = 'Print monthly summary for a sales rep (validates analytics queries).'

    def add_arguments(self, parser):
        parser.add_argument('--rep', help='Sales rep name (e.g. Ahmed)')
        parser.add_argument('--year', type=int)
        parser.add_argument('--month', type=int)
        parser.add_argument('--store', help='Print full history for a store by name')
        parser.add_argument('--owner', default='', help='Owner name (with --store)')
        parser.add_argument('--area', default='', help='Area (with --store)')

    def handle(self, *args, **options):
        if options.get('store'):
            store = find_store(options['store'], options.get('owner', ''), options.get('area', ''))
            if not store:
                candidates = find_store_candidates(options['store'])
                if not candidates.exists():
                    raise CommandError(f"Store not found: {options['store']}")
                self.stdout.write(self.style.WARNING(
                    f"Multiple or no exact match for {options['store']!r}. "
                    'Provide --owner and --area. Candidates:'
                ))
                for candidate in candidates:
                    self.stdout.write(f'  - {candidate}')
                return

            summary = get_store_history_summary(store)
            self.stdout.write(f"\n=== Store history: {store} ===")
            self.stdout.write(f"Total visits: {summary['total_visits']}\n")
            for visit in summary['visits']:
                self.stdout.write(
                    f"  {visit.visit_date} | {visit.visit_report.sales_rep.name} | "
                    f"{visit.get_status_display()} | bags={visit.quantity_requested or '-'}"
                )
            return

        if not all([options.get('rep'), options.get('year'), options.get('month')]):
            raise CommandError('Provide --rep, --year, and --month (or use --store).')

        try:
            rep = SalesRep.objects.get(name__iexact=options['rep'])
        except SalesRep.DoesNotExist as exc:
            raise CommandError(f"Sales rep not found: {options['rep']}") from exc

        summary = get_rep_month_summary(rep, options['year'], options['month'])
        self.stdout.write(f"\n=== {summary['rep']} — {summary['year']}-{summary['month']:02d} ===")
        self.stdout.write(f"Total store visits:     {summary['total_visits']}")
        self.stdout.write(f"Successful orders:      {summary['successful_orders']}")
        self.stdout.write(f"Unsuccessful:           {summary['unsuccessful']}")
        self.stdout.write(f"Total bags sold:        {summary['total_bags_sold']}")
        self.stdout.write(f"Pending follow-ups:     {summary['pending_followups']}")
        self.stdout.write(f"Completed follow-ups:   {summary['completed_followups']}")

        self.stdout.write('\nVisits this month:')
        for visit in summary['visits']:
            self.stdout.write(
                f"  {visit.visit_date} | {visit.store.store_name} | "
                f"{visit.get_status_display()} | bags={visit.quantity_requested or '-'}"
            )

        if summary['pending_followup_list']:
            self.stdout.write('\nAll pending follow-ups (any month):')
            for visit in summary['pending_followup_list']:
                self.stdout.write(
                    f"  {visit.store.store_name} | due {visit.follow_up_date} | "
                    f"{visit.remarks or ''}"
                )
