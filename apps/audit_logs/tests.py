from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Role

from .models import AuditLog

User = get_user_model()


def make_staff_user(role=Role.MANAGER, username='auditstaff'):
    user = User.objects.create_user(
        username=username, email=f'{username}@example.com', password='StrongPass1!', role=role,
    )
    user.is_email_verified = True
    user.save()
    return user


class AuditLogMiddlewareTests(TestCase):
    """
    The generic AuditLogMiddleware is the safety net that guarantees
    every state-changing request gets recorded even if a view forgets
    an explicit log call -- these tests exercise that net directly
    rather than relying on it only being incidentally covered by other
    apps' tests.
    """

    def setUp(self):
        self.user = make_staff_user()
        self.client.login(username='auditstaff', password='StrongPass1!')

    def test_get_requests_are_not_logged_by_the_safety_net(self):
        count_before = AuditLog.objects.count()
        self.client.get('/')
        self.assertEqual(AuditLog.objects.count(), count_before)

    def test_post_request_is_logged_as_other(self):
        # The public contact form is a plain POST with no explicit
        # AuditLog call of its own -- a clean way to exercise only the
        # middleware's safety net, not a view's own logging.
        self.client.post(reverse('core:contact'), {
            'name': 'Audit Test', 'email': 'audit@example.com', 'subject': 'Test Subject', 'message': 'Testing the safety net.',
        })
        entry = AuditLog.objects.filter(path=reverse('core:contact'), method='POST').first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.action, AuditLog.Action.OTHER)

    def test_static_and_media_paths_are_never_logged(self):
        count_before = AuditLog.objects.count()
        self.client.post('/static/does-not-matter.css')
        self.assertEqual(AuditLog.objects.count(), count_before)

    def test_logged_entry_captures_user_and_ip(self):
        self.client.post(reverse('core:contact'), {
            'name': 'Audit Test 2', 'email': 'audit2@example.com', 'subject': 'Test Subject 2', 'message': 'Testing user/IP capture.',
        }, REMOTE_ADDR='203.0.113.55')
        entry = AuditLog.objects.filter(path=reverse('core:contact'), method='POST').order_by('-created_at').first()
        self.assertEqual(entry.user, self.user)
        self.assertEqual(entry.ip_address, '203.0.113.55')

    def test_anonymous_state_changing_request_logs_null_user(self):
        self.client.logout()
        self.client.post(reverse('core:contact'), {
            'name': 'Anon', 'email': 'anon@example.com', 'subject': 'Anon Subject', 'message': 'Anonymous contact test.',
        })
        entry = AuditLog.objects.filter(path=reverse('core:contact'), method='POST').order_by('-created_at').first()
        self.assertIsNone(entry.user)


class AuditLogAdminTests(TestCase):
    """The audit trail must be tamper-evident: nobody, including a
    superuser, should be able to add or edit entries through the admin."""

    def setUp(self):
        self.superuser = User.objects.create_superuser(username='auditadmin', email='auditadmin@example.com', password='AuditAdmin1!@#')
        self.client.login(username='auditadmin', password='AuditAdmin1!@#')

    def test_cannot_add_audit_log_via_admin(self):
        response = self.client.get('/admin/audit_logs/auditlog/add/')
        self.assertEqual(response.status_code, 403)

    def test_cannot_edit_existing_audit_log_via_admin(self):
        entry = AuditLog.objects.create(action=AuditLog.Action.OTHER, description='Pre-existing entry')
        response = self.client.post(f'/admin/audit_logs/auditlog/{entry.pk}/change/', {'description': 'Tampered'})
        self.assertEqual(response.status_code, 403)
        entry.refresh_from_db()
        self.assertEqual(entry.description, 'Pre-existing entry')

    def test_admin_list_view_loads(self):
        AuditLog.objects.create(action=AuditLog.Action.LOGIN, description='Test login entry')
        response = self.client.get('/admin/audit_logs/auditlog/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test login entry')
