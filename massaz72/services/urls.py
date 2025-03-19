from django.urls import path

from .views import MassageDetailView, home

app_name = "services"
urlpatterns = [
    path("", home, name="index"),
    path("massage/<int:pk>/", MassageDetailView.as_view(), name="massage_detail"),
]
