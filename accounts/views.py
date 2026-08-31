from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import update_session_auth_hash
from django.contrib import messages
from django.db.models import Q
from django.utils import timezone

from .models import User
from .permissions import require_capability, Cap
from .forms import (
    UserCreateForm, UserEditForm, AdminSetPasswordForm,
    ProfileForm, StyledPasswordChangeForm, FinancialPinForm, PortalPasswordChangeForm
)
from notifications.models import notify


# ═════════════════════════════════════════
# USER ADMINISTRATION  (Agency Owner only)
# ═════════════════════════════════════════

@login_required
@require_capability(Cap.MANAGE_USERS)
def user_list(request):
    organization = request.user.organization
    query = request.GET.get('q', '')
    role = request.GET.get('role', '')

    users = User.objects.filter(organization=organization)

    if query:
        users = users.filter(
            Q(full_name__icontains=query) |
            Q(email__icontains=query) |
            Q(phone__icontains=query)
        )
    if role:
        users = users.filter(role=role)

    users = users.order_by('full_name')

    context = {
        'page_title':    'Users',
        'users':         users,
        'query':         query,
        'selected_role': role,
        'role_choices':  User.Role.choices,
        'total':         users.count(),
    }
    return render(request, 'accounts/user_list.html', context)


@login_required
@require_capability(Cap.MANAGE_USERS)
def user_create(request):
    organization = request.user.organization

    if request.method == 'POST':
        form = UserCreateForm(request.POST)
        if form.is_valid():
            user = form.save(organization=organization)
            notify(
                user,
                'Welcome to RawaRent — your account has been created. '
                'Please change your password on first sign-in.',
                level='info',
                actor=request.user,
            )
            messages.success(request, f'User "{user.full_name}" created.')
            return redirect('accounts:user_list')
    else:
        form = UserCreateForm()

    context = {
        'page_title': 'Add User',
        'form':       form,
        'action':     'Create User',
    }
    return render(request, 'accounts/user_form.html', context)


@login_required
@require_capability(Cap.MANAGE_USERS)
def user_edit(request, pk):
    organization = request.user.organization
    user_obj = get_object_or_404(User, pk=pk, organization=organization)
    is_self = user_obj.pk == request.user.pk

    if request.method == 'POST':
        form = UserEditForm(request.POST, instance=user_obj, lock_role=is_self)
        if form.is_valid():
            form.save()
            messages.success(request, f'User "{user_obj.full_name}" updated.')
            return redirect('accounts:user_list')
    else:
        form = UserEditForm(instance=user_obj, lock_role=is_self)

    context = {
        'page_title': f'Edit {user_obj.full_name}',
        'form':       form,
        'user_obj':   user_obj,
        'is_self':    is_self,
        'action':     'Save Changes',
    }
    return render(request, 'accounts/user_form.html', context)


@login_required
@require_capability(Cap.MANAGE_USERS)
def user_set_password(request, pk):
    organization = request.user.organization
    user_obj = get_object_or_404(User, pk=pk, organization=organization)

    if request.method == 'POST':
        form = AdminSetPasswordForm(user_obj, request.POST)
        if form.is_valid():
            form.save()
            # Force the user to change it on next login (unless resetting self).
            if user_obj.pk != request.user.pk:
                user_obj.must_change_password = True
                user_obj.save(update_fields=['must_change_password'])
            else:
                update_session_auth_hash(request, user_obj)
            messages.success(
                request, f'Password updated for {user_obj.full_name}.')
            return redirect('accounts:user_list')
    else:
        form = AdminSetPasswordForm(user_obj)

    context = {
        'page_title': f'Set Password — {user_obj.full_name}',
        'form':       form,
        'user_obj':   user_obj,
    }
    return render(request, 'accounts/user_set_password.html', context)


# ═════════════════════════════════════════
# SELF-SERVICE  (any authenticated staff)
# ═════════════════════════════════════════

@login_required
def profile(request):
    if request.method == 'POST':
        form = ProfileForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated.')
            return redirect('accounts:profile')
    else:
        form = ProfileForm(instance=request.user)

    context = {
        'page_title':    'My Profile',
        'form':          form,
        'pin_form':      FinancialPinForm(),
        'password_form': StyledPasswordChangeForm(request.user),
    }
    return render(request, 'accounts/profile.html', context)


@login_required
def change_password(request):
    if request.method == 'POST':
        form = StyledPasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            user.must_change_password = False
            user.last_password_change = timezone.now()
            user.save(update_fields=[
                      'must_change_password', 'last_password_change'])
            update_session_auth_hash(request, user)  # keep the user logged in
            messages.success(request, 'Password changed successfully.')
            return redirect('accounts:profile')
    else:
        form = StyledPasswordChangeForm(request.user)

    context = {
        'page_title':    'Change Password',
        'password_form': form,
        'force':         request.user.must_change_password,
    }
    return render(request, 'accounts/change_password.html', context)


@login_required
def set_financial_pin(request):
    if request.method == 'POST':
        form = FinancialPinForm(request.POST)
        if form.is_valid():
            request.user.financial_pin = form.hashed_pin()
            request.user.save(update_fields=['financial_pin'])
            messages.success(request, 'Financial PIN set.')
            return redirect('accounts:profile')
    else:
        form = FinancialPinForm()

    context = {
        'page_title': 'Financial PIN',
        'pin_form':   form,
    }
    return render(request, 'accounts/set_pin.html', context)


@login_required
def portal_placeholder(request):
    """
    Redirect tenant users to the actual portal or dashboard.
    """
    # Check if user has a tenant profile
    if hasattr(request.user, 'tenant_profile'):
        tenant = request.user.tenant_profile
        tenancy = tenant.get_active_tenancy()

        # If tenant has an active tenancy, redirect to portal dashboard
        if tenancy:
            return redirect('portal:dashboard')
        else:
            # No active tenancy, redirect to main dashboard with message
            messages.info(request, 'You do not have an active tenancy.')
            # Use the correct URL name - check what your dashboard URL is named
            # or 'dashboard' or 'core_dashboard'
            return redirect('core:dashboard')
    else:
        # User is not a tenant, redirect to main dashboard
        return redirect('core:dashboard')  # or 'dashboard' or 'core_dashboard'


@login_required
def password_change(request):
    """
    Handles both forced first-login change and voluntary password change.
    After success, clears must_change_password flag.
    """
    if request.method == 'POST':
        form = PortalPasswordChangeForm(user=request.user, data=request.POST)
        if form.is_valid():
            user = form.save()
            # Clear the force-change flag
            user.must_change_password = False
            user.last_password_change = timezone.now()
            user.save(update_fields=[
                      'must_change_password', 'last_password_change'])

            # Keep session alive after password change
            update_session_auth_hash(request, user)

            messages.success(
                request, 'Password changed successfully. Welcome!')

            # Redirect tenant to portal, staff to dashboard
            if request.user.role == 'TENANT':
                return redirect('portal:dashboard')
            return redirect('core:dashboard')
    else:
        form = PortalPasswordChangeForm(user=request.user)

    forced = request.user.must_change_password

    context = {
        'form':   form,
        'forced': forced,
    }
    return render(request, 'accounts/password_change.html', context)
