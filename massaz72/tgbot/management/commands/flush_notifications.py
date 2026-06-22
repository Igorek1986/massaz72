"""Отправляет отложенные (из-за тихих часов) автоуведомления, у которых
наступило окно. Запускается периодически планировщиком django-q.

    python manage.py flush_notifications
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Отправляет отложенные автоуведомления (тихие часы)."

    def handle(self, *args, **options):
        from tgbot.notify import flush_due
        n = flush_due()
        self.stdout.write(f"Отправлено отложенных уведомлений: {n}")
