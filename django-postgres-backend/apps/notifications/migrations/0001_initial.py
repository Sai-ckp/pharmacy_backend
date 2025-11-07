from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Notification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),

                ('channel', models.CharField(choices=[('EMAIL', 'EMAIL'), ('SMS', 'SMS'), ('PUSH', 'PUSH'), ('WEBHOOK', 'WEBHOOK')], max_length=16)),
                ('to', models.CharField(max_length=1024)),
                ('subject', models.CharField(blank=True, max_length=512, null=True)),
                ('message', models.TextField()),
                ('payload', models.JSONField(blank=True, null=True)),
                ('status', models.CharField(choices=[('QUEUED', 'QUEUED'), ('SENT', 'SENT'), ('FAILED', 'FAILED')], db_index=True, default='QUEUED', max_length=16)),
                ('error', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('sent_at', models.DateTimeField(blank=True, null=True)),
            ],
        ),
    ]
