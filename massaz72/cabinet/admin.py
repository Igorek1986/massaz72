from django.contrib import admin

from main.models import Certificate

from .models import (
    Appointment, AppointmentSeries, BlockedSlot,
    Discount, ScheduleException, Specialist, Specialty, WorkSchedule,
)


@admin.register(Specialty)
class SpecialtyAdmin(admin.ModelAdmin):
    list_display = ("name", "order")
    list_editable = ("order",)
    search_fields = ("name",)


class CertificateInline(admin.TabularInline):
    model = Certificate
    extra = 1


@admin.register(Specialist)
class SpecialistAdmin(admin.ModelAdmin):
    inlines = [CertificateInline]
    list_display = ("name", "experience", "is_active", "order", "user")
    list_editable = ("is_active", "order")
    list_filter = ("specialty", "is_active")
    search_fields = ("name", "user__username", "user__email")
    fieldsets = (
        (None, {"fields": (
            "name", "photo", "description", "start_date",
            "specialty", "is_active", "order",
        )}),
        ("Контакты", {"fields": (
            ("telegram_username", "telegram_active"),
            ("whatsapp_number", "whatsapp_active"),
            ("max_messanger", "max_messanger_active"),
        )}),
        ("Кабинет", {"fields": (
            "user", "head", "can_manage_prices", "can_manage_reviews",
        )}),
    )


@admin.register(WorkSchedule)
class WorkScheduleAdmin(admin.ModelAdmin):
    list_display = ("specialist", "default_start", "default_end", "break_between_minutes")
    fieldsets = (
        (None, {"fields": ("specialist",)}),
        ("Рабочие дни и часы", {
            "description": "Отметьте рабочий день и при необходимости задайте его "
                           "часы. Если часы дня не заданы — берутся часы по умолчанию.",
            "fields": (
                ("monday", "monday_start", "monday_end"),
                ("tuesday", "tuesday_start", "tuesday_end"),
                ("wednesday", "wednesday_start", "wednesday_end"),
                ("thursday", "thursday_start", "thursday_end"),
                ("friday", "friday_start", "friday_end"),
                ("saturday", "saturday_start", "saturday_end"),
                ("sunday", "sunday_start", "sunday_end"),
            ),
        }),
        ("Часы по умолчанию", {"fields": (("default_start", "default_end"),)}),
        ("Перерывы", {"fields": (
            "break_between_minutes", "break_between_travel_minutes",
        )}),
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
    list_display = ("discount_type", "value", "date_from", "date_to", "description")
    list_filter = ("discount_type",)
    ordering = ("-date_from",)
