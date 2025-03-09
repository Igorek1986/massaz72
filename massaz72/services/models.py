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
    name = models.CharField(max_length=255, verbose_name="Название массажа")
    price = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name="Стоимость"
    )
    description = models.TextField(verbose_name="Описание", blank=True, null=True)
    duration = models.PositiveIntegerField(verbose_name="Продолжительность (в минутах)")
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
