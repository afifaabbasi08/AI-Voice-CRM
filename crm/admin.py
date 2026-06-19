from django.contrib import admin

# Register your models here.
from .models import Employee, Store, VoiceNote, Lead, LeadActivity, FollowUp, Delivery


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'whatsapp_id', 'area', 'joining_date', 'is_active')
    list_filter = ('is_active', 'area')
    search_fields = ('name', 'phone', 'whatsapp_id')


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner_name', 'owner_phone', 'area', 'is_active')
    list_filter = ('is_active', 'area')
    search_fields = ('name', 'owner_name', 'owner_phone', 'area')


class LeadActivityInline(admin.TabularInline):
    model = LeadActivity
    extra = 0
    readonly_fields = ('from_status', 'to_status', 'actor_type', 'actor_id', 'notes', 'voice_note', 'created_at')
    can_delete = False


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ('id', 'store', 'employee', 'bags_requested', 'rice_variety', 'status', 'created_at')
    list_filter = ('status', 'rice_variety', 'created_at')
    search_fields = ('store__name', 'employee__name', 'notes')
    inlines = [LeadActivityInline]


@admin.register(VoiceNote)
class VoiceNoteAdmin(admin.ModelAdmin):
    list_display = ('id', 'employee', 'file_format', 'processing_status', 'received_at')
    list_filter = ('processing_status', 'file_format', 'received_at')
    search_fields = ('transcript', 'employee__name')


@admin.register(FollowUp)
class FollowUpAdmin(admin.ModelAdmin):
    list_display = ('lead', 'assigned_to', 'due_date', 'is_completed', 'completed_at')
    list_filter = ('is_completed', 'due_date')
    search_fields = ('lead__store__name', 'notes')


@admin.register(Delivery)
class DeliveryAdmin(admin.ModelAdmin):
    list_display = ('lead', 'scheduled_date', 'actual_date', 'bags_delivered', 'status')
    list_filter = ('status', 'scheduled_date')
    search_fields = ('lead__store__name', 'failure_reason')