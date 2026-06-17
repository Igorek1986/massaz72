from django.contrib import admin

from .models import Client


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("user", "phone", "telegram_username", "telegram_id", "created_at")
    search_fields = ("user__username", "phone", "telegram_username")
    readonly_fields = ("created_at", "telegram_id", "telegram_username", "link_token")
