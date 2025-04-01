from django.db import models
from django.db.models import QuerySet
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from massaz72.utils import delete_old_file, get_file_path, validate_file_size


class Certificate(models.Model):
    about = models.ForeignKey(
        "About",
        on_delete=models.CASCADE,
        related_name="certificates",
        verbose_name="О массажисте",
    )
    title = models.CharField("Название", max_length=100)
    image = models.ImageField(
        "Изображение сертификата",
        upload_to=get_file_path,
        validators=[validate_file_size],
    )
    date_received = models.DateField("Дата получения", blank=True, null=True)
    order = models.PositiveIntegerField("Порядок отображения", default=0)
    created_at = models.DateTimeField("Дата создания", auto_now_add=True)
    is_archived = models.BooleanField("В архиве", default=False)

    class Meta:
        verbose_name = "Сертификат"
        verbose_name_plural = "Сертификаты"
        ordering = ["order"]

    def save(self, *args, **kwargs):
        if self.pk:
            delete_old_file(self, "image")
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class About(models.Model):
    name = models.CharField(
        "Имя массажиста", max_length=100, help_text="Введите полное имя массажиста"
    )
    photo = models.ImageField(
        "Фото массажиста",
        upload_to=get_file_path,
        blank=True,
        validators=[validate_file_size],
        help_text="Загрузите профессиональное фото массажиста",
    )
    description = models.TextField(
        "Описание",
        blank=True,
        help_text="Опишите опыт, специализацию и подход к работе",
    )
    start_date = models.DateField(
        "Дата начала работы",
        blank=True,
        null=True,
        help_text="Укажите дату начала работы массажистом",
    )
    is_active = models.BooleanField(
        "Активный массажист",
        default=True,
        help_text="Отметьте, если массажист активно принимает клиентов",
    )
    order = models.PositiveIntegerField(
        "Порядок сортировки",
        default=0,
        help_text="Укажите порядок отображения на сайте (чем меньше число, тем выше в списке)",
    )
    created_at = models.DateTimeField("Дата создания", auto_now_add=True)
    updated_at = models.DateTimeField("Дата обновления", auto_now=True)

    certificates: QuerySet[Certificate]  # type hint для related_name

    class Meta:
        verbose_name = "Обо мне"
        verbose_name_plural = "Обо мне"
        ordering = ["order"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.pk:
            delete_old_file(self, "photo")
        super().save(*args, **kwargs)

    @property
    def experience(self):
        """Вычисляет количество лет опыта работы"""
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
    def experience_text(self):
        """Возвращает опыт работы с правильным склонением слова 'год'"""
        years = self.experience
        if years % 10 == 1 and years % 100 != 11:
            return f"{years} год"
        elif 2 <= years % 10 <= 4 and (years % 100 < 10 or years % 100 >= 20):
            return f"{years} года"
        else:
            return f"{years} лет"


class SiteSettings(models.Model):
    """Модель для хранения основных настроек сайта."""

    head_title = models.CharField(
        verbose_name="Head Title",
        max_length=100,
        default="Услуги массажа",
    )
    main_title = models.CharField(
        verbose_name="Главный заголовок",
        max_length=100,
        default="Твой массажист",
    )
    main_subtitle = models.CharField(
        verbose_name="Главный подзаголовок",
        max_length=100,
        default="Забота о Вашем здоровье",
    )
    child_massage_title = models.CharField(
        verbose_name="Детский массаж",
        max_length=100,
        default="Детский массаж",
    )
    massage_title = models.CharField(
        verbose_name="Массаж", max_length=100, default="Массаж"
    )
    about_title = models.CharField(
        verbose_name="Обо мне", max_length=100, default="Обо мне"
    )
    contact_title = models.CharField(
        verbose_name="Контакты", max_length=50, default="Контакты"
    )
    career_start_year = models.PositiveIntegerField(
        verbose_name="Год начала практики массажа",
        default=2021,
    )
    background = models.ImageField(
        upload_to=get_file_path,
        verbose_name="Фоновое изображение",
        validators=[validate_file_size],
        blank=True,
        null=True,
    )

    class Meta:
        verbose_name = "Настройки сайта"
        verbose_name_plural = "Настройки сайта"

    def __str__(self):
        return "Настройки"

    def save(self, *args, **kwargs):
        if self.pk:
            delete_old_file(self, "background")
        super().save(*args, **kwargs)


@receiver(pre_delete, sender=Certificate)
def certificate_delete_file(sender, instance, **kwargs):
    """Удаляет файл при удалении объекта Certificate"""
    if instance.image:
        instance.image.delete(False)


@receiver(pre_delete, sender=About)
def about_delete_file(sender, instance, **kwargs):
    """Удаляет файл при удалении объекта About"""
    if instance.photo:
        instance.photo.delete(False)


@receiver(pre_delete, sender=SiteSettings)
def sitesettings_delete_file(sender, instance, **kwargs):
    """Удаляет файл при удалении объекта SiteSettings"""
    if instance.background:
        instance.background.delete(False)
