from django.db import migrations

ROLE_GROUP_NAMES = [
    'Super Admin',
    'Manager',
    'Cashier',
    'Employee',
    'Customer',
]


def create_groups(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    for name in ROLE_GROUP_NAMES:
        Group.objects.get_or_create(name=name)


def delete_groups(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Group.objects.filter(name__in=ROLE_GROUP_NAMES).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.RunPython(create_groups, reverse_code=delete_groups),
    ]
