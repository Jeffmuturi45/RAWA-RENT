import uuid
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models


class UserManager(BaseUserManager):

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email address is required')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('role', User.Role.AGENCY_OWNER)

        if not extra_fields.get('is_staff'):
            raise ValueError('Superuser must have is_staff=True')
        if not extra_fields.get('is_superuser'):
            raise ValueError('Superuser must have is_superuser=True')

        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):

    class Role(models.TextChoices):
        AGENCY_OWNER = 'AGENCY_OWNER',   'Agency Owner'
        MANAGER = 'MANAGER',        'Manager'
        ACCOUNTS_OFFICER = 'ACCOUNTS_OFFICER', 'Accounts Officer'
        RECEPTIONIST = 'RECEPTIONIST',   'Receptionist'
        TENANT = 'TENANT',         'Tenant'

    # ── Identity ──────────────────────────────────────────
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20, blank=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)

    # ── Role ──────────────────────────────────────────────
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.RECEPTIONIST
    )

    # ── Organization link ─────────────────────────────────
    organization = models.ForeignKey(
        'organizations.Organization',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='users'
    )

    # ── Security ──────────────────────────────────────────
    financial_pin = models.CharField(max_length=128, blank=True)
    must_change_password = models.BooleanField(default=False)
    last_password_change = models.DateTimeField(null=True, blank=True)
    failed_login_attempts = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    # ── Status ────────────────────────────────────────────
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    # ── Timestamps ────────────────────────────────────────
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['full_name']

    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        ordering = ['full_name']

    def __str__(self):
        return f'{self.full_name} ({self.email})'

    @property
    def is_owner(self):
        return self.role == self.Role.AGENCY_OWNER

    @property
    def is_manager(self):
        return self.role == self.Role.MANAGER

    @property
    def is_accounts_officer(self):
        return self.role == self.Role.ACCOUNTS_OFFICER

    @property
    def is_receptionist(self):
        return self.role == self.Role.RECEPTIONIST

    @property
    def is_tenant_user(self):
        return self.role == self.Role.TENANT

    def has_financial_pin(self):
        return bool(self.financial_pin)

    def has_cap(self, cap):
        """RBAC capability check — delegates to accounts.permissions."""
        from .permissions import has_capability
        return has_capability(self, cap)

    def get_role_display_badge(self):
        badge_classes = {
            self.Role.AGENCY_OWNER:     'badge-owner',
            self.Role.MANAGER:          'badge-manager',
            self.Role.ACCOUNTS_OFFICER: 'badge-accounts',
            self.Role.RECEPTIONIST:     'badge-receptionist',
            self.Role.TENANT:           'badge-tenant',
        }
        return badge_classes.get(self.role, 'badge-secondary')
