from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("register/", views.register, name="register"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("reset/", views.password_reset_request, name="password_reset"),
    path("reset/<uidb64>/<token>/", views.password_reset_confirm, name="password_reset_confirm"),
    path("profile/", views.profile, name="profile"),
    path("events/", views.events, name="events"),
    path("day/<str:date_str>/", views.day_sessions, name="day_sessions"),
    path("sessions/<int:pk>/cancel/", views.session_cancel, name="session_cancel"),
    path("sessions/<int:pk>/reschedule/", views.session_reschedule, name="session_reschedule"),
    path("bookings/<int:pk>/cancel/", views.cancel_booking, name="cancel_booking"),
]
