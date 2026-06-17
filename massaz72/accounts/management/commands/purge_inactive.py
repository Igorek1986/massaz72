"""Авто-удаление неактивных аккаунтов клиентов.

Логика (запускать раз в день, напр. в 9:00):
  * «Неактивность» считается по last_login (фолбэк — date_joined).
  * Аккаунт с будущей записью считается активным — не трогаем,
    предупреждение сбрасываем.
  * За WARN_BEFORE_DAYS до порога клиенту шлётся предупреждение в бот
    (если привязан) и ставится дата deletion_warned_at — старт grace.
  * По достижении порога неактивности и если grace-период прошёл —
    аккаунт удаляется (User → каскадом Client; booking_requests.user
    обнуляется, история в календаре мастера сохраняется).

    python manage.py purge_inactive          # боевой режим
    python manage.py purge_inactive --dry-run # только показать, без изменений
"""

from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

INACTIVE_DAYS = 365
WARN_BEFORE_DAYS = 30


def last_activity_date(user) -> date:
    """Дата последней активности аккаунта (вход, иначе — регистрация)."""
    dt = user.last_login or user.date_joined
    return timezone.localtime(dt).date()


def has_future_appointment(user, today: date) -> bool:
    from accounts.views import _client_appointment_qs

    return _client_appointment_qs(user).filter(date__gte=today).exists()


class Command(BaseCommand):
    help = "Удаляет неактивные аккаунты клиентов (с предупреждением за месяц)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Показать, что произошло бы, без изменений в БД.",
        )

    def handle(self, *args, **options):
        from accounts.models import Client
        from tgbot.notifications import send_deletion_warning

        dry = options["dry_run"]
        today = date.today()
        warn_threshold = INACTIVE_DAYS - WARN_BEFORE_DAYS

        warned = deleted = 0
        clients = Client.objects.select_related("user")
        for client in clients:
            user = client.user
            # Сотрудников/админов не трогаем.
            if user.is_staff or user.is_superuser:
                continue

            # Будущая запись = активный клиент.
            if has_future_appointment(user, today):
                if client.deletion_warned_at and not dry:
                    client.deletion_warned_at = None
                    client.save(update_fields=["deletion_warned_at"])
                continue

            inactive_days = (today - last_activity_date(user)).days

            # Снова активен (вошёл) — снимаем предупреждение.
            if inactive_days < warn_threshold:
                if client.deletion_warned_at and not dry:
                    client.deletion_warned_at = None
                    client.save(update_fields=["deletion_warned_at"])
                continue

            # Порог + grace прошёл → удаляем.
            if (
                inactive_days >= INACTIVE_DAYS
                and client.deletion_warned_at
                and (today - client.deletion_warned_at).days >= WARN_BEFORE_DAYS
            ):
                username = user.get_username()
                if not dry:
                    user.delete()
                deleted += 1
                tag = "[dry-run] " if dry else ""
                self.stdout.write(f"{tag}Удалён аккаунт: {username}")
                continue

            # Зона предупреждения, ещё не предупреждали → шлём и стартуем grace.
            if not client.deletion_warned_at:
                if client.telegram_id and not dry:
                    send_deletion_warning(client.telegram_id, WARN_BEFORE_DAYS)
                if not dry:
                    client.deletion_warned_at = today
                    client.save(update_fields=["deletion_warned_at"])
                warned += 1

        prefix = "[dry-run] " if dry else ""
        self.stdout.write(self.style.SUCCESS(
            f"{prefix}Предупреждено: {warned}, удалено: {deleted}"
        ))
