from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Role
from apps.audit_logs.models import AuditLog
from apps.customers.models import Customer

from .models import Vehicle, VehicleStatus

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


class VehicleModelTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(first_name='Jane', last_name='Doe', phone_number='0722000001')

    def test_display_name(self):
        vehicle = Vehicle.objects.create(
            customer=self.customer, license_plate='KDA 001A', make='Toyota', model='Corolla',
            year=2020, color='White',
        )
        self.assertEqual(vehicle.display_name, '2020 Toyota Corolla')

    def test_license_plate_unique(self):
        Vehicle.objects.create(
            customer=self.customer, license_plate='KDA 002A', make='Toyota', model='Corolla',
            year=2020, color='White',
        )
        with self.assertRaises(Exception):
            Vehicle.objects.create(
                customer=self.customer, license_plate='KDA 002A', make='Honda', model='Civic',
                year=2021, color='Blue',
            )

    def test_is_self_registered_false_when_created_by_set(self):
        staff = make_staff_user()
        vehicle = Vehicle.objects.create(
            customer=self.customer, license_plate='KDA 003A', make='Toyota', model='Corolla',
            year=2020, color='White', created_by=staff,
        )
        self.assertFalse(vehicle.is_self_registered)

    def test_default_status_is_active(self):
        vehicle = Vehicle.objects.create(
            customer=self.customer, license_plate='KDA 004A', make='Toyota', model='Corolla',
            year=2020, color='White',
        )
        self.assertEqual(vehicle.status, VehicleStatus.ACTIVE)


class LicensePlateValidationTests(TestCase):
    def setUp(self):
        self.staff = make_staff_user()
        self.customer = Customer.objects.create(first_name='Jane', last_name='Doe', phone_number='0722000002')
        self.client.login(username='staffuser', password='StrongPass1!')
        self.create_url = reverse('vehicles:create') + f'?customer={self.customer.public_id}'

    def _post(self, plate):
        return self.client.post(self.create_url, {
            'make': 'Toyota', 'model': 'Corolla', 'year': 2020, 'color': 'White',
            'vehicle_type': 'sedan', 'license_plate': plate,
        }, follow=True)

    def test_accepts_correctly_formatted_plate(self):
        self._post('KDA 001A')
        self.assertTrue(Vehicle.objects.filter(license_plate='KDA 001A').exists())

    def test_normalizes_unspaced_lowercase_plate(self):
        self._post('kda005a')
        self.assertTrue(Vehicle.objects.filter(license_plate='KDA 005A').exists())

    def test_rejects_invalid_format(self):
        self._post('ABC123')
        self.assertFalse(Vehicle.objects.filter(make='Toyota', model='Corolla', color='White').exclude(license_plate__startswith='KDA').exists())

    def test_rejects_wrong_letter_count(self):
        response = self._post('KD 001A')
        self.assertFalse(Vehicle.objects.filter(license_plate__icontains='KD 001A').exists())

    def test_duplicate_plate_rejected(self):
        Vehicle.objects.create(customer=self.customer, license_plate='KDA 009A', make='Honda', model='Civic', year=2019, color='Red')
        self._post('KDA009A')
        self.assertEqual(Vehicle.objects.filter(license_plate='KDA 009A').count(), 1)


class VehiclePermissionTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(first_name='Jane', last_name='Doe', phone_number='0722000003')
        self.vehicle = Vehicle.objects.create(
            customer=self.customer, license_plate='KDA 010A', make='Toyota', model='Corolla', year=2020, color='White',
        )
        self.list_url = reverse('vehicles:list')

    def test_anonymous_redirected(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 302)

    def test_customer_role_gets_403_on_staff_list(self):
        make_customer_user(username='cust1', phone='0733000001')
        self.client.login(username='cust1', password='StrongPass1!')
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 403)

    def test_manager_allowed_on_staff_list(self):
        make_staff_user(username='mgr1')
        self.client.login(username='mgr1', password='StrongPass1!')
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)

    def test_staff_role_gets_403_on_my_vehicles(self):
        make_staff_user(username='mgr2')
        self.client.login(username='mgr2', password='StrongPass1!')
        response = self.client.get(reverse('vehicles:my_list'))
        self.assertEqual(response.status_code, 403)

    def test_customer_cannot_edit_another_customers_vehicle(self):
        make_customer_user(username='cust2', phone='0733000002')
        self.client.login(username='cust2', password='StrongPass1!')
        response = self.client.get(reverse('vehicles:my_edit', args=[self.vehicle.public_id]))
        self.assertEqual(response.status_code, 404)


class StaffVehicleCRUDTests(TestCase):
    def setUp(self):
        self.staff = make_staff_user()
        self.customer = Customer.objects.create(first_name='Jane', last_name='Doe', phone_number='0722000004')
        self.client.login(username='staffuser', password='StrongPass1!')

    def test_create_requires_customer_selection(self):
        response = self.client.post(reverse('vehicles:create'), {
            'make': 'Toyota', 'model': 'Corolla', 'year': 2020, 'color': 'White',
            'vehicle_type': 'sedan', 'license_plate': 'KDA 020A',
        })
        self.assertFalse(Vehicle.objects.filter(license_plate='KDA 020A').exists())

    def test_create_with_customer_succeeds(self):
        response = self.client.post(reverse('vehicles:create') + f'?customer={self.customer.public_id}', {
            'make': 'Toyota', 'model': 'Corolla', 'year': 2020, 'color': 'White',
            'vehicle_type': 'sedan', 'license_plate': 'KDA 021A', 'customer': str(self.customer.public_id),
        }, follow=True)
        vehicle = Vehicle.objects.get(license_plate='KDA 021A')
        self.assertEqual(vehicle.customer, self.customer)
        self.assertEqual(vehicle.created_by, self.staff)
        self.assertTrue(AuditLog.objects.filter(model_name='Vehicle', object_id=str(vehicle.pk)).exists())

    def test_create_without_status_field_defaults_to_active(self):
        # The create template never shows the "status" field (it's edit-only),
        # so the form must not require it, and must fall back to Active
        # rather than silently rejecting the whole submission.
        response = self.client.post(reverse('vehicles:create') + f'?customer={self.customer.public_id}', {
            'make': 'Honda', 'model': 'Fit', 'year': 2019, 'color': 'Grey',
            'vehicle_type': 'hatchback', 'license_plate': 'KDA 099A', 'customer': str(self.customer.public_id),
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        vehicle = Vehicle.objects.get(license_plate='KDA 099A')
        self.assertEqual(vehicle.status, VehicleStatus.ACTIVE)

    def test_edit_vehicle(self):
        vehicle = Vehicle.objects.create(
            customer=self.customer, license_plate='KDA 022A', make='Toyota', model='Corolla', year=2020, color='White',
        )
        response = self.client.post(reverse('vehicles:edit', args=[vehicle.public_id]), {
            'make': 'Toyota', 'model': 'Corolla', 'year': 2020, 'color': 'Black',
            'vehicle_type': 'sedan', 'license_plate': 'KDA 022A', 'status': 'active',
        }, follow=True)
        vehicle.refresh_from_db()
        self.assertEqual(vehicle.color, 'Black')

    def test_set_status_inactive_then_active(self):
        vehicle = Vehicle.objects.create(
            customer=self.customer, license_plate='KDA 023A', make='Toyota', model='Corolla', year=2020, color='White',
        )
        self.client.post(reverse('vehicles:set_status', args=[vehicle.public_id, 'inactive']))
        vehicle.refresh_from_db()
        self.assertEqual(vehicle.status, VehicleStatus.INACTIVE)

        self.client.post(reverse('vehicles:set_status', args=[vehicle.public_id, 'active']))
        vehicle.refresh_from_db()
        self.assertEqual(vehicle.status, VehicleStatus.ACTIVE)

    def test_detail_shows_history(self):
        vehicle = Vehicle.objects.create(
            customer=self.customer, license_plate='KDA 024A', make='Toyota', model='Corolla', year=2020, color='White',
        )
        AuditLog.objects.create(user=self.staff, action=AuditLog.Action.CREATE, model_name='Vehicle', object_id=str(vehicle.pk), description='Test history entry')
        response = self.client.get(reverse('vehicles:detail', args=[vehicle.public_id]))
        self.assertContains(response, 'Test history entry')


class VehicleSearchTests(TestCase):
    def setUp(self):
        make_staff_user()
        self.client.login(username='staffuser', password='StrongPass1!')
        self.customer = Customer.objects.create(first_name='Alice', last_name='Wanjiru', phone_number='0744000001')
        self.vehicle = Vehicle.objects.create(
            customer=self.customer, license_plate='KDA 030A', make='Toyota', model='Prado', year=2022, color='Silver',
        )

    def test_search_by_plate(self):
        response = self.client.get(reverse('vehicles:list'), {'q': 'KDA 030A'})
        self.assertContains(response, 'Prado')

    def test_search_by_customer_name(self):
        response = self.client.get(reverse('vehicles:list'), {'q': 'Wanjiru'})
        self.assertContains(response, 'Prado')

    def test_filter_by_status(self):
        Vehicle.objects.filter(pk=self.vehicle.pk).update(status=VehicleStatus.SOLD)
        response = self.client.get(reverse('vehicles:list'), {'status': 'active'})
        self.assertNotContains(response, 'Prado')


class VehicleExportTests(TestCase):
    def setUp(self):
        make_staff_user()
        self.client.login(username='staffuser', password='StrongPass1!')
        customer = Customer.objects.create(first_name='Export', last_name='Test', phone_number='0755000001')
        Vehicle.objects.create(customer=customer, license_plate='KDA 040A', make='Mazda', model='Demio', year=2018, color='Red')

    def test_csv_export(self):
        response = self.client.get(reverse('vehicles:export_csv'))
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertIn('KDA 040A', response.content.decode())

    def test_excel_export(self):
        response = self.client.get(reverse('vehicles:export_excel'))
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )


class CustomerSelfServiceVehicleTests(TestCase):
    def setUp(self):
        self.user = make_customer_user(username='selfcust', phone='0766000001')
        self.client.login(username='selfcust', password='StrongPass1!')
        self.customer = Customer.objects.get(user=self.user)

    def test_my_vehicles_list_loads_empty(self):
        response = self.client.get(reverse('vehicles:my_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No vehicles yet')

    def test_add_own_vehicle(self):
        response = self.client.post(reverse('vehicles:my_create'), {
            'make': 'Subaru', 'model': 'Forester', 'year': 2021, 'color': 'Green',
            'vehicle_type': 'suv', 'license_plate': 'KDA 050A',
        }, follow=True)
        vehicle = Vehicle.objects.get(license_plate='KDA 050A')
        self.assertEqual(vehicle.customer, self.customer)
        self.assertTrue(vehicle.is_self_registered)

    def test_edit_own_vehicle(self):
        vehicle = Vehicle.objects.create(
            customer=self.customer, license_plate='KDA 051A', make='Subaru', model='Forester', year=2021, color='Green',
        )
        response = self.client.post(reverse('vehicles:my_edit', args=[vehicle.public_id]), {
            'make': 'Subaru', 'model': 'Forester', 'year': 2021, 'color': 'Blue',
            'vehicle_type': 'suv', 'license_plate': 'KDA 051A',
        }, follow=True)
        vehicle.refresh_from_db()
        self.assertEqual(vehicle.color, 'Blue')

    def test_customer_form_has_no_status_or_notes_field(self):
        response = self.client.get(reverse('vehicles:my_create'))
        self.assertNotContains(response, 'id_status')
        self.assertNotContains(response, 'id_notes')

    def test_mark_own_vehicle_sold(self):
        vehicle = Vehicle.objects.create(
            customer=self.customer, license_plate='KDA 052A', make='Subaru', model='Forester', year=2021, color='Green',
        )
        self.client.post(reverse('vehicles:my_mark_sold', args=[vehicle.public_id]))
        vehicle.refresh_from_db()
        self.assertEqual(vehicle.status, VehicleStatus.SOLD)

    def test_customer_without_profile_redirected_gracefully(self):
        orphan_user = User.objects.create_user(
            username='orphan', email='orphan@example.com', password='StrongPass1!', role=Role.CUSTOMER,
        )
        # No phone_number -> signal skips auto-creating a Customer profile
        self.client.login(username='orphan', password='StrongPass1!')
        response = self.client.get(reverse('vehicles:my_list'), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Complete your profile')
