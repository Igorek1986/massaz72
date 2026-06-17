"""Шлёт клиентам напоминания о записи на массаж (по интервалу).

Запускать раз в день (напр. в 9:00) по cron:
    python manage.py send_reminders
"""

import calendar
from datetime import date

from django.core.management.base import BaseCommand


def add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    year = d.year + m // 12
    month = m % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def last_visit_date(client):
    """Дата последнего сеанса клиента (по его записям)."""
    from accounts.views import _client_appointment_qs

    return (
        _client_appointment_qs(client.user)
        .order_by("-date")
        .values_list("date", flat=True)
        .first()
    )


class Command(BaseCommand):
    help = "Отправляет напоминания о записи клиентам с включёнными напоминаниями."

    def handle(self, *args, **options):
        from accounts.models import Client
        from tgbot.notifications import send_reminder

        today = date.today()
        sent = 0
        clients = Client.objects.filter(
            reminder_enabled=True, telegram_id__isnull=False
        )
        for client in clients:
            base = client.last_reminder_at or last_visit_date(client) \
                or client.created_at.date()
            if base is None:
                continue
            if today >= add_months(base, client.reminder_interval_months):
                if send_reminder(client.telegram_id):
                    client.last_reminder_at = today
                    client.save(update_fields=["last_reminder_at"])
                    sent += 1

        self.stdout.write(self.style.SUCCESS(f"Напоминаний отправлено: {sent}"))
