"""Напоминает мастеру о необработанных (PENDING) заявках старше интервала
напоминания (WorkSchedule.booking_reminder_minutes, по умолчанию 60; 0 — выкл).
Напоминаем один раз. С учётом тихих часов (notify откладывает на утро).

    python manage.py remind_unconfirmed_bookings
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Напоминает мастеру о необработанных заявках."

    def handle(self, *args, **options):
        from booking.models import BookingRequest
        from cabinet.models import WorkSchedule
        from tgbot.notify import notify

        now = timezone.now()
        qs = (
            BookingRequest.objects.filter(
                status=BookingRequest.Status.PENDING,
                reminded_at__isnull=True,
                specialist__isnull=False,
            )
            .select_related("specialist")
        )
        count = 0
        for b in qs:
            schedule = WorkSchedule.for_specialist(b.specialist)
            interval = schedule.booking_reminder_minutes
            if not interval:  # 0 — напоминания выключены
                continue
            if b.created_at <= now - timedelta(minutes=interval):
                notify("booking_reminder", {"booking_id": b.pk})
                b.reminded_at = now
                b.save(update_fields=["reminded_at"])
                count += 1
        self.stdout.write(f"Напоминаний отправлено: {count}")
