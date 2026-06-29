from django.db import models


class SalesRep(models.Model):
    """Field sales employee who submits voice visit reports."""

    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20, unique=True)
    email = models.EmailField(blank=True, null=True)
    territory = models.CharField(max_length=100, blank=True, null=True)
    joining_date = models.DateField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Store(models.Model):
    """Unique store/customer outlet. One row per real-world store."""

    store_name = models.CharField(max_length=200, default='')
    name_normalized = models.CharField(
        max_length=200,
        blank=True,
        db_index=True,
        help_text='Lowercased, stripped name used for duplicate detection.',
    )
    owner_name = models.CharField(
        max_length=150,
        blank=True,
        default='',
        help_text='Shop owner name — required for disambiguating same-named stores.',
    )
    owner_normalized = models.CharField(
        max_length=150,
        blank=True,
        db_index=True,
        help_text='Lowercased, stripped owner name used for duplicate detection.',
    )
    phone = models.CharField(max_length=20, blank=True, null=True)
    area = models.CharField(max_length=100, blank=True, default='')
    address = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['store_name']
        constraints = [
            models.UniqueConstraint(
                fields=['name_normalized', 'owner_normalized', 'area'],
                name='unique_store_identity',
            ),
        ]

    @staticmethod
    def normalize_text(value):
        if not value:
            return ''
        return ''.join(str(value).split()).lower()

    def save(self, *args, **kwargs):
        self.name_normalized = self.normalize_text(self.store_name)
        self.owner_normalized = self.normalize_text(self.owner_name)
        super().save(*args, **kwargs)

    def __str__(self):
        parts = [self.store_name]
        if self.owner_name:
            parts.append(f'({self.owner_name})')
        if self.area:
            parts.append(f'- {self.area}')
        return ' '.join(parts)


class VisitReport(models.Model):
    """One voice note submitted by a sales rep. May mention multiple stores."""

    class ProcessingStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        TRANSCRIBED = 'TRANSCRIBED', 'Transcribed'
        EXTRACTED = 'EXTRACTED', 'Extracted'
        REVIEWED = 'REVIEWED', 'Reviewed'
        FAILED = 'FAILED', 'Failed'

    sales_rep = models.ForeignKey(
        SalesRep,
        on_delete=models.PROTECT,
        related_name='visit_reports',
    )
    report_date = models.DateField(help_text='Date the rep recorded or submitted this report.')
    audio_file = models.FileField(
        upload_to='visit_reports/%Y/%m/%d/',
        blank=True,
        null=True,
        help_text='Voice note audio (mp3, m4a, ogg, wav).',
    )
    transcript = models.TextField(blank=True, null=True)
    processing_status = models.CharField(
        max_length=20,
        choices=ProcessingStatus.choices,
        default=ProcessingStatus.PENDING,
    )
    extraction_payload = models.JSONField(
        blank=True,
        null=True,
        help_text='AI extraction output, auto-created visit IDs, and items needing review.',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-report_date', '-created_at']

    @property
    def has_audio(self):
        return bool(self.audio_file)

    def __str__(self):
        return f'Report #{self.id} by {self.sales_rep.name} on {self.report_date}'


class StoreVisit(models.Model):
    """One store mentioned inside a visit report. Core fact table for analytics."""

    class VisitStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        ORDER_CONFIRMED = 'ORDER_CONFIRMED', 'Order Confirmed'
        FOLLOW_UP_NEEDED = 'FOLLOW_UP_NEEDED', 'Follow-Up Needed'
        NO_REQUIREMENT = 'NO_REQUIREMENT', 'No Requirement'
        NOT_INTERESTED = 'NOT_INTERESTED', 'Not Interested'

    visit_report = models.ForeignKey(
        VisitReport,
        on_delete=models.CASCADE,
        related_name='store_visits',
    )
    store = models.ForeignKey(
        Store,
        on_delete=models.PROTECT,
        related_name='visits',
    )
    visit_date = models.DateField(help_text='Date this specific store visit occurred.')
    status = models.CharField(
        max_length=30,
        choices=VisitStatus.choices,
        default=VisitStatus.PENDING,
    )
    quantity_requested = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text='Number of bags requested or ordered.',
    )
    rate_offered = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        help_text='Price per bag discussed during the visit.',
    )
    needed_by_date = models.DateField(
        blank=True,
        null=True,
        help_text='When the store needs the bags, if mentioned.',
    )
    follow_up_required = models.BooleanField(default=False)
    follow_up_date = models.DateField(blank=True, null=True)
    follow_up_completed = models.BooleanField(default=False)
    follow_up_completed_at = models.DateTimeField(blank=True, null=True)
    remarks = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-visit_date', '-created_at']
        indexes = [
            models.Index(fields=['visit_date']),
            models.Index(fields=['status']),
            models.Index(fields=['follow_up_required', 'follow_up_completed']),
            models.Index(fields=['visit_report', 'visit_date']),
        ]

    def __str__(self):
        return f'{self.store.store_name} on {self.visit_date} ({self.get_status_display()})'
