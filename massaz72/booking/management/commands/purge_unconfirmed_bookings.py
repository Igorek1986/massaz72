"""Удаляет неподтверждённые заявки без контакта (AWAITING_CONTACT) старше
таймаута удержания, чтобы освободить забронированное время.

Таймаут берётся из SiteSettings.booking_hold_minutes (по умолчанию 15).
Запускается периодически планировщиком django-q (см. ensure_schedules):

    python manage.py purge_unconfirmed_bookings
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Удаляет заявки без контакта, не подтверждённые в боте за N минут."

    def handle(self, *args, **options):
        from booking.models import BookingRequest
        from main.models import SiteSettings

        s = SiteSettings.objects.first()
        hold = s.booking_hold_minutes if s else 15
        cutoff = timezone.now() - timedelta(minutes=hold)
        qs = BookingRequest.objects.filter(
            status=BookingRequest.Status.AWAITING_CONTACT,
            client_confirmed=False,
            created_at__lt=cutoff,
        )
        count = qs.count()
        qs.delete()
        self.stdout.write(f"Удалено заявок без контакта: {count}")
