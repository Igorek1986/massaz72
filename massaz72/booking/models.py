import secrets

from django.db import models


def gen_link_token() -> str:
    return secrets.token_urlsafe(16)


class BookingSessionOption(models.Model):
    """Вариант количества сеансов (настраивается в админке). Используется
    и онлайн-формой записи, и Telegram-ботом."""

    count = models.PositiveIntegerField("Количество сеансов")
    label = models.CharField(
        "Метка", max_length=50, blank=True, default="",
        help_text="Если пусто — отображается «N сеансов».",
    )
    is_active = models.BooleanField("Активен", default=True)
    order = models.PositiveIntegerField("Порядок", default=0)

    class Meta:
        verbose_name = "Вариант кол-ва сеансов"
        verbose_name_plural = "Варианты кол-ва сеансов"
        ordering = ["order", "count"]

    def __str__(self) -> str:
        return self.label if self.label else f"{self.count} сеансов"

    @property
    def button_label(self) -> str:
        return self.label if self.label else f"{self.count} сеансов"


class BookingRequestQuerySet(models.QuerySet):
    def pending(self):
        return self.filter(status=BookingRequest.Status.PENDING)


class BookingRequest(models.Model):
    """Заявка на запись с сайта (или из бота). При подтверждении мастером/в боте
    создаётся обычная запись cabinet.Appointment."""

    class Status(models.TextChoices):
        PENDING = "pending", "На подтверждении"
        CONFIRMED = "confirmed", "Подтверждена"
        DECLINED = "declined", "Отклонена"
        CANCELLED = "cancelled", "Отменена клиентом"

    class Source(models.TextChoices):
        GUEST = "guest", "Сайт (гость)"
        ACCOUNT = "account", "Сайт (аккаунт)"
        BOT = "bot", "Бот"

    user = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="booking_requests", verbose_name="Аккаунт клиента",
    )
    client_name = models.CharField("Имя", max_length=255)
    phone = models.CharField("Телефон", max_length=20, blank=True)
    address = models.CharField("Адрес", max_length=500, blank=True)
    service = models.ForeignKey(
        "services.Massage", on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="Услуга",
    )
    specialist = models.ForeignKey(
        "cabinet.Specialist", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="booking_requests",
        verbose_name="Мастер",
    )
    sessions = models.ForeignKey(
        "BookingSessionOption", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="booking_requests",
        verbose_name="Количество сеансов",
    )
    preferred_date = models.DateField("Желаемая дата")
    preferred_time = models.TimeField("Желаемое время")
    comment = models.TextField("Комментарий", max_length=2000, blank=True)
    source = models.CharField(
        "Источник", max_length=10, choices=Source.choices, default=Source.GUEST
    )
    status = models.CharField(
        "Статус", max_length=10, choices=Status.choices, default=Status.PENDING
    )
    ip_address = models.GenericIPAddressField("IP-адрес", null=True, blank=True)

    # Привязка к боту (для связи без телефона). Канал — задел под Telegram/Max.
    class Messenger(models.TextChoices):
        TELEGRAM = "telegram", "Telegram"
        MAX = "max", "Max"

    messenger = models.CharField(
        "Мессенджер", max_length=10, choices=Messenger.choices, blank=True, default="",
    )
    messenger_user_id = models.BigIntegerField("ID в мессенджере", null=True, blank=True)
    messenger_username = models.CharField(
        "Username в мессенджере", max_length=150, blank=True, default="",
    )
    client_confirmed = models.BooleanField(
        "Подтверждена клиентом", default=False,
        help_text="Клиент подтвердил заявку в боте.",
    )
    consent_at = models.DateTimeField(
        "Согласие на обработку ПД", null=True, blank=True,
        help_text="Момент согласия клиента на обработку ПД (через бота).",
    )
    link_token = models.CharField(
        "Токен привязки к боту", max_length=43, unique=True,
        default=gen_link_token, editable=False,
    )
    appointment = models.ForeignKey(
        "cabinet.Appointment", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="booking_request",
        verbose_name="Созданная запись",
    )
    created_at = models.DateTimeField("Создана", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлена", auto_now=True)

    objects = BookingRequestQuerySet.as_manager()

    class Meta:
        verbose_name = "Заявка на запись"
        verbose_name_plural = "Заявки на запись"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.client_name} — {self.preferred_date} {self.preferred_time} ({self.get_status_display()})"


class RescheduleRequest(models.Model):
    """Запрос клиента на перенос сеанса. Подтверждает мастер (в боте/кабинете)."""

    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает подтверждения"
        APPROVED = "approved", "Подтверждён"
        DECLINED = "declined", "Отклонён"

    appointment = models.ForeignKey(
        "cabinet.Appointment", on_delete=models.CASCADE,
        related_name="reschedule_requests", verbose_name="Запись",
    )
    new_date = models.DateField("Новая дата")
    new_time = models.TimeField("Новое время")
    status = models.CharField(
        "Статус", max_length=10, choices=Status.choices, default=Status.PENDING,
    )
    created_at = models.DateTimeField("Создан", auto_now_add=True)

    class Meta:
        verbose_name = "Запрос на перенос"
        verbose_name_plural = "Запросы на перенос"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Перенос записи {self.appointment_id} → {self.new_date} {self.new_time}"
