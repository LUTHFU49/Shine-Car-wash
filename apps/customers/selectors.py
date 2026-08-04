from django.db.models import Q

from .models import Customer


def search_active_customers(query, limit=20):
    """
    Search-as-you-type lookup used by every staff-facing "pick a customer"
    flow (Vehicle registration, Booking creation, ...). Kept in one place
    so the search fields and active-only filter never drift between apps.
    """
    customers = Customer.objects.filter(is_active=True)
    query = (query or '').strip()
    if query:
        customers = customers.filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(phone_number__icontains=query)
        )
    return customers.order_by('last_name', 'first_name')[:limit]
