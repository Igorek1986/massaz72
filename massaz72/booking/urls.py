from django.urls import path

from . import views

app_name = "booking"

urlpatterns = [
    path("", views.booking_page, name="page"),
    path("status/<str:token>/", views.booking_status, name="status"),
]
