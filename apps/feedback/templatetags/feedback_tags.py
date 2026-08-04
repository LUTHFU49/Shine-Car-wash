from django import template

register = template.Library()


@register.inclusion_tag('feedback/_review_widget.html', takes_context=True)
def review_widget(context, booking):
    """Renders the "leave a review" form (or the review already left)
    on a customer's own booking detail page. A self-contained
    inclusion tag, same pattern as apps.loyalty's booking widget, so
    apps.bookings' template only needed one new line."""
    from apps.bookings.models import BookingStatus
    from apps.feedback.models import Review

    review = Review.objects.filter(booking=booking).first()
    show_form = booking.status == BookingStatus.COMPLETED and review is None
    return {'booking': booking, 'review': review, 'show_form': show_form, 'rating_range': range(5, 0, -1)}
