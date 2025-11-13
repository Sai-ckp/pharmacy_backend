from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('settingsx', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='PaymentMethod',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120, unique=True)),
                ('description', models.CharField(blank=True, max_length=512, null=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name='PaymentTerm',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120, unique=True)),
                ('days', models.PositiveIntegerField(default=0)),
                ('description', models.CharField(blank=True, max_length=512, null=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.AddIndex(
            model_name='paymentmethod',
            index=models.Index(fields=['name'], name='idx_paymethod_name'),
        ),
        migrations.AddIndex(
            model_name='paymentmethod',
            index=models.Index(fields=['is_active'], name='idx_paymethod_active'),
        ),
        migrations.AddIndex(
            model_name='paymentterm',
            index=models.Index(fields=['name'], name='idx_payterm_name'),
        ),
        migrations.AddIndex(
            model_name='paymentterm',
            index=models.Index(fields=['is_active'], name='idx_payterm_active'),
        ),
    ]

