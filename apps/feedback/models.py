import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Review(models.Model):
    """A star rating + optional comment for one completed booking --
    at most one per booking. Kept separate from Feedback below since a
    review is always tied to a specific service experience, while
    complaints/suggestions/general feedback often aren't."""
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    booking = models.OneToOneField('bookings.Booking', on_delete=models.CASCADE, related_name='review')
    customer = models.ForeignKey('customers.Customer', on_delete=models.CASCADE, related_name='reviews')

    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField(blank=True)
    is_published = models.BooleanField(default=True, help_text='Unpublish to hide an inappropriate review from staff-facing listings.')

    manager_response = models.TextField(blank=True)
    responded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='review_responses',
    )
    responded_at = models.DateTimeField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'feedback_review'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['rating'])]

    def __str__(self):
        return f'{self.rating}\u2605 review for {self.booking.booking_code}'

    @property
    def has_response(self):
        return bool(self.manager_response)


class FeedbackType(models.TextChoices):
    COMPLAINT = 'complaint', 'Complaint'
    SUGGESTION = 'suggestion', 'Suggestion'
    GENERAL = 'general', 'General Feedback'


class FeedbackStatus(models.TextChoices):
    NEW = 'new', 'New'
    IN_REVIEW = 'in_review', 'In Review'
    RESOLVED = 'resolved', 'Resolved'
    CLOSED = 'closed', 'Closed'


class FeedbackPriority(models.TextChoices):
    LOW = 'low', 'Low'
    MEDIUM = 'medium', 'Medium'
    HIGH = 'high', 'High'


class Feedback(models.Model):
    """Complaints, suggestions, and general feedback -- not
    necessarily tied to a booking, and tracked through a status
    workflow the way a support ticket would be."""
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    customer = models.ForeignKey('customers.Customer', on_delete=models.CASCADE, related_name='feedback_items')
    booking = models.ForeignKey(
        'bookings.Booking', on_delete=models.SET_NULL, null=True, blank=True, related_name='feedback_items',
        help_text='Optional -- set if this feedback concerns a specific booking.',
    )

    feedback_type = models.CharField(max_length=15, choices=FeedbackType.choices, db_index=True)
    subject = models.CharField(max_length=150)
    message = models.TextField()
    priority = models.CharField(max_length=10, choices=FeedbackPriority.choices, default=FeedbackPriority.MEDIUM)
    status = models.CharField(max_length=15, choices=FeedbackStatus.choices, default=FeedbackStatus.NEW, db_index=True)

    response = models.TextField(blank=True)
    responded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='feedback_responses',
    )
    responded_at = models.DateTimeField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'feedback_item'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_feedback_type_display()}: {self.subject}'

    @property
    def has_response(self):
        return bool(self.response)
