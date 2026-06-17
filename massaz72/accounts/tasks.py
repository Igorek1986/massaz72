"""Задачи для планировщика django-q2.

Тонкие обёртки над management-командами — django-q вызывает их по
строковому пути (см. accounts/management/commands/ensure_schedules.py).
"""

from django.core.management import call_command


def send_reminders():
    """Ежедневно: напоминания клиентам о записи."""
    call_command("send_reminders")


def purge_inactive():
    """Ежедневно: удаление неактивных аккаунтов (с предупреждением)."""
    call_command("purge_inactive")
