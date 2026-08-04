"""
Business logic for reviews and general feedback. Kept the same shape
as every other services.py in this project: validation lives here,
not in views, so the customer self-service views and any future
caller (an admin action, a management command) stay consistent.
"""
from django.core.exceptions import ValidationError
from django.db.models import Avg, Count
from django.urls import reverse
from django.utils import timezone

from .models import Feedback, FeedbackStatus, Review


# ============================================================
# Reviews
# ============================================================

def submit_review(booking, rating, comment=''):
    from apps.bookings.models import BookingStatus

    if booking.status != BookingStatus.COMPLETED:
        raise ValidationError('You can only review a completed booking.')
    if Review.objects.filter(booking=booking).exists():
        raise ValidationError('You have already reviewed this booking.')
    if rating < 1 or rating > 5:
        raise ValidationError('Rating must be between 1 and 5.')

    review = Review.objects.create(booking=booking, customer=booking.customer, rating=rating, comment=comment)

    if rating <= 2:
        # A low rating is worth surfacing to management immediately,
        # the same way a booking cancellation already is (Phase 11).
        from apps.notifications.utils import notify_roles
        from apps.notifications.models import NotificationLevel
        from apps.accounts.models import Role
        notify_roles(
            [Role.SUPER_ADMIN, Role.MANAGER], title='Low rating received',
            message=f'{booking.customer} rated {booking.booking_code} {rating}/5.',
            level=NotificationLevel.WARNING, url=reverse('feedback:review_detail', args=[review.public_id]),
        )

    return review


def respond_to_review(review, response_text, user):
    if not response_text.strip():
        raise ValidationError('Response cannot be empty.')

    review.manager_response = response_text
    review.responded_by = user
    review.responded_at = timezone.now()
    review.save(update_fields=['manager_response', 'responded_by', 'responded_at', 'updated_at'])

    from apps.notifications.utils import notify
    from apps.notifications.models import NotificationLevel
    notify(
        review.customer.user, title='A manager responded to your review',
        message=response_text[:150], level=NotificationLevel.INFO,
        url=reverse('bookings:my_detail', args=[review.booking.public_id]),
    )
    return review


# ============================================================
# Feedback (complaints / suggestions / general)
# ============================================================

def submit_feedback(customer, feedback_type, subject, message, booking=None):
    if not subject.strip() or not message.strip():
        raise ValidationError('Subject and message are required.')
    return Feedback.objects.create(
        customer=customer, feedback_type=feedback_type, subject=subject, message=message, booking=booking,
    )


def respond_to_feedback(feedback, response_text, user, new_status=FeedbackStatus.RESOLVED):
    if not response_text.strip():
        raise ValidationError('Response cannot be empty.')

    feedback.response = response_text
    feedback.responded_by = user
    feedback.responded_at = timezone.now()
    feedback.status = new_status
    feedback.save(update_fields=['response', 'responded_by', 'responded_at', 'status', 'updated_at'])

    from apps.notifications.utils import notify
    from apps.notifications.models import NotificationLevel
    from apps.accounts.emails import send_branded_email

    notify(
        feedback.customer.user, title=f'Update on "{feedback.subject}"',
        message=response_text[:150], level=NotificationLevel.INFO, url=reverse('feedback:my_list'),
    )
    if feedback.customer.user.email:
        send_branded_email(
            subject=f'Update on your {feedback.get_feedback_type_display().lower()}',
            template_name='feedback_response_email.html',
            context={'user': feedback.customer.user, 'feedback': feedback},
            to_email=feedback.customer.user.email,
        )
    return feedback


# ============================================================
# Satisfaction analytics
# ============================================================

def satisfaction_summary(start_date, end_date):
    reviews = Review.objects.filter(created_at__date__range=[start_date, end_date])
    average_rating = reviews.aggregate(avg=Avg('rating'))['avg']
    distribution = {i: reviews.filter(rating=i).count() for i in range(1, 6)}

    feedback_items = Feedback.objects.filter(created_at__date__range=[start_date, end_date])
    by_type = list(feedback_items.values('feedback_type').annotate(count=Count('id')).order_by('-count'))
    by_status = list(feedback_items.values('status').annotate(count=Count('id')).order_by('-count'))

    open_complaints = Feedback.objects.filter(
        feedback_type='complaint', status__in=[FeedbackStatus.NEW, FeedbackStatus.IN_REVIEW],
    ).count()

    return {
        'review_count': reviews.count(),
        'average_rating': round(average_rating, 2) if average_rating else None,
        'distribution': distribution,
        'feedback_count': feedback_items.count(),
        'by_type': by_type,
        'by_status': by_status,
        'open_complaints': open_complaints,
    }


def rating_trend(start_date, end_date):
    """One row per day with at least one review, for a trend chart."""
    from django.db.models.functions import TruncDate

    reviews = (
        Review.objects.filter(created_at__date__range=[start_date, end_date])
        .annotate(day=TruncDate('created_at'))
        .values('day').annotate(average=Avg('rating'), count=Count('id')).order_by('day')
    )
    return list(reviews)
