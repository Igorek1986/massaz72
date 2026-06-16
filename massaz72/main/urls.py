from django.urls import path

from .views import cookies, index, personal_data, privacy

app_name = "main"
urlpatterns = [
    path("", index, name="index"),
    path("cookies/", cookies, name="cookies"),
    path("privacy/", privacy, name="privacy"),
    path("personal-data/", personal_data, name="personal_data"),
]
