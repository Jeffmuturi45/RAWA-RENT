from django import forms
from .models import Property, HouseType, Unit


class PropertyForm(forms.ModelForm):

    class Meta:
        model = Property
        fields = [
            'name', 'code', 'address', 'city',
            'county', 'country', 'description',
            'image', 'status'
        ]
        widgets = {
            'name':        forms.TextInput(attrs={'class': 'rw-input', 'placeholder': 'e.g. Anju Apartments'}),
            'code':        forms.TextInput(attrs={'class': 'rw-input', 'placeholder': 'e.g. ANJU'}),
            'address':     forms.Textarea(attrs={'class': 'rw-textarea', 'rows': 2}),
            'city':        forms.TextInput(attrs={'class': 'rw-input'}),
            'county':      forms.TextInput(attrs={'class': 'rw-input'}),
            'country':     forms.TextInput(attrs={'class': 'rw-input'}),
            'description': forms.Textarea(attrs={'class': 'rw-textarea', 'rows': 3}),
            'status':      forms.Select(attrs={'class': 'rw-select'}),
        }


class HouseTypeForm(forms.ModelForm):

    class Meta:
        model = HouseType
        fields = ['name', 'description', 'default_rent', 'default_deposit']
        widgets = {
            'name':            forms.TextInput(attrs={'class': 'rw-input', 'placeholder': 'e.g. Bedsitter'}),
            'description':     forms.Textarea(attrs={'class': 'rw-textarea', 'rows': 2}),
            'default_rent':    forms.NumberInput(attrs={'class': 'rw-input', 'placeholder': '0.00'}),
            'default_deposit': forms.NumberInput(attrs={'class': 'rw-input', 'placeholder': '0.00'}),
        }


class UnitForm(forms.ModelForm):

    class Meta:
        model = Unit
        fields = [
            'unit_number', 'house_type', 'floor',
            'rent_amount', 'deposit_amount',
            'description', 'status'
        ]
        widgets = {
            'unit_number':    forms.TextInput(attrs={'class': 'rw-input', 'placeholder': 'e.g. A101'}),
            'house_type':     forms.Select(attrs={'class': 'rw-select'}),
            'floor':          forms.TextInput(attrs={'class': 'rw-input', 'placeholder': 'e.g. Ground, 1st'}),
            'rent_amount':    forms.NumberInput(attrs={'class': 'rw-input', 'placeholder': '0.00'}),
            'deposit_amount': forms.NumberInput(attrs={'class': 'rw-input', 'placeholder': '0.00'}),
            'description':    forms.Textarea(attrs={'class': 'rw-textarea', 'rows': 2}),
            'status':         forms.Select(attrs={'class': 'rw-select'}),
        }

    def __init__(self, *args, prop=None, **kwargs):
        super().__init__(*args, **kwargs)
        if prop:
            self.fields['house_type'].queryset = HouseType.objects.filter(
                prop=prop)
        self.fields['house_type'].required = False
