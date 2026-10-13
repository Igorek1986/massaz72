from django.urls import path
from django.views.generic import RedirectView

from .views import cookies, index, privacy

app_name = "main"
urlpatterns = [
    path("", index, name="index"),
    path("cookies/", cookies, name="cookies"),
    path("privacy/", privacy, name="privacy"),
    # Старый адрес: единая политика теперь на /privacy/ (имя маршрута сохранено
    # для обратной совместимости).
    path(
        "personal-data/",
        RedirectView.as_view(pattern_name="main:privacy", permanent=True),
        name="personal_data",
    ),
]
