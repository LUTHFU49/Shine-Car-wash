from django.contrib.auth.models import Group, Permission
from django.test import TestCase

from apps.audit_logs.models import AuditLog

from .models import Role, User, UserSession
from .validators import ComplexPasswordValidator
from django.core.exceptions import ValidationError


class UserModelTests(TestCase):
    def test_create_user_defaults_to_customer_role(self):
        user = User.objects.create_user(username='jane', email='jane@example.com', password='StrongPass1!')
        self.assertEqual(user.role, Role.CUSTOMER)
        self.assertFalse(user.is_email_verified)

    def test_email_must_be_unique(self):
        User.objects.create_user(username='jane', email='jane@example.com', password='StrongPass1!')
        with self.assertRaises(Exception):
            User.objects.create_user(username='jane2', email='jane@example.com', password='StrongPass1!')

    def test_initials_property(self):
        user = User.objects.create_user(
            username='jdoe', email='jdoe@example.com', password='StrongPass1!',
            first_name='Jane', last_name='Doe',
        )
        self.assertEqual(user.initials, 'JD')

    def test_is_locked_out_false_by_default(self):
        user = User.objects.create_user(username='jane', email='jane@example.com', password='StrongPass1!')
        self.assertFalse(user.is_locked_out)


class RoleGroupMigrationTests(TestCase):
    def test_all_role_groups_exist(self):
        expected = {'Super Admin', 'Manager', 'Cashier', 'Employee', 'Customer'}
        actual = set(Group.objects.filter(name__in=expected).values_list('name', flat=True))
        self.assertEqual(expected, actual)


class ComplexPasswordValidatorTests(TestCase):
    def setUp(self):
        self.validator = ComplexPasswordValidator()

    def test_valid_password_passes(self):
        self.validator.validate('StrongPass1!')  # should not raise

    def test_missing_uppercase_fails(self):
        with self.assertRaises(ValidationError):
            self.validator.validate('weakpass1!')

    def test_missing_special_char_fails(self):
        with self.assertRaises(ValidationError):
            self.validator.validate('WeakPass1')

    def test_missing_digit_fails(self):
        with self.assertRaises(ValidationError):
            self.validator.validate('WeakPass!')


class EmailOrUsernameBackendTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='jane', email='jane@example.com', password='StrongPass1!')

    def test_authenticate_with_username(self):
        from django.contrib.auth import authenticate
        user = authenticate(username='jane', password='StrongPass1!')
        self.assertEqual(user, self.user)

    def test_authenticate_with_email(self):
        from django.contrib.auth import authenticate
        user = authenticate(username='jane@example.com', password='StrongPass1!')
        self.assertEqual(user, self.user)

    def test_authenticate_with_wrong_password_fails(self):
        from django.contrib.auth import authenticate
        user = authenticate(username='jane', password='WrongPassword1!')
        self.assertIsNone(user)


# ============================================================
# PHASE 2: Registration, Login, Password Reset, Verification, Profile
# ============================================================

from django.core import mail
from django.urls import reverse

from .models import EmailVerificationToken, LoginAuditEntry


class RegistrationViewTests(TestCase):
    def setUp(self):
        self.url = reverse('accounts:register')
        self.valid_data = {
            'first_name': 'Jane',
            'last_name': 'Doe',
            'username': 'janedoe',
            'email': 'jane@example.com',
            'phone_number': '0712345678',
            'password1': 'StrongPass1!',
            'password2': 'StrongPass1!',
            'agree_to_terms': 'on',
        }

    def test_valid_registration_creates_user_in_customer_role(self):
        response = self.client.post(self.url, self.valid_data, follow=True)
        self.assertEqual(response.status_code, 200)
        user = User.objects.get(username='janedoe')
        self.assertEqual(user.role, Role.CUSTOMER)
        self.assertTrue(user.groups.filter(name='Customer').exists())

    def test_registration_sends_welcome_and_verification_emails(self):
        self.client.post(self.url, self.valid_data)
        self.assertEqual(len(mail.outbox), 2)
        subjects = [m.subject for m in mail.outbox]
        self.assertTrue(any('Welcome' in s for s in subjects))
        self.assertTrue(any('Verify' in s for s in subjects))

    def test_registration_creates_verification_token(self):
        self.client.post(self.url, self.valid_data)
        user = User.objects.get(username='janedoe')
        self.assertTrue(EmailVerificationToken.objects.filter(user=user).exists())

    def test_duplicate_email_rejected(self):
        User.objects.create_user(username='existing', email='jane@example.com', password='StrongPass1!')
        response = self.client.post(self.url, self.valid_data)
        self.assertEqual(response.status_code, 200)  # re-renders form with errors
        self.assertFalse(User.objects.filter(username='janedoe').exists())

    def test_mismatched_passwords_rejected(self):
        data = {**self.valid_data, 'password2': 'Different1!'}
        response = self.client.post(self.url, data)
        self.assertFalse(User.objects.filter(username='janedoe').exists())

    def test_weak_password_rejected(self):
        data = {**self.valid_data, 'password1': 'weakpass', 'password2': 'weakpass'}
        response = self.client.post(self.url, data)
        self.assertFalse(User.objects.filter(username='janedoe').exists())

    def test_invalid_name_characters_rejected(self):
        data = {**self.valid_data, 'first_name': 'Jane123'}
        response = self.client.post(self.url, data)
        self.assertFalse(User.objects.filter(username='janedoe').exists())

    def test_must_agree_to_terms(self):
        data = {**self.valid_data}
        del data['agree_to_terms']
        response = self.client.post(self.url, data)
        self.assertFalse(User.objects.filter(username='janedoe').exists())


class LoginViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='janedoe', email='jane@example.com', password='StrongPass1!',
        )
        self.url = reverse('accounts:login')

    def test_valid_login_succeeds(self):
        response = self.client.post(self.url, {'username': 'janedoe', 'password': 'StrongPass1!'}, follow=True)
        self.assertTrue(response.context['user'].is_authenticated)

    def test_login_with_email_succeeds(self):
        response = self.client.post(self.url, {'username': 'jane@example.com', 'password': 'StrongPass1!'}, follow=True)
        self.assertTrue(response.context['user'].is_authenticated)

    def test_invalid_password_fails(self):
        response = self.client.post(self.url, {'username': 'janedoe', 'password': 'WrongPass1!'})
        self.assertFalse(response.context['user'].is_authenticated)

    def test_account_locks_after_max_failed_attempts(self):
        from django.conf import settings
        for _ in range(settings.ACCOUNT_LOCKOUT_ATTEMPTS):
            self.client.post(self.url, {'username': 'janedoe', 'password': 'WrongPass1!'})

        self.user.refresh_from_db()
        self.assertTrue(self.user.is_locked_out)

        # Even correct password now fails while locked
        response = self.client.post(self.url, {'username': 'janedoe', 'password': 'StrongPass1!'})
        self.assertFalse(response.context['user'].is_authenticated)

    def test_deactivated_account_cannot_log_in(self):
        self.user.is_deactivated = True
        self.user.is_active = False
        self.user.save()
        response = self.client.post(self.url, {'username': 'janedoe', 'password': 'StrongPass1!'})
        self.assertFalse(response.context['user'].is_authenticated)
        # Must show the specific "deactivated" message, not a generic
        # "incorrect password" -- Django's ModelBackend rejects
        # is_active=False users internally, so this message has to be
        # produced by our own pre-authenticate() check, not a post-auth one.
        messages_shown = [str(m) for m in response.context['messages']]
        self.assertTrue(any('deactivated' in m.lower() for m in messages_shown))
        self.assertTrue(
            LoginAuditEntry.objects.filter(user=self.user, reason='account_deactivated').exists()
        )

    def test_login_creates_audit_entry(self):
        self.client.post(self.url, {'username': 'janedoe', 'password': 'StrongPass1!'})
        self.assertTrue(LoginAuditEntry.objects.filter(user=self.user, was_successful=True).exists())


class LogoutViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='janedoe', email='jane@example.com', password='StrongPass1!')

    def test_logout_requires_post(self):
        self.client.login(username='janedoe', password='StrongPass1!')
        response = self.client.get(reverse('accounts:logout'))
        self.assertEqual(response.status_code, 405)

    def test_logout_logs_user_out(self):
        self.client.login(username='janedoe', password='StrongPass1!')
        response = self.client.post(reverse('accounts:logout'), follow=True)
        self.assertFalse(response.context['user'].is_authenticated)


class PasswordResetFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='janedoe', email='jane@example.com', password='OldPass1!')
        mail.outbox = []

    def test_forgot_password_with_existing_email_sends_email(self):
        self.client.post(reverse('accounts:password_reset'), {'email': 'jane@example.com'})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Reset', mail.outbox[0].subject)

    def test_forgot_password_with_nonexistent_email_sends_nothing_but_same_message(self):
        response = self.client.post(reverse('accounts:password_reset'), {'email': 'nobody@example.com'}, follow=True)
        self.assertEqual(len(mail.outbox), 0)
        messages = list(response.context['messages'])
        self.assertTrue(any('password reset link has been sent' in str(m) for m in messages))

    def test_full_reset_flow_with_valid_token(self):
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        url = reverse('accounts:password_reset_confirm', kwargs={'uidb64': uidb64, 'token': token})

        response = self.client.post(url, {'password1': 'BrandNewPass1!', 'password2': 'BrandNewPass1!'}, follow=True)
        self.assertEqual(response.status_code, 200)

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('BrandNewPass1!'))

    def test_invalid_token_shows_invalid_page(self):
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))
        url = reverse('accounts:password_reset_confirm', kwargs={'uidb64': uidb64, 'token': 'bad-token'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 400)


class EmailVerificationTests(TestCase):
    def setUp(self):
        mail.outbox = []
        self.user = User.objects.create_user(username='janedoe', email='jane@example.com', password='StrongPass1!')
        self.token = EmailVerificationToken.objects.get(user=self.user)

    def test_valid_token_verifies_email(self):
        url = reverse('accounts:verify_email', kwargs={'token': str(self.token.token)})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_email_verified)

    def test_expired_token_does_not_verify(self):
        from django.utils import timezone
        from datetime import timedelta
        self.token.expires_at = timezone.now() - timedelta(hours=1)
        self.token.save()
        url = reverse('accounts:verify_email', kwargs={'token': str(self.token.token)})
        response = self.client.get(url)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_email_verified)

    def test_resend_verification_requires_login(self):
        response = self.client.get(reverse('accounts:resend_verification'))
        self.assertEqual(response.status_code, 302)  # redirected to login


class ProfileViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='janedoe', email='jane@example.com', password='StrongPass1!',
            first_name='Jane', last_name='Doe',
        )
        self.client.login(username='janedoe', password='StrongPass1!')

    def test_profile_page_loads(self):
        response = self.client.get(reverse('accounts:profile'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Jane')

    def test_profile_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse('accounts:profile'))
        self.assertEqual(response.status_code, 302)

    def test_profile_edit_updates_fields(self):
        response = self.client.post(reverse('accounts:profile_edit'), {
            'first_name': 'Janet', 'last_name': 'Doe', 'phone_number': '0798765432',
        }, follow=True)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Janet')

    def test_profile_edit_rejects_invalid_name(self):
        response = self.client.post(reverse('accounts:profile_edit'), {
            'first_name': 'Jane123', 'last_name': 'Doe', 'phone_number': '0798765432',
        })
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Jane')  # unchanged


class ChangePasswordViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='janedoe', email='jane@example.com', password='OldPass1!')
        self.client.login(username='janedoe', password='OldPass1!')

    def test_change_password_success(self):
        response = self.client.post(reverse('accounts:change_password'), {
            'old_password': 'OldPass1!', 'new_password1': 'NewPass1!', 'new_password2': 'NewPass1!',
        }, follow=True)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NewPass1!'))

    def test_change_password_wrong_old_password_fails(self):
        response = self.client.post(reverse('accounts:change_password'), {
            'old_password': 'WrongOld1!', 'new_password1': 'NewPass1!', 'new_password2': 'NewPass1!',
        })
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('OldPass1!'))

    def test_change_password_same_as_old_rejected(self):
        response = self.client.post(reverse('accounts:change_password'), {
            'old_password': 'OldPass1!', 'new_password1': 'OldPass1!', 'new_password2': 'OldPass1!',
        })
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('OldPass1!'))

    def test_stays_logged_in_after_password_change(self):
        response = self.client.post(reverse('accounts:change_password'), {
            'old_password': 'OldPass1!', 'new_password1': 'NewPass1!', 'new_password2': 'NewPass1!',
        }, follow=True)
        self.assertTrue(response.context['user'].is_authenticated)


class AccountDeletionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='janedoe', email='jane@example.com', password='StrongPass1!')
        self.client.login(username='janedoe', password='StrongPass1!')

    def test_deletion_requires_correct_password(self):
        response = self.client.post(reverse('accounts:delete_account'), {
            'password': 'WrongPass1!', 'confirm': 'on',
        })
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_deactivated)

    def test_deletion_deactivates_account(self):
        response = self.client.post(reverse('accounts:delete_account'), {
            'password': 'StrongPass1!', 'confirm': 'on',
        }, follow=True)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_deactivated)
        self.assertFalse(self.user.is_active)

    def test_deactivated_user_logged_out(self):
        response = self.client.post(reverse('accounts:delete_account'), {
            'password': 'StrongPass1!', 'confirm': 'on',
        }, follow=True)
        self.assertFalse(response.context['user'].is_authenticated)


class ProfilePhotoTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='janedoe', email='jane@example.com', password='StrongPass1!')
        self.client.login(username='janedoe', password='StrongPass1!')

    def test_upload_valid_image(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image
        import io

        img = Image.new('RGB', (100, 100), color='blue')
        buf = io.BytesIO()
        img.save(buf, format='JPEG')
        buf.seek(0)
        upload = SimpleUploadedFile('test.jpg', buf.read(), content_type='image/jpeg')

        response = self.client.post(reverse('accounts:profile_photo_upload'), {'profile_photo': upload})
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(bool(self.user.profile_photo))

    def test_upload_rejects_non_image_file(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        upload = SimpleUploadedFile('test.txt', b'not an image', content_type='text/plain')
        response = self.client.post(reverse('accounts:profile_photo_upload'), {'profile_photo': upload})
        self.assertEqual(response.status_code, 400)

    def test_remove_photo(self):
        response = self.client.post(reverse('accounts:profile_photo_remove'))
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertFalse(bool(self.user.profile_photo))


class AdminAuditLoggingTests(TestCase):
    """
    Phase 15: admin-driven user/permission changes must produce
    structured AuditLog entries with before/after values, not just
    the generic 'POST /admin/...' safety-net entry.
    """
    def setUp(self):
        self.admin = User.objects.create_superuser(username='root', email='root@example.com', password='RootPass1!@#')
        self.client.login(username='root', password='RootPass1!@#')
        self.target = User.objects.create_user(username='bob', email='bob@example.com', password='BobPass1!@#', role=Role.EMPLOYEE)

    def test_creating_user_via_admin_logs_create(self):
        self.client.post('/admin/accounts/user/add/', {
            'username': 'newstaff', 'password1': 'NewStaffPass1!@#', 'password2': 'NewStaffPass1!@#',
        })
        entry = AuditLog.objects.filter(model_name='User', action=AuditLog.Action.CREATE, description__icontains='newstaff').first()
        self.assertIsNotNone(entry)

    def test_changing_role_via_admin_logs_before_after(self):
        user = User.objects.get(pk=self.target.pk)
        data = {
            'username': user.username, 'email': user.email, 'role': Role.MANAGER,
            'is_active': 'on', 'date_joined_0': '2026-01-01', 'date_joined_1': '00:00:00',
        }
        response = self.client.post(f'/admin/accounts/user/{user.pk}/change/', data, follow=True)
        self.assertEqual(response.status_code, 200)
        entry = AuditLog.objects.filter(model_name='User', object_id=str(user.pk), action=AuditLog.Action.UPDATE).order_by('-created_at').first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.metadata['before']['role'], Role.EMPLOYEE)
        self.assertEqual(entry.metadata['after']['role'], Role.MANAGER)

    def test_deleting_user_via_admin_logs_delete(self):
        target_id = self.target.pk
        target_username = self.target.username
        self.client.post(f'/admin/accounts/user/{target_id}/delete/', {'post': 'yes'})
        entry = AuditLog.objects.filter(model_name='User', object_id=str(target_id), action=AuditLog.Action.DELETE).first()
        self.assertIsNotNone(entry)
        self.assertIn(target_username, entry.description)

    def test_group_permission_change_is_logged(self):
        group = Group.objects.create(name='Test Cashiers')
        perm = Permission.objects.filter(codename__startswith='view_').first()
        response = self.client.post(f'/admin/auth/group/{group.pk}/change/', {
            'name': 'Test Cashiers', 'permissions': [str(perm.pk)],
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        entry = AuditLog.objects.filter(model_name='Group', object_id=str(group.pk), action=AuditLog.Action.UPDATE).first()
        self.assertIsNotNone(entry)
        self.assertIn(perm.codename, entry.metadata['permissions_after'])


class SessionSecurityTests(TestCase):
    """Phase 15: sliding inactivity timeout + active-session tracking."""

    def setUp(self):
        self.user = User.objects.create_user(username='sess', email='sess@example.com', password='SessPass1!@#')

    def test_login_creates_user_session_row(self):
        self.client.login(username='sess', password='SessPass1!@#')
        self.client.get('/accounts/profile/')  # any authenticated request touches the session
        self.assertTrue(UserSession.objects.filter(user=self.user).exists())

    def test_revoking_own_session_logs_out(self):
        self.client.login(username='sess', password='SessPass1!@#')
        self.client.get('/accounts/profile/')
        session_row = UserSession.objects.get(user=self.user)
        self.client.post(f'/accounts/sessions/{session_row.pk}/revoke/')
        response = self.client.get('/accounts/profile/')
        self.assertNotEqual(response.status_code, 200)  # redirected to login, no longer authenticated

    def test_password_change_revokes_other_sessions(self):
        self.client.login(username='sess', password='SessPass1!@#')
        self.client.get('/accounts/profile/')

        other_client = self.client_class()
        other_client.login(username='sess', password='SessPass1!@#')
        other_client.get('/accounts/profile/')

        self.assertEqual(UserSession.objects.filter(user=self.user).count(), 2)

        self.client.post('/accounts/profile/change-password/', {
            'old_password': 'SessPass1!@#', 'new_password1': 'NewSessPass1!@#', 'new_password2': 'NewSessPass1!@#',
        })

        # The other device's session should now be gone.
        self.assertEqual(UserSession.objects.filter(user=self.user).count(), 1)
        response = other_client.get('/accounts/profile/')
        self.assertNotEqual(response.status_code, 200)


class PasswordHistoryTests(TestCase):
    """Phase 15: password reuse prevention."""

    def setUp(self):
        self.user = User.objects.create_user(username='reuser', email='reuser@example.com', password='FirstPass1!@#')
        self.client.login(username='reuser', password='FirstPass1!@#')

    def _change_password(self, old, new):
        return self.client.post(reverse('accounts:change_password'), {
            'old_password': old, 'new_password1': new, 'new_password2': new,
        })

    def test_cannot_reuse_current_password(self):
        response = self._change_password('FirstPass1!@#', 'FirstPass1!@#')
        self.assertContains(response, "can&#x27;t reuse your current password", status_code=200)

    def test_cannot_reuse_a_recent_password(self):
        self._change_password('FirstPass1!@#', 'SecondPass1!@#')
        self.user.refresh_from_db()
        self.client.login(username='reuser', password='SecondPass1!@#')

        response = self._change_password('SecondPass1!@#', 'FirstPass1!@#')
        self.assertContains(response, "can&#x27;t reuse one of your last", status_code=200)

    def test_can_change_to_a_genuinely_new_password(self):
        response = self._change_password('FirstPass1!@#', 'BrandNewPass1!@#')
        self.assertRedirects(response, reverse('accounts:profile'))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('BrandNewPass1!@#'))

    def test_history_is_pruned_to_configured_count(self):
        from django.test import override_settings
        from .models import PasswordHistory

        with override_settings(PASSWORD_HISTORY_COUNT=2):
            passwords = ['FirstPass1!@#', 'P2Pass1!@#', 'P3Pass1!@#', 'P4Pass1!@#']
            current = passwords[0]
            for nxt in passwords[1:]:
                self.client.login(username='reuser', password=current)
                self._change_password(current, nxt)
                current = nxt
            self.assertLessEqual(PasswordHistory.objects.filter(user=self.user).count(), 2)


class ForcePasswordResetTests(TestCase):
    """Phase 15: admin-forced password reset on next login."""

    def setUp(self):
        self.admin = User.objects.create_superuser(username='root2', email='root2@example.com', password='RootPass1!@#')
        self.target = User.objects.create_user(username='flagged', email='flagged@example.com', password='FlaggedPass1!@#')

    def test_admin_action_sets_flag_and_revokes_sessions(self):
        self.client.login(username='flagged', password='FlaggedPass1!@#')
        self.client.get('/accounts/profile/')  # creates a UserSession row

        self.client.logout()
        self.client.login(username='root2', password='RootPass1!@#')
        self.client.post('/admin/accounts/user/', {
            'action': 'force_password_reset', '_selected_action': [str(self.target.pk)],
        })
        self.target.refresh_from_db()
        self.assertTrue(self.target.must_change_password)
        self.assertEqual(UserSession.objects.filter(user=self.target).count(), 0)

    def test_flagged_user_is_redirected_to_change_password(self):
        self.target.must_change_password = True
        self.target.save()
        self.client.login(username='flagged', password='FlaggedPass1!@#')

        response = self.client.get('/accounts/profile/')
        self.assertRedirects(response, reverse('accounts:change_password'))

    def test_changing_password_clears_the_flag(self):
        self.target.must_change_password = True
        self.target.save()
        self.client.login(username='flagged', password='FlaggedPass1!@#')

        self.client.post(reverse('accounts:change_password'), {
            'old_password': 'FlaggedPass1!@#', 'new_password1': 'BrandNewFlagPass1!@#', 'new_password2': 'BrandNewFlagPass1!@#',
        })
        self.target.refresh_from_db()
        self.assertFalse(self.target.must_change_password)

        # And now they can reach a normal page again.
        response = self.client.get('/accounts/profile/')
        self.assertEqual(response.status_code, 200)


class OpenRedirectTests(TestCase):
    """Phase 15: ?next= must never send a user off-site after login."""

    def setUp(self):
        self.user = User.objects.create_user(username='redir', email='redir@example.com', password='RedirPass1!@#')

    def test_malicious_next_is_ignored(self):
        response = self.client.post(
            f"{reverse('accounts:login')}?next=https://evil.example.com/phish",
            {'username': 'redir', 'password': 'RedirPass1!@#'},
        )
        self.assertNotIn('evil.example.com', response.url)

    def test_protocol_relative_next_is_ignored(self):
        response = self.client.post(
            f"{reverse('accounts:login')}?next=//evil.example.com/phish",
            {'username': 'redir', 'password': 'RedirPass1!@#'},
        )
        self.assertNotIn('evil.example.com', response.url)

    def test_legitimate_local_next_still_works(self):
        response = self.client.post(
            f"{reverse('accounts:login')}?next=/accounts/profile/",
            {'username': 'redir', 'password': 'RedirPass1!@#'},
        )
        self.assertEqual(response.url, '/accounts/profile/')


class NewDeviceNotificationTests(TestCase):
    """Phase 15 (optional item): notify on login from an unrecognized device."""

    def setUp(self):
        self.user = User.objects.create_user(username='devicetest', email='devicetest@example.com', password='DevicePass1!@#')

    def test_first_login_ever_does_not_send_new_device_email(self):
        from django.core import mail
        mail.outbox = []
        self.client.post(reverse('accounts:login'), {'username': 'devicetest', 'password': 'DevicePass1!@#'})
        subjects = [m.subject for m in mail.outbox]
        self.assertNotIn('New login to your account', subjects)

    def test_login_from_new_ip_after_a_known_one_sends_email(self):
        from django.core import mail

        self.client.post(reverse('accounts:login'), {'username': 'devicetest', 'password': 'DevicePass1!@#'},
                          REMOTE_ADDR='10.0.0.1')
        self.client.logout()
        mail.outbox = []

        self.client.post(reverse('accounts:login'), {'username': 'devicetest', 'password': 'DevicePass1!@#'},
                          REMOTE_ADDR='10.0.0.2')
        subjects = [m.subject for m in mail.outbox]
        self.assertTrue(any('New login to your account' in s for s in subjects))

    def test_login_from_same_ip_and_agent_again_does_not_resend(self):
        from django.core import mail

        self.client.post(reverse('accounts:login'), {'username': 'devicetest', 'password': 'DevicePass1!@#'},
                          REMOTE_ADDR='10.0.0.5')
        self.client.logout()
        mail.outbox = []

        self.client.post(reverse('accounts:login'), {'username': 'devicetest', 'password': 'DevicePass1!@#'},
                          REMOTE_ADDR='10.0.0.5')
        subjects = [m.subject for m in mail.outbox]
        self.assertNotIn('New login to your account', subjects)
