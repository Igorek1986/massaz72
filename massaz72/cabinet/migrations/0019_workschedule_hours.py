from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cabinet", "0018_specialist_can_manage_reviews_specialist_head"),
    ]

    operations = [
        migrations.AddField(
            model_name="workschedule",
            name="monday_start",
            field=models.TimeField(blank=True, null=True, verbose_name="Пн, с"),
        ),
        migrations.AddField(
            model_name="workschedule",
            name="monday_end",
            field=models.TimeField(blank=True, null=True, verbose_name="Пн, до"),
        ),
        migrations.AddField(
            model_name="workschedule",
            name="tuesday_start",
            field=models.TimeField(blank=True, null=True, verbose_name="Вт, с"),
        ),
        migrations.AddField(
            model_name="workschedule",
            name="tuesday_end",
            field=models.TimeField(blank=True, null=True, verbose_name="Вт, до"),
        ),
        migrations.AddField(
            model_name="workschedule",
            name="wednesday_start",
            field=models.TimeField(blank=True, null=True, verbose_name="Ср, с"),
        ),
        migrations.AddField(
            model_name="workschedule",
            name="wednesday_end",
            field=models.TimeField(blank=True, null=True, verbose_name="Ср, до"),
        ),
        migrations.AddField(
            model_name="workschedule",
            name="thursday_start",
            field=models.TimeField(blank=True, null=True, verbose_name="Чт, с"),
        ),
        migrations.AddField(
            model_name="workschedule",
            name="thursday_end",
            field=models.TimeField(blank=True, null=True, verbose_name="Чт, до"),
        ),
        migrations.AddField(
            model_name="workschedule",
            name="friday_start",
            field=models.TimeField(blank=True, null=True, verbose_name="Пт, с"),
        ),
        migrations.AddField(
            model_name="workschedule",
            name="friday_end",
            field=models.TimeField(blank=True, null=True, verbose_name="Пт, до"),
        ),
        migrations.AddField(
            model_name="workschedule",
            name="saturday_start",
            field=models.TimeField(blank=True, null=True, verbose_name="Сб, с"),
        ),
        migrations.AddField(
            model_name="workschedule",
            name="saturday_end",
            field=models.TimeField(blank=True, null=True, verbose_name="Сб, до"),
        ),
        migrations.AddField(
            model_name="workschedule",
            name="sunday_start",
            field=models.TimeField(blank=True, null=True, verbose_name="Вс, с"),
        ),
        migrations.AddField(
            model_name="workschedule",
            name="sunday_end",
            field=models.TimeField(blank=True, null=True, verbose_name="Вс, до"),
        ),
    ]
