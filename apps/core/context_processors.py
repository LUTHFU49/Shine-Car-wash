from django.conf import settings


def site_context(request):
    """
    Injects global branding + theme variables into every template context,
    so base.html / navbar / footer / emails can all reference one source
    of truth for the brand name and colors.
    """
    return {
        'SITE_NAME': getattr(settings, 'SITE_NAME', 'ShineHub'),
        'COMPANY_NAME': getattr(settings, 'COMPANY_NAME', 'ALPHACODE SOLUTIONS'),
        'SITE_DOMAIN': getattr(settings, 'SITE_DOMAIN', 'localhost:8000'),
        'THEME_COLORS': {
            'blue': '#0013DE',
            'pink': '#FF0090',
        },
        # Roles allowed into the internal "Operations" nav section (Customers,
        # Vehicles, Bookings, Inventory, etc. as each phase is built) — kept
        # here so templates never hardcode role strings in more than one place.
        'staff_roles': ['super_admin', 'manager', 'cashier'],
        'business_hours_start': f'{getattr(settings, "BUSINESS_HOURS_START_HOUR", 8):02d}:00',
        'business_hours_end': f'{getattr(settings, "BUSINESS_HOURS_END_HOUR", 18):02d}:00',
    }
