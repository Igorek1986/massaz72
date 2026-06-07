from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from main.models import SiteSettings

from .models import Massage


@admin.register(Massage)
class MassageAdmin(admin.ModelAdmin):
    prepopulated_fields = {"slug": ("name", )}
    list_display = ("name", "price", "new_price", "duration_min", "duration_max", "massage_type", "order", "is_archived")
    list_filter = ("massage_type", "is_archived")
    search_fields = ("name", "description")
    readonly_fields = ("created_at", "updated_at", "image_tag", "new_price_applies_from")
    list_editable = ("order", "is_archived")
    actions = ['archive_massages', 'unarchive_massages']

    @admin.display(description="Новая цена применится с")
    def new_price_applies_from(self, obj):
        """Подсказывает глобальную дату изменения цен (SiteSettings)."""
        settings_obj = SiteSettings.objects.first()
        change_date = settings_obj.price_change_date if settings_obj else None
        if change_date:
            return format_html("<b>{}</b>", change_date.strftime("%d.%m.%Y"))
        url = reverse("admin:main_sitesettings_changelist")
        return format_html(
            'Дата не задана — укажите её в <a href="{}">Настройках сайта</a>.', url
        )

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.order_by(
            # Сначала детские (CHILD), потом взрослые (ADULT)
            '-massage_type', 'order'
        )

    def image_tag(self, obj):
        return obj.image_tag()

    @admin.action(description="Архивировать выбранные массажи")
    def archive_massages(self, request, queryset):
        queryset.update(is_archived=True)
        self.message_user(request, f'Архивировано массажей: {queryset.count()}')

    @admin.action(description="Разархивировать выбранные массажи")
    def unarchive_massages(self, request, queryset):
        queryset.update(is_archived=False)
        self.message_user(request, f'Разархивировано массажей: {queryset.count()}')

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "name",
                    "slug",
                    "is_archived",
                    "price",
                    "new_price",
                    "new_price_applies_from",
                    "order",
                    "description",
                    "duration_min",
                    "duration_max",
                    "massage_type",
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
