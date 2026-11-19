from django.db.models import Q
from django.utils import timezone

from booking.models import BookingRequest
from cabinet.models import Appointment


def client_bookings(user):
    # Гостевые заявки могли быть привязаны при регистрации по непроверенному номеру.
    return BookingRequest.objects.filter(user=user, source=BookingRequest.Source.ACCOUNT)


def client_appointments(user):
    bookings = client_bookings(user).filter(appointment__isnull=False)
    return Appointment.objects.filter(
        Q(pk__in=bookings.values("appointment_id"))
        | Q(series_id__in=bookings.values("appointment__series_id"))
    )


def has_completed_appointment(user):
    return (
        user.is_authenticated
        and hasattr(user, "client_profile")
        and not hasattr(user, "account_erasure_request")
        and client_appointments(user).filter(
            status=Appointment.COMPLETED, date__lte=timezone.localdate(),
        ).exists()
    )
