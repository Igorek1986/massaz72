from django.urls import path

from . import views

app_name = "booking"

urlpatterns = [
    path("", views.booking_page, name="page"),
    path("slots/", views.booking_slots, name="slots"),
    path("month/", views.booking_month, name="month"),
    path("sessions/", views.booking_sessions, name="sessions"),
    path("confirm/<str:token>/", views.booking_confirm, name="confirm"),
    path("status/<str:token>/", views.booking_status, name="status"),
]
