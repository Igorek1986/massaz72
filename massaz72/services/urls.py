from django.urls import path

from .views import home

appname = "services"
urlpatterns = [
    path("", home, name="index"),
]
