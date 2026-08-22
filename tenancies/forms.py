from django import forms
from tenants.models import Tenant
from properties.models import Unit
from .models import Tenancy


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
