from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='productcategory',
            name='description',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='productcategory',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, null=True),
        ),
        migrations.CreateModel(
            name='MedicineForm',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120, unique=True)),
                ('description', models.CharField(blank=True, max_length=512, null=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={},
        ),
        migrations.CreateModel(
            name='Uom',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120, unique=True)),
                ('description', models.CharField(blank=True, max_length=512, null=True)),
                ('uom_type', models.CharField(choices=[('BASE', 'BASE'), ('PACK', 'PACK'), ('BOTH', 'BOTH')], default='BOTH', max_length=8)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={},
        ),
        migrations.AddIndex(
            model_name='medicineform',
            index=models.Index(fields=['name'], name='idx_form_name'),
        ),
        migrations.AddIndex(
            model_name='medicineform',
            index=models.Index(fields=['is_active'], name='idx_form_active'),
        ),
        migrations.AddIndex(
            model_name='uom',
            index=models.Index(fields=['name'], name='idx_uom_name'),
        ),
        migrations.AddIndex(
            model_name='uom',
            index=models.Index(fields=['is_active'], name='idx_uom_active'),
        ),
    ]
