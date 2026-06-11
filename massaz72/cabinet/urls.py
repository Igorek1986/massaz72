from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "cabinet"

urlpatterns = [
    path("", views.index, name="index"),
    path("settings/", views.settings, name="settings"),
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="cabinet/login.html"),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),

    # HTMX partials — calendar
    path("day/<str:date_str>/", views.day_schedule, name="day_schedule"),
    path("events/", views.calendar_events, name="calendar_events"),

    # Appointment actions
    path("appointments/add/", views.appointment_add, name="appointment_add"),
    path("appointments/<int:pk>/edit/", views.appointment_edit, name="appointment_edit"),
    path("appointments/<int:pk>/status/", views.appointment_status, name="appointment_status"),
    path("appointments/<int:pk>/confirm-delete/", views.appointment_confirm_delete, name="appointment_confirm_delete"),
    path("appointments/<int:pk>/delete/", views.appointment_delete, name="appointment_delete"),
    path("appointments/<int:pk>/series-cancel-following/", views.series_cancel_following, name="series_cancel_following"),
    path("appointments/<int:pk>/series-cancel/", views.series_cancel_action, name="series_cancel_action"),
    path("appointments/<int:pk>/reschedule/", views.series_reschedule, name="series_reschedule"),

    # Prices
    path("prices/", views.prices, name="prices"),
    path("prices/save-current/", views.prices_save_current, name="prices_save_current"),
    path("prices/save-change/", views.prices_save_change, name="prices_save_change"),
    path("prices/confirm-apply/", views.prices_confirm_apply, name="prices_confirm_apply"),
    path("prices/apply-change/", views.prices_apply_change, name="prices_apply_change"),
    path("prices/discounts/add/", views.discount_add, name="discount_add"),
    path("prices/discounts/<int:pk>/edit/", views.discount_edit, name="discount_edit"),
    path("prices/discounts/<int:pk>/confirm-delete/", views.discount_confirm_delete, name="discount_confirm_delete"),
    path("prices/discounts/<int:pk>/delete/", views.discount_delete, name="discount_delete"),
    path("prices/massages/add/", views.massage_add, name="massage_add"),
    path("prices/massages/<int:pk>/edit/", views.massage_edit, name="massage_edit"),
    path("prices/massages/<int:pk>/confirm-archive/", views.massage_confirm_archive, name="massage_confirm_archive"),
    path("prices/massages/<int:pk>/toggle-archive/", views.massage_toggle_archive, name="massage_toggle_archive"),

    # Settings actions
    path("settings/schedule/", views.schedule_save, name="schedule_save"),
    path("settings/exceptions/add/", views.exception_add, name="exception_add"),
    path("settings/exceptions/<int:pk>/edit/", views.exception_edit, name="exception_edit"),
    path("settings/exceptions/<int:pk>/confirm-delete/", views.exception_confirm_delete, name="exception_confirm_delete"),
    path("settings/exceptions/<int:pk>/delete/", views.exception_delete, name="exception_delete"),
    path("settings/blocked-slots/add/", views.blocked_slot_add, name="blocked_slot_add"),
    path("settings/blocked-slots/<int:pk>/edit/", views.blocked_slot_edit, name="blocked_slot_edit"),
    path("settings/blocked-slots/<int:pk>/confirm-delete/", views.blocked_slot_confirm_delete, name="blocked_slot_confirm_delete"),
    path("settings/blocked-slots/<int:pk>/delete/", views.blocked_slot_delete, name="blocked_slot_delete"),
]
