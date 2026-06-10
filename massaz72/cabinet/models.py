from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Specialist(models.Model):
    SPECIALTY_CHOICES = [
        ("masseur", "Массажист"),
        ("other", "Другое"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="specialist",
        verbose_name="Пользователь",
    )
    specialty = models.CharField(
        "Специальность", max_length=30, choices=SPECIALTY_CHOICES, default="masseur"
    )
    name = models.CharField("Имя", max_length=100)
    photo = models.ImageField("Фото", upload_to="specialists/", null=True, blank=True)
    can_manage_prices = models.BooleanField(
        "Управление ценами",
        default=True,
        help_text="Разрешить изменять цены и скидки",
    )

    class Meta:
        verbose_name = "Специалист"
        verbose_name_plural = "Специалисты"

    def __str__(self) -> str:
        return f"{self.name} ({self.get_specialty_display()})"


class WorkSchedule(models.Model):
    specialist = models.OneToOneField(
        Specialist,
        on_delete=models.CASCADE,
        related_name="schedule",
        verbose_name="Специалист",
    )
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
    break_between_travel_minutes = models.PositiveIntegerField(
        "Перерыв между выездными массажами (мин)", default=60
    )

    class Meta:
        verbose_name = "Рабочее расписание"
        verbose_name_plural = "Рабочее расписание"

    def __str__(self) -> str:
        return f"Расписание — {self.specialist}"

    @classmethod
    def for_specialist(cls, specialist: "Specialist") -> "WorkSchedule":
        obj, _ = cls.objects.get_or_create(specialist=specialist)
        return obj

    def working_weekdays(self) -> list[int]:
        mapping = [
            (0, self.monday), (1, self.tuesday), (2, self.wednesday),
            (3, self.thursday), (4, self.friday), (5, self.saturday), (6, self.sunday),
        ]
        return [day for day, active in mapping if active]


class ScheduleException(models.Model):
    DAY_OFF = "day_off"
    VACATION = "vacation"
    TYPE_CHOICES = [(DAY_OFF, "Выходной"), (VACATION, "Отпуск")]

    specialist = models.ForeignKey(
        Specialist, on_delete=models.CASCADE,
        related_name="exceptions", verbose_name="Специалист",
    )
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
            raise ValidationError({"date_to": "Дата окончания не может быть раньше даты начала."})


class BlockedSlot(models.Model):
    specialist = models.ForeignKey(
        Specialist, on_delete=models.CASCADE,
        related_name="blocked_slots", verbose_name="Специалист",
    )
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
            raise ValidationError({"time_end": "Время окончания должно быть позже времени начала."})


class AppointmentSeries(models.Model):
    specialist = models.ForeignKey(
        Specialist, on_delete=models.CASCADE,
        related_name="series", verbose_name="Специалист",
    )
    service = models.ForeignKey(
        "services.Massage", on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="Услуга",
    )
    total_sessions = models.PositiveIntegerField("Количество сеансов")
    created_at = models.DateTimeField("Создана", auto_now_add=True)

    class Meta:
        verbose_name = "Серия сеансов"
        verbose_name_plural = "Серии сеансов"

    def __str__(self) -> str:
        return f"Серия #{self.pk} ({self.total_sessions} сеансов)"


class Appointment(models.Model):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (SCHEDULED, "Запланировано"),
        (COMPLETED, "Выполнено"),
        (CANCELLED, "Отменено"),
    ]

    specialist = models.ForeignKey(
        Specialist, on_delete=models.CASCADE,
        related_name="appointments", verbose_name="Специалист",
    )
    client_name = models.CharField("Имя клиента", max_length=255)
    client_phone = models.CharField("Телефон", max_length=20, blank=True)
    address = models.CharField("Адрес", max_length=500, blank=True)
    is_travel = models.BooleanField("Выездной", default=False)
    service = models.ForeignKey(
        "services.Massage", on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="Услуга",
    )
    date = models.DateField("Дата")
    time_start = models.TimeField("Время начала")
    cost = models.DecimalField("Стоимость", max_digits=10, decimal_places=2)
    transport_cost = models.DecimalField(
        "Транспортные расходы", max_digits=10, decimal_places=2, null=True, blank=True,
    )
    notes = models.TextField("Заметки", blank=True)
    status = models.CharField(
        "Статус", max_length=10, choices=STATUS_CHOICES, default=SCHEDULED
    )
    series = models.ForeignKey(
        AppointmentSeries, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="appointments", verbose_name="Серия",
    )
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE,
        related_name="additional_services", verbose_name="Основная запись",
    )
    discount = models.ForeignKey(
        "Discount", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="appointments", verbose_name="Скидка",
    )
    created_at = models.DateTimeField("Создана", auto_now_add=True)

    class Meta:
        verbose_name = "Запись"
        verbose_name_plural = "Записи"
        ordering = ["date", "time_start"]

    def __str__(self) -> str:
        return f"{self.client_name} — {self.date} {self.time_start}"


class Discount(models.Model):
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
        "Текст баннера", max_length=255, blank=True,
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
        v = int(self.value) if self.value == int(self.value) else self.value
        if self.discount_type == self.PERCENTAGE:
            return f"Скидка {v}% действует до {date_str}"
        return f"Скидка {v} ₽ на все услуги до {date_str}"

    def apply_to(self, price: Decimal) -> Decimal:
        if self.discount_type == self.PERCENTAGE:
            discounted = price * (1 - self.value / Decimal("100"))
        else:
            discounted = price - self.value
        return max(discounted, Decimal("0")).quantize(Decimal("1"))
