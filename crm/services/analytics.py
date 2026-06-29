from django.db.models import Sum

from crm.models import StoreVisit


def _visits_for_rep_month(rep, year, month):
    return StoreVisit.objects.filter(
        visit_report__sales_rep=rep,
        visit_date__year=year,
        visit_date__month=month,
    )


def stores_visited_count(rep, year, month):
    return _visits_for_rep_month(rep, year, month).count()


def orders_count(rep, year, month):
    return _visits_for_rep_month(rep, year, month).filter(
        status=StoreVisit.VisitStatus.ORDER_CONFIRMED,
    ).count()


def unsuccessful_count(rep, year, month):
    return _visits_for_rep_month(rep, year, month).filter(
        status__in=[
            StoreVisit.VisitStatus.NOT_INTERESTED,
            StoreVisit.VisitStatus.NO_REQUIREMENT,
        ],
    ).count()


def bags_sold(rep, year, month):
    result = _visits_for_rep_month(rep, year, month).filter(
        status=StoreVisit.VisitStatus.ORDER_CONFIRMED,
    ).aggregate(total=Sum('quantity_requested'))
    return result['total'] or 0


def pending_followups(rep):
    return StoreVisit.objects.filter(
        visit_report__sales_rep=rep,
        follow_up_required=True,
        follow_up_completed=False,
    )


def completed_followups_count(rep, year, month):
    return _visits_for_rep_month(rep, year, month).filter(
        follow_up_required=True,
        follow_up_completed=True,
    ).count()


def store_visit_history(store):
    return StoreVisit.objects.filter(store=store).select_related(
        'visit_report__sales_rep',
        'store',
    )


def get_rep_month_summary(rep, year, month):
    month_visits = _visits_for_rep_month(rep, year, month)
    pending = pending_followups(rep)

    return {
        'rep': rep.name,
        'year': year,
        'month': month,
        'total_visits': month_visits.count(),
        'successful_orders': orders_count(rep, year, month),
        'unsuccessful': unsuccessful_count(rep, year, month),
        'total_bags_sold': bags_sold(rep, year, month),
        'pending_followups': pending.count(),
        'completed_followups': completed_followups_count(rep, year, month),
        'visits': list(month_visits.select_related('store').order_by('visit_date')),
        'pending_followup_list': list(
            pending.select_related('store').order_by('follow_up_date')
        ),
    }


def get_store_history_summary(store):
    visits = store_visit_history(store)
    return {
        'store': store.store_name,
        'total_visits': visits.count(),
        'visits': list(visits.order_by('-visit_date')),
    }
