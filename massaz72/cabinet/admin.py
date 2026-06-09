from django.contrib import admin

from .models import Appointment, AppointmentSeries, BlockedSlot, Discount, ScheduleException, WorkSchedule


@admin.register(WorkSchedule)
class WorkScheduleAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not WorkSchedule.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ScheduleException)
class ScheduleExceptionAdmin(admin.ModelAdmin):
    list_display = ("exception_type", "date_from", "date_to", "note")
    list_filter = ("exception_type",)
    ordering = ("date_from",)


@admin.register(BlockedSlot)
class BlockedSlotAdmin(admin.ModelAdmin):
    list_display = ("date", "time_start", "time_end", "note")
    ordering = ("date", "time_start")


class AppointmentInline(admin.TabularInline):
    model = Appointment
    fields = ("date", "time_start", "status", "cost")
    readonly_fields = ("date", "time_start", "cost")
    extra = 0
    can_delete = False


@admin.register(AppointmentSeries)
class AppointmentSeriesAdmin(admin.ModelAdmin):
    list_display = ("__str__", "service", "total_sessions", "created_at")
    inlines = [AppointmentInline]


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ("client_name", "date", "time_start", "service", "cost", "status")
    list_filter = ("status", "date", "service")
    search_fields = ("client_name", "client_phone", "address")
    ordering = ("-date", "time_start")
    date_hierarchy = "date"


@admin.register(Discount)
class DiscountAdmin(admin.ModelAdmin):
    list_display = ("discount_type", "value", "date_from", "date_to", "description")
    ordering = ("-date_from",)
