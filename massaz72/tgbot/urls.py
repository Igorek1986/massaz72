from django.urls import path

from . import views

app_name = "tgbot"

urlpatterns = [
    path("tg/webhook/<str:secret_path>/", views.webhook, name="webhook"),
]
