from django.urls import path

from crm.views import dashboard

app_name = 'crm'

urlpatterns = [
    path('', dashboard.employee_list, name='dashboard_home'),
    path('rep/<int:rep_id>/', dashboard.rep_month, name='rep_month'),
    path('followups/', dashboard.followups, name='followups'),
    path('store/', dashboard.store_history, name='store_history'),
]
