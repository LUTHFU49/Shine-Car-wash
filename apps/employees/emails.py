from apps.accounts.emails import send_branded_email


def send_employee_welcome_email(user, set_password_url):
    return send_branded_email(
        subject='Welcome to the Team — Set Your Password',
        template_name='employee_welcome_email.html',
        context={'user': user, 'set_password_url': set_password_url},
        to_email=user.email,
    )
