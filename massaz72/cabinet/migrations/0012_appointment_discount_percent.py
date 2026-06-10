import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cabinet', '0011_appointment_parent_discount'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='appointment',
            name='discount',
        ),
        migrations.AddField(
            model_name='appointment',
            name='discount_percent',
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=5,
                null=True, verbose_name='Скидка (%)',
            ),
        ),
    ]
