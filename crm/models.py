from django.db import models


class Employee(models.Model):
    """
    crm_employee: Represents field sales representatives.
    Includes WhatsApp ID mappings for Phase 2 automation.
    """
    name = models.CharField(max_length=150, help_text="Full name of field representative")
    phone = models.CharField(max_length=20, unique=True, help_text="Primary phone number")
    whatsapp_id = models.CharField(max_length=50, unique=True, null=True, blank=True, help_text="WhatsApp sender ID for Phase 2 attribution")
    area = models.CharField(max_length=100, null=True, blank=True, help_text="Assigned territory or city zone")
    joining_date = models.DateField(help_text="Date of employment start")
    is_active = models.BooleanField(default=True, help_text="Soft delete flag; inactive employees excluded from assignments")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'crm_employee'
        ordering = ['name']

    def __str__(self):
        return self.name


class Store(models.Model):
    """
    crm_store: Represents physical client outlets.
    Enforces normalized fields to facilitate Levenshtein deduplication suggestions.
    """
    name = models.CharField(max_length=200, help_text="Store display name as spoken")
    name_normalized = models.CharField(max_length=200, db_index=True, blank=True, help_text="Lowercased, stripped for dedup comparison")
    area = models.CharField(max_length=100, null=True, blank=True, help_text="Neighborhood or zone")
    address = models.TextField(null=True, blank=True, help_text="Full street address")
    
    # Coordinates for mapping enhancements
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True, help_text="GPS latitude for map view")
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True, help_text="GPS longitude for map view")
    
    owner_name = models.CharField(max_length=150, null=True, blank=True, help_text="Shop owner or buyer contact name")
    owner_phone = models.CharField(max_length=20, null=True, blank=True, help_text="Contact phone number")
    is_active = models.BooleanField(default=True, help_text="Soft delete flag")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'crm_store'
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if self.name:
            self.name_normalized = "".join(self.name.split()).lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class VoiceNote(models.Model):
    """
    crm_voicenote: Tracks incoming audio media pipelines and processing statuses.
    """
    class ProcessingStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        TRANSCRIBING = 'TRANSCRIBING', 'Transcribing'
        EXTRACTING = 'EXTRACTING', 'Extracting'
        AWAITING_REVIEW = 'AWAITING_REVIEW', 'Awaiting Review'
        DONE = 'DONE', 'Done'
        FAILED = 'FAILED', 'Failed'

    employee = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name='voice_notes')
    audio_file = models.FileField(upload_to='voice_notes/%Y/%m/%d/', max_length=500, help_text="Relative path under MEDIA_ROOT")
    file_format = models.CharField(max_length=10, help_text="mp3 / ogg / m4a / wav / webm")
    duration_seconds = models.IntegerField(null=True, blank=True, help_text="Audio duration in seconds")
    transcript = models.TextField(null=True, blank=True, help_text="Raw Whisper output (verbatim)")
    transcript_confidence = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True, help_text="Whisper confidence score 0.0-1.0")
    extracted_json = models.JSONField(null=True, blank=True, help_text="Raw GPT extraction output stored for debugging")
    processing_status = models.CharField(max_length=30, choices=ProcessingStatus.choices, default=ProcessingStatus.PENDING)
    whatsapp_message_id = models.CharField(max_length=100, unique=True, null=True, blank=True, help_text="Meta message ID for Phase 2 dedup")
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'crm_voicenote'
        ordering = ['-received_at']

    def __str__(self):
        return f"VoiceNote #{self.id} ({self.get_processing_status_display()})"


class Lead(models.Model):
    """
    crm_lead: Represents a single sales opportunity at a specific Store.
    Status transitions are tracked via an explicit cached field.
    """
    class LeadStatus(models.TextChoices):
        NEW_LEAD = 'NEW_LEAD', 'New Lead'
        FOLLOW_UP_REQUIRED = 'FOLLOW_UP_REQUIRED', 'Follow-Up Required'
        ORDER_CONFIRMED = 'ORDER_CONFIRMED', 'Order Confirmed'
        DELIVERY_SCHEDULED = 'DELIVERY_SCHEDULED', 'Delivery Scheduled'
        DELIVERED = 'DELIVERED', 'Delivered'
        REJECTED = 'REJECTED', 'Rejected'

    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='leads')
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name='leads')
    voice_note = models.ForeignKey(VoiceNote, on_delete=models.SET_NULL, null=True, blank=True, related_name='leads')
    bags_requested = models.PositiveIntegerField(null=True, blank=True, help_text="Number of rice bags requested")
    price_offered = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Price per bag quoted by rep (PKR)")
    rice_variety = models.CharField(max_length=100, null=True, blank=True, help_text="e.g. Basmati, Sella, IRRI")
    status = models.CharField(max_length=40, choices=LeadStatus.choices, default=LeadStatus.NEW_LEAD, help_text="Cached current status")
    notes = models.TextField(null=True, blank=True, help_text="Free-form text context details")
    visit_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'crm_lead'
        ordering = ['-created_at']

    def __str__(self):
        return f"Lead #{self.id} - {self.store.name} ({self.get_status_display()})"


class LeadActivity(models.Model):
    """
    crm_leadactivity: Implements the strict append-only transactional state audit log.
    NO UPDATES OR DELETES ALLOWED.
    """
    class ActorType(models.TextChoices):
        EMPLOYEE = 'employee', 'Employee'
        ADMIN = 'admin', 'Admin'
        SYSTEM = 'system', 'System'

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='activities')
    from_status = models.CharField(max_length=40)
    to_status = models.CharField(max_length=40)
    actor_type = models.CharField(max_length=20, choices=ActorType.choices)
    actor_id = models.IntegerField(null=True, blank=True, help_text="ID of Employee or User who triggered transition")
    notes = models.TextField(null=True, blank=True)
    voice_note = models.ForeignKey(VoiceNote, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'crm_leadactivity'
        ordering = ['created_at']

    def __str__(self):
        return f"Activity #{self.id}: Lead #{self.lead_id} changed to {self.to_status}"


class FollowUp(models.Model):
    """
    crm_followup: Automates tracking actionable next steps derived from text insights.
    """
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='followups')
    assigned_to = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name='assigned_followups')
    due_date = models.DateField(help_text="Target date for follow-up action")
    notes = models.TextField(null=True, blank=True)
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'crm_followup'
        ordering = ['due_date']

    def __str__(self):
        return f"FollowUp for Lead #{self.lead_id} due on {self.due_date}"


class Delivery(models.Model):
    """
    crm_delivery: Tracks fulfillment lifecycle logs. Links 1-to-1 with confirmed transactions.
    """
    class DeliveryStatus(models.TextChoices):
        SCHEDULED = 'SCHEDULED', 'Scheduled'
        IN_TRANSIT = 'IN_TRANSIT', 'In Transit'
        DELIVERED = 'DELIVERED', 'Delivered'
        FAILED = 'FAILED', 'Failed'

    lead = models.OneToOneField(Lead, on_delete=models.CASCADE, related_name='delivery')
    scheduled_date = models.DateField(null=True, blank=True)
    actual_date = models.DateField(null=True, blank=True)
    bags_delivered = models.PositiveIntegerField(null=True, blank=True)
    delivered_by = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name='handled_deliveries')
    status = models.CharField(max_length=20, choices=DeliveryStatus.choices, default=DeliveryStatus.SCHEDULED)
    failure_reason = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'crm_delivery'
        ordering = ['-scheduled_date']

    def __str__(self):
        return f"Delivery for Lead #{self.lead_id} ({self.get_status_display()})"