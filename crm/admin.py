from django.contrib import admin, messages
from django.utils.html import format_html
import json

from crm.services.extraction import ExtractionError, extract_visit_report
from crm.services.transcription import TranscriptionError, transcribe_visit_report

from .models import SalesRep, Store, StoreVisit, VisitReport


@admin.register(SalesRep)
class SalesRepAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'email', 'territory', 'joining_date', 'is_active')
    list_filter = ('is_active', 'territory')
    search_fields = ('name', 'phone', 'email')


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ('store_name', 'owner_name', 'area', 'phone', 'created_at')
    list_filter = ('area',)
    search_fields = (
        'store_name', 'name_normalized', 'owner_name', 'owner_normalized', 'phone', 'area',
    )
    readonly_fields = ('name_normalized', 'owner_normalized', 'created_at')


class StoreVisitInline(admin.TabularInline):
    model = StoreVisit
    extra = 1
    fields = (
        'store',
        'visit_date',
        'status',
        'quantity_requested',
        'rate_offered',
        'needed_by_date',
        'follow_up_required',
        'follow_up_date',
        'follow_up_completed',
        'follow_up_completed_at',
        'remarks',
    )


@admin.register(VisitReport)
class VisitReportAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'sales_rep', 'report_date', 'has_audio_display', 'processing_status', 'created_at',
    )
    list_filter = ('report_date', 'sales_rep', 'processing_status')
    search_fields = ('sales_rep__name', 'transcript')
    date_hierarchy = 'report_date'
    inlines = [StoreVisitInline]
    readonly_fields = ('audio_preview', 'extraction_payload_display', 'created_at')
    actions = [
        'transcribe_selected_reports',
        'extract_selected_reports',
        'mark_selected_as_reviewed',
    ]
    fieldsets = (
        (None, {
            'fields': (
                'sales_rep',
                'report_date',
                'audio_file',
                'audio_preview',
                'processing_status',
                'transcript',
                'extraction_payload_display',
                'created_at',
            ),
        }),
    )

    @admin.display(boolean=True, description='Audio')
    def has_audio_display(self, obj):
        return obj.has_audio

    @admin.display(description='Preview')
    def audio_preview(self, obj):
        if not obj.audio_file:
            return '—'
        return format_html(
            '<audio controls src="{}"></audio><br><a href="{}" target="_blank">Download</a>',
            obj.audio_file.url,
            obj.audio_file.url,
        )

    @admin.display(description='Extraction payload')
    def extraction_payload_display(self, obj):
        if not obj.extraction_payload:
            return '—'
        text = json.dumps(obj.extraction_payload, indent=2, ensure_ascii=False)
        return format_html('<pre style="white-space:pre-wrap">{}</pre>', text)

    @admin.action(description='Transcribe selected reports (Whisper)')
    def transcribe_selected_reports(self, request, queryset):
        done = 0
        for report in queryset:
            if not report.has_audio:
                self.message_user(
                    request,
                    f'Report #{report.pk} has no audio — skipped.',
                    level=messages.WARNING,
                )
                continue
            try:
                transcribe_visit_report(report)
            except TranscriptionError as exc:
                self.message_user(
                    request,
                    f'Report #{report.pk} failed: {exc}',
                    level=messages.ERROR,
                )
                continue
            done += 1

        if done:
            self.message_user(request, f'Transcribed {done} report(s).', level=messages.SUCCESS)

    @admin.action(description='Extract selected reports (AI)')
    def extract_selected_reports(self, request, queryset):
        done = 0
        for report in queryset:
            if not report.transcript:
                self.message_user(
                    request,
                    f'Report #{report.pk} has no transcript — transcribe first.',
                    level=messages.WARNING,
                )
                continue
            try:
                payload = extract_visit_report(report)
            except ExtractionError as exc:
                self.message_user(
                    request,
                    f'Report #{report.pk} failed: {exc}',
                    level=messages.ERROR,
                )
                continue
            created = len(payload.get('created_visit_ids', []))
            review = len(payload.get('needs_review', []))
            self.message_user(
                request,
                f'Report #{report.pk}: {created} visit(s) created, {review} need review.',
                level=messages.SUCCESS if not review else messages.WARNING,
            )
            done += 1

    @admin.action(description='Mark selected reports as reviewed')
    def mark_selected_as_reviewed(self, request, queryset):
        updated = queryset.update(processing_status=VisitReport.ProcessingStatus.REVIEWED)
        if updated:
            self.message_user(request, f'Marked {updated} report(s) as reviewed.', level=messages.SUCCESS)


@admin.register(StoreVisit)
class StoreVisitAdmin(admin.ModelAdmin):
    list_display = (
        'store',
        'visit_report',
        'visit_date',
        'status',
        'quantity_requested',
        'follow_up_required',
        'follow_up_completed',
    )
    list_filter = ('status', 'follow_up_required', 'follow_up_completed', 'visit_date')
    search_fields = ('store__store_name', 'visit_report__sales_rep__name', 'remarks')
    date_hierarchy = 'visit_date'
    autocomplete_fields = ('store', 'visit_report')
