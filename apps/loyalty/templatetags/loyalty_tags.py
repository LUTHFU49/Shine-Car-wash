from django import template

from apps.loyalty import services

register = template.Library()


@register.inclusion_tag('loyalty/_booking_widget.html', takes_context=True)
def loyalty_booking_widget(context, booking):
    """Renders the "Apply Coupon" / "Pay with Wallet" mini-forms on a
    customer's own booking detail page. Kept as a self-contained
    inclusion tag (rather than passed in from apps.bookings' own view)
    so apps.bookings never needed to change at all -- only its
    template gained one `{% loyalty_booking_widget booking %}` line."""
    profile = services.get_or_create_profile(booking.customer)
    return {'booking': booking, 'profile': profile, 'request': context.get('request')}
