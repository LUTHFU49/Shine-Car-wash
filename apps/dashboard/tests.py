from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Role, User


class DashboardHomeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='janedoe', email='jane@example.com', password='StrongPass1!')

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse('dashboard:home'))
        self.assertEqual(response.status_code, 302)

    def test_dashboard_loads_when_authenticated(self):
        self.client.login(username='janedoe', password='StrongPass1!')
        response = self.client.get(reverse('dashboard:home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Welcome back')

    def test_manager_quick_actions_link_to_real_customers_url(self):
        manager = User.objects.create_user(
            username='mgrqa', email='mgrqa@example.com', password='StrongPass1!', role=Role.MANAGER,
        )
        self.client.login(username='mgrqa', password='StrongPass1!')
        response = self.client.get(reverse('dashboard:home'))
        self.assertContains(response, reverse('customers:list'))

    def test_dashboard_shows_customer_quick_actions(self):
        self.client.login(username='janedoe', password='StrongPass1!')
        response = self.client.get(reverse('dashboard:home'))
        self.assertContains(response, 'Book a Wash')
