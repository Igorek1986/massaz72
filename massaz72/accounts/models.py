import secrets

from django.conf import settings
from django.db import models


def gen_link_token() -> str:
    return secrets.token_urlsafe(16)


class Client(models.Model):
    """Профиль клиента. Аккаунт первичен, вход — стандартный Django User.
    Телефон необязателен. Привязка к боту даёт возможность писать клиенту
    (напоминания, сброс пароля, уведомления)."""

    class Messenger(models.TextChoices):
        TELEGRAM = "telegram", "Telegram"
        MAX = "max", "Max"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="client_profile",
        verbose_name="Пользователь",
    )
    phone = models.CharField("Телефон", max_length=20, blank=True, default="")

    # Привязка к боту (Telegram сейчас, Max — задел).
    messenger = models.CharField(
        "Мессенджер", max_length=10, choices=Messenger.choices, blank=True, default="",
    )
    telegram_id = models.BigIntegerField("Telegram ID", null=True, blank=True)
    telegram_username = models.CharField(
        "Telegram username", max_length=150, blank=True, default="",
    )
    # Не unique на уровне БД (token_urlsafe(16) практически уникален),
    # чтобы не усложнять миграцию; поиск — filter(link_token=...).first().
    link_token = models.CharField(
        "Токен привязки к боту", max_length=43, db_index=True,
        default=gen_link_token, editable=False,
    )

    # Напоминания о периодическом массаже (клиент включает сам).
    INTERVAL_CHOICES = [(6, "Раз в 6 месяцев"), (12, "Раз в год")]
    reminder_enabled = models.BooleanField("Напоминания о записи", default=False)
    reminder_interval_months = models.PositiveSmallIntegerField(
        "Интервал напоминаний", choices=INTERVAL_CHOICES, default=6,
    )
    last_reminder_at = models.DateField(
        "Последнее напоминание", null=True, blank=True,
    )

    # Личное окно уведомлений от бота (переопределяет глобальное для сообщений
    # этому клиенту). Пусто — используется глобальное (SiteSettings).
    notify_start = models.TimeField("Уведомления: с", null=True, blank=True)
    notify_end = models.TimeField("Уведомления: до", null=True, blank=True)

    # Авто-удаление неактивных аккаунтов: дата отправки предупреждения
    # (начало grace-периода перед удалением). Сбрасывается, если клиент
    # снова активен.
    deletion_warned_at = models.DateField(
        "Предупреждение об удалении", null=True, blank=True,
    )

    created_at = models.DateTimeField("Дата регистрации", auto_now_add=True)

    class Meta:
        verbose_name = "Клиент"
        verbose_name_plural = "Клиенты"

    def __str__(self) -> str:
        return self.user.get_username()

    @property
    def bot_linked(self) -> bool:
        return self.telegram_id is not None
