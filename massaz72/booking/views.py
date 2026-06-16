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


def _qr_svg(data: str) -> str:
    """QR-код как inline-SVG (без внешних сервисов, без Pillow)."""
    import io

    import qrcode
    import qrcode.image.svg

    img = qrcode.make(data, image_factory=qrcode.image.svg.SvgPathImage, box_size=10)
    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue().decode()


def _bots_context(booking: BookingRequest | None = None) -> dict:
    """Ссылки на наших ботов для экрана «спасибо». Если есть заявка — даём
    deep-link с токеном привязки и QR (Telegram сейчас, Max — задел)."""
    bot_settings = BotSettings.load()
    username = (
        bot_settings.bot_username
        if bot_settings and bot_settings.is_enabled and bot_settings.bot_username
        else ""
    )
    if not username:
        return {"telegram_bot_url": None, "telegram_qr_svg": None, "max_bot_url": None}

    if booking is not None:
        url = f"https://t.me/{username}?start={booking.link_token}"
    else:
        url = f"https://t.me/{username}"
    return {
        "telegram_bot_url": url,
        "telegram_qr_svg": _qr_svg(url),
        "max_bot_url": None,
    }


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
            booking.status = BookingRequest.Status.PENDING
            # Залогиненный клиент — привязываем заявку к аккаунту.
            if request.user.is_authenticated and hasattr(request.user, "client_profile"):
                booking.user = request.user
                booking.source = BookingRequest.Source.ACCOUNT
            else:
                booking.source = BookingRequest.Source.GUEST
            booking.save()
            _notify_admins(booking)
            return _render_done(request, booking)
        return render(request, "booking/booking.html", {"form": form})

    # Предвыбор услуги, если пришли со страницы массажа (?service=<id>).
    initial = {}
    service_id = request.GET.get("service", "")
    if service_id.isdigit():
        initial["service"] = int(service_id)
    # Для залогиненного клиента подставляем телефон из профиля.
    if request.user.is_authenticated and hasattr(request.user, "client_profile"):
        initial.setdefault("phone", request.user.client_profile.phone)
    return render(request, "booking/booking.html", {"form": BookingForm(initial=initial)})


def _render_done(request: HttpRequest, booking: BookingRequest | None = None) -> HttpResponse:
    return render(request, "booking/booking.html", {"done": True, **_bots_context(booking)})
