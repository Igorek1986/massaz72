import logging
from datetime import timedelta

from django.http import HttpRequest, HttpResponse, JsonResponse
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


def _service_durations() -> dict:
    """Текст длительности по id услуги — для подсказки в форме (JS)."""
    from services.models import Massage

    out = {}
    for m in Massage.objects.filter(is_archived=False).only("pk", "duration_min", "duration_max"):
        lo, hi = m.duration_min, m.duration_max
        if lo and hi and lo != hi:
            out[str(m.pk)] = f"{lo}–{hi} мин"
        else:
            out[str(m.pk)] = f"{hi or lo or 60} мин"
    return out


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
                "service_durations": _service_durations(),
            })

        form = BookingForm(request.POST)
        if form.is_valid():
            booking: BookingRequest = form.save(commit=False)
            booking.ip_address = ip
            # Залогиненный клиент — привязываем заявку к аккаунту.
            if request.user.is_authenticated and hasattr(request.user, "client_profile"):
                booking.user = request.user
                booking.source = BookingRequest.Source.ACCOUNT
                # Нет телефона в форме — берём из профиля аккаунта.
                if not booking.phone:
                    booking.phone = (request.user.client_profile.phone or "").strip()
            else:
                booking.source = BookingRequest.Source.GUEST
            # Гейт по контакту: с телефоном — сразу «на подтверждении» и
            # уведомляем мастера. Без телефона — «ожидает контакта», мастеру не
            # показываем и не шлём, пока клиент не подтвердит в боте
            # (см. tgbot: подтверждение переключит статус и уведомит мастера).
            if booking.phone:
                booking.status = BookingRequest.Status.PENDING
            else:
                booking.status = BookingRequest.Status.AWAITING_CONTACT
            booking.save()
            if booking.phone:
                _notify_admins(booking)
            # PRG: уводим на закладываемую страницу подтверждения по токену.
            return redirect("booking:confirm", token=booking.link_token)
        return render(request, "booking/booking.html", {
            "form": form, "service_durations": _service_durations(),
        })

    # Предвыбор услуги (?service=<id>) и даты (?date=YYYY-MM-DD) — из кабинета.
    initial = {}
    service_id = request.GET.get("service", "")
    if service_id.isdigit():
        initial["service"] = int(service_id)
    raw_date = request.GET.get("date", "")
    if raw_date:
        from datetime import datetime
        try:
            d = datetime.strptime(raw_date, "%Y-%m-%d").date()
            if d >= timezone.localdate():
                initial["preferred_date"] = d
        except ValueError:
            pass
    # Для залогиненного клиента подставляем телефон из профиля.
    if request.user.is_authenticated and hasattr(request.user, "client_profile"):
        initial.setdefault("phone", request.user.client_profile.phone)
    return render(request, "booking/booking.html", {
        "form": BookingForm(initial=initial),
        "service_durations": _service_durations(),
    })


def _render_done(request: HttpRequest, booking: BookingRequest | None = None) -> HttpResponse:
    context = {"done": True, **_bots_context(booking)}
    if booking is not None:
        context["booking_token"] = booking.link_token
        # Без телефона бронь держится ограниченное время до подтверждения в боте.
        if booking.status == BookingRequest.Status.AWAITING_CONTACT:
            s = SiteSettings.objects.first()
            context["hold_minutes"] = s.booking_hold_minutes if s else 15
    return render(request, "booking/booking.html", context)


def booking_slots(request: HttpRequest) -> JsonResponse:
    """Свободные времена начала для выбранного мастера/услуги/даты/курса.

    GET-параметры: specialist, service, date (YYYY-MM-DD), sessions
    (id BookingSessionOption). Возвращает day_availability (с автопереносом
    на ближайший доступный день, если запрошенный недоступен)."""
    from datetime import datetime as _dt

    from cabinet.models import Specialist

    from .availability import day_availability
    from .models import BookingSessionOption

    if not _booking_enabled():
        return JsonResponse({"slots": [], "shifted": False})

    raw_date = request.GET.get("date", "")
    try:
        day = _dt.strptime(raw_date, "%Y-%m-%d").date()
    except ValueError:
        return JsonResponse({"error": "bad_date", "slots": []}, status=400)
    if day < timezone.localdate():
        day = timezone.localdate()

    spec_id = request.GET.get("specialist", "")
    specialist = None
    if spec_id.isdigit():
        specialist = Specialist.objects.filter(pk=int(spec_id), is_active=True).first()
    if specialist is None:
        specialist = Specialist.objects.filter(is_active=True).first()

    service = None
    service_id = request.GET.get("service", "")
    if service_id.isdigit():
        from services.models import Massage
        service = Massage.objects.filter(pk=int(service_id), is_archived=False).first()

    sessions = 1
    sessions_id = request.GET.get("sessions", "")
    if sessions_id.isdigit():
        opt = BookingSessionOption.objects.filter(pk=int(sessions_id), is_active=True).first()
        if opt:
            sessions = opt.count

    is_travel = request.GET.get("travel") in ("1", "true", "on")
    return JsonResponse(
        day_availability(specialist, day, service, sessions, is_travel=is_travel)
    )


def booking_month(request: HttpRequest) -> JsonResponse:
    """Доступные для выбора даты в месяце (рабочие, не выходные/отпуск, не в прошлом).

    GET-параметры: specialist, year, month. Используется календарём на странице
    записи, чтобы нерабочие дни были некликабельны."""
    import calendar as _calendar
    from datetime import date as _date

    from cabinet.models import Specialist

    from .availability import enabled_days

    if not _booking_enabled():
        return JsonResponse({"enabled": []})

    try:
        year = int(request.GET.get("year", ""))
        month = int(request.GET.get("month", ""))
        if not (1 <= month <= 12 and 2000 <= year <= 2100):
            raise ValueError
    except ValueError:
        return JsonResponse({"error": "bad_month", "enabled": []}, status=400)

    spec_id = request.GET.get("specialist", "")
    specialist = None
    if spec_id.isdigit():
        specialist = Specialist.objects.filter(pk=int(spec_id), is_active=True).first()
    if specialist is None:
        specialist = Specialist.objects.filter(is_active=True).first()

    first = _date(year, month, 1)
    last = _date(year, month, _calendar.monthrange(year, month)[1])
    days = enabled_days(specialist, first, last)
    return JsonResponse({
        "year": year,
        "month": month,
        "today": timezone.localdate().isoformat(),
        "enabled": [d.isoformat() for d in days],
    })


def booking_sessions(request: HttpRequest) -> JsonResponse:
    """Варианты количества сеансов выбранного мастера (для формы записи)."""
    from cabinet.models import Specialist

    from .models import BookingSessionOption

    if not _booking_enabled():
        return JsonResponse({"options": []})

    spec_id = request.GET.get("specialist", "")
    specialist = None
    if spec_id.isdigit():
        specialist = Specialist.objects.filter(pk=int(spec_id), is_active=True).first()
    if specialist is None:
        specialist = Specialist.objects.filter(is_active=True).first()

    options = []
    if specialist is not None:
        options = [
            {"id": o.pk, "label": o.button_label}
            for o in BookingSessionOption.objects.filter(
                specialist=specialist, is_active=True
            )
        ]
    return JsonResponse({"options": options})


def _booking_hold_minutes() -> int:
    s = SiteSettings.objects.first()
    return s.booking_hold_minutes if s else 15


def _booking_deadline(booking: BookingRequest):
    return booking.created_at + timedelta(minutes=_booking_hold_minutes())


def _booking_expired(booking: BookingRequest) -> bool:
    """Заявка без контакта, у которой истёк таймаут удержания (слот уже свободен)."""
    return (
        booking.status == BookingRequest.Status.AWAITING_CONTACT
        and timezone.now() >= _booking_deadline(booking)
    )


def _confirm_context(booking: BookingRequest | None) -> dict:
    """Состояние страницы подтверждения по токену."""
    if booking is None or _booking_expired(booking):
        return {"state": "expired"}
    S = BookingRequest.Status
    if booking.status == S.CONFIRMED:
        state = "master_confirmed"
    elif booking.status in (S.DECLINED, S.CANCELLED):
        state = "closed"
    elif booking.status == S.PENDING:
        state = "pending"  # есть контакт (телефон или подтверждение в боте)
    else:
        state = "awaiting"  # ждём подтверждения/контакта
    ctx = {
        "state": state,
        "booking": booking,
        "booking_token": booking.link_token,
        **_bots_context(booking),
    }
    if state == "awaiting":
        ctx["hold_minutes"] = _booking_hold_minutes()
        ctx["deadline_iso"] = _booking_deadline(booking).isoformat()
    return ctx


def booking_confirm(request: HttpRequest, token: str) -> HttpResponse:
    """Страница подтверждения заявки по токену (доступна без регистрации,
    закладываемая, восстанавливается на том же устройстве через localStorage)."""
    booking = (
        BookingRequest.objects.select_related("service", "specialist", "sessions")
        .filter(link_token=token).first()
    )

    if request.method == "POST":
        if booking is None:
            return redirect("booking:confirm", token=token)

        # Отмена клиентом: освобождает слот, чтобы перезаписаться (напр. сдвинуть
        # время). Доступна, пока мастер не подтвердил.
        if request.POST.get("action") == "cancel":
            S = BookingRequest.Status
            if booking.status in (S.AWAITING_CONTACT, S.PENDING):
                booking.status = S.CANCELLED
                booking.save(update_fields=["status", "updated_at"])
                try:
                    from tgbot.notifications import notify_booking_cancelled
                    notify_booking_cancelled(booking)
                except Exception:  # noqa: BLE001
                    logger.exception("Не уведомить об отмене заявки %s", booking.pk)
            return redirect("booking:confirm", token=token)

        # Подтверждение телефоном прямо на странице (третий способ).
        if booking.status != BookingRequest.Status.AWAITING_CONTACT \
                or _booking_expired(booking):
            return redirect("booking:confirm", token=token)
        from .phone import normalize_ru_phone
        try:
            phone = normalize_ru_phone(request.POST.get("phone"))
        except ValueError:
            phone = ""
        if not phone:
            ctx = _confirm_context(booking)
            ctx["phone_error"] = "Укажите корректный номер телефона."
            return render(request, "booking/confirm.html", ctx)
        booking.phone = phone
        booking.status = BookingRequest.Status.PENDING
        booking.save(update_fields=["phone", "status", "updated_at"])
        _notify_admins(booking)
        return redirect("booking:confirm", token=token)

    return render(request, "booking/confirm.html", _confirm_context(booking))


def booking_status(request: HttpRequest, token: str) -> JsonResponse:
    """Статус заявки по токену (для опроса и обратного отсчёта)."""
    booking = BookingRequest.objects.filter(link_token=token).first()
    if booking is None:
        return JsonResponse({"found": False})
    expired = _booking_expired(booking)
    seconds_left = None
    if booking.status == BookingRequest.Status.AWAITING_CONTACT and not expired:
        seconds_left = max(
            0, int((_booking_deadline(booking) - timezone.now()).total_seconds())
        )
    return JsonResponse({
        "found": not expired,  # истёкшую для UI считаем отсутствующей
        "status": booking.status,
        "linked": bool(booking.messenger_user_id),
        "confirmed": booking.client_confirmed,
        "master_confirmed": booking.status == BookingRequest.Status.CONFIRMED,
        "seconds_left": seconds_left,
    })
