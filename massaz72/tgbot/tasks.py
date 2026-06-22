"""Задачи django-q2 (тонкие обёртки над management-командами)."""

from django.core.management import call_command


def flush_notifications():
    """Периодически: отправка отложенных автоуведомлений (тихие часы)."""
    call_command("flush_notifications")
