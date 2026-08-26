from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

app_name = 'accounts'

urlpatterns = [
    # ── Auth ──────────────────────────────────────────────
    path(
        'login/',
        auth_views.LoginView.as_view(template_name='accounts/login.html'),
        name='login'
    ),
    path(
        'logout/',
        auth_views.LogoutView.as_view(),
        name='logout'
    ),
    path(
        'password-change/',
        views.password_change,
        name='password_change'
    ),

    # ── User administration (owner) ───────────────────────
    path('users/',                    views.user_list,         name='user_list'),
    path('users/add/',                views.user_create,       name='user_create'),
    path('users/<uuid:pk>/edit/',     views.user_edit,         name='user_edit'),
    path('users/<uuid:pk>/password/',
         views.user_set_password, name='user_set_password'),

    # ── Self-service ──────────────────────────────────────
    path('profile/',           views.profile,           name='profile'),
    path('profile/password/',  views.change_password,   name='change_password'),
    path('profile/pin/',       views.set_financial_pin, name='set_financial_pin'),

    # ── Tenant portal placeholder ─────────────────────────
    path('portal/',            views.portal_placeholder, name='portal_placeholder'),
]
