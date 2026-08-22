from django import forms
from .models import Tenant


class TenantForm(forms.ModelForm):

    class Meta:
        model = Tenant
        fields = [
            'full_name', 'phone', 'email', 'national_id', 'date_of_birth',
            'emergency_contact', 'emergency_phone', 'emergency_relation',
            'address', 'status', 'notes',
        ]
        widgets = {
            'full_name':          forms.TextInput(attrs={'class': 'rw-input', 'placeholder': 'e.g. Jane Wanjiru'}),
            'phone':              forms.TextInput(attrs={'class': 'rw-input', 'placeholder': 'e.g. 0712 345 678'}),
            'email':              forms.EmailInput(attrs={'class': 'rw-input', 'placeholder': 'name@example.com'}),
            'national_id':        forms.TextInput(attrs={'class': 'rw-input'}),
            'date_of_birth':      forms.DateInput(attrs={'class': 'rw-input', 'type': 'date'}),
            'emergency_contact':  forms.TextInput(attrs={'class': 'rw-input'}),
            'emergency_phone':    forms.TextInput(attrs={'class': 'rw-input'}),
            'emergency_relation': forms.TextInput(attrs={'class': 'rw-input', 'placeholder': 'e.g. Spouse, Parent'}),
            'address':            forms.Textarea(attrs={'class': 'rw-textarea', 'rows': 2}),
            'status':             forms.Select(attrs={'class': 'rw-select'}),
            'notes':              forms.Textarea(attrs={'class': 'rw-textarea', 'rows': 3}),
        }
