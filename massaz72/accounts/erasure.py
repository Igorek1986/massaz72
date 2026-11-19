from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

from booking.models import BookingRequest
from cabinet.models import Appointment, Specialist
from reviews.models import Review
from tgbot.models import BotAdmin, PendingNotification, TelegramUser

from .appointments import client_appointments, client_bookings
from .models import AccountErasureRequest, Client, PushSubscription
from .permissions import can_process_erasure


@dataclass(frozen=True)
class ErasureScope:
    user_id: int | None = None
    profile_id: int | None = None
    booking_ids: tuple[int, ...] = ()
    guest_booking_ids: tuple[int, ...] = ()
    review_ids: tuple[int, ...] = ()
    visit_ids: tuple[int, ...] = ()
    shared_visit_ids: tuple[int, ...] = ()
    push_ids: tuple[int, ...] = ()
    notification_ids: tuple[int, ...] = ()
    telegram_ids: tuple[int, ...] = ()
    shared_telegram: bool = False

    def confirmation(self, request_id):
        return salted_hmac("accounts.erasure_scope", f"{request_id}:{self}", algorithm="sha256").hexdigest()


def is_client_account(user):
    return (
        hasattr(user, "client_profile") and not user.is_staff and not user.is_superuser
        and not hasattr(user, "specialist")
        and not can_process_erasure(user)
    )


def _ids(queryset, *, lock):
    if lock:
        queryset = queryset.select_for_update()
    return tuple(queryset.order_by("pk").values_list("pk", flat=True))


def erasure_scope(user, *, lock=False):
    """Подбирает один и тот же набор записей для проверки и удаления."""
    if user is None:
        return ErasureScope()
    if not is_client_account(user):
        return None

    booking_ids = _ids(client_bookings(user), lock=lock)
    guest_booking_ids = _ids(BookingRequest.objects.filter(user=user).exclude(pk__in=booking_ids), lock=lock)
    review_ids = _ids(Review.objects.filter(author=user), lock=lock)
    push_ids = _ids(PushSubscription.objects.filter(user=user), lock=lock)
    visits = _ids(client_appointments(user), lock=lock)
    visit_ids = _ids(Appointment.objects.filter(Q(pk__in=visits) | Q(parent_id__in=visits)), lock=lock)
    other_bookings = BookingRequest.objects.filter(appointment_id__in=visit_ids).exclude(pk__in=booking_ids)
    other_appointments = other_bookings.values("appointment_id")
    other_series = other_bookings.values("appointment__series_id")
    shared_visit_ids = _ids(Appointment.objects.filter(pk__in=visit_ids).filter(
        Q(pk__in=other_appointments) | Q(parent_id__in=other_appointments)
        | Q(series_id__in=other_series) | Q(parent__series_id__in=other_series),
    ), lock=False)
    shared_visits = set(shared_visit_ids)

    telegram_id = user.client_profile.telegram_id
    shared_telegram = telegram_id is not None and (
        Client.objects.exclude(user=user).filter(telegram_id=telegram_id).exists()
        or Specialist.objects.filter(telegram_id=telegram_id).exists()
        or BotAdmin.objects.filter(telegram_id=telegram_id).exists()
        or BookingRequest.objects.filter(
            messenger=BookingRequest.Messenger.TELEGRAM, messenger_user_id=telegram_id,
        ).exclude(pk__in=booking_ids).exists()
    )
    telegram_ids = ()
    notifications = Q(payload__booking_id__in=booking_ids) | Q(payload__review_id__in=review_ids)
    if telegram_id is not None and not shared_telegram:
        telegram_ids = _ids(TelegramUser.objects.filter(telegram_id=telegram_id), lock=lock)
        notifications |= Q(payload__telegram_id=telegram_id)

    return ErasureScope(
        user_id=user.pk,
        profile_id=user.client_profile.pk,
        booking_ids=booking_ids,
        guest_booking_ids=guest_booking_ids,
        review_ids=review_ids,
        visit_ids=tuple(pk for pk in visit_ids if pk not in shared_visits),
        shared_visit_ids=shared_visit_ids,
        push_ids=push_ids,
        notification_ids=_ids(PendingNotification.objects.filter(notifications), lock=lock),
        telegram_ids=telegram_ids,
        shared_telegram=shared_telegram,
    )


@transaction.atomic
def complete_account_erasure(erasure_id, confirmation):
    request = AccountErasureRequest.objects.select_for_update().get(pk=erasure_id)
    if request.completed_at:
        return False

    user = None
    if request.user_id is not None:
        user = get_user_model().objects.select_for_update().get(pk=request.user_id)
    scope = erasure_scope(user, lock=True)
    if scope is None:
        raise ValidationError("Можно удалить только аккаунт клиента.")
    if not constant_time_compare(scope.confirmation(request.pk), confirmation):
        raise ValidationError("Состав запроса изменился. Проверьте список заново и подтвердите действие.")

    if user is not None:
        Appointment.objects.filter(pk__in=scope.visit_ids).update(
            client_name="Клиент удалён", client_phone="", address="", notes="", series=None,
        )
        PendingNotification.objects.filter(pk__in=scope.notification_ids).delete()
        BookingRequest.objects.filter(pk__in=scope.booking_ids).delete()
        Review.objects.filter(pk__in=scope.review_ids).delete()
        TelegramUser.objects.filter(pk__in=scope.telegram_ids).delete()
        user.delete()

    request.completed_at = timezone.now()
    request.save(update_fields=["completed_at"])
    return True
