from django import forms
from django.utils import timezone
from tenants.models import Tenant
from properties.models import Unit
from .models import Tenancy, Transfer, MoveOut


class TenancyForm(forms.ModelForm):

    class Meta:
        model = Tenancy
        fields = [
            'tenant', 'unit', 'start_date',
            'monthly_rent', 'required_deposit', 'billing_day',
        ]
        widgets = {
            'tenant':           forms.Select(attrs={'class': 'rw-select'}),
            'unit':             forms.Select(attrs={'class': 'rw-select'}),
            'start_date':       forms.DateInput(attrs={'class': 'rw-input', 'type': 'date'}),
            'monthly_rent':     forms.NumberInput(attrs={'class': 'rw-input', 'placeholder': '0.00'}),
            'required_deposit': forms.NumberInput(attrs={'class': 'rw-input', 'placeholder': '0.00'}),
            'billing_day':      forms.Select(attrs={'class': 'rw-select'}),
        }

    def __init__(self, *args, org=None, **kwargs):
        super().__init__(*args, **kwargs)
        if org:
            self.fields['tenant'].queryset = Tenant.objects.filter(
                organization=org,
                status=Tenant.Status.ACTIVE,
            ).order_by('full_name')
            self.fields['unit'].queryset = Unit.objects.filter(
                prop__organization=org,
                is_archived=False,
                status__in=[Unit.Status.VACANT, Unit.Status.RESERVED],
            ).select_related('prop').order_by('prop__name', 'unit_number')

    def clean(self):
        cleaned = super().clean()
        tenant = cleaned.get('tenant')
        unit = cleaned.get('unit')

        # ── Guard 1: tenant must not already have an active tenancy ──
        if tenant:
            existing = Tenancy.objects.filter(
                tenant=tenant,
                status=Tenancy.Status.ACTIVE
            ).first()
            if existing:
                raise forms.ValidationError(
                    f'{tenant.full_name} already has an active tenancy in '
                    f'Unit {existing.unit.unit_number}, {existing.unit.prop.name}. '
                    f'Use the Transfer workflow to move them to a new unit.'
                )

        # ── Guard 2: unit must not already have an active tenancy ──
        if unit:
            existing = Tenancy.objects.filter(
                unit=unit,
                status=Tenancy.Status.ACTIVE
            ).first()
            if existing:
                raise forms.ValidationError(
                    f'Unit {unit.unit_number} is already occupied by '
                    f'{existing.tenant.full_name}. '
                    f'End or transfer the existing tenancy first.'
                )

        return cleaned


class TransferInitiateForm(forms.Form):
    """
    Step 1 — staff selects the new unit and transfer date.
    The system then calculates the financial summary before confirmation.
    """
    new_unit = forms.ModelChoiceField(
        queryset=Unit.objects.none(),
        widget=forms.Select(attrs={'class': 'rw-select'}),
        label='New Unit',
        help_text='Only vacant or reserved units are shown.',
    )
    transfer_date = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'rw-input', 'type': 'date'}),
        initial=timezone.now().date,
        label='Transfer Date',
    )
    new_monthly_rent = forms.DecimalField(
        max_digits=12, decimal_places=2,
        widget=forms.NumberInput(
            attrs={'class': 'rw-input', 'placeholder': '0.00'}),
        label='New Monthly Rent (KSh)',
        help_text='Pre-filled from unit — change if negotiated differently.',
    )
    new_required_deposit = forms.DecimalField(
        max_digits=12, decimal_places=2,
        widget=forms.NumberInput(
            attrs={'class': 'rw-input', 'placeholder': '0.00'}),
        label='New Required Deposit (KSh)',
    )
    reason = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'rw-textarea', 'rows': 2}),
        label='Reason for Transfer',
    )

    def __init__(self, *args, org=None, current_unit=None, **kwargs):
        super().__init__(*args, **kwargs)
        if org:
            qs = Unit.objects.filter(
                prop__organization=org,
                is_archived=False,
                status__in=[Unit.Status.VACANT, Unit.Status.RESERVED],
            ).select_related('prop').order_by('prop__name', 'unit_number')
            if current_unit:
                qs = qs.exclude(pk=current_unit.pk)
            self.fields['new_unit'].queryset = qs


class TransferConfirmForm(forms.Form):
    """
    Step 2 — manager reviews the summary and selects deposit disposition.
    """
    DISPOSITION_CHOICES = [
        ('TOPUP',       'Tenant will pay the deposit top-up'),
        ('REFUND',      'Refund surplus to tenant (cash/M-Pesa)'),
        ('RENT_CREDIT', 'Credit surplus against next rent charge'),
        ('HOLD',        'Hold surplus in deposit account'),
        ('EXACT',       'No deposit difference'),
    ]

    deposit_disposition = forms.ChoiceField(
        choices=DISPOSITION_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'rw-radio'}),
        label='Deposit Surplus/Shortfall Handling',
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'rw-textarea', 'rows': 2}),
        label='Additional Notes',
    )
    confirm = forms.BooleanField(
        label='I confirm this transfer is correct and authorised.',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )


class MoveOutForm(forms.Form):
    """
    Move-out form — captures inspection checklist and settlement details.
    """
    CONDITION_CHOICES = [
        ('GOOD', 'Good'),
        ('FAIR', 'Fair'),
        ('POOR', 'Poor'),
    ]

    SETTLEMENT_CHOICES = [
        ('FULL_REFUND',    'Full Refund'),
        ('PARTIAL_REFUND', 'Partial Refund'),
        ('NO_REFUND',      'No Refund (damages/arrears cover deposit)'),
        ('PENDING',        'Pending Review'),
    ]

    notice_date = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'rw-input', 'type': 'date'}),
        label='Notice Date',
    )
    moveout_date = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'rw-input', 'type': 'date'}),
        initial=timezone.now().date,
        label='Move-Out Date',
    )
    keys_returned = forms.BooleanField(
        required=False,
        label='Keys returned',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )

    # Inspection
    walls_condition = forms.ChoiceField(choices=CONDITION_CHOICES,
                                        widget=forms.Select(
                                            attrs={'class': 'rw-select'}),
                                        label='Walls')
    windows_condition = forms.ChoiceField(choices=CONDITION_CHOICES,
                                          widget=forms.Select(
                                              attrs={'class': 'rw-select'}),
                                          label='Windows')
    plumbing_condition = forms.ChoiceField(choices=CONDITION_CHOICES,
                                           widget=forms.Select(
                                               attrs={'class': 'rw-select'}),
                                           label='Plumbing')
    electrical_condition = forms.ChoiceField(choices=CONDITION_CHOICES,
                                             widget=forms.Select(
                                                 attrs={'class': 'rw-select'}),
                                             label='Electrical')
    general_condition = forms.ChoiceField(choices=CONDITION_CHOICES,
                                          widget=forms.Select(
                                              attrs={'class': 'rw-select'}),
                                          label='General Condition')
    inspection_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'rw-textarea', 'rows': 3}),
        label='Inspection Notes',
    )

    # Financial settlement
    damage_deductions = forms.DecimalField(
        max_digits=12, decimal_places=2,
        min_value=0,
        initial=0,
        widget=forms.NumberInput(
            attrs={'class': 'rw-input', 'placeholder': '0.00'}),
        label='Damage Deductions (KSh)',
        help_text='Amount to deduct from deposit for damages.',
    )
    deposit_settlement = forms.ChoiceField(
        choices=SETTLEMENT_CHOICES,
        widget=forms.Select(attrs={'class': 'rw-select'}),
        label='Deposit Settlement',
    )
    reason = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'rw-textarea', 'rows': 2}),
        label='Reason for Move-Out',
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'rw-textarea', 'rows': 2}),
        label='Additional Notes',
    )
    confirm = forms.BooleanField(
        label='I confirm this move-out is correct and authorised.',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )

    def clean(self):
        cleaned = super().clean()
        notice = cleaned.get('notice_date')
        moveout = cleaned.get('moveout_date')
        if notice and moveout and moveout < notice:
            raise forms.ValidationError(
                'Move-out date cannot be before the notice date.'
            )
        return cleaned
