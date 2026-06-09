import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cabinet', '0007_populate_specialists'),
    ]

    operations = [
        migrations.AlterField(
            model_name='workschedule',
            name='specialist',
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='schedule',
                to='cabinet.specialist',
                verbose_name='Специалист',
            ),
        ),
        migrations.AlterField(
            model_name='scheduleexception',
            name='specialist',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='exceptions',
                to='cabinet.specialist',
                verbose_name='Специалист',
            ),
        ),
        migrations.AlterField(
            model_name='blockedslot',
            name='specialist',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='blocked_slots',
                to='cabinet.specialist',
                verbose_name='Специалист',
            ),
        ),
        migrations.AlterField(
            model_name='appointmentseries',
            name='specialist',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='series',
                to='cabinet.specialist',
                verbose_name='Специалист',
            ),
        ),
        migrations.AlterField(
            model_name='appointment',
            name='specialist',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='appointments',
                to='cabinet.specialist',
                verbose_name='Специалист',
            ),
        ),
        migrations.AlterField(
            model_name='discount',
            name='specialist',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='discounts',
                to='cabinet.specialist',
                verbose_name='Специалист',
            ),
        ),
    ]
