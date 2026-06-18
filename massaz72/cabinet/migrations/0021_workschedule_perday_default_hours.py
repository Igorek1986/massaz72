import datetime

from django.db import migrations, models

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def backfill_hours(apps, schema_editor):
    """Существующим дням без часов проставляем текущие часы по умолчанию
    (default_start/default_end), чтобы сохранить нынешнее поведение."""
    WorkSchedule = apps.get_model("cabinet", "WorkSchedule")
    for ws in WorkSchedule.objects.all():
        changed = False
        for day in DAYS:
            if getattr(ws, f"{day}_start") is None:
                setattr(ws, f"{day}_start", ws.default_start)
                changed = True
            if getattr(ws, f"{day}_end") is None:
                setattr(ws, f"{day}_end", ws.default_end)
                changed = True
        if changed:
            ws.save()


def noop(apps, schema_editor):
    pass


_START = datetime.time(9, 0)
_END = datetime.time(19, 0)
_LABELS = {
    "monday": "Пн", "tuesday": "Вт", "wednesday": "Ср", "thursday": "Чт",
    "friday": "Пт", "saturday": "Сб", "sunday": "Вс",
}


def _alter_ops():
    ops = []
    for day in DAYS:
        ops.append(migrations.AlterField(
            model_name="workschedule", name=f"{day}_start",
            field=models.TimeField(default=_START, verbose_name=f"{_LABELS[day]}, с"),
        ))
        ops.append(migrations.AlterField(
            model_name="workschedule", name=f"{day}_end",
            field=models.TimeField(default=_END, verbose_name=f"{_LABELS[day]}, до"),
        ))
    return ops


class Migration(migrations.Migration):

    dependencies = [
        ("cabinet", "0020_workschedule_default_hours"),
    ]

    operations = [
        migrations.RunPython(backfill_hours, noop),
        *_alter_ops(),
        migrations.RemoveField(model_name="workschedule", name="default_start"),
        migrations.RemoveField(model_name="workschedule", name="default_end"),
    ]
