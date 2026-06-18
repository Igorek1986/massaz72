from datetime import time
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Specialty(models.Model):
    """Справочник специальностей (управляется в админке)."""
    name = models.CharField("Название", max_length=100, unique=True)
    order = models.PositiveIntegerField("Порядок", default=0)

    class Meta:
        verbose_name = "Специальность"
        verbose_name_plural = "Специальности"
        ordering = ["order", "name"]

    def __str__(self) -> str:
        return self.name


class Specialist(models.Model):
    # Вход в кабинет — необязательная привязка к пользователю.
    # Специалист первичен; аккаунт прикрепляется по желанию.
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="specialist",
        verbose_name="Аккаунт для входа",
        help_text="Необязательно. Привяжите пользователя, если специалисту нужен вход в кабинет.",
    )
    specialty = models.ForeignKey(
        "Specialty", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="specialists", verbose_name="Специальность",
    )
    name = models.CharField("Имя", max_length=100)
    photo = models.ImageField("Фото", upload_to="specialists/", null=True, blank=True)
    description = models.TextField(
        "Описание", blank=True,
        help_text="Опыт, специализация и подход к работе (показывается на сайте)",
    )
    start_date = models.DateField(
        "Дата начала работы", blank=True, null=True,
    )
    telegram_username = models.CharField(
        "Telegram (username без @)", max_length=100, blank=True, default="",
    )
    telegram_active = models.BooleanField("Telegram активен", default=True)
    whatsapp_number = models.CharField(
        "WhatsApp (номер с кодом страны, без +)", max_length=20, blank=True, default="",
    )
    whatsapp_active = models.BooleanField("WhatsApp активен", default=True)
    max_messanger = models.CharField(
        "MAX Messenger (ссылка профиля)", max_length=255, blank=True, default="",
        help_text=(
            "Полная ссылка профиля из приложения MAX. "
            "MAX → Настройки → QR-код профиля → Поделиться → Скопировать ссылку. "
            "Выглядит так: https://max.ru/u/xxxxxxxx"
        ),
    )
    max_messanger_active = models.BooleanField("MAX активен", default=True)
    is_active = models.BooleanField(
        "Активный специалист", default=True,
        help_text="Показывать на сайте и в выборе при записи",
    )
    order = models.PositiveIntegerField("Порядок сортировки", default=0)
    can_manage_prices = models.BooleanField(
        "Управление ценами",
        default=True,
        help_text="Разрешить изменять цены и скидки",
    )
    head = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="subordinates", verbose_name="Главный специалист",
        help_text="Главный видит записи своих специалистов в календаре (без редактирования).",
    )
    can_manage_reviews = models.BooleanField(
        "Управление отзывами",
        default=False,
        help_text="Доступ к разделу «Отзывы» в кабинете (независимо от прочих ролей).",
    )

    class Meta:
        verbose_name = "Специалист"
        verbose_name_plural = "Специалисты"
        ordering = ["order"]

    def visible_specialist_ids(self) -> list[int]:
        """ID специалистов, чьи записи видит этот специалист: свои + подчинённые
        (для главного специалиста)."""
        ids = [self.pk]
        ids += list(self.subordinates.values_list("pk", flat=True))
        return ids

    def __str__(self) -> str:
        return self.name

    @property
    def experience(self) -> int:
        """Число полных лет опыта по дате начала работы."""
        if not self.start_date:
            return 0
        from datetime import date
        today = date.today()
        years = today.year - self.start_date.year
        if today.month < self.start_date.month or (
            today.month == self.start_date.month and today.day < self.start_date.day
        ):
            years -= 1
        return years

    @property
    def experience_text(self) -> str:
        """Опыт с правильным склонением слова «год»."""
        years = self.experience
        if years % 10 == 1 and years % 100 != 11:
            return f"{years} год"
        elif 2 <= years % 10 <= 4 and (years % 100 < 10 or years % 100 >= 20):
            return f"{years} года"
        else:
            return f"{years} лет"


class WorkSchedule(models.Model):
    specialist = models.OneToOneField(
        Specialist,
        on_delete=models.CASCADE,
        related_name="schedule",
        verbose_name="Специалист",
    )
    monday = models.BooleanField("Понедельник", default=True)
    monday_start = models.TimeField("Пн, с", null=True, blank=True)
    monday_end = models.TimeField("Пн, до", null=True, blank=True)
    tuesday = models.BooleanField("Вторник", default=True)
    tuesday_start = models.TimeField("Вт, с", null=True, blank=True)
    tuesday_end = models.TimeField("Вт, до", null=True, blank=True)
    wednesday = models.BooleanField("Среда", default=True)
    wednesday_start = models.TimeField("Ср, с", null=True, blank=True)
    wednesday_end = models.TimeField("Ср, до", null=True, blank=True)
    thursday = models.BooleanField("Четверг", default=True)
    thursday_start = models.TimeField("Чт, с", null=True, blank=True)
    thursday_end = models.TimeField("Чт, до", null=True, blank=True)
    friday = models.BooleanField("Пятница", default=True)
    friday_start = models.TimeField("Пт, с", null=True, blank=True)
    friday_end = models.TimeField("Пт, до", null=True, blank=True)
    saturday = models.BooleanField("Суббота", default=False)
    saturday_start = models.TimeField("Сб, с", null=True, blank=True)
    saturday_end = models.TimeField("Сб, до", null=True, blank=True)
    sunday = models.BooleanField("Воскресенье", default=False)
    sunday_start = models.TimeField("Вс, с", null=True, blank=True)
    sunday_end = models.TimeField("Вс, до", null=True, blank=True)
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

    # Часы по умолчанию, если день рабочий, но конкретное время не задано.
    DEFAULT_START = time(9, 0)
    DEFAULT_END = time(20, 0)
    DAY_NAMES = [
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    ]

    def working_weekdays(self) -> list[int]:
        return [wd for wd, name in enumerate(self.DAY_NAMES) if getattr(self, name)]

    def hours_for_weekday(self, weekday: int) -> tuple[time, time] | None:
        """Рабочие часы (начало, конец) для дня недели (0=Пн) или None, если
        день нерабочий. Если день рабочий, но время не задано — дефолтные часы."""
        name = self.DAY_NAMES[weekday]
        if not getattr(self, name):
            return None
        start = getattr(self, f"{name}_start") or self.DEFAULT_START
        end = getattr(self, f"{name}_end") or self.DEFAULT_END
        return start, end


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
    discount_percent = models.DecimalField(
        "Скидка (%)", max_digits=5, decimal_places=2, null=True, blank=True,
    )
    discount_amount = models.DecimalField(
        "Скидка (₽)", max_digits=10, decimal_places=2, null=True, blank=True,
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
