import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cabinet', '0005_specialist'),
    ]

    operations = [
        # WorkSchedule: OneToOneField (unique FK)
        migrations.AddField(
            model_name='workschedule',
            name='specialist',
            field=models.OneToOneField(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='schedule',
                to='cabinet.specialist',
                verbose_name='Специалист',
            ),
        ),
        # ScheduleException
        migrations.AddField(
            model_name='scheduleexception',
            name='specialist',
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='exceptions',
                to='cabinet.specialist',
                verbose_name='Специалист',
            ),
        ),
        # BlockedSlot
        migrations.AddField(
            model_name='blockedslot',
            name='specialist',
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='blocked_slots',
                to='cabinet.specialist',
                verbose_name='Специалист',
            ),
        ),
        # AppointmentSeries
        migrations.AddField(
            model_name='appointmentseries',
            name='specialist',
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='series',
                to='cabinet.specialist',
                verbose_name='Специалист',
            ),
        ),
        # Appointment
        migrations.AddField(
            model_name='appointment',
            name='specialist',
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='appointments',
                to='cabinet.specialist',
                verbose_name='Специалист',
            ),
        ),
        # Discount
        migrations.AddField(
            model_name='discount',
            name='specialist',
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='discounts',
                to='cabinet.specialist',
                verbose_name='Специалист',
            ),
        ),
    ]
