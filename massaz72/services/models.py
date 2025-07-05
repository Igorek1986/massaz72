from django.core.exceptions import ValidationError
from django.db import models
from django.utils.safestring import mark_safe

from massaz72.utils import delete_old_file, get_file_path, validate_file_size


class Massage(models.Model):
    ADULT = "adult"
    CHILD = "child"
    MASSAGE_TYPE_CHOICES = [
        (ADULT, "Взрослый"),
        (CHILD, "Детский"),
    ]

    name = models.CharField(max_length=255, verbose_name="Название массажа")
    price = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name="Стоимость"
    )
    description = models.TextField(verbose_name="Описание", blank=True, null=True)
    duration_min = models.PositiveIntegerField(
        verbose_name="Минимальная продолжительность (в минутах)"
    )
    duration_max = models.PositiveIntegerField(
        verbose_name="Максимальная продолжительность (в минутах)"
    )
    location = models.CharField(max_length=255, verbose_name="Место проведения")
    massage_type = models.CharField(
        max_length=5,
        choices=MASSAGE_TYPE_CHOICES,
        default=CHILD,
        verbose_name="Тип массажа",
    )
    order = models.PositiveIntegerField(default=0, verbose_name="Очередность")
    slug = models.SlugField(
        max_length=200, unique=True, blank=True, null=True, verbose_name="URL"
    )
    image = models.ImageField(
        upload_to=get_file_path,
        verbose_name="Изображение",
        blank=True,
        null=True,
        validators=[validate_file_size],
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(
        auto_now=True, verbose_name="Дата последнего обновления"
    )
    is_archived = models.BooleanField("В архиве", default=False)

    class Meta:
        verbose_name = "Массаж"
        verbose_name_plural = "Массажи"
        ordering = ["-massage_type", "order"]

    def __str__(self) -> str:
        return self.name

    def image_tag(self):
        if self.image:
            return mark_safe(
                f'<img src="{self.image.url}" width="150" height="auto" />'
            )
        return "Нет изображения"

    def clean(self):
        """Валидация модели"""
        if self.price < 0:
            raise ValidationError({"price": "Цена не может быть отрицательной"})

        if self.duration_min > self.duration_max:
            raise ValidationError(
                {
                    "duration_max": "Максимальная длительность должна быть больше минимальной"
                }
            )

    def save(self, *args, **kwargs):
        if self.pk:
            delete_old_file(self, "image")
        super().save(*args, **kwargs)
