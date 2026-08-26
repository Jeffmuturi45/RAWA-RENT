from django import forms
from django.contrib.auth.forms import SetPasswordForm, PasswordChangeForm  # noqa: F401
from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from .models import User


# Staff roles selectable when creating/editing users (TENANT excluded for now).
STAFF_ROLE_CHOICES = [
    (value, label) for value, label in User.Role.choices
    if value != User.Role.TENANT
]


class UserCreateForm(forms.ModelForm):

    password1 = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(
            attrs={'class': 'rw-input', 'placeholder': 'Initial password'}),
    )
    password2 = forms.CharField(
        label='Confirm Password',
        widget=forms.PasswordInput(
            attrs={'class': 'rw-input', 'placeholder': 'Re-enter password'}),
    )

    class Meta:
        model = User
        fields = ['full_name', 'email', 'phone',
                  'role', 'is_active', 'must_change_password']
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'rw-input', 'placeholder': 'e.g. Peter Kamau'}),
            'email':     forms.EmailInput(attrs={'class': 'rw-input', 'placeholder': 'name@agency.co.ke'}),
            'phone':     forms.TextInput(attrs={'class': 'rw-input'}),
            'role':      forms.Select(attrs={'class': 'rw-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'must_change_password': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['role'].choices = STAFF_ROLE_CHOICES
        self.fields['must_change_password'].initial = True
        self.fields['is_active'].initial = True

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError(
                'A user with this email already exists.')
        return email

    def clean_password2(self):
        p1 = self.cleaned_data.get('password1')
        p2 = self.cleaned_data.get('password2')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError('Passwords do not match.')
        validate_password(p2)
        return p2

    def save(self, commit=True, organization=None):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email'].lower()
        user.set_password(self.cleaned_data['password1'])
        if organization is not None:
            user.organization = organization
        if commit:
            user.save()
        return user


class UserEditForm(forms.ModelForm):

    class Meta:
        model = User
        fields = ['full_name', 'phone', 'role', 'is_active']
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'rw-input'}),
            'phone':     forms.TextInput(attrs={'class': 'rw-input'}),
            'role':      forms.Select(attrs={'class': 'rw-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, lock_role=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['role'].choices = STAFF_ROLE_CHOICES
        if lock_role:
            # Prevent an owner from demoting/deactivating themselves.
            self.fields['role'].disabled = True
            self.fields['is_active'].disabled = True


class AdminSetPasswordForm(SetPasswordForm):
    """Owner sets/resets another user's password. Styles Django's SetPasswordForm."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.widget.attrs.update({'class': 'rw-input'})


class ProfileForm(forms.ModelForm):

    class Meta:
        model = User
        fields = ['full_name', 'phone', 'avatar']
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'rw-input'}),
            'phone':     forms.TextInput(attrs={'class': 'rw-input'}),
        }


class StyledPasswordChangeForm(PasswordChangeForm):
    """Self password change with rw-input styling."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.widget.attrs.update({'class': 'rw-input'})


class FinancialPinForm(forms.Form):
    pin = forms.CharField(
        label='Financial PIN',
        min_length=4, max_length=6,
        widget=forms.PasswordInput(attrs={'class': 'rw-input', 'inputmode': 'numeric',
                                          'placeholder': '4–6 digits'}),
    )
    confirm_pin = forms.CharField(
        label='Confirm PIN',
        min_length=4, max_length=6,
        widget=forms.PasswordInput(
            attrs={'class': 'rw-input', 'inputmode': 'numeric'}),
    )

    def clean_pin(self):
        pin = self.cleaned_data['pin']
        if not pin.isdigit():
            raise forms.ValidationError('PIN must contain digits only.')
        return pin

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('pin') and cleaned.get('confirm_pin') \
                and cleaned['pin'] != cleaned['confirm_pin']:
            self.add_error('confirm_pin', 'PINs do not match.')
        return cleaned

    def hashed_pin(self):
        return make_password(self.cleaned_data['pin'])


class PortalPasswordChangeForm(PasswordChangeForm):
    """
    Extends Django's built-in PasswordChangeForm with RawaRent styling.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['old_password'].widget = forms.PasswordInput(attrs={
            'class': 'rw-input',
            'placeholder': 'Current password',
            'autofocus': True,
        })
        self.fields['new_password1'].widget = forms.PasswordInput(attrs={
            'class': 'rw-input',
            'placeholder': 'New password',
        })
        self.fields['new_password2'].widget = forms.PasswordInput(attrs={
            'class': 'rw-input',
            'placeholder': 'Confirm new password',
        })

        self.fields['old_password'].label = 'Current Password'
        self.fields['new_password1'].label = 'New Password'
        self.fields['new_password2'].label = 'Confirm New Password'
