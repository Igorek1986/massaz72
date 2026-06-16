import logging
from datetime import timedelta

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from main.models import SiteSettings
from reviews.spam import timing_is_human
from tgbot.models import BotSettings

from .forms import BookingForm
from .models import BookingRequest

logger = logging.getLogger(__name__)

THROTTLE_LIMIT = 5
THROTTLE_WINDOW_SECONDS = 60 * 60


def get_client_ip(request: HttpRequest) -> str | None:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _is_rate_limited(ip: str | None) -> bool:
    if not ip:
        return False
    since = timezone.now() - timedelta(seconds=THROTTLE_WINDOW_SECONDS)
    return BookingRequest.objects.filter(
        ip_address=ip, created_at__gte=since
    ).count() >= THROTTLE_LIMIT


def _booking_enabled() -> bool:
    s = SiteSettings.objects.first()
    return bool(s and s.online_booking_enabled)


def _bots_context() -> dict:
    """Ссылки на наших ботов для экрана «спасибо». Telegram сейчас, Max — задел."""
    bot_settings = BotSettings.load()
    telegram_url = None
    if bot_settings and bot_settings.bot_username:
        telegram_url = f"https://t.me/{bot_settings.bot_username}"
    return {"telegram_bot_url": telegram_url, "max_bot_url": None}


def _notify_admins(booking: BookingRequest) -> None:
    try:
        from tgbot.notifications import notify_new_booking

        notify_new_booking(booking)
    except Exception:  # noqa: BLE001
        logger.exception("Не удалось уведомить админов о заявке %s", booking.pk)


def booking_page(request: HttpRequest) -> HttpResponse:
    if not _booking_enabled():
        return redirect("main:index")

    if request.method == "POST":
        # Honeypot / time-trap — для ботов делаем вид успеха, ничего не сохраняем.
        if request.POST.get("website"):
            return _render_done(request)
        if not timing_is_human(request.POST.get("ts", "")):
            return _render_done(request)

        ip = get_client_ip(request)
        if _is_rate_limited(ip):
            return render(request, "booking/booking.html", {
                "form": BookingForm(request.POST), "throttled": True,
            })

        form = BookingForm(request.POST)
        if form.is_valid():
            booking: BookingRequest = form.save(commit=False)
            booking.ip_address = ip
            booking.source = BookingRequest.Source.GUEST
            booking.status = BookingRequest.Status.PENDING
            booking.save()
            _notify_admins(booking)
            return _render_done(request)
        return render(request, "booking/booking.html", {"form": form})

    # Предвыбор услуги, если пришли со страницы массажа (?service=<id>).
    initial = {}
    service_id = request.GET.get("service", "")
    if service_id.isdigit():
        initial["service"] = int(service_id)
    return render(request, "booking/booking.html", {"form": BookingForm(initial=initial)})


def _render_done(request: HttpRequest) -> HttpResponse:
    return render(request, "booking/booking.html", {"done": True, **_bots_context()})
