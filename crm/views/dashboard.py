from datetime import date

from django.shortcuts import get_object_or_404, render

from crm.models import SalesRep, StoreVisit
from crm.services.analytics import get_rep_month_summary, get_store_history_summary
from crm.services.store_matching import find_store, find_store_candidates

MONTH_NAMES = [
    '', 'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
]


def _parse_year_month(request):
    today = date.today()
    try:
        year = int(request.GET.get('year', today.year))
    except (TypeError, ValueError):
        year = today.year
    try:
        month = int(request.GET.get('month', today.month))
    except (TypeError, ValueError):
        month = today.month
    month = max(1, min(12, month))
    return year, month


def employee_list(request):
    reps = SalesRep.objects.filter(is_active=True)
    year, month = _parse_year_month(request)
    return render(request, 'crm/dashboard/employees.html', {
        'reps': reps,
        'year': year,
        'month': month,
        'month_name': MONTH_NAMES[month],
    })


def rep_month(request, rep_id):
    rep = get_object_or_404(SalesRep, pk=rep_id)
    year, month = _parse_year_month(request)
    summary = get_rep_month_summary(rep, year, month)
    return render(request, 'crm/dashboard/rep_month.html', {
        'rep': rep,
        'summary': summary,
        'year': year,
        'month': month,
        'month_name': MONTH_NAMES[month],
        'month_choices': [(i, MONTH_NAMES[i]) for i in range(1, 13)],
    })


def followups(request):
    rep_id = request.GET.get('rep')
    visits = StoreVisit.objects.filter(
        follow_up_required=True,
        follow_up_completed=False,
    ).select_related('store', 'visit_report__sales_rep').order_by('follow_up_date', 'store__store_name')

    selected_rep = None
    if rep_id:
        selected_rep = get_object_or_404(SalesRep, pk=rep_id)
        visits = visits.filter(visit_report__sales_rep=selected_rep)

    reps = SalesRep.objects.filter(is_active=True)
    return render(request, 'crm/dashboard/followups.html', {
        'visits': visits,
        'reps': reps,
        'selected_rep': selected_rep,
    })


def store_history(request):
    store_name = request.GET.get('name', '').strip()
    owner_name = request.GET.get('owner', '').strip()
    area = request.GET.get('area', '').strip()

    store = None
    summary = None
    candidates = []

    if store_name:
        store = find_store(store_name, owner_name, area)
        if store:
            summary = get_store_history_summary(store)
        else:
            candidates = list(find_store_candidates(store_name, owner_name, area))

    return render(request, 'crm/dashboard/store_history.html', {
        'store_name': store_name,
        'owner_name': owner_name,
        'area': area,
        'store': store,
        'summary': summary,
        'candidates': candidates,
    })
