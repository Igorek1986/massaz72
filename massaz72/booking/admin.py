from django.contrib import admin

from .models import BookingRequest, BookingSessionOption, RescheduleRequest


@admin.register(RescheduleRequest)
class RescheduleRequestAdmin(admin.ModelAdmin):
    list_display = ("appointment", "new_date", "new_time", "status", "created_at")
    list_filter = ("status",)


@admin.register(BookingSessionOption)
class BookingSessionOptionAdmin(admin.ModelAdmin):
    list_display = ("__str__", "specialist", "count", "is_active", "order")
    list_editable = ("is_active", "order")
    list_filter = ("specialist", "is_active")


@admin.register(BookingRequest)
class BookingRequestAdmin(admin.ModelAdmin):
    list_display = (
        "client_name", "phone", "service", "specialist",
        "preferred_date", "preferred_time", "status", "source", "created_at",
    )
    list_filter = ("status", "source", "specialist")
    search_fields = ("client_name", "phone", "comment")
    readonly_fields = ("ip_address", "appointment", "created_at", "updated_at")
    list_per_page = 50
    actions = ["mark_declined"]

    @admin.action(description="Отклонить выбранные заявки")
    def mark_declined(self, request, queryset):
        updated = queryset.update(status=BookingRequest.Status.DECLINED)
        self.message_user(request, f"Отклонено заявок: {updated}.")
