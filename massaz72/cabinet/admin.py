from django.contrib import admin

from .models import (
    Appointment, AppointmentSeries, BlockedSlot,
    Discount, ScheduleException, Specialist, WorkSchedule,
)


@admin.register(Specialist)
class SpecialistAdmin(admin.ModelAdmin):
    list_display = ("name", "specialty", "user")
    list_filter = ("specialty",)
    search_fields = ("name", "user__username", "user__email")


@admin.register(WorkSchedule)
class WorkScheduleAdmin(admin.ModelAdmin):
    list_display = ("specialist", "break_between_minutes")
    fieldsets = (
        (None, {"fields": ("specialist",)}),
        ("Рабочие дни", {"fields": (
            "monday", "tuesday", "wednesday", "thursday",
            "friday", "saturday", "sunday",
        )}),
        ("Настройки", {"fields": ("break_between_minutes",)}),
    )


@admin.register(ScheduleException)
class ScheduleExceptionAdmin(admin.ModelAdmin):
    list_display = ("specialist", "exception_type", "date_from", "date_to", "note")
    list_filter = ("exception_type", "specialist")
    ordering = ("date_from",)


@admin.register(BlockedSlot)
class BlockedSlotAdmin(admin.ModelAdmin):
    list_display = ("specialist", "date", "time_start", "time_end", "note")
    list_filter = ("specialist",)
    ordering = ("date", "time_start")


class AppointmentInline(admin.TabularInline):
    model = Appointment
    fields = ("date", "time_start", "status", "cost")
    readonly_fields = ("date", "time_start", "cost")
    extra = 0
    can_delete = False


@admin.register(AppointmentSeries)
class AppointmentSeriesAdmin(admin.ModelAdmin):
    list_display = ("__str__", "specialist", "service", "total_sessions", "created_at")
    list_filter = ("specialist",)
    inlines = [AppointmentInline]


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ("client_name", "specialist", "date", "time_start", "service", "cost", "status")
    list_filter = ("specialist", "status", "date", "service")
    search_fields = ("client_name", "client_phone", "address")
    ordering = ("-date", "time_start")
    date_hierarchy = "date"


@admin.register(Discount)
class DiscountAdmin(admin.ModelAdmin):
    list_display = ("specialist", "discount_type", "value", "date_from", "date_to", "description")
    list_filter = ("specialist",)
    ordering = ("-date_from",)
