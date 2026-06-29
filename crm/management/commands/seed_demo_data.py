from datetime import date

from django.core.management.base import BaseCommand
from django.db import transaction

from crm.models import SalesRep, Store, StoreVisit, VisitReport
from crm.services.store_matching import get_or_create_store


class Command(BaseCommand):
    help = 'Seed realistic demo data to validate the CRM schema.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Delete existing demo data and recreate it.',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options['force']:
            StoreVisit.objects.all().delete()
            VisitReport.objects.all().delete()
            Store.objects.all().delete()
            SalesRep.objects.all().delete()
            self.stdout.write('Cleared existing CRM demo data.')

        ahmed, _ = SalesRep.objects.get_or_create(
            phone='03001234567',
            defaults={
                'name': 'Ahmed',
                'email': 'ahmed@example.com',
                'territory': 'North Lahore',
                'joining_date': date(2025, 1, 15),
            },
        )
        sara, _ = SalesRep.objects.get_or_create(
            phone='03007654321',
            defaults={
                'name': 'Sara',
                'email': 'sara@example.com',
                'territory': 'South Lahore',
                'joining_date': date(2025, 3, 1),
            },
        )

        def store(name, area='', owner=''):
            obj, _ = get_or_create_store(name, owner_name=owner, area=area)
            return obj

        store_a = store('Store A', 'Gulberg', 'Owner A')
        store_b = store('Store B', 'Model Town', 'Owner B')
        store_c = store('Store C', 'Johar Town', 'Owner C')
        madina_hassan = store('Madina Store', 'Faisal Town', 'Hassan Ali')
        madina_khalid = store('Madina Store', 'Faisal Town', 'Khalid Ahmed')
        al_noor = store('Al-Noor Mart', 'DHA', 'Khalid')

        if VisitReport.objects.filter(sales_rep=ahmed, report_date=date(2026, 6, 18)).exists():
            self.stdout.write(self.style.WARNING('Demo data already exists. Use --force to recreate.'))
            return

        june18 = VisitReport.objects.create(
            sales_rep=ahmed,
            report_date=date(2026, 6, 18),
            transcript=(
                'Today I visited Store A, Store B and Store C. '
                'Store A needs 40 bags by Monday. '
                'Store B has no need right now but ask again next week. '
                'Store C needs bags tomorrow.'
            ),
        )
        StoreVisit.objects.create(
            visit_report=june18,
            store=store_a,
            visit_date=date(2026, 6, 18),
            status=StoreVisit.VisitStatus.ORDER_CONFIRMED,
            quantity_requested=40,
            rate_offered=2500,
            needed_by_date=date(2026, 6, 22),
            remarks='40 bags at discussed rate, needed by Monday.',
        )
        StoreVisit.objects.create(
            visit_report=june18,
            store=store_b,
            visit_date=date(2026, 6, 18),
            status=StoreVisit.VisitStatus.FOLLOW_UP_NEEDED,
            follow_up_required=True,
            follow_up_date=date(2026, 6, 25),
            remarks='No need right now; follow up next week.',
        )
        StoreVisit.objects.create(
            visit_report=june18,
            store=store_c,
            visit_date=date(2026, 6, 18),
            status=StoreVisit.VisitStatus.ORDER_CONFIRMED,
            quantity_requested=15,
            needed_by_date=date(2026, 6, 19),
            remarks='Needs bags tomorrow.',
        )

        march1 = VisitReport.objects.create(sales_rep=ahmed, report_date=date(2026, 3, 5))
        StoreVisit.objects.create(
            visit_report=march1,
            store=madina_hassan,
            visit_date=date(2026, 3, 5),
            status=StoreVisit.VisitStatus.ORDER_CONFIRMED,
            quantity_requested=30,
            rate_offered=2400,
        )
        StoreVisit.objects.create(
            visit_report=march1,
            store=al_noor,
            visit_date=date(2026, 3, 5),
            status=StoreVisit.VisitStatus.NOT_INTERESTED,
            remarks='Not interested this month.',
        )

        march2 = VisitReport.objects.create(sales_rep=ahmed, report_date=date(2026, 3, 12))
        StoreVisit.objects.create(
            visit_report=march2,
            store=store_a,
            visit_date=date(2026, 3, 12),
            status=StoreVisit.VisitStatus.FOLLOW_UP_NEEDED,
            follow_up_required=True,
            follow_up_date=date(2026, 3, 20),
            follow_up_completed=True,
            remarks='Follow-up completed on revisit.',
        )
        StoreVisit.objects.create(
            visit_report=march2,
            store=madina_hassan,
            visit_date=date(2026, 3, 12),
            status=StoreVisit.VisitStatus.ORDER_CONFIRMED,
            quantity_requested=20,
        )
        StoreVisit.objects.create(
            visit_report=march2,
            store=madina_khalid,
            visit_date=date(2026, 3, 12),
            status=StoreVisit.VisitStatus.FOLLOW_UP_NEEDED,
            follow_up_required=True,
            follow_up_date=date(2026, 3, 22),
            remarks='Different Madina Store — Khalid wala, same area.',
        )

        sara_march = VisitReport.objects.create(sales_rep=sara, report_date=date(2026, 3, 8))
        StoreVisit.objects.create(
            visit_report=sara_march,
            store=store_b,
            visit_date=date(2026, 3, 8),
            status=StoreVisit.VisitStatus.NO_REQUIREMENT,
        )
        StoreVisit.objects.create(
            visit_report=sara_march,
            store=store_c,
            visit_date=date(2026, 3, 8),
            status=StoreVisit.VisitStatus.ORDER_CONFIRMED,
            quantity_requested=10,
        )

        madina_count = Store.objects.filter(name_normalized=Store.normalize_text('Madina Store')).count()
        self.stdout.write(self.style.SUCCESS('Demo data seeded successfully.'))
        self.stdout.write(f'  Sales reps: {SalesRep.objects.count()}')
        self.stdout.write(f'  Stores: {Store.objects.count()} (Madina Store rows: {madina_count})')
        self.stdout.write(f'  Visit reports: {VisitReport.objects.count()}')
        self.stdout.write(f'  Store visits: {StoreVisit.objects.count()}')
