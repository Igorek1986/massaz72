"""Тихие часы и адресная доставка автоуведомлений.

Окно по умолчанию 08:00–21:00 (SiteSettings; у клиента может быть своё).
Сообщение, выпавшее вне окна, откладывается в PendingNotification и
отправляется flush-задачей, когда окно открывается. Тихие часы действуют
только на автоуведомления (не на живую переписку мастер↔клиент).
"""

from datetime import time, timedelta

from django.utils import timezone


def global_window():
    from main.models import SiteSettings
    s = SiteSettings.objects.first()
    if s and s.notify_start and s.notify_end:
        return s.notify_start, s.notify_end
    return time(8, 0), time(21, 0)


def client_window(telegram_id):
    """Окно уведомлений клиента по его telegram_id (или глобальное)."""
    if telegram_id is not None:
        from accounts.models import Client
        c = Client.objects.filter(telegram_id=telegram_id).first()
        if c and c.notify_start and c.notify_end:
            return c.notify_start, c.notify_end
    return global_window()


def master_window(booking_id):
    """Окно уведомлений мастера заявки (его личное или глобальное)."""
    from booking.models import BookingRequest
    b = (
        BookingRequest.objects.filter(pk=booking_id)
        .select_related("specialist__schedule").first()
    )
    spec = b.specialist if b else None
    schedule = getattr(spec, "schedule", None) if spec else None
    if schedule and schedule.notify_start and schedule.notify_end:
        return schedule.notify_start, schedule.notify_end
    return global_window()


def is_open(now, start, end) -> bool:
    t = now.time()
    if start <= end:
        return start <= t < end
    return t >= start or t < end  # окно через полночь


def next_open(now, start, end):
    if is_open(now, start, end):
        return now
    start_dt = now.replace(hour=start.hour, minute=start.minute, second=0, microsecond=0)
    if now.time() < start:
        return start_dt
    return start_dt + timedelta(days=1)


def _window_for(kind, payload):
    if kind == "client_text":
        return client_window(payload.get("telegram_id"))
    if kind in ("new_booking", "booking_reminder"):
        return master_window(payload.get("booking_id"))
    return global_window()


def _dispatch(kind, payload) -> None:
    """Фактическая отправка автоуведомления по типу."""
    from .bot import get_bot

    bot = get_bot()
    if bot is None:
        return
    if kind == "new_booking":
        from booking.models import BookingRequest

        from .notifications import send_booking_to_admins
        b = BookingRequest.objects.filter(pk=payload.get("booking_id")).first()
        if b is not None:
            send_booking_to_admins(bot, b)
    elif kind == "booking_reminder":
        from booking.models import BookingRequest

        from .notifications import send_booking_reminder
        b = BookingRequest.objects.filter(pk=payload.get("booking_id")).first()
        if b is not None:
            send_booking_reminder(bot, b)
    elif kind == "client_text":
        try:
            bot.send_message(payload["telegram_id"], payload["text"])
        except Exception:  # noqa: BLE001
            pass


def notify(kind, payload, *, now=None) -> None:
    """Отправить автоуведомление сейчас (если окно открыто) или отложить."""
    now = now or timezone.localtime()
    start, end = _window_for(kind, payload)
    if is_open(now, start, end):
        _dispatch(kind, payload)
    else:
        from .models import PendingNotification
        PendingNotification.objects.create(
            kind=kind, payload=payload, available_at=next_open(now, start, end),
        )


def flush_due(*, now=None) -> int:
    """Отправляет отложенные уведомления, у которых наступило окно."""
    from .models import PendingNotification

    now = now or timezone.localtime()
    sent = 0
    for pn in PendingNotification.objects.filter(sent=False, available_at__lte=now):
        start, end = _window_for(pn.kind, pn.payload)
        if not is_open(now, start, end):
            # Окно ещё/уже закрыто (напр. воркер стоял) — перенесём на ближайшее.
            pn.available_at = next_open(now, start, end)
            pn.save(update_fields=["available_at"])
            continue
        _dispatch(pn.kind, pn.payload)
        pn.sent = True
        pn.save(update_fields=["sent"])
        sent += 1
    return sent
