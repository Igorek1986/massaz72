from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models


class WorkSchedule(models.Model):
    """Недельное расписание — singleton."""

    monday = models.BooleanField("Понедельник", default=True)
    tuesday = models.BooleanField("Вторник", default=True)
    wednesday = models.BooleanField("Среда", default=True)
    thursday = models.BooleanField("Четверг", default=True)
    friday = models.BooleanField("Пятница", default=True)
    saturday = models.BooleanField("Суббота", default=False)
    sunday = models.BooleanField("Воскресенье", default=False)
    break_between_minutes = models.PositiveIntegerField(
        "Перерыв между массажами (мин)", default=15
    )

    class Meta:
        verbose_name = "Рабочее расписание"
        verbose_name_plural = "Рабочее расписание"

    def __str__(self) -> str:
        return "Рабочее расписание"

    def save(self, *args, **kwargs) -> None:
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass

    @classmethod
    def get_solo(cls) -> "WorkSchedule":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def working_weekdays(self) -> list[int]:
        """Возвращает список рабочих дней недели (0=пн, 6=вс)."""
        mapping = [
            (0, self.monday),
            (1, self.tuesday),
            (2, self.wednesday),
            (3, self.thursday),
            (4, self.friday),
            (5, self.saturday),
            (6, self.sunday),
        ]
        return [day for day, active in mapping if active]


class ScheduleException(models.Model):
    """Диапазон дат, когда массажист не работает (выходной, отпуск)."""

    DAY_OFF = "day_off"
    VACATION = "vacation"
    TYPE_CHOICES = [
        (DAY_OFF, "Выходной"),
        (VACATION, "Отпуск"),
    ]

    date_from = models.DateField("Дата начала")
    date_to = models.DateField("Дата окончания")
    exception_type = models.CharField(
        "Тип", max_length=10, choices=TYPE_CHOICES, default=DAY_OFF
    )
    note = models.CharField("Примечание", max_length=255, blank=True)

    class Meta:
        verbose_name = "Исключение в расписании"
        verbose_name_plural = "Исключения в расписании"
        ordering = ["date_from"]

    def __str__(self) -> str:
        return f"{self.get_exception_type_display()}: {self.date_from} – {self.date_to}"

    def clean(self) -> None:
        if self.date_to < self.date_from:
            raise ValidationError(
                {"date_to": "Дата окончания не может быть раньше даты начала."}
            )


class BlockedSlot(models.Model):
    """Заблокированный временной промежуток внутри рабочего дня."""

    date = models.DateField("Дата")
    time_start = models.TimeField("Начало")
    time_end = models.TimeField("Конец")
    note = models.CharField("Причина", max_length=255, blank=True)

    class Meta:
        verbose_name = "Заблокированное время"
        verbose_name_plural = "Заблокированное время"
        ordering = ["date", "time_start"]

    def __str__(self) -> str:
        return f"{self.date} {self.time_start}–{self.time_end}"

    def clean(self) -> None:
        if self.time_end <= self.time_start:
            raise ValidationError(
                {"time_end": "Время окончания должно быть позже времени начала."}
            )


class AppointmentSeries(models.Model):
    """Серия сеансов — объединяет записи одного курса лечения."""

    service = models.ForeignKey(
        "services.Massage",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Услуга",
    )
    total_sessions = models.PositiveIntegerField("Количество сеансов")
    created_at = models.DateTimeField("Создана", auto_now_add=True)

    class Meta:
        verbose_name = "Серия сеансов"
        verbose_name_plural = "Серии сеансов"

    def __str__(self) -> str:
        return f"Серия #{self.pk} ({self.total_sessions} сеансов)"


class Appointment(models.Model):
    """Запись клиента на сеанс."""

    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (SCHEDULED, "Запланировано"),
        (COMPLETED, "Выполнено"),
        (CANCELLED, "Отменено"),
    ]

    client_name = models.CharField("Имя клиента", max_length=255)
    client_phone = models.CharField("Телефон", max_length=20, blank=True)
    address = models.CharField("Адрес", max_length=500, blank=True)
    service = models.ForeignKey(
        "services.Massage",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Услуга",
    )
    date = models.DateField("Дата")
    time_start = models.TimeField("Время начала")
    cost = models.DecimalField("Стоимость", max_digits=10, decimal_places=2)
    transport_cost = models.DecimalField(
        "Транспортные расходы",
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    notes = models.TextField("Заметки", blank=True)
    status = models.CharField(
        "Статус", max_length=10, choices=STATUS_CHOICES, default=SCHEDULED
    )
    series = models.ForeignKey(
        AppointmentSeries,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="appointments",
        verbose_name="Серия",
    )
    created_at = models.DateTimeField("Создана", auto_now_add=True)

    class Meta:
        verbose_name = "Запись"
        verbose_name_plural = "Записи"
        ordering = ["date", "time_start"]

    def __str__(self) -> str:
        return f"{self.client_name} — {self.date} {self.time_start}"


class Discount(models.Model):
    """Скидка на услуги — показывает баннер на сайте и изменяет отображаемую цену."""

    PERCENTAGE = "percentage"
    AMOUNT = "amount"
    TYPE_CHOICES = [
        (PERCENTAGE, "Процент (%)"),
        (AMOUNT, "Фиксированная сумма (₽)"),
    ]

    discount_type = models.CharField(
        "Тип скидки", max_length=10, choices=TYPE_CHOICES, default=PERCENTAGE
    )
    value = models.DecimalField("Размер скидки", max_digits=10, decimal_places=2)
    date_from = models.DateField("Дата начала")
    date_to = models.DateField("Дата окончания")
    description = models.CharField(
        "Текст баннера",
        max_length=255,
        blank=True,
        help_text="Оставьте пустым — текст сформируется автоматически",
    )

    class Meta:
        verbose_name = "Скидка"
        verbose_name_plural = "Скидки"
        ordering = ["-date_from"]

    def __str__(self) -> str:
        return f"{self.get_discount_type_display()} {self.value} ({self.date_from}–{self.date_to})"

    def clean(self) -> None:
        if self.date_to < self.date_from:
            raise ValidationError({"date_to": "Дата окончания не может быть раньше даты начала."})
        if self.value <= 0:
            raise ValidationError({"value": "Размер скидки должен быть больше нуля."})
        if self.discount_type == self.PERCENTAGE and self.value > 100:
            raise ValidationError({"value": "Процент скидки не может превышать 100."})

    @property
    def banner_text(self) -> str:
        if self.description:
            return self.description
        date_str = self.date_to.strftime("%d.%m.%Y")
        if self.discount_type == self.PERCENTAGE:
            v = int(self.value) if self.value == int(self.value) else self.value
            return f"Скидка {v}% действует до {date_str}"
        v = int(self.value) if self.value == int(self.value) else self.value
        return f"Скидка {v} ₽ на все услуги до {date_str}"

    def apply_to(self, price: Decimal) -> Decimal:
        """Возвращает цену после скидки, округлённую до целых."""
        if self.discount_type == self.PERCENTAGE:
            discounted = price * (1 - self.value / Decimal("100"))
        else:
            discounted = price - self.value
        return max(discounted, Decimal("0")).quantize(Decimal("1"))
