from django.contrib import admin
from django.utils.html import format_html

from .models import Category, Massage


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "image_tag", "description")
    search_fields = ("name", "description")

    def image_tag(self, obj):
        if obj.image:

            return format_html(
                '<img src="{}" width="150" height="auto" />', obj.image.url
            )
        return "Нет изображения"


@admin.register(Massage)
class MassageAdmin(admin.ModelAdmin):
    prepopulated_fields = {"slug": ("name", )}
    list_display = ("name", "order", "price", "duration_min", "duration_max", "category")
    list_filter = ("category",)
    search_fields = ("name", "description")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "name",
                    "slug",
                    "price",
                    "order",
                    "description",
                    "duration_min",
                    "duration_max",
                    "massage_type",
                    "category",
                    "image",
                )
            },
        ),
        (
            "Даты",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),  # Сворачиваемый блок
            },
        ),
    )

    def image_tag(self, obj):
        return obj.image_tag()
