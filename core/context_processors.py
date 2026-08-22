def agency_settings(request):
    """
    Injects agency theme and settings into every template context.
    """
    theme_vars = {}
    agency_name = 'RawaRent'

    if request.user.is_authenticated and hasattr(request.user, 'organization') \
            and request.user.organization:
        org = request.user.organization
        agency_name = org.name
        theme_vars = org.get_theme_css_variables()

    return {
        'agency_name': agency_name,
        'theme_vars': theme_vars,
    }
