from django.urls import path

from .views import cookies, index, privacy

app_name = "main"
urlpatterns = [
    path("", index, name="index"),
    path("cookies/", cookies, name="cookies"),
    path("privacy/", privacy, name="privacy"),
]
