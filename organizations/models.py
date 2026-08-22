import uuid
from django.db import models


class Organization(models.Model):

    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE',     'Active'
        SUSPENDED = 'SUSPENDED',  'Suspended'
        INACTIVE = 'INACTIVE',   'Inactive'

    # ── Identity ──────────────────────────────────────────
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    registration_no = models.CharField(max_length=100, blank=True)

    # ── Contact ───────────────────────────────────────────
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    website = models.URLField(blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, default='Kenya')

    # ── Branding ──────────────────────────────────────────
    logo = models.ImageField(upload_to='org/logos/', blank=True, null=True)
    favicon = models.ImageField(
        upload_to='org/favicons/', blank=True, null=True)
    footer_text = models.CharField(max_length=255, blank=True)

    # ── Theme ─────────────────────────────────────────────
    theme_primary = models.CharField(max_length=7, default='#1B3A6B')
    theme_secondary = models.CharField(max_length=7, default='#C9A84C')
    theme_accent = models.CharField(max_length=7, default='#2E86AB')
    theme_dark = models.CharField(max_length=7, default='#0D1B2A')
    theme_light = models.CharField(max_length=7, default='#F8F9FA')
    theme_success = models.CharField(max_length=7, default='#28A745')
    theme_warning = models.CharField(max_length=7, default='#FFC107')
    theme_danger = models.CharField(max_length=7, default='#DC3545')
    theme_text_primary = models.CharField(max_length=7, default='#212529')
    theme_text_secondary = models.CharField(max_length=7, default='#6C757D')
    theme_border = models.CharField(max_length=7, default='#DEE2E6')

    # ── Receipt ───────────────────────────────────────────
    class ReceiptSize(models.TextChoices):
        MM80 = 'MM80', '80mm Thermal'
        MM58 = 'MM58', '58mm Thermal'
        MOBILE = 'MOBILE', 'Mobile PDF'

    receipt_size = models.CharField(
        max_length=10,
        choices=ReceiptSize.choices,
        default=ReceiptSize.MM80
    )

    # ── System ────────────────────────────────────────────
    cutover_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE
    )

    # ── Timestamps ────────────────────────────────────────
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Organization'
        verbose_name_plural = 'Organizations'
        ordering = ['name']

    def __str__(self):
        return self.name

    def get_theme_css_variables(self):
        """Returns a dict of CSS variable names to values for dynamic theming."""
        return {
            '--brand-primary':          self.theme_primary,
            '--brand-secondary':        self.theme_secondary,
            '--brand-accent':           self.theme_accent,
            '--brand-dark':             self.theme_dark,
            '--brand-light':            self.theme_light,
            '--success':                self.theme_success,
            '--warning':                self.theme_warning,
            '--danger':                 self.theme_danger,
            '--text-primary':           self.theme_text_primary,
            '--text-secondary':         self.theme_text_secondary,
            '--border':                 self.theme_border,
        }
