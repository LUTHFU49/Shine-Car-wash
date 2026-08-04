from django.test import TestCase
from django.urls import reverse


class LandingPageTests(TestCase):
    def test_landing_page_loads(self):
        response = self.client.get(reverse('core:landing'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ShineHub')

    def test_about_page_loads(self):
        response = self.client.get(reverse('core:about'))
        self.assertEqual(response.status_code, 200)

    def test_pricing_page_loads(self):
        response = self.client.get(reverse('core:pricing'))
        self.assertEqual(response.status_code, 200)

    def test_faq_page_loads(self):
        response = self.client.get(reverse('core:faq'))
        self.assertEqual(response.status_code, 200)

    def test_404_page_uses_custom_template(self):
        response = self.client.get('/this-page-does-not-exist/')
        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, 'errors/404.html')


class ContactFormTests(TestCase):
    def setUp(self):
        self.url = reverse('core:contact')

    def test_valid_submission_succeeds(self):
        response = self.client.post(self.url, {
            'name': 'Jane Doe',
            'email': 'jane@example.com',
            'subject': 'Booking question',
            'message': 'Do you support fleet bookings for 10 vehicles?',
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        messages = list(response.context['messages'])
        self.assertTrue(any('Thanks for reaching out' in str(m) for m in messages))

    def test_invalid_email_is_rejected(self):
        response = self.client.post(self.url, {
            'name': 'Jane Doe',
            'email': 'not-an-email',
            'subject': 'Booking question',
            'message': 'Do you support fleet bookings for 10 vehicles?',
        })
        self.assertEqual(response.status_code, 200)
        messages = list(response.context['messages'])
        self.assertTrue(any('valid email' in str(m) for m in messages))

    def test_short_message_is_rejected(self):
        response = self.client.post(self.url, {
            'name': 'Jane Doe',
            'email': 'jane@example.com',
            'subject': 'Hi',
            'message': 'short',
        })
        messages = list(response.context['messages'])
        self.assertTrue(len(messages) > 0)


class SafeCSVWriterTests(TestCase):
    """Phase 15: CSV/formula injection protection for exports."""

    def test_formula_prefixes_are_neutralized(self):
        import csv
        import io
        from apps.core.csv_utils import safe_csv_writer

        buf = io.StringIO()
        writer = safe_csv_writer(buf)
        writer.writerow(['=cmd|/c calc!A0', '+1+1', '-2+3', '@SUM(A1)', 'Normal Name', 42])
        buf.seek(0)
        row = next(csv.reader(io.StringIO(buf.getvalue())))
        self.assertTrue(row[0].startswith("'="))
        self.assertTrue(row[1].startswith("'+"))
        self.assertTrue(row[2].startswith("'-"))
        self.assertTrue(row[3].startswith("'@"))
        self.assertEqual(row[4], 'Normal Name')
        self.assertEqual(row[5], '42')


class SecurityVerificationTests(TestCase):
    """
    Phase 15 "Security Verification" checklist, as explicit automated
    regression tests rather than a one-time manual check:
    SQL injection, XSS, CSRF, clickjacking, broken access control,
    unsafe file uploads, and open redirects each have dedicated,
    more thorough tests elsewhere (accounts/notifications/customers
    tests) -- this class covers the ones that don't already have a
    natural home in a specific app.
    """

    def test_clickjacking_header_present_on_every_response(self):
        response = self.client.get('/')
        self.assertEqual(response['X-Frame-Options'], 'DENY')
        self.assertIn("frame-ancestors 'none'", response['Content-Security-Policy'])

    def test_csrf_protection_rejects_tokenless_post(self):
        from django.test import Client

        csrf_enforcing_client = Client(enforce_csrf_checks=True)
        response = csrf_enforcing_client.post('/accounts/login/', {'username': 'x', 'password': 'y'})
        self.assertEqual(response.status_code, 403)

    def test_content_type_nosniff_present(self):
        response = self.client.get('/')
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')

    def test_user_submitted_text_is_html_escaped_not_executed(self):
        from django.contrib.auth import get_user_model
        from apps.accounts.models import Role
        from apps.customers.models import Customer
        from apps.feedback.models import Feedback, FeedbackType

        User = get_user_model()
        manager = User.objects.create_user(username='xssmgr', email='xssmgr@example.com', password='XssMgrPass1!@#', role=Role.MANAGER)
        manager.is_email_verified = True
        manager.save()
        customer_user = User.objects.create_user(username='xsscust', email='xsscust@example.com', password='XssCustPass1!@#', role=Role.CUSTOMER)
        customer = Customer.objects.create(user=customer_user, first_name='XSS', last_name='Test', email='xsscust@example.com', phone_number='0700000002')
        feedback = Feedback.objects.create(
            customer=customer, feedback_type=FeedbackType.COMPLAINT,
            subject='Test', message='<script>alert(1)</script>',
        )
        self.client.login(username='xssmgr', password='XssMgrPass1!@#')
        response = self.client.get(reverse('feedback:feedback_detail', args=[feedback.public_id]))
        self.assertNotContains(response, '<script>alert(1)</script>')
        self.assertContains(response, '&lt;script&gt;')
