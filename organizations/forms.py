from django import forms
from .models import Organization


class AgencyProfileForm(forms.ModelForm):
    """Agency identity and contact details (appear on receipts)."""

    class Meta:
        model = Organization
        fields = ['name', 'registration_no', 'phone', 'email',
                  'website', 'address', 'city', 'country']
        widgets = {
            'name':            forms.TextInput(attrs={'class': 'rw-input'}),
            'registration_no': forms.TextInput(attrs={'class': 'rw-input'}),
            'phone':           forms.TextInput(attrs={'class': 'rw-input'}),
            'email':           forms.EmailInput(attrs={'class': 'rw-input'}),
            'website':         forms.URLInput(attrs={'class': 'rw-input'}),
            'address':         forms.Textarea(attrs={'class': 'rw-textarea', 'rows': 2}),
            'city':            forms.TextInput(attrs={'class': 'rw-input'}),
            'country':         forms.TextInput(attrs={'class': 'rw-input'}),
        }


# The theme fields, in the order they're shown in the UI.
THEME_FIELDS = [
    'theme_primary', 'theme_secondary', 'theme_accent',
    'theme_dark', 'theme_light', 'theme_success',
    'theme_warning', 'theme_danger',
    'theme_text_primary', 'theme_text_secondary', 'theme_border',
]


class BrandingForm(forms.ModelForm):
    """Logo, footer, receipt size and the theme palette."""

    class Meta:
        model = Organization
        fields = ['logo', 'favicon', 'footer_text', 'receipt_size'] + THEME_FIELDS
        widgets = {
            'footer_text':  forms.TextInput(attrs={
                'class': 'rw-input',
                'placeholder': 'e.g. Thank you for your payment.'}),
            'receipt_size': forms.Select(attrs={'class': 'rw-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Render every theme_* field as a native colour picker.
        for name in THEME_FIELDS:
            self.fields[name].widget = forms.TextInput(attrs={
                'type': 'color',
                'class': 'rw-color-input',
            })
            self.fields[name].label = (
                name.replace('theme_', '').replace('_', ' ').title()
            )


class SystemSettingsForm(forms.ModelForm):
    """Cutover date and agency status."""

    class Meta:
        model = Organization
        fields = ['cutover_date', 'status']
        widgets = {
            'cutover_date': forms.DateInput(attrs={'class': 'rw-input', 'type': 'date'}),
            'status':       forms.Select(attrs={'class': 'rw-select'}),
        }
