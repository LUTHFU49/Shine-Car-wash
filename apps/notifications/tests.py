from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Notification, NotificationLevel

User = get_user_model()


class NotificationRedirectTests(TestCase):
    """Phase 15: ?next=/POST 'next' must never send a user off-site."""

    def setUp(self):
        self.user = User.objects.create_user(username='notifredir', email='nr@example.com', password='NotifRedir1!@#')
        self.client.login(username='notifredir', password='NotifRedir1!@#')
        self.notification = Notification.objects.create(
            recipient=self.user, title='Test', message='Test message',
            level=NotificationLevel.INFO, url='/accounts/profile/',
        )

    def test_malicious_next_ignored_on_mark_read(self):
        response = self.client.post(
            reverse('notifications:mark_read', args=[self.notification.public_id]),
            {'next': 'https://evil.example.com/phish'},
        )
        self.assertNotIn('evil.example.com', response.url)

    def test_legitimate_next_honored_on_mark_all_read(self):
        response = self.client.post(reverse('notifications:mark_all_read'), {'next': '/accounts/profile/'})
        self.assertEqual(response.url, '/accounts/profile/')

    def test_malicious_next_ignored_on_mark_all_read(self):
        response = self.client.post(reverse('notifications:mark_all_read'), {'next': '//evil.example.com/'})
        self.assertNotIn('evil.example.com', response.url)
