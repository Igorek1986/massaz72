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


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    list_display = [
        "head_title",
    ]
