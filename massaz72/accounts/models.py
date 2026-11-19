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
    consent_at = models.DateTimeField(
        "Согласие на обработку ПД", null=True, blank=True,
        help_text="Момент согласия при регистрации.",
    )

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


class AccountErasureRequest(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name="account_erasure_request",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        permissions = [
            ("process_account_erasure", "Обработка запросов на удаление данных клиентов"),
        ]
        verbose_name = "Запрос на удаление данных клиента"
        verbose_name_plural = "Запросы на удаление данных клиентов"


class AccountErasureReminder(models.Model):
    recipient = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    last_sent_at = models.DateTimeField(null=True, blank=True)


class PushSubscription(models.Model):
    class Device(models.TextChoices):
        UNKNOWN = "", "iPhone или iPad"
        IPHONE = "iphone", "iPhone"
        IPAD = "ipad", "iPad"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    session = models.OneToOneField("sessions.Session", on_delete=models.CASCADE)
    endpoint = models.URLField(max_length=2048, unique=True)
    auth = models.CharField(max_length=22)
    p256dh = models.CharField(max_length=87)
    vapid_key = models.CharField(max_length=87)
    consent_at = models.DateTimeField()
    last_test_at = models.DateTimeField(null=True, blank=True)
    device = models.CharField(max_length=6, choices=Device.choices, default=Device.UNKNOWN, blank=True)


class PushDelivery(models.Model):
    class Kind(models.TextChoices):
        NEW_BOOKING = "new_booking"
        BOOKING_CONFIRMED = "booking_confirmed"
        BOOKING_DECLINED = "booking_declined"
        ERASURE_REQUEST = "erasure_request"
        TEST = "test"

    subscription = models.ForeignKey(PushSubscription, on_delete=models.CASCADE)
    booking = models.ForeignKey("booking.BookingRequest", null=True, on_delete=models.CASCADE)
    erasure_request = models.ForeignKey(AccountErasureRequest, null=True, on_delete=models.CASCADE)
    kind = models.CharField(max_length=24, choices=Kind.choices)
    available_at = models.DateTimeField(db_index=True)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["subscription", "booking", "kind"], name="one_push_per_booking_event",
            ),
            models.UniqueConstraint(
                fields=["subscription", "erasure_request"], name="one_push_per_erasure_request",
            ),
        ]
