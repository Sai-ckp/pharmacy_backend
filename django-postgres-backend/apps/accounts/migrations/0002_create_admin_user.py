from django.db import migrations
from django.contrib.auth.hashers import make_password


def create_admin_user(apps, schema_editor):
    User = apps.get_model("auth", "User")
    if not User.objects.filter(username="Admin").exists():
        User.objects.create(
            username="Admin",
            email="admin@example.com",
            is_superuser=True,
            is_staff=True,
            is_active=True,
            password=make_password("admin123"),
        )


def delete_admin_user(apps, schema_editor):
    User = apps.get_model("auth", "User")
    User.objects.filter(username="Admin").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(create_admin_user, delete_admin_user),
    ]

