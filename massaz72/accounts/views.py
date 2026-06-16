from functools import wraps

from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from main.models import SiteSettings

from .forms import ProfileForm, RegisterForm
from .models import Client


def _cabinet_enabled() -> bool:
    s = SiteSettings.objects.first()
    return bool(s and s.client_cabinet_enabled)


def client_required(view_func):
    @wraps(view_func)
    def wrapper(request: HttpRequest, *args, **kwargs):
        if not _cabinet_enabled():
            return redirect("main:index")
        if not request.user.is_authenticated:
            return redirect(f"{reverse('accounts:login')}?next={request.path}")
        if not hasattr(request.user, "client_profile"):
            return redirect("main:index")
        return view_func(request, *args, **kwargs)
    return wrapper


def register(request: HttpRequest) -> HttpResponse:
    if not _cabinet_enabled():
        return redirect("main:index")
    if request.user.is_authenticated:
        return redirect("accounts:dashboard")

    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            phone = form.cleaned_data.get("phone", "")
            Client.objects.create(user=user, phone=phone)
            # Привязываем прежние заявки клиента по телефону.
            if phone:
                from booking.models import BookingRequest
                BookingRequest.objects.filter(
                    phone=phone, user__isnull=True
                ).update(user=user)
            # Бэкенд указываем явно: настроены axes + ModelBackend.
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            return redirect("accounts:dashboard")
    else:
        form = RegisterForm()
    return render(request, "accounts/register.html", {"form": form})


def login_view(request: HttpRequest) -> HttpResponse:
    if not _cabinet_enabled():
        return redirect("main:index")
    if request.user.is_authenticated:
        return redirect("accounts:dashboard")

    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            nxt = request.GET.get("next") or request.POST.get("next")
            return redirect(nxt or "accounts:dashboard")
    else:
        form = AuthenticationForm(request)
    return render(request, "accounts/login.html", {"form": form})


@require_POST
def logout_view(request: HttpRequest) -> HttpResponse:
    logout(request)
    return redirect("main:index")


@client_required
def dashboard(request: HttpRequest) -> HttpResponse:
    from booking.models import BookingRequest

    bookings = (
        BookingRequest.objects.filter(user=request.user)
        .select_related("service", "specialist", "appointment")
        .order_by("-created_at")
    )
    return render(request, "accounts/dashboard.html", {"bookings": bookings})


@client_required
@require_POST
def cancel_booking(request: HttpRequest, pk: int) -> HttpResponse:
    from booking.models import BookingRequest

    booking = get_object_or_404(BookingRequest, pk=pk, user=request.user)
    if booking.status == BookingRequest.Status.PENDING:
        booking.status = BookingRequest.Status.CANCELLED
        booking.save(update_fields=["status", "updated_at"])
    return redirect("accounts:dashboard")


@client_required
def profile(request: HttpRequest) -> HttpResponse:
    client = request.user.client_profile
    profile_form = ProfileForm(instance=client)
    password_form = PasswordChangeForm(request.user)

    if request.method == "POST":
        if "save_profile" in request.POST:
            profile_form = ProfileForm(request.POST, instance=client)
            if profile_form.is_valid():
                profile_form.save()
                return redirect(f"{reverse('accounts:profile')}?saved=1")
        elif "change_password" in request.POST:
            password_form = PasswordChangeForm(request.user, request.POST)
            if password_form.is_valid():
                password_form.save()
                update_session_auth_hash(request, password_form.user)
                return redirect(f"{reverse('accounts:profile')}?password=1")

    return render(request, "accounts/profile.html", {
        "profile_form": profile_form,
        "password_form": password_form,
    })
