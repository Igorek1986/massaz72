from django.db import models


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

    class Source(models.TextChoices):
        GUEST = "guest", "Сайт (гость)"
        ACCOUNT = "account", "Сайт (аккаунт)"
        BOT = "bot", "Бот"

    client_name = models.CharField("Имя", max_length=255)
    phone = models.CharField("Телефон", max_length=20, blank=True)
    service = models.ForeignKey(
        "services.Massage", on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="Услуга",
    )
    specialist = models.ForeignKey(
        "cabinet.Specialist", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="booking_requests",
        verbose_name="Мастер",
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
