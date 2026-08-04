from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from apps.audit_logs.models import AuditLog
from apps.core.decorators import customer_required, management_required

from . import services
from .forms import FeedbackForm, FeedbackResponseForm, ReviewForm, ReviewResponseForm
from .models import Feedback, Review

PAGE_SIZE = 20


def _client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def _log(request, action, model_name, obj, description):
    AuditLog.objects.create(
        user=request.user, action=action, model_name=model_name,
        object_id=str(obj.pk), description=description,
        ip_address=_client_ip(request),
    )


# ============================================================
# Customer self-service
# ============================================================

@customer_required
def my_list_view(request):
    customer = request.user.customer_profile
    reviews = Review.objects.filter(customer=customer).select_related('booking')
    feedback_items = Feedback.objects.filter(customer=customer)
    return render(request, 'feedback/my_list.html', {'reviews': reviews, 'feedback_items': feedback_items})


@customer_required
@ratelimit(key='user', rate=settings.RATELIMIT_FEEDBACK_SUBMIT, method='POST', block=True)
def submit_feedback_view(request):
    if request.method == 'POST':
        form = FeedbackForm(request.POST)
        if form.is_valid():
            services.submit_feedback(
                request.user.customer_profile, form.cleaned_data['feedback_type'],
                form.cleaned_data['subject'], form.cleaned_data['message'],
            )
            messages.success(request, 'Thanks -- we\'ve received your feedback.')
            return redirect('feedback:my_list')
    else:
        form = FeedbackForm()
    return render(request, 'feedback/submit_feedback.html', {'form': form})


@customer_required
@require_POST
@ratelimit(key='user', rate=settings.RATELIMIT_FEEDBACK_SUBMIT, block=True)
def submit_review_view(request, booking_public_id):
    from apps.bookings.models import Booking

    booking = get_object_or_404(Booking, public_id=booking_public_id, customer__user=request.user)
    form = ReviewForm(request.POST)
    if form.is_valid():
        try:
            services.submit_review(booking, int(form.cleaned_data['rating']), form.cleaned_data['comment'])
            messages.success(request, 'Thanks for your review!')
        except ValidationError as exc:
            messages.error(request, exc.message if hasattr(exc, 'message') else str(exc))
    else:
        messages.error(request, 'Please choose a rating.')
    return redirect('bookings:my_detail', public_id=booking.public_id)


# ============================================================
# Staff: Reviews
# ============================================================

@management_required
def review_list_view(request):
    reviews = Review.objects.select_related('booking', 'customer').order_by('-created_at')

    rating = request.GET.get('rating')
    if rating in ('1', '2', '3', '4', '5'):
        reviews = reviews.filter(rating=int(rating))

    published = request.GET.get('published')
    if published == 'yes':
        reviews = reviews.filter(is_published=True)
    elif published == 'no':
        reviews = reviews.filter(is_published=False)

    paginator = Paginator(reviews, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'feedback/review_list.html', {'page_obj': page_obj})


@management_required
def review_detail_view(request, public_id):
    review = get_object_or_404(Review.objects.select_related('booking', 'customer'), public_id=public_id)
    return render(request, 'feedback/review_detail.html', {'review': review, 'form': ReviewResponseForm()})


@management_required
@require_POST
def review_respond_view(request, public_id):
    review = get_object_or_404(Review, public_id=public_id)
    form = ReviewResponseForm(request.POST)
    if form.is_valid():
        services.respond_to_review(review, form.cleaned_data['response'], request.user)
        _log(request, AuditLog.Action.UPDATE, 'Review', review, f'Responded to review for "{review.booking.booking_code}"')
        messages.success(request, 'Response sent.')
    else:
        messages.error(request, 'Please enter a response.')
    return redirect('feedback:review_detail', public_id=review.public_id)


@management_required
@require_POST
def review_set_published_view(request, public_id, new_status):
    review = get_object_or_404(Review, public_id=public_id)
    review.is_published = new_status == 'published'
    review.save(update_fields=['is_published', 'updated_at'])
    _log(request, AuditLog.Action.UPDATE, 'Review', review, f'Visibility set to {new_status}')
    messages.success(request, f'Review marked as {"published" if review.is_published else "hidden"}.')
    return redirect('feedback:review_detail', public_id=review.public_id)


# ============================================================
# Staff: Feedback (complaints / suggestions / general)
# ============================================================

@management_required
def feedback_list_view(request):
    feedback_items = Feedback.objects.select_related('customer', 'booking').order_by('-created_at')

    feedback_type = request.GET.get('type')
    if feedback_type in ('complaint', 'suggestion', 'general'):
        feedback_items = feedback_items.filter(feedback_type=feedback_type)

    status = request.GET.get('status')
    if status in ('new', 'in_review', 'resolved', 'closed'):
        feedback_items = feedback_items.filter(status=status)

    paginator = Paginator(feedback_items, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'feedback/feedback_list.html', {'page_obj': page_obj})


@management_required
def feedback_detail_view(request, public_id):
    feedback = get_object_or_404(Feedback.objects.select_related('customer', 'booking'), public_id=public_id)
    initial = {'status': feedback.status}
    return render(request, 'feedback/feedback_detail.html', {'feedback': feedback, 'form': FeedbackResponseForm(initial=initial)})


@management_required
@require_POST
def feedback_respond_view(request, public_id):
    feedback = get_object_or_404(Feedback, public_id=public_id)
    form = FeedbackResponseForm(request.POST)
    if form.is_valid():
        services.respond_to_feedback(feedback, form.cleaned_data['response'], request.user, form.cleaned_data['status'])
        _log(request, AuditLog.Action.UPDATE, 'Feedback', feedback, f'Responded to "{feedback.subject}"')
        messages.success(request, 'Response sent.')
    else:
        messages.error(request, 'Please enter a response and status.')
    return redirect('feedback:feedback_detail', public_id=feedback.public_id)


# ============================================================
# Staff: Satisfaction analytics
# ============================================================

@management_required
def satisfaction_view(request):
    from apps.reports.services import default_date_range

    start, end = default_date_range(30)
    summary = services.satisfaction_summary(start, end)
    trend = services.rating_trend(start, end)
    recent_reviews = Review.objects.filter(created_at__date__range=[start, end]).select_related('booking', 'customer').order_by('-created_at')[:10]

    return render(request, 'feedback/satisfaction.html', {
        'start': start, 'end': end, 'trend': trend, 'recent_reviews': recent_reviews, **summary,
    })


@management_required
def satisfaction_export_view(request):
    from apps.reports import exports
    from apps.reports.services import default_date_range

    start, end = default_date_range(30)
    reviews = Review.objects.filter(created_at__date__range=[start, end]).select_related('booking', 'customer').order_by('-created_at')
    headers = ['Date', 'Booking', 'Customer', 'Rating', 'Comment']
    rows = [[
        r.created_at.strftime('%Y-%m-%d %H:%M'), r.booking.booking_code,
        f'{r.customer.first_name} {r.customer.last_name}', r.rating, r.comment,
    ] for r in reviews]

    fmt = request.GET.get('format', 'csv').lower()
    if fmt == 'excel':
        return exports.excel_response('shinehub-satisfaction-reviews', 'Reviews', headers, rows)
    if fmt == 'pdf':
        return exports.pdf_response('shinehub-satisfaction-reviews', 'Satisfaction — Reviews', f'{start} to {end}', headers, rows)
    return exports.csv_response('shinehub-satisfaction-reviews', headers, rows)
