from django.urls import path
from .views import index, cookies

app_name = "main"
urlpatterns = [
    path("", index, name="index"),
    path('cookies/', cookies, name='cookies'),
]
