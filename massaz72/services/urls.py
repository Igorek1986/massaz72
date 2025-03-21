from django.urls import path

from .views import MassageDetailView

app_name = "services"
urlpatterns = [
    # path("<int:pk>/", MassageDetailView.as_view(), name="massage_detail"),
    path("<slug:slug>/", MassageDetailView.as_view(), name="massage_detail"),
]

