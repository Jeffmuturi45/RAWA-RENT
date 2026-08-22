import uuid
from django.db import models
from django.utils.text import slugify


class Property(models.Model):

    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE',     'Active'
        INACTIVE = 'INACTIVE',   'Inactive'
        ARCHIVED = 'ARCHIVED',   'Archived'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'organizations.Organization',
        on_delete=models.PROTECT,
        related_name='properties'
    )
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, blank=True)
    code = models.CharField(max_length=20, unique=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, default='Nyeri')
    county = models.CharField(max_length=100, default='Nyeri')
    country = models.CharField(max_length=100, default='Kenya')
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='properties/', blank=True, null=True)
    total_units = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Property'
        verbose_name_plural = 'Properties'
        ordering = ['name']
        unique_together = [['organization', 'name']]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def get_code_prefix(self):
        return self.code.upper()

    def get_occupied_units(self):
        return self.units.filter(status='OCCUPIED').count()

    def get_vacant_units(self):
        return self.units.filter(status='VACANT').count()

    def get_maintenance_units(self):
        return self.units.filter(status='MAINTENANCE').count()

    def get_occupancy_rate(self):
        total = self.units.count()
        if total == 0:
            return 0
        return round((self.get_occupied_units() / total) * 100, 1)


class HouseType(models.Model):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    prop = models.ForeignKey(
        Property,
        on_delete=models.PROTECT,
        related_name='house_types'
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    default_rent = models.DecimalField(
        max_digits=10, decimal_places=2, default=0)
    default_deposit = models.DecimalField(
        max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'House Type'
        verbose_name_plural = 'House Types'
        ordering = ['name']
        unique_together = [['prop', 'name']]

    def __str__(self):
        return f'{self.prop.name} — {self.name}'


class Unit(models.Model):

    class Status(models.TextChoices):
        VACANT = 'VACANT',      'Vacant'
        OCCUPIED = 'OCCUPIED',    'Occupied'
        RESERVED = 'RESERVED',    'Reserved'
        MAINTENANCE = 'MAINTENANCE', 'Under Maintenance'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    prop = models.ForeignKey(
        Property,
        on_delete=models.PROTECT,
        related_name='units'
    )
    house_type = models.ForeignKey(
        HouseType,
        on_delete=models.PROTECT,
        related_name='units',
        null=True,
        blank=True
    )
    unit_number = models.CharField(max_length=20)
    floor = models.CharField(max_length=20, blank=True)
    description = models.TextField(blank=True)
    rent_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=0)
    deposit_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=0)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.VACANT
    )
    is_archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Unit'
        verbose_name_plural = 'Units'
        ordering = ['prop', 'unit_number']
        unique_together = [['prop', 'unit_number']]

    def __str__(self):
        return f'{self.prop.name} — {self.unit_number}'

    def get_active_tenancy(self):
        return self.tenancies.filter(status='ACTIVE').first()

    def get_current_tenant(self):
        tenancy = self.get_active_tenancy()
        return tenancy.tenant if tenancy else None

    def get_status_badge(self):
        badge_map = {
            self.Status.VACANT:      'rw-badge-warning',
            self.Status.OCCUPIED:    'rw-badge-success',
            self.Status.RESERVED:    'rw-badge-info',
            self.Status.MAINTENANCE: 'rw-badge-danger',
        }
        return badge_map.get(self.status, 'rw-badge-dark')
