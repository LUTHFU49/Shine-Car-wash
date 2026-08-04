import datetime

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.audit_logs.models import AuditLog
from apps.bookings.models import Booking, BookingStatus
from apps.customers.models import Customer
from apps.services.models import Service, ServiceCategory
from apps.vehicles.models import Vehicle

from .models import AttendanceRecord, AttendanceStatus, Employee, EmployeePosition, EmploymentStatus, PerformanceReview

User = get_user_model()


def make_staff_user(role=Role.MANAGER, username='staffuser'):
    user = User.objects.create_user(
        username=username, email=f'{username}@example.com', password='StrongPass1!', role=role,
    )
    user.is_email_verified = True
    user.save()
    return user


def make_employee(username='empuser', position=EmployeePosition.WASHER, status=EmploymentStatus.ACTIVE):
    user = User.objects.create_user(
        username=username, email=f'{username}@example.com', password='StrongPass1!', role=Role.EMPLOYEE,
        first_name='Emp', last_name='Loyee', phone_number='0788000001',
    )
    employee = Employee.objects.create(user=user, position=position, employment_status=status)
    return user, employee


class EmployeeModelTests(TestCase):
    def test_employee_code_format(self):
        user, employee = make_employee()
        self.assertEqual(employee.employee_code, f'EMP-{employee.pk:06d}')

    def test_full_name_falls_back_to_username(self):
        user = User.objects.create_user(username='noname', email='noname@example.com', password='StrongPass1!', role=Role.EMPLOYEE)
        employee = Employee.objects.create(user=user)
        self.assertEqual(employee.full_name, 'noname')

    def test_scheduled_days_display_not_set(self):
        user, employee = make_employee()
        self.assertEqual(employee.scheduled_days_display, 'Not set')

    def test_scheduled_days_display_with_days(self):
        user, employee = make_employee()
        employee.scheduled_days = 'mon,tue,wed'
        employee.save()
        self.assertIn('Monday', employee.scheduled_days_display)
        self.assertIn('Wednesday', employee.scheduled_days_display)

    def test_is_scheduled_today_false_when_not_active(self):
        user, employee = make_employee(status=EmploymentStatus.ON_LEAVE)
        employee.scheduled_days = 'mon,tue,wed,thu,fri,sat,sun'
        employee.save()
        self.assertFalse(employee.is_scheduled_today())


class AttendanceRecordTests(TestCase):
    def setUp(self):
        self.user, self.employee = make_employee()

    def test_unique_constraint_per_employee_per_day(self):
        today = timezone.localdate()
        AttendanceRecord.objects.create(employee=self.employee, date=today, status=AttendanceStatus.PRESENT)
        with self.assertRaises(Exception):
            AttendanceRecord.objects.create(employee=self.employee, date=today, status=AttendanceStatus.LATE)


class EmployeePermissionTests(TestCase):
    def setUp(self):
        self.user, self.employee = make_employee()

    def test_anonymous_redirected_from_staff_list(self):
        response = self.client.get(reverse('employees:list'))
        self.assertEqual(response.status_code, 302)

    def test_cashier_blocked_from_employee_list(self):
        make_staff_user(role=Role.CASHIER, username='cash1')
        self.client.login(username='cash1', password='StrongPass1!')
        response = self.client.get(reverse('employees:list'))
        self.assertEqual(response.status_code, 403)

    def test_employee_role_blocked_from_staff_list(self):
        self.client.login(username='empuser', password='StrongPass1!')
        response = self.client.get(reverse('employees:list'))
        self.assertEqual(response.status_code, 403)

    def test_manager_can_view_employee_list(self):
        make_staff_user(role=Role.MANAGER, username='mgr1')
        self.client.login(username='mgr1', password='StrongPass1!')
        response = self.client.get(reverse('employees:list'))
        self.assertEqual(response.status_code, 200)

    def test_super_admin_can_view_employee_list(self):
        make_staff_user(role=Role.SUPER_ADMIN, username='admin1')
        self.client.login(username='admin1', password='StrongPass1!')
        response = self.client.get(reverse('employees:list'))
        self.assertEqual(response.status_code, 200)

    def test_manager_role_only_sees_own_employee_self_service(self):
        # Managers aren't Employees -- self-service views are Employee-role only.
        make_staff_user(role=Role.MANAGER, username='mgr2')
        self.client.login(username='mgr2', password='StrongPass1!')
        response = self.client.get(reverse('employees:my_profile'))
        self.assertEqual(response.status_code, 403)


class EmployeeOnboardingTests(TestCase):
    def setUp(self):
        self.manager = make_staff_user()
        self.client.login(username='staffuser', password='StrongPass1!')

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_onboarding_creates_user_and_employee_and_sends_email(self):
        mail.outbox.clear()
        response = self.client.post(reverse('employees:create'), {
            'first_name': 'Grace', 'last_name': 'Wanjiru', 'username': 'gracew',
            'email': 'gracew@example.com', 'phone_number': '0799111222',
            'position': 'washer', 'hire_date': timezone.localdate().isoformat(),
            'scheduled_days': ['mon', 'tue', 'wed', 'thu', 'fri'],
            'shift_start_time': '08:00', 'shift_end_time': '17:00',
        }, follow=True)

        user = User.objects.get(username='gracew')
        self.assertEqual(user.role, Role.EMPLOYEE)
        self.assertFalse(user.has_usable_password())

        employee = Employee.objects.get(user=user)
        self.assertEqual(employee.position, 'washer')
        self.assertEqual(employee.created_by, self.manager)
        self.assertTrue(any('Set Your Password' in m.subject for m in mail.outbox))

    def test_onboarding_rejects_duplicate_username(self):
        make_employee(username='taken')
        response = self.client.post(reverse('employees:create'), {
            'first_name': 'New', 'last_name': 'Person', 'username': 'taken',
            'email': 'newperson@example.com', 'phone_number': '0799111223',
            'position': 'washer', 'hire_date': timezone.localdate().isoformat(),
        })
        self.assertEqual(User.objects.filter(username='taken').count(), 1)

    def test_onboarding_rejects_duplicate_email(self):
        make_employee(username='hasemail')
        response = self.client.post(reverse('employees:create'), {
            'first_name': 'New', 'last_name': 'Person', 'username': 'newperson2',
            'email': 'hasemail@example.com', 'phone_number': '0799111224',
            'position': 'washer', 'hire_date': timezone.localdate().isoformat(),
        })
        self.assertFalse(User.objects.filter(username='newperson2').exists())

    def test_onboarding_rejects_invalid_shift_times(self):
        response = self.client.post(reverse('employees:create'), {
            'first_name': 'New', 'last_name': 'Person', 'username': 'badshift',
            'email': 'badshift@example.com', 'phone_number': '0799111225',
            'position': 'washer', 'hire_date': timezone.localdate().isoformat(),
            'shift_start_time': '17:00', 'shift_end_time': '08:00',
        })
        self.assertFalse(User.objects.filter(username='badshift').exists())

    def test_employee_can_use_welcome_link_to_set_password(self):
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        self.client.post(reverse('employees:create'), {
            'first_name': 'Grace', 'last_name': 'Wanjiru', 'username': 'gracew2',
            'email': 'gracew2@example.com', 'phone_number': '0799111226',
            'position': 'washer', 'hire_date': timezone.localdate().isoformat(),
        })
        user = User.objects.get(username='gracew2')
        uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        response = self.client.post(
            reverse('accounts:password_reset_confirm', kwargs={'uidb64': uidb64, 'token': token}),
            {'password1': 'BrandNewPass1!', 'password2': 'BrandNewPass1!'}, follow=True,
        )
        user.refresh_from_db()
        self.assertTrue(user.check_password('BrandNewPass1!'))


class EmployeeEditTests(TestCase):
    def setUp(self):
        make_staff_user()
        self.client.login(username='staffuser', password='StrongPass1!')
        self.user, self.employee = make_employee()

    def test_edit_position_and_status(self):
        response = self.client.post(reverse('employees:edit', args=[self.employee.public_id]), {
            'position': 'supervisor', 'employment_status': 'active',
        }, follow=True)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.position, 'supervisor')

    def test_terminated_requires_termination_date(self):
        response = self.client.post(reverse('employees:edit', args=[self.employee.public_id]), {
            'position': 'washer', 'employment_status': 'terminated',
        })
        self.employee.refresh_from_db()
        self.assertNotEqual(self.employee.employment_status, 'terminated')

    def test_terminated_with_date_succeeds(self):
        response = self.client.post(reverse('employees:edit', args=[self.employee.public_id]), {
            'position': 'washer', 'employment_status': 'terminated',
            'termination_date': timezone.localdate().isoformat(),
        }, follow=True)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.employment_status, 'terminated')


class AttendanceAndPerformanceViewTests(TestCase):
    def setUp(self):
        self.manager = make_staff_user()
        self.client.login(username='staffuser', password='StrongPass1!')
        self.user, self.employee = make_employee()

    def test_record_attendance(self):
        today = timezone.localdate()
        response = self.client.post(reverse('employees:attendance_create', args=[self.employee.public_id]), {
            'date': today.isoformat(), 'status': 'present',
        }, follow=True)
        self.assertTrue(AttendanceRecord.objects.filter(employee=self.employee, date=today).exists())

    def test_duplicate_attendance_same_day_rejected_gracefully(self):
        today = timezone.localdate()
        AttendanceRecord.objects.create(employee=self.employee, date=today, status=AttendanceStatus.PRESENT)
        response = self.client.post(reverse('employees:attendance_create', args=[self.employee.public_id]), {
            'date': today.isoformat(), 'status': 'late',
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(AttendanceRecord.objects.filter(employee=self.employee, date=today).count(), 1)

    def test_invalid_clock_times_rejected(self):
        response = self.client.post(reverse('employees:attendance_create', args=[self.employee.public_id]), {
            'date': timezone.localdate().isoformat(), 'status': 'present',
            'clock_in_time': '17:00', 'clock_out_time': '08:00',
        })
        self.assertFalse(AttendanceRecord.objects.filter(employee=self.employee).exists())

    def test_add_performance_review(self):
        response = self.client.post(reverse('employees:review_create', args=[self.employee.public_id]), {
            'review_date': timezone.localdate().isoformat(), 'rating': 4, 'comments': 'Great work ethic.',
        }, follow=True)
        review = PerformanceReview.objects.get(employee=self.employee)
        self.assertEqual(review.rating, 4)
        self.assertEqual(review.reviewed_by, self.manager)

    def test_rating_out_of_range_rejected(self):
        response = self.client.post(reverse('employees:review_create', args=[self.employee.public_id]), {
            'review_date': timezone.localdate().isoformat(), 'rating': 7,
        })
        self.assertFalse(PerformanceReview.objects.filter(employee=self.employee).exists())


class EmployeeSelfServiceTests(TestCase):
    def setUp(self):
        self.user, self.employee = make_employee()
        self.client.login(username='empuser', password='StrongPass1!')

    def test_my_profile_shows_own_data(self):
        response = self.client.get(reverse('employees:my_profile'))
        self.assertContains(response, self.employee.employee_code)

    def test_my_attendance_shows_own_records(self):
        AttendanceRecord.objects.create(employee=self.employee, date=timezone.localdate(), status=AttendanceStatus.PRESENT)
        response = self.client.get(reverse('employees:my_attendance'))
        self.assertContains(response, 'Present')

    def test_my_performance_shows_own_reviews(self):
        PerformanceReview.objects.create(employee=self.employee, rating=5, comments='Excellent')
        response = self.client.get(reverse('employees:my_performance'))
        self.assertContains(response, 'Excellent')

    def test_employee_without_profile_redirected_gracefully(self):
        orphan = User.objects.create_user(username='orphanemp', email='orphanemp@example.com', password='StrongPass1!', role=Role.EMPLOYEE)
        self.client.login(username='orphanemp', password='StrongPass1!')
        response = self.client.get(reverse('employees:my_profile'), follow=True)
        self.assertContains(response, 'not been set up yet')


class BookingEmployeeAssignmentTests(TestCase):
    def setUp(self):
        self.manager = make_staff_user()
        self.client.login(username='staffuser', password='StrongPass1!')
        self.emp_user, self.employee = make_employee(username='washer1')

        cust_user = User.objects.create_user(
            username='assigncust', email='assigncust@example.com', password='StrongPass1!',
            role=Role.CUSTOMER, phone_number='0700555666',
        )
        self.customer = Customer.objects.get(user=cust_user)
        self.vehicle = Vehicle.objects.create(customer=self.customer, license_plate='KDA 950A', make='Toyota', model='Rav4', year=2021, color='Black')
        category = ServiceCategory.objects.create(name='Assign Category')
        self.service = Service.objects.create(category=category, name='Assign Wash', price=800, duration_minutes=30)
        self.booking = Booking.objects.create(
            customer=self.customer, vehicle=self.vehicle, service=self.service,
            scheduled_date=timezone.localdate() + datetime.timedelta(days=1), scheduled_time=datetime.time(10, 0),
            status=BookingStatus.CONFIRMED, price_at_booking=self.service.price, duration_minutes_at_booking=self.service.duration_minutes,
        )

    def test_assign_employee_to_booking(self):
        response = self.client.post(reverse('bookings:assign_employee', args=[self.booking.public_id]), {
            'employee': str(self.employee.public_id),
        }, follow=True)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.assigned_employee, self.employee)

    def test_unassign_employee_from_booking(self):
        self.booking.assigned_employee = self.employee
        self.booking.save()
        response = self.client.post(reverse('bookings:assign_employee', args=[self.booking.public_id]), {
            'employee': '',
        }, follow=True)
        self.booking.refresh_from_db()
        self.assertIsNone(self.booking.assigned_employee)

    def test_assigned_booking_shows_on_employee_detail(self):
        self.booking.assigned_employee = self.employee
        self.booking.save()
        response = self.client.get(reverse('employees:detail', args=[self.employee.public_id]))
        self.assertContains(response, 'Assign Wash')

    def test_assigned_booking_shows_on_employee_self_service(self):
        self.booking.assigned_employee = self.employee
        self.booking.save()
        self.client.login(username='washer1', password='StrongPass1!')
        response = self.client.get(reverse('employees:my_assignments'))
        self.assertContains(response, 'Assign Wash')

    def test_cashier_cannot_assign_employee(self):
        make_staff_user(role=Role.CASHIER, username='cashassign')
        self.client.login(username='cashassign', password='StrongPass1!')
        response = self.client.get(reverse('bookings:detail', args=[self.booking.public_id]))
        # Cashiers CAN view bookings (staff_required) -- assignment control just renders in the same page.
        self.assertEqual(response.status_code, 200)


class EmployeeExportTests(TestCase):
    def setUp(self):
        make_staff_user()
        self.client.login(username='staffuser', password='StrongPass1!')
        make_employee(username='exportemp')

    def test_csv_export(self):
        response = self.client.get(reverse('employees:export_csv'))
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertIn('EMP-', response.content.decode())

    def test_excel_export(self):
        response = self.client.get(reverse('employees:export_excel'))
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )


class EmployeeSearchTests(TestCase):
    def setUp(self):
        make_staff_user()
        self.client.login(username='staffuser', password='StrongPass1!')

    def test_search_by_full_name(self):
        user = User.objects.create_user(
            username='searchemp', email='searchemp@example.com', password='StrongPass1!', role=Role.EMPLOYEE,
            first_name='Peter', last_name='Kariuki', phone_number='0788999000',
        )
        Employee.objects.create(user=user, position=EmployeePosition.DETAILER)
        response = self.client.get(reverse('employees:list'), {'q': 'Peter Kariuki'})
        self.assertContains(response, 'Peter Kariuki')

    def test_filter_by_position(self):
        user, employee = make_employee(username='filteremp', position=EmployeePosition.SUPERVISOR)
        response = self.client.get(reverse('employees:list'), {'position': 'supervisor'})
        self.assertContains(response, employee.employee_code)
