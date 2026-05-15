from django.contrib import admin

from .models import About, Certificate, SiteSettings


class CertificateInline(admin.TabularInline):
    model = Certificate
    extra = 1


@admin.register(About)
class AboutAdmin(admin.ModelAdmin):
    inlines = [CertificateInline]
    list_display = ["name", "experience", "is_active", "order"]
    list_editable = ["is_active", "order"]
    fieldsets = (
        (None, {"fields": ("name", "photo", "description", "start_date", "is_active", "order")}),
        ("Контакты", {"fields": (
            ("telegram_username", "telegram_active"),
            ("whatsapp_number", "whatsapp_active"),
            ("max_messanger", "max_messanger_active"),
        )}),
    )


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    list_display = [
        "head_title",
    ]
