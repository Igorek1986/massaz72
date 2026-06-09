from django.contrib import admin, messages

from .bot import ALLOWED_UPDATES, get_bot
from .models import (
    AdminForward,
    BotAdmin,
    BotSettings,
    BookingSessionOption,
    BookingTimeSlot,
    DialogMessage,
    TelegramUser,
)


@admin.register(BotSettings)
class BotSettingsAdmin(admin.ModelAdmin):
    list_display = ["__str__", "is_enabled", "mode", "bot_username"]
    readonly_fields = ["bot_username", "webhook_url"]
    fieldsets = (
        (None, {"fields": ("token", "is_enabled", "mode", "bot_username")}),
        (
            "Webhook",
            {
                "fields": ("public_url", "webhook_url"),
                "description": (
                    "Для режима webhook укажите публичный адрес сайта и выполните "
                    "действие «Установить webhook». Для polling запускайте процесс "
                    "командой <code>manage.py runbot</code>."
                ),
            },
        ),
        ("Тексты", {"fields": ("welcome_text", "request_prompt")}),
    )
    actions = ["action_set_webhook", "action_delete_webhook", "action_check_bot"]

    @admin.display(description="Адрес webhook")
    def webhook_url(self, obj):
        return obj.webhook_url or "—"

    def has_add_permission(self, request):
        # Singleton: запрещаем добавлять, если запись уже есть.
        return not BotSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def _bot_or_warn(self, request):
        settings = BotSettings.load()
        if not settings.token:
            self.message_user(request, "Токен бота не задан.", level=messages.ERROR)
            return None, settings
        return get_bot(settings.token), settings

    @admin.action(description="Установить webhook (по адресу из настроек)")
    def action_set_webhook(self, request, queryset):
        bot, settings = self._bot_or_warn(request)
        if bot is None:
            return
        if not settings.public_url:
            self.message_user(request, "Не задан публичный адрес сайта.", level=messages.ERROR)
            return
        try:
            bot.remove_webhook()
            bot.set_webhook(
                url=settings.webhook_url,
                secret_token=settings.secret_token,
                allowed_updates=ALLOWED_UPDATES,
            )
            self.message_user(request, f"Webhook установлен: {settings.webhook_url}")
        except Exception as exc:  # noqa: BLE001
            self.message_user(request, f"Ошибка: {exc}", level=messages.ERROR)

    @admin.action(description="Удалить webhook (перейти на polling)")
    def action_delete_webhook(self, request, queryset):
        bot, _ = self._bot_or_warn(request)
        if bot is None:
            return
        try:
            bot.remove_webhook()
            self.message_user(request, "Webhook удалён.")
        except Exception as exc:  # noqa: BLE001
            self.message_user(request, f"Ошибка: {exc}", level=messages.ERROR)

    @admin.action(description="Проверить бота (getMe)")
    def action_check_bot(self, request, queryset):
        bot, settings = self._bot_or_warn(request)
        if bot is None:
            return
        try:
            me = bot.get_me()
            if settings.bot_username != me.username:
                settings.bot_username = me.username
                settings.save(update_fields=["bot_username"])
            self.message_user(request, f"OK: @{me.username} (id {me.id})")
        except Exception as exc:  # noqa: BLE001
            self.message_user(request, f"Ошибка: {exc}", level=messages.ERROR)


@admin.register(BotAdmin)
class BotAdminAdmin(admin.ModelAdmin):
    list_display = ["__str__", "telegram_id", "is_active", "created_at"]
    list_editable = ["is_active"]
    search_fields = ["name", "telegram_id"]


@admin.register(TelegramUser)
class TelegramUserAdmin(admin.ModelAdmin):
    list_display = ["display_name", "username", "telegram_id", "updated_at"]
    search_fields = ["username", "first_name", "last_name", "telegram_id"]
    readonly_fields = [f.name for f in TelegramUser._meta.fields]

    def has_add_permission(self, request):
        return False


@admin.register(BookingSessionOption)
class BookingSessionOptionAdmin(admin.ModelAdmin):
    list_display = ["__str__", "count", "is_active", "order"]
    list_editable = ["is_active", "order"]


@admin.register(BookingTimeSlot)
class BookingTimeSlotAdmin(admin.ModelAdmin):
    list_display = ["label", "is_active", "order"]
    list_editable = ["is_active", "order"]


@admin.register(DialogMessage)
class DialogMessageAdmin(admin.ModelAdmin):
    list_display = ["created_at", "direction", "user", "text"]
    list_filter = ["direction"]
    search_fields = ["text", "user__username", "user__telegram_id"]
    readonly_fields = [f.name for f in DialogMessage._meta.fields]

    def has_add_permission(self, request):
        return False
