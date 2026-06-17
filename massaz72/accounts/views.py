from datetime import datetime
from functools import wraps

from django.contrib.auth import (
    get_user_model, login, logout, update_session_auth_hash,
)
from django.contrib.auth.forms import (
    AuthenticationForm, PasswordChangeForm, SetPasswordForm,
)
from django.contrib.auth.tokens import default_token_generator
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
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

    # Заявки без подтверждённой записи (на подтверждении/отклонённые) — отдельным
    # списком; подтверждённые сеансы показываются в календаре и день-панели.
    requests = (
        BookingRequest.objects.filter(user=request.user, appointment__isnull=True)
        .exclude(status=BookingRequest.Status.CONFIRMED)
        .select_related("service", "specialist", "sessions")
        .order_by("-created_at")
    )
    has_sessions = _client_appointment_qs(request.user).exists()
    return render(request, "accounts/dashboard.html", {
        "requests": requests,
        "has_sessions": has_sessions,
        "today": timezone.localdate().isoformat(),
    })


def _client_appointment_qs(user):
    """Все записи клиента (через его заявки и серии)."""
    from booking.models import BookingRequest
    from cabinet.models import Appointment

    apt_ids = set()
    qs = (
        BookingRequest.objects.filter(user=user, appointment__isnull=False)
        .select_related("appointment__series")
    )
    for b in qs:
        apt = b.appointment
        if apt.series_id:
            apt_ids.update(apt.series.appointments.values_list("id", flat=True))
        else:
            apt_ids.add(apt.id)
    return Appointment.objects.filter(id__in=apt_ids)


def _telegram_bot_url() -> str | None:
    from tgbot.models import BotSettings
    s = BotSettings.load()
    if s and s.is_enabled and s.bot_username:
        return f"https://t.me/{s.bot_username}"
    return None


def _day_panel(request: HttpRequest, day) -> HttpResponse:
    from cabinet.models import Specialist

    sessions = list(
        _client_appointment_qs(request.user)
        .filter(date=day)
        .select_related("service", "specialist")
        .order_by("time_start")
    )
    today = timezone.localdate()
    for a in sessions:
        # Отменять/переносить можно только будущие запланированные сеансы.
        a.can_edit = a.date > today and a.status == "scheduled"
        a.has_pending_reschedule = a.reschedule_requests.filter(status="pending").exists()
    return render(request, "accounts/partials/day_panel.html", {
        "day": day,
        "sessions": sessions,
        "telegram_bot_url": _telegram_bot_url(),
        "multiple_specialists": Specialist.objects.filter(is_active=True).count() > 1,
    })


@client_required
def events(request: HttpRequest) -> JsonResponse:
    """События календаря: на каждый день — плашка с количеством сеансов."""
    from collections import Counter

    counts = Counter()
    for a in _client_appointment_qs(request.user).exclude(status="cancelled"):
        counts[a.date] += 1

    events_data = []
    for day, count in counts.items():
        events_data.append({
            "start": day.isoformat(),
            "title": f"{count} зап." if count != 1 else "1 зап.",
            "allDay": True,
            "backgroundColor": "#3b82f6",
            "borderColor": "#2563eb",
            "textColor": "#fff",
            "classNames": ["fc-apt-count"],
        })
    return JsonResponse(events_data, safe=False)


def _parse_date(date_str):
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


@client_required
def day_sessions(request: HttpRequest, date_str: str) -> HttpResponse:
    day = _parse_date(date_str)
    if day is None:
        return HttpResponse("Неверная дата", status=400)
    return _day_panel(request, day)


@client_required
@require_POST
def session_cancel(request: HttpRequest, pk: int) -> HttpResponse:
    from booking.services import cancel_appointment

    appt = get_object_or_404(_client_appointment_qs(request.user), pk=pk)
    if appt.date > timezone.localdate() and appt.status == "scheduled":
        cancel_appointment(appt)
        try:
            from tgbot.notifications import notify_master_cancel
            notify_master_cancel(appt)
        except Exception:  # noqa: BLE001
            pass
    return _day_panel(request, appt.date)


@client_required
def session_reschedule(request: HttpRequest, pk: int) -> HttpResponse:
    from booking.services import request_reschedule

    appt = get_object_or_404(_client_appointment_qs(request.user), pk=pk)
    editable = appt.date > timezone.localdate() and appt.status == "scheduled"
    if not editable:
        return _day_panel(request, appt.date)

    error = None
    if request.method == "POST":
        new_date = _parse_date(request.POST.get("new_date", ""))
        try:
            new_time = datetime.strptime(request.POST.get("new_time", ""), "%H:%M").time()
        except (ValueError, TypeError):
            new_time = None
        if new_date and new_time and new_date > timezone.localdate():
            req = request_reschedule(appt, new_date, new_time)
            try:
                from tgbot.notifications import notify_master_reschedule
                notify_master_reschedule(req)
            except Exception:  # noqa: BLE001
                pass
            return _day_panel(request, appt.date)
        error = "Укажите корректные новые дату (в будущем) и время."

    return render(request, "accounts/partials/reschedule_form.html", {
        "appt": appt, "error": error,
    })


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

    # У PasswordChangeForm поле «Старый пароль» по умолчанию с autofocus —
    # из-за него после сохранения профиля браузер прыгает в смену пароля.
    password_form.fields["old_password"].widget.attrs.pop("autofocus", None)
    return render(request, "accounts/profile.html", {
        "profile_form": profile_form,
        "password_form": password_form,
        "client": client,
        **_telegram_link_context(client),
    })


def password_reset_request(request: HttpRequest) -> HttpResponse:
    """Запрос сброса пароля: ссылка отправляется в Telegram (если привязан)."""
    if not _cabinet_enabled():
        return redirect("main:index")

    status = None  # sent | no_telegram | not_found
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        user = get_user_model().objects.filter(username=username).first()
        if user is None or not hasattr(user, "client_profile"):
            status = "not_found"
        elif not user.client_profile.telegram_id:
            status = "no_telegram"
        else:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            url = request.build_absolute_uri(
                reverse("accounts:password_reset_confirm", args=[uid, token])
            )
            try:
                from tgbot.notifications import send_password_reset
                send_password_reset(user.client_profile.telegram_id, url)
            except Exception:  # noqa: BLE001
                pass
            status = "sent"
    return render(request, "accounts/password_reset.html", {"status": status})


def password_reset_confirm(request: HttpRequest, uidb64: str, token: str) -> HttpResponse:
    """Установка нового пароля по ссылке из Telegram."""
    if not _cabinet_enabled():
        return redirect("main:index")

    user = None
    try:
        uid = urlsafe_base64_decode(uidb64).decode()
        user = get_user_model().objects.get(pk=uid)
    except Exception:  # noqa: BLE001
        user = None

    if user is None or not default_token_generator.check_token(user, token):
        return render(request, "accounts/password_reset_confirm.html", {"invalid": True})

    if request.method == "POST":
        form = SetPasswordForm(user, request.POST)
        if form.is_valid():
            form.save()
            return redirect(f"{reverse('accounts:login')}?reset=1")
    else:
        form = SetPasswordForm(user)
    return render(request, "accounts/password_reset_confirm.html", {"form": form})


def _telegram_link_context(client) -> dict:
    """deep-link и QR для привязки аккаунта к боту."""
    from tgbot.models import BotSettings

    s = BotSettings.load()
    if not (s and s.is_enabled and s.bot_username):
        return {"tg_link": None, "tg_qr": None}
    link = f"https://t.me/{s.bot_username}?start=acc_{client.link_token}"
    from booking.views import _qr_svg
    return {"tg_link": link, "tg_qr": _qr_svg(link)}
