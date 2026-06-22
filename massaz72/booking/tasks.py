"""Задачи для планировщика django-q2.

Тонкая обёртка над management-командой — django-q вызывает её по строковому
пути (см. accounts/management/commands/ensure_schedules.py).
"""

from django.core.management import call_command


def purge_unconfirmed_bookings():
    """Периодически: удаление заявок без контакта, не подтверждённых в боте."""
    call_command("purge_unconfirmed_bookings")


def remind_unconfirmed_bookings():
    """Периодически: напоминание мастеру о необработанных заявках."""
    call_command("remind_unconfirmed_bookings")
