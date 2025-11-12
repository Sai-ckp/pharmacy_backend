from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0003_masters_models'),
        ('procurement', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='VendorProductCode',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('vendor_code', models.CharField(max_length=120)),
                ('vendor_name_alias', models.CharField(blank=True, max_length=200, null=True)),
                ('product', models.ForeignKey(on_delete=models.deletion.CASCADE, to='catalog.product')),
                ('vendor', models.ForeignKey(on_delete=models.deletion.CASCADE, to='procurement.vendor')),
            ],
        ),
        migrations.AddConstraint(
            model_name='vendorproductcode',
            constraint=models.UniqueConstraint(fields=('vendor', 'vendor_code'), name='uq_vendor_code'),
        ),
    ]

