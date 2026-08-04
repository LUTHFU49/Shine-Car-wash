from django.conf import settings
from django.contrib import messages
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django_ratelimit.decorators import ratelimit

from apps.bookings.models import Booking, BookingStatus
from apps.customers.models import Customer
from apps.employees.models import Employee, EmploymentStatus
from apps.vehicles.models import Vehicle


def landing_page(request):
    """
    The ShineHub marketing landing page: hero, features, services,
    pricing teaser, testimonials, stats, about, FAQ, and contact —
    all in one scrollable, section-anchored page as specified.
    """
    features = [
        {
            'icon': 'fa-calendar-check',
            'title': 'Effortless Online Booking',
            'text': 'Customers book a wash slot in under a minute, from any device, any time of day.',
        },
        {
            'icon': 'fa-bolt',
            'title': 'Real-Time Notifications',
            'text': 'Booking confirmations, reminders, and status changes land instantly — no page refresh needed.',
        },
        {
            'icon': 'fa-mobile-screen-button',
            'title': 'M-Pesa Payments Built In',
            'text': 'Pay by cash or M-Pesa via Safaricom Daraja, with instant receipts and verified transactions.',
        },
        {
            'icon': 'fa-chart-line',
            'title': 'Live Business Analytics',
            'text': 'Revenue trends, peak hours, repeat customers, and employee performance — all in one dashboard.',
        },
        {
            'icon': 'fa-boxes-stacked',
            'title': 'Smart Inventory Alerts',
            'text': 'Never run out of soap or wax again — automatic low-stock alerts keep every branch stocked.',
        },
        {
            'icon': 'fa-shield-halved',
            'title': 'Bank-Grade Security',
            'text': 'Role-based access, audit logs, and hardened sessions protect every customer and transaction record.',
        },
    ]

    services = [
        {'icon': 'fa-car', 'title': 'Basic Wash', 'text': 'Exterior wash, tyre shine, and a quick vacuum.'},
        {'icon': 'fa-car-side', 'title': 'Premium Wash', 'text': 'Full interior detail, wax, and engine bay clean.'},
        {'icon': 'fa-spray-can-sparkles', 'title': 'Full Detailing', 'text': 'Showroom finish, inside and out, top to bottom.'},
        {'icon': 'fa-caravan', 'title': 'Fleet & Multi-Vehicle', 'text': 'Scheduled washes for fleets, with per-vehicle history.'},
    ]

    pricing_tiers = [
        {
            'name': 'Basic', 'price': 'KSh 500', 'period': 'per wash',
            'features': ['Exterior wash', 'Tyre shine', 'Quick vacuum', 'SMS confirmation'],
            'highlighted': False,
        },
        {
            'name': 'Premium', 'price': 'KSh 1,200', 'period': 'per wash',
            'features': ['Everything in Basic', 'Interior detail', 'Wax coat', 'Engine bay clean', 'Priority slot'],
            'highlighted': True,
        },
        {
            'name': 'Fleet', 'price': 'Custom', 'period': 'monthly contract',
            'features': ['Multi-vehicle scheduling', 'Dedicated account manager', 'Consolidated invoicing', 'Volume discounts'],
            'highlighted': False,
        },
    ]

    testimonials = [
        {'name': 'Amina W.', 'role': 'Loyal Customer', 'text': 'Booking a wash used to mean phone calls and guesswork. Now I do it in thirty seconds and get a reminder before my slot.'},
        {'name': 'David K.', 'role': 'Fleet Manager', 'text': 'We track every vehicle in our fleet in one place. The reports alone have paid for the system.'},
        {'name': 'Grace N.', 'role': 'Branch Manager', 'text': 'Inventory alerts mean we never turn away a customer because we ran out of supplies.'},
    ]

    stats = [
        {
            'icon': 'fa-users', 'label': 'Registered Customers',
            'raw_value': Customer.objects.filter(is_active=True).count(),
        },
        {
            'icon': 'fa-car', 'label': 'Vehicles Registered',
            'raw_value': Vehicle.objects.count(),
        },
        {
            'icon': 'fa-calendar-check', 'label': 'Washes Completed',
            'raw_value': Booking.objects.filter(status=BookingStatus.COMPLETED).count(),
        },
        {
            'icon': 'fa-people-group', 'label': 'Team Members',
            'raw_value': Employee.objects.filter(employment_status=EmploymentStatus.ACTIVE).count(),
        },
    ]
    for stat in stats:
        stat['value'] = f"{stat['raw_value']:,}"

    faqs = [
        {'q': 'Can I book a wash for multiple vehicles?', 'a': 'Yes — register every vehicle on your account and book them individually or as a fleet.'},
        {'q': 'What payment methods are supported?', 'a': 'Cash at the branch, or M-Pesa through Safaricom Daraja for instant, verified digital payments.'},
        {'q': 'Will I be notified about my booking status?', 'a': 'Yes — you get real-time in-app notifications and branded emails at every stage, from confirmation to completion.'},
        {'q': 'Can I reschedule or cancel a booking?', 'a': 'Yes, from your dashboard, subject to the branch\u2019s cancellation window.'},
        {'q': 'Is my data secure?', 'a': 'All traffic is encrypted, passwords are hashed, and every account action is protected by role-based access control and audit logging.'},
    ]

    gallery_items = [
        {
            'id': '1607860108855-64acf2078ed9',
            'caption': 'Full Wash',
            'alt': 'Car being rinsed with a high-pressure water jet during a wash',
        },
        {
            'id': '1565689876697-e467b6c54da2',
            'caption': 'Wheel & Rim Detailing',
            'alt': 'Close-up of a clean, detailed wheel and rim',
        },
        {
            'id': '1704796141009-5ed5cc8ca5f3',
            'caption': 'Hand Wash',
            'alt': 'Staff member hand-washing a car with a sponge',
        },
        {
            'id': '1575844611398-2a68400b437c',
            'caption': 'Premium Finish',
            'alt': 'A freshly washed car with a glossy, premium finish',
        },
        {
            'id': '1611239179213-d972da54091a',
            'caption': 'Sparkling Clean',
            'alt': 'Water beading on a freshly cleaned car exterior',
        },
        {
            'id': '1515569067071-ec3b51335dd0',
            'caption': 'Detail Work',
            'alt': 'Close-up detailing work on a vehicle interior',
        },
    ]

    context = {
        'features': features,
        'services': services,
        'pricing_tiers': pricing_tiers,
        'testimonials': testimonials,
        'stats': stats,
        'faqs': faqs,
        'gallery_items': gallery_items,
    }
    return render(request, 'core/landing.html', context)


def about_page(request):
    return render(request, 'core/about.html')


def pricing_page(request):
    return render(request, 'core/pricing.html')


def faq_page(request):
    return render(request, 'core/faq.html')


@ratelimit(key='ip', rate=settings.RATELIMIT_CONTACT, method='POST', block=True)
def contact_page(request):
    """
    Contact form with strict backend validation (never trust the
    frontend alone). On success, shows a toast via Django messages —
    actual email dispatch to the ShineHub team is wired in when the
    branded-email templates are built in a later phase.

    Rate-limited by IP (see RATELIMIT_CONTACT in settings) since this
    is a public, unauthenticated endpoint -- otherwise it's an open
    invitation for spam/mail-bombing scripts.
    """
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        email = request.POST.get('email', '').strip()
        subject = request.POST.get('subject', '').strip()
        message = request.POST.get('message', '').strip()

        errors = []
        if len(name) < 2:
            errors.append('Please enter your full name.')
        try:
            validate_email(email)
        except ValidationError:
            errors.append('Please enter a valid email address.')
        if len(subject) < 3:
            errors.append('Please enter a subject.')
        if len(message) < 10:
            errors.append('Your message should be at least 10 characters long.')

        if errors:
            for err in errors:
                messages.error(request, err)
            return render(request, 'core/contact.html', {
                'form_data': {'name': name, 'email': email, 'subject': subject, 'message': message},
            })

        messages.success(request, 'Thanks for reaching out! Our team will get back to you shortly.')
        return redirect('core:contact')

    return render(request, 'core/contact.html')


def error_403(request, exception=None):
    return render(request, 'errors/403.html', status=403)


def error_404(request, exception=None):
    return render(request, 'errors/404.html', status=404)


def error_500(request):
    return render(request, 'errors/500.html', status=500)
