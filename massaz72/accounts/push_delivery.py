"""Очередь Web Push в БД. Сетевые запросы выполняет qcluster."""

import logging
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import DatabaseError, transaction
from django.db.models import Q
from django.utils import timezone

from booking.models import BookingRequest
from cabinet.models import Specialist
from main.models import SiteSettings
from tgbot.notify import global_window, is_open, master_window, next_open

from . import web_push
from .models import PushDelivery, PushSubscription
from .permissions import BOOKING_ADMIN_PERMISSIONS, is_booking_admin

logger = logging.getLogger(__name__)
Kind = PushDelivery.Kind
Status = BookingRequest.Status
EXPECTED_STATUS = {
    Kind.NEW_BOOKING: Status.PENDING,
    Kind.BOOKING_CONFIRMED: Status.CONFIRMED,
    Kind.BOOKING_DECLINED: Status.DECLINED,
}


def enabled_for_client():
    return SiteSettings.objects.filter(client_cabinet_enabled=True).exists()


def eligible(user):
    if not user.is_active or hasattr(user, "account_erasure_request"):
        return False
    specialist = getattr(user, "specialist", None)
    return bool(
        (specialist and specialist.is_active)
        or is_booking_admin(user)
        or (hasattr(user, "client_profile") and enabled_for_client())
    )


def _recipients(booking, kind):
    users = get_user_model().objects
    if kind == Kind.NEW_BOOKING:
        specialists = Specialist.objects.filter(is_active=True, user__is_active=True)
        if booking.specialist_id:
            specialists = specialists.filter(pk__in=[booking.specialist_id, booking.specialist.head_id])
        view, change = (
            users.with_perm(permission, backend="django.contrib.auth.backends.ModelBackend")
            for permission in BOOKING_ADMIN_PERMISSIONS
        )
        admins = users.filter(is_staff=True).exclude(specialist__is_active=True).filter(
            Q(pk__in=view) | Q(pk__in=change),
        )
        return users.filter(Q(pk__in=specialists.values("user_id")) | Q(pk__in=admins))

    if booking.source == BookingRequest.Source.ACCOUNT and booking.user_id and enabled_for_client():
        return users.filter(pk=booking.user_id, client_profile__isnull=False)
    return users.none()


@transaction.atomic
def _enqueue_booking(booking, kind):
    config = web_push.config()
    if config is None or booking.status != EXPECTED_STATUS[kind]:
        return
    now = timezone.now()
    subscriptions = PushSubscription.objects.filter(
        user_id__in=_recipients(booking, kind).values("pk"), user__is_active=True,
        user__account_erasure_request__isnull=True, session__expire_date__gt=now,
        vapid_key=config[1],
    )
    PushDelivery.objects.bulk_create([
        PushDelivery(
            subscription_id=pk, booking=booking, kind=kind, available_at=now,
            expires_at=now + timedelta(days=1),
        )
        for pk in subscriptions.select_for_update(of=("self",)).order_by("pk").values_list("pk", flat=True)
    ], ignore_conflicts=True)


def queue_booking(booking, kind):
    def enqueue():
        try:
            _enqueue_booking(booking, kind)
        except DatabaseError:
            logger.warning("Не удалось поставить Web Push в очередь.")

    if web_push.config():
        transaction.on_commit(enqueue)


def queue_test(subscription, now):
    PushDelivery.objects.create(
        subscription=subscription, kind=Kind.TEST, available_at=now,
        expires_at=now + timedelta(minutes=5),
    )


def _booking_window(delivery, user):
    if delivery.kind == Kind.NEW_BOOKING:
        return master_window(delivery.booking_id)
    profile = user.client_profile
    if profile.notify_start and profile.notify_end:
        return profile.notify_start, profile.notify_end
    return global_window()


@transaction.atomic
def _deliver(pk, config, now):
    delivery = PushDelivery.objects.select_for_update(skip_locked=True).filter(pk=pk).first()
    if delivery is None or delivery.available_at > now:
        return
    subscription = PushSubscription.objects.select_related("user", "session").get(
        pk=delivery.subscription_id,
    )
    user = subscription.user
    if subscription.session.expire_date <= now or subscription.vapid_key != config[1]:
        subscription.delete()
        return
    if not user.is_active or hasattr(user, "account_erasure_request"):
        subscription.delete()
        return
    if delivery.kind == Kind.TEST:
        if not eligible(user):
            delivery.delete()
            return
    else:
        booking = delivery.booking
        if (
            booking is None or booking.status != EXPECTED_STATUS[delivery.kind]
            or not _recipients(booking, delivery.kind).filter(pk=user.pk).exists()
        ):
            delivery.delete()
            return
        start, end = _booking_window(delivery, user)
        local_now = timezone.localtime(now)
        if not is_open(local_now, start, end):
            delivery.available_at = next_open(local_now, start, end)
            delivery.save(update_fields=["available_at"])
            return

    ttl = int((delivery.expires_at - now).total_seconds())
    if ttl <= 0:
        delivery.delete()
        return

    kind = delivery.kind
    if kind == Kind.NEW_BOOKING and not getattr(getattr(user, "specialist", None), "is_active", False):
        kind = "new_booking_admin"
    result = web_push.send(subscription, kind, config[0], config[2], ttl)
    if result in (404, 410):
        subscription.delete()
    elif result in (0, 429, 500, 502, 503, 504) and delivery.attempts < 2:
        delivery.attempts += 1
        delivery.available_at = now + timedelta(minutes=delivery.attempts)
        delivery.save(update_fields=["attempts", "available_at"])
    else:
        if result not in (200, 201, 202, 204):
            logger.warning("Web Push не доставлен. Статус APNs: %s.", result)
        delivery.delete()


def flush():
    now = timezone.now()
    PushDelivery.objects.filter(expires_at__lte=now).delete()
    PushSubscription.objects.filter(session__expire_date__lte=now).delete()
    config = web_push.config()
    if config is None:
        return
    for pk in PushDelivery.objects.filter(
        available_at__lte=now,
    ).order_by("available_at", "pk").values_list("pk", flat=True)[:12]:
        _deliver(pk, config, now)
