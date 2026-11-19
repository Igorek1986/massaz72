from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from booking.models import BookingRequest
from cabinet.models import Appointment, Specialist
from reviews.models import Review
from tgbot.models import BotAdmin, PendingNotification, TelegramUser

from .appointments import client_appointments, client_bookings
from .models import AccountErasureRequest, Client


def is_client_account(user):
    return (
        hasattr(user, "client_profile") and not user.is_staff and not user.is_superuser
        and not hasattr(user, "specialist")
    )


@transaction.atomic
def complete_account_erasure(erasure_id):
    request = AccountErasureRequest.objects.select_for_update().get(pk=erasure_id)
    if request.completed_at:
        return False
    if request.user_id is None:
        request.completed_at = timezone.now()
        request.save(update_fields=["completed_at"])
        return True

    user = get_user_model().objects.select_for_update().get(pk=request.user_id)
    if not is_client_account(user):
        raise ValidationError("Можно удалить только аккаунт клиента.")

    visits = client_appointments(user)
    visit_ids = list(visits.values_list("pk", flat=True))
    Appointment.objects.filter(Q(pk__in=visit_ids) | Q(parent_id__in=visit_ids)).update(
        client_name="Клиент удалён", client_phone="", address="", notes="", series=None,
    )

    bookings = client_bookings(user)
    reviews = Review.objects.filter(author=user)
    PendingNotification.objects.filter(
        Q(payload__booking_id__in=list(bookings.values_list("pk", flat=True)))
        | Q(payload__review_id__in=list(reviews.values_list("pk", flat=True)))
    ).delete()
    bookings.delete()
    reviews.delete()

    telegram_id = user.client_profile.telegram_id
    if (
        telegram_id is not None
        and not Client.objects.exclude(user=user).filter(telegram_id=telegram_id).exists()
        and not Specialist.objects.filter(telegram_id=telegram_id).exists()
        and not BotAdmin.objects.filter(telegram_id=telegram_id).exists()
        and not BookingRequest.objects.filter(
            messenger=BookingRequest.Messenger.TELEGRAM, messenger_user_id=telegram_id,
        ).exists()
    ):
        PendingNotification.objects.filter(payload__telegram_id=telegram_id).delete()
        TelegramUser.objects.filter(telegram_id=telegram_id).delete()

    user.delete()
    request.completed_at = timezone.now()
    request.save(update_fields=["completed_at"])
    return True
