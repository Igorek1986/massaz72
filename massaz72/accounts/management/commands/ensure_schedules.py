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

# Ежедневные задачи (запуск в 09:00).
DAILY_SCHEDULES = [
    ("send_reminders_daily", "accounts.tasks.send_reminders"),
    ("purge_inactive_daily", "accounts.tasks.purge_inactive"),
]

# Частые задачи: (имя, путь, период в минутах).
MINUTE_SCHEDULES = [
    ("purge_unconfirmed_bookings", "booking.tasks.purge_unconfirmed_bookings", 5),
    ("flush_notifications", "tgbot.tasks.flush_notifications", 5),
    ("remind_unconfirmed_bookings", "booking.tasks.remind_unconfirmed_bookings", 5),
]


class Command(BaseCommand):
    help = "Создаёт/обновляет расписания django-q (ежедневные и минутные)."

    def handle(self, *args, **options):
        from django_q.models import Schedule

        now = timezone.localtime()
        run_at = now.replace(hour=RUN_HOUR, minute=0, second=0, microsecond=0)
        if now >= run_at:
            run_at += timedelta(days=1)

        for name, func in DAILY_SCHEDULES:
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

        for name, func, minutes in MINUTE_SCHEDULES:
            obj, created = Schedule.objects.update_or_create(
                name=name,
                defaults={
                    "func": func,
                    "schedule_type": Schedule.MINUTES,
                    "minutes": minutes,
                    "repeats": -1,
                },
            )
            if created:
                obj.next_run = now + timedelta(minutes=minutes)
                obj.save(update_fields=["next_run"])
            self.stdout.write(("создано: " if created else "уже есть: ") + name)
