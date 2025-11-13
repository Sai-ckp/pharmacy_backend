from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='RackLocation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120, unique=True)),
                ('description', models.CharField(blank=True, max_length=512, null=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.AddIndex(
            model_name='racklocation',
            index=models.Index(fields=['name'], name='idx_rackloc_name'),
        ),
        migrations.AddIndex(
            model_name='racklocation',
            index=models.Index(fields=['is_active'], name='idx_rackloc_active'),
        ),
    ]

