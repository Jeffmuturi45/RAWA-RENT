from django import forms
from django.utils import timezone

from properties.models import Unit

from .models import (
    MaintenanceRequest,
    TransferRequest,
    MoveOutRequest,
)


class MaintenanceRequestForm(forms.ModelForm):

    class Meta:
        model = MaintenanceRequest
        fields = [
            'title',
            'description',
            'priority',
        ]

        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Leaking bathroom tap',
            }),

            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 5,
                'placeholder': (
                    'Describe the problem and where it is located...'
                ),
            }),

            'priority': forms.Select(attrs={
                'class': 'form-select',
            }),
        }


class TransferRequestForm(forms.ModelForm):

    class Meta:
        model = TransferRequest
        fields = [
            'requested_unit',
            'requested_date',
            'reason',
        ]

        widgets = {
            'requested_unit': forms.Select(attrs={
                'class': 'form-select',
            }),

            'requested_date': forms.DateInput(
                attrs={
                    'class': 'form-control',
                    'type': 'date',
                }
            ),

            'reason': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 5,
                'placeholder': (
                    'Please explain why you would like to transfer...'
                ),
            }),
        }

    def __init__(self, *args, organization=None, current_unit=None, **kwargs):
        super().__init__(*args, **kwargs)

        if organization is not None:

            qs = Unit.objects.filter(
                prop__organization=organization
            )

            if current_unit is not None:
                qs = qs.exclude(pk=current_unit.pk)

            qs = qs.filter(
                status=Unit.Status.VACANT
            ).select_related('prop').order_by(
                'prop__name',
                'unit_number'
            )

            self.fields['requested_unit'].queryset = qs

        self.fields['requested_date'].widget.attrs['min'] = (
            timezone.now().date().isoformat()
        )


class MoveOutRequestForm(forms.ModelForm):

    class Meta:
        model = MoveOutRequest
        fields = [
            'requested_moveout_date',
            'reason',
        ]

        widgets = {
            'requested_moveout_date': forms.DateInput(
                attrs={
                    'class': 'form-control',
                    'type': 'date',
                }
            ),

            'reason': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 5,
                'placeholder': (
                    'Optional: tell the property management office '
                    'why you are moving out...'
                ),
            }),
        }

    def clean_requested_moveout_date(self):
        value = self.cleaned_data['requested_moveout_date']

        if value < timezone.now().date():
            raise forms.ValidationError(
                'Move-out date cannot be in the past.'
            )

        return value
