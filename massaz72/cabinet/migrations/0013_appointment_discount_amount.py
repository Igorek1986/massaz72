from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cabinet', '0012_appointment_discount_percent'),
    ]

    operations = [
        migrations.AddField(
            model_name='appointment',
            name='discount_amount',
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=10,
                null=True, verbose_name='Скидка (₽)',
            ),
        ),
    ]
