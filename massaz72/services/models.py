from django.db import models
from django.utils.safestring import mark_safe


class Category(models.Model):
    name = models.CharField(max_length=255, verbose_name="Название категории")
    image = models.ImageField(
        upload_to="category_images/",
        verbose_name="Изображение категории",
        blank=True,
        null=True,
    )
    description = models.TextField(verbose_name="Описание", blank=True, null=True)

    def __str__(self):
        return self.name

    def image_tag(self):
        if self.image:
            return mark_safe(
                f'<img src="{self.image.url}" width="150" height="auto" />'
            )
        return "Нет изображения"

    class Meta:

        verbose_name = "Категория"
        verbose_name_plural = "Категории"


class Massage(models.Model):
    ADULT = 'adult'
    CHILD = 'child'
    MASSAGE_TYPE_CHOICES = [
        (ADULT, 'Взрослый'),
        (CHILD, 'Детский'),
    ]

    name = models.CharField(max_length=255, verbose_name="Название массажа")
    price = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name="Стоимость"
    )
    description = models.TextField(verbose_name="Описание", blank=True, null=True)
    duration_min = models.PositiveIntegerField(verbose_name="Минимальная продолжительность (в минутах)")
    duration_max = models.PositiveIntegerField(verbose_name="Максимальная продолжительность (в минутах)")
    # duration = models.PositiveIntegerField(verbose_name="Продолжительность (в минутах)")
    massage_type = models.CharField(
        max_length=5,
        choices=MASSAGE_TYPE_CHOICES,
        default=CHILD,
        verbose_name="Тип массажа"
    )
    order = models.PositiveIntegerField(default=0, verbose_name="Очередность")
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        verbose_name="Категория",
        blank=True,
        null=True,
    )
    image = models.ImageField(
        upload_to="massage_images/", verbose_name="Изображение", blank=True, null=True
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(
        auto_now=True, verbose_name="Дата последнего обновления"
    )

    def __str__(self) -> str:
        return self.name

    def image_tag(self):
        if self.image:
            return mark_safe(
                f'<img src="{self.image.url}" width="150" height="auto" />'
            )
        return "Нет изображения"

    class Meta:
        verbose_name = "Массаж"
        verbose_name_plural = "Массажи"
        ordering = ['massage_type', 'order']  # Сортировка по типу и очередности
