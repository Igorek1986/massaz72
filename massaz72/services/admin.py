from django.contrib import admin
from django.utils.html import format_html

from .models import Category, Massage


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "image_tag", "created_at", "updated_at")
    readonly_fields = ("image_tag",)
    search_fields = ("name",)

    def image_tag(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" width="150" height="auto" />', obj.image.url
            )
        return "Нет изображения"


@admin.register(Massage)
class MassageAdmin(admin.ModelAdmin):
    prepopulated_fields = {"slug": ("name", )}
    list_display = ("name", "price", "duration_min", "duration_max", "massage_type", "order", "is_archived")
    list_filter = ("massage_type", "is_archived", "category")
    search_fields = ("name", "description")
    readonly_fields = ("created_at", "updated_at", "image_tag")
    list_editable = ("order", "is_archived")
    actions = ['archive_massages', 'unarchive_massages']

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.order_by(
            # Сначала детские (CHILD), потом взрослые (ADULT)
            '-massage_type', 'order'
        )

    def image_tag(self, obj):
        return obj.image_tag()

    def archive_massages(self, request, queryset):
        queryset.update(is_archived=True)
        self.message_user(request, f'Архивировано массажей: {queryset.count()}')
    archive_massages.short_description = 'Архивировать выбранные массажи'

    def unarchive_massages(self, request, queryset):
        queryset.update(is_archived=False)
        self.message_user(request, f'Разархивировано массажей: {queryset.count()}')
    unarchive_massages.short_description = 'Разархивировать выбранные массажи'

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "name",
                    "slug",
                    "is_archived",
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
