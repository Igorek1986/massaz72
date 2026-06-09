from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cabinet', '0003_appointment_transport_cost'),
    ]

    operations = [
        migrations.AddField(
            model_name='workschedule',
            name='break_between_minutes',
            field=models.PositiveIntegerField(default=15, verbose_name='Перерыв между массажами (мин)'),
        ),
    ]
