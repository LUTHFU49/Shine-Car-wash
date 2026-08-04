from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Role
from apps.audit_logs.models import AuditLog

from .models import Service, ServiceCategory, ServiceStatus

User = get_user_model()


def make_staff_user(role=Role.MANAGER, username='staffuser'):
    user = User.objects.create_user(
        username=username, email=f'{username}@example.com', password='StrongPass1!', role=role,
    )
    user.is_email_verified = True
    user.save()
    return user


def make_customer_user(username='customeruser', phone='0711111111'):
    return User.objects.create_user(
        username=username, email=f'{username}@example.com', password='StrongPass1!', role=Role.CUSTOMER,
        first_name='Auto', last_name='Created', phone_number=phone,
    )


def make_category(name='Wash', **kwargs):
    return ServiceCategory.objects.create(name=name, **kwargs)


class ServiceModelTests(TestCase):
    def setUp(self):
        self.category = make_category()

    def test_duration_display_minutes_only(self):
        service = Service.objects.create(category=self.category, name='Basic Wash', price=500, duration_minutes=30)
        self.assertEqual(service.duration_display, '30m')

    def test_duration_display_hours_and_minutes(self):
        service = Service.objects.create(category=self.category, name='Full Detail', price=3000, duration_minutes=90)
        self.assertEqual(service.duration_display, '1h 30m')

    def test_available_days_blank_means_every_day(self):
        service = Service.objects.create(category=self.category, name='Basic Wash', price=500, duration_minutes=30)
        self.assertEqual(service.available_days_display, 'Every day')
        self.assertEqual(len(service.available_days_list), 7)

    def test_available_days_custom_subset(self):
        service = Service.objects.create(category=self.category, name='Weekend Detail', price=3000, duration_minutes=90, available_days='sat,sun')
        self.assertIn('Saturday', service.available_days_display)
        self.assertIn('Sunday', service.available_days_display)
        self.assertNotIn('Monday', service.available_days_display)

    def test_is_available_today_false_when_inactive(self):
        service = Service.objects.create(category=self.category, name='Basic Wash', price=500, duration_minutes=30, status=ServiceStatus.INACTIVE)
        self.assertFalse(service.is_available_today())

    def test_default_status_active(self):
        service = Service.objects.create(category=self.category, name='Basic Wash', price=500, duration_minutes=30)
        self.assertEqual(service.status, ServiceStatus.ACTIVE)


class ServicePermissionTests(TestCase):
    def setUp(self):
        self.category = make_category()
        self.service = Service.objects.create(category=self.category, name='Basic Wash', price=500, duration_minutes=30)

    def test_public_catalog_accessible_anonymously(self):
        response = self.client.get(reverse('services:catalog'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Basic Wash')

    def test_manage_list_requires_login(self):
        response = self.client.get(reverse('services:list'))
        self.assertEqual(response.status_code, 302)

    def test_customer_blocked_from_manage_list(self):
        make_customer_user()
        self.client.login(username='customeruser', password='StrongPass1!')
        response = self.client.get(reverse('services:list'))
        self.assertEqual(response.status_code, 403)

    def test_cashier_can_view_manage_list(self):
        make_staff_user(role=Role.CASHIER, username='cash1')
        self.client.login(username='cash1', password='StrongPass1!')
        response = self.client.get(reverse('services:list'))
        self.assertEqual(response.status_code, 200)

    def test_cashier_cannot_create_service(self):
        make_staff_user(role=Role.CASHIER, username='cash2')
        self.client.login(username='cash2', password='StrongPass1!')
        response = self.client.get(reverse('services:create'))
        self.assertEqual(response.status_code, 403)

    def test_cashier_cannot_edit_service(self):
        make_staff_user(role=Role.CASHIER, username='cash3')
        self.client.login(username='cash3', password='StrongPass1!')
        response = self.client.get(reverse('services:edit', args=[self.service.public_id]))
        self.assertEqual(response.status_code, 403)

    def test_manager_can_create_service(self):
        make_staff_user(role=Role.MANAGER, username='mgr1')
        self.client.login(username='mgr1', password='StrongPass1!')
        response = self.client.get(reverse('services:create'))
        self.assertEqual(response.status_code, 200)

    def test_super_admin_can_create_service(self):
        make_staff_user(role=Role.SUPER_ADMIN, username='admin1')
        self.client.login(username='admin1', password='StrongPass1!')
        response = self.client.get(reverse('services:create'))
        self.assertEqual(response.status_code, 200)


class ServiceCategoryPermissionTests(TestCase):
    def setUp(self):
        self.category = make_category()

    def test_cashier_can_view_categories(self):
        make_staff_user(role=Role.CASHIER, username='cash4')
        self.client.login(username='cash4', password='StrongPass1!')
        response = self.client.get(reverse('services:category_list'))
        self.assertEqual(response.status_code, 200)

    def test_cashier_cannot_create_category(self):
        make_staff_user(role=Role.CASHIER, username='cash5')
        self.client.login(username='cash5', password='StrongPass1!')
        response = self.client.get(reverse('services:category_create'))
        self.assertEqual(response.status_code, 403)

    def test_manager_can_create_category(self):
        make_staff_user(role=Role.MANAGER, username='mgr2')
        self.client.login(username='mgr2', password='StrongPass1!')
        response = self.client.post(reverse('services:category_create'), {
            'name': 'Detailing', 'icon': 'fa-spray-can-sparkles', 'display_order': 1,
        }, follow=True)
        self.assertTrue(ServiceCategory.objects.filter(name='Detailing').exists())


class ServiceCategoryCRUDTests(TestCase):
    def setUp(self):
        make_staff_user()
        self.client.login(username='staffuser', password='StrongPass1!')

    def test_create_category(self):
        response = self.client.post(reverse('services:category_create'), {
            'name': 'Premium Care', 'icon': 'fa-brush', 'display_order': 2,
        }, follow=True)
        category = ServiceCategory.objects.get(name='Premium Care')
        self.assertTrue(AuditLog.objects.filter(model_name='ServiceCategory', object_id=str(category.pk)).exists())

    def test_duplicate_category_name_rejected(self):
        make_category(name='Basic')
        response = self.client.post(reverse('services:category_create'), {
            'name': 'basic', 'icon': 'fa-car', 'display_order': 0,
        })
        self.assertEqual(ServiceCategory.objects.filter(name__iexact='basic').count(), 1)

    def test_deactivate_and_reactivate_category(self):
        category = make_category(name='Temp Category')
        self.client.post(reverse('services:category_set_status', args=[category.public_id, 'inactive']))
        category.refresh_from_db()
        self.assertFalse(category.is_active)

        self.client.post(reverse('services:category_set_status', args=[category.public_id, 'active']))
        category.refresh_from_db()
        self.assertTrue(category.is_active)


class ServiceCRUDTests(TestCase):
    def setUp(self):
        self.staff = make_staff_user()
        self.category = make_category()
        self.client.login(username='staffuser', password='StrongPass1!')

    def test_create_service_without_status_defaults_active(self):
        response = self.client.post(reverse('services:create'), {
            'category': self.category.pk, 'name': 'Express Wash', 'price': '450.00',
            'duration_minutes': 20,
        }, follow=True)
        service = Service.objects.get(name='Express Wash')
        self.assertEqual(service.status, ServiceStatus.ACTIVE)
        self.assertEqual(service.created_by, self.staff)

    def test_create_service_with_negative_price_rejected(self):
        response = self.client.post(reverse('services:create'), {
            'category': self.category.pk, 'name': 'Bad Price', 'price': '-10.00', 'duration_minutes': 20,
        })
        self.assertFalse(Service.objects.filter(name='Bad Price').exists())

    def test_create_service_with_zero_duration_rejected(self):
        response = self.client.post(reverse('services:create'), {
            'category': self.category.pk, 'name': 'Bad Duration', 'price': '100.00', 'duration_minutes': 0,
        })
        self.assertFalse(Service.objects.filter(name='Bad Duration').exists())

    def test_create_service_with_excessive_duration_rejected(self):
        response = self.client.post(reverse('services:create'), {
            'category': self.category.pk, 'name': 'Too Long', 'price': '100.00', 'duration_minutes': 10000,
        })
        self.assertFalse(Service.objects.filter(name='Too Long').exists())

    def test_create_with_specific_availability_days(self):
        response = self.client.post(reverse('services:create'), {
            'category': self.category.pk, 'name': 'Weekend Detail', 'price': '3000.00',
            'duration_minutes': 90, 'available_days': ['sat', 'sun'],
        }, follow=True)
        service = Service.objects.get(name='Weekend Detail')
        self.assertEqual(service.available_days, 'sat,sun')

    def test_selecting_all_seven_days_normalizes_to_blank(self):
        response = self.client.post(reverse('services:create'), {
            'category': self.category.pk, 'name': 'All Week', 'price': '500.00',
            'duration_minutes': 30, 'available_days': ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'],
        }, follow=True)
        service = Service.objects.get(name='All Week')
        self.assertEqual(service.available_days, '')
        self.assertEqual(service.available_days_display, 'Every day')

    def test_edit_service_price_and_logs_change(self):
        service = Service.objects.create(category=self.category, name='Basic Wash', price=500, duration_minutes=30)
        response = self.client.post(reverse('services:edit', args=[service.public_id]), {
            'category': self.category.pk, 'name': 'Basic Wash', 'price': '600.00', 'duration_minutes': 30,
            'status': 'active',
        }, follow=True)
        service.refresh_from_db()
        self.assertEqual(service.price, 600)
        log_entry = AuditLog.objects.filter(model_name='Service', object_id=str(service.pk)).order_by('-created_at').first()
        self.assertIn('price changed', log_entry.description)

    def test_deactivate_removes_from_public_catalog(self):
        service = Service.objects.create(category=self.category, name='Basic Wash', price=500, duration_minutes=30)
        # follow=True consumes the one-time success toast ("Basic Wash
        # marked as Inactive") so it doesn't leak into the next request
        # and produce a false positive on the substring "Basic Wash".
        self.client.post(reverse('services:set_status', args=[service.public_id, 'inactive']), follow=True)

        response = self.client.get(reverse('services:catalog'))
        self.assertNotContains(response, 'Basic Wash')

    def test_create_requires_active_category(self):
        ServiceCategory.objects.all().update(is_active=False)
        response = self.client.get(reverse('services:create'), follow=True)
        self.assertContains(response, 'Create a service category first')

    def test_detail_shows_history(self):
        service = Service.objects.create(category=self.category, name='Basic Wash', price=500, duration_minutes=30)
        AuditLog.objects.create(user=self.staff, action=AuditLog.Action.CREATE, model_name='Service', object_id=str(service.pk), description='Test history entry')
        response = self.client.get(reverse('services:detail', args=[service.public_id]))
        self.assertContains(response, 'Test history entry')


class ServiceCatalogTests(TestCase):
    def setUp(self):
        self.category = make_category(name='Wash', display_order=1)
        self.other_category = make_category(name='Detailing', display_order=2)
        Service.objects.create(category=self.category, name='Basic Wash', price=500, duration_minutes=30, status=ServiceStatus.ACTIVE)
        Service.objects.create(category=self.other_category, name='Full Detail', price=3000, duration_minutes=120, status=ServiceStatus.ACTIVE)
        Service.objects.create(category=self.category, name='Hidden Service', price=100, duration_minutes=10, status=ServiceStatus.INACTIVE)

    def test_catalog_shows_active_services_grouped_by_category(self):
        response = self.client.get(reverse('services:catalog'))
        self.assertContains(response, 'Basic Wash')
        self.assertContains(response, 'Full Detail')
        self.assertContains(response, 'Wash')
        self.assertContains(response, 'Detailing')

    def test_catalog_hides_inactive_services(self):
        response = self.client.get(reverse('services:catalog'))
        self.assertNotContains(response, 'Hidden Service')

    def test_catalog_hides_services_in_inactive_categories(self):
        self.other_category.is_active = False
        self.other_category.save()
        response = self.client.get(reverse('services:catalog'))
        self.assertNotContains(response, 'Full Detail')


class ServiceExportTests(TestCase):
    def setUp(self):
        make_staff_user()
        self.client.login(username='staffuser', password='StrongPass1!')
        category = make_category()
        Service.objects.create(category=category, name='Export Service', price=750, duration_minutes=45)

    def test_csv_export(self):
        response = self.client.get(reverse('services:export_csv'))
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertIn('Export Service', response.content.decode())

    def test_excel_export(self):
        response = self.client.get(reverse('services:export_excel'))
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
