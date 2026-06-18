import datetime

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cabinet", "0019_workschedule_hours"),
    ]

    operations = [
        migrations.AddField(
            model_name="workschedule",
            name="default_start",
            field=models.TimeField(
                default=datetime.time(9, 0), verbose_name="Начало по умолчанию"
            ),
        ),
        migrations.AddField(
            model_name="workschedule",
            name="default_end",
            field=models.TimeField(
                default=datetime.time(19, 0), verbose_name="Конец по умолчанию"
            ),
        ),
    ]
