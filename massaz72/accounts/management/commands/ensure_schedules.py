"""Создаёт/обновляет ежедневные расписания django-q2 (идемпотентно).

Запускается при старте воркера `qcluster` (см. docker-compose). Расписания
ежедневные, время первого запуска — ближайшие 09:00 по settings.TIME_ZONE.
Дальше django-q сам сдвигает next_run на сутки.

    python manage.py ensure_schedules
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

RUN_HOUR = 9  # 09:00 по settings.TIME_ZONE (Asia/Yekaterinburg)

# (имя расписания, путь к функции-задаче)
SCHEDULES = [
    ("send_reminders_daily", "accounts.tasks.send_reminders"),
    ("purge_inactive_daily", "accounts.tasks.purge_inactive"),
]


class Command(BaseCommand):
    help = "Создаёт/обновляет ежедневные расписания django-q (09:00)."

    def handle(self, *args, **options):
        from django_q.models import Schedule

        now = timezone.localtime()
        run_at = now.replace(hour=RUN_HOUR, minute=0, second=0, microsecond=0)
        if now >= run_at:
            run_at += timedelta(days=1)

        for name, func in SCHEDULES:
            obj, created = Schedule.objects.update_or_create(
                name=name,
                defaults={
                    "func": func,
                    "schedule_type": Schedule.DAILY,
                    "repeats": -1,
                },
            )
            # next_run задаём только при создании — чтобы не сбивать живое
            # расписание при каждом рестарте.
            if created:
                obj.next_run = run_at
                obj.save(update_fields=["next_run"])
            self.stdout.write(("создано: " if created else "уже есть: ") + name)
