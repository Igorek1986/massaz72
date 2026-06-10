import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cabinet', '0010_travel_massage_break'),
    ]

    operations = [
        migrations.AddField(
            model_name='appointment',
            name='parent',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='additional_services',
                to='cabinet.appointment',
                verbose_name='Основная запись',
            ),
        ),
        migrations.AddField(
            model_name='appointment',
            name='discount',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='appointments',
                to='cabinet.discount',
                verbose_name='Скидка',
            ),
        ),
    ]
