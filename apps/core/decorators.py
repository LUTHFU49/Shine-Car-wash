"""
Role-based access control helpers.

Every phase from here on (Customers, Vehicles, Bookings, Inventory,
Employees, Reports, ...) gates its staff-facing views with these
decorators rather than re-implementing the same role check five times
in five apps.
"""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.shortcuts import render


def role_required(*allowed_roles):
    """
    Restricts a view to users whose `request.user.role` is one of
    `allowed_roles` (see apps.accounts.models.Role). Implies login_required.
    Renders the branded 403 page directly (rather than raising
    PermissionDenied) so behavior is identical whether DEBUG is on or off.
    """

    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped_view(request, *args, **kwargs):
            if request.user.role not in allowed_roles:
                return render(request, 'errors/403.html', status=403)
            return view_func(request, *args, **kwargs)
        return _wrapped_view

    return decorator


def staff_required(view_func):
    """Shortcut for the three internal-operations roles."""
    from apps.accounts.models import Role
    return role_required(Role.SUPER_ADMIN, Role.MANAGER, Role.CASHIER)(view_func)


def management_required(view_func):
    """
    Stricter than staff_required: Super Admin and Manager only. Used for
    actions with real business consequences a Cashier shouldn't have --
    setting prices, editing the service catalog, etc. Cashiers can still
    view this data through the staff_required views; they just can't
    change it.
    """
    from apps.accounts.models import Role
    return role_required(Role.SUPER_ADMIN, Role.MANAGER)(view_func)


def customer_required(view_func):
    """Shortcut for customer-facing self-service views (My Vehicles, etc.)."""
    from apps.accounts.models import Role
    return role_required(Role.CUSTOMER)(view_func)


def employee_required(view_func):
    """Shortcut for employee-facing self-service views (My Schedule, etc.)."""
    from apps.accounts.models import Role
    return role_required(Role.EMPLOYEE)(view_func)
