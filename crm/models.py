from django.db import models

# Create your models here.
from django.db import models


class SalesRep(models.Model):
    """
    Represents the field sales employee submitting voice notes.
    Used for employee performance and workload analysis dashboards.
    """
    name = models.CharField(max_length=150, help_text="Full name of the sales representative")
    phone = models.CharField(max_length=20, unique=True, help_text="Primary contact number")
    email = models.EmailField(max_length=254, unique=True, null=True, blank=True)
    territory = models.CharField(max_length=100, null=True, blank=True, help_text="Assigned market region or city zone")
    joining_date = models.DateField(help_text="Employment start date")
    is_active = models.BooleanField(default=True, help_text="Toggle to soft-delete inactive employees")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'crm_sales_rep'
        ordering = ['name']

    def __str__(self):
        return self.name


class Store(models.Model):
    """
    Represents a unique customer outlet. 
    Enforces structural fields to facilitate system-wide deduplication.
    """
    store_name = models.CharField(max_length=200, help_text="Store name as spoken or displayed")
    # Normalized name field used for ultra-fast indexing and fuzzy match comparisons
    store_name_normalized = models.CharField(max_length=200, db_index=True, blank=True)
    owner_name = models.CharField(max_length=150, null=True, blank=True)
    phone = models.CharField(max_length=20, null=True, blank=True)
    area = models.CharField(max_length=100, null=True, blank=True, help_text="Neighborhood or locality")
    address = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'crm_store'
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        # Automatically normalize the store name before saving to ensure easy lookup checks
        if self.store_name:
            self.store_name_normalized = "".join(self.store_name.split()).lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.store_name


class VisitReport(models.Model):
    """
    Represents a single audio asset submitted by a rep.
    Acts as the parent container for multiple individual store findings.
    """
    # Protected to ensure historical audit trails are never broken by deleting an employee account
    sales_rep = models.ForeignKey(SalesRep, on_delete=models.PROTECT, related_name='visit_reports')
    report_date = models.DateField(help_text="The actual date the field visits took place")
    audio_file = models.FileField(upload_to='voice_notes/%Y/%m/%d/', help_text="Path to stored audio binary")
    transcript = models.TextField(null=True, blank=True, help_text="Verbatim output text from Whisper transcription")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'crm_visit_report'
        ordering = ['-report_date', '-created_at']

    def __str__(self):
        return f"Report #{self.id} by {self.sales_rep.name} on {self.report_date}"


class StoreVisit(models.Model):
    """
    The core table representing a single store mentioned inside a parent voice note.
    Directly drives the analytics dashboards and individual store timelines.
    """
    class VisitStatus(models.TextChoices):
        INTERESTED = 'INTERESTED', 'Interested'
        ORDER_PLACED = 'ORDER_PLACED', 'Order Placed'
        NO_REQUIREMENT = 'NO_REQUIREMENT', 'No Requirement'
        FOLLOW_UP_NEEDED = 'FOLLOW_UP_NEEDED', 'Follow Up Needed'
        LOST_OPPORTUNITY = 'LOST_OPPORTUNITY', 'Lost Opportunity'

    visit_report = models.ForeignKey(VisitReport, on_delete=models.CASCADE, related_name='store_visits')
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='store_visits')
    visit_date = models.DateField()
    status = models.CharField(max_length=30, choices=VisitStatus.choices, help_text="Outcome classification")
    
    # Quantitative fields
    quantity_requested = models.PositiveIntegerField(default=0, help_text="Number of bags ordered or requested")
    price_per_bag = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Price per bag in PKR")
    
    # Follow-up flags
    follow_up_required = models.BooleanField(default=False)
    follow_up_date = models.DateField(null=True, blank=True)
    follow_up_completed = models.BooleanField(default=False)
    
    remarks = models.TextField(null=True, blank=True, help_text="Contextual notes or specific customer instructions")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'crm_store_visit'
        ordering = ['-visit_date', '-created_at']

    def __str__(self):
        return f"{self.store.store_name} - {self.get_status_display()} ({self.visit_date})"