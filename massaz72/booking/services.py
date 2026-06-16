"""Бизнес-логика обработки заявок: подтверждение создаёт cabinet.Appointment.

Используется и кабинетом мастера, и Telegram-ботом, чтобы поведение совпадало.
"""

from decimal import Decimal

from .models import BookingRequest


def confirm_booking(booking, specialist=None, *, date=None, time_start=None,
                    cost=None):
    """Подтверждает заявку и создаёт запись (Appointment).

    `specialist` — кто проводит (по умолчанию из заявки или единственный мастер).
    `date`/`time_start`/`cost` — переопределение значений из заявки (мастер мог
    поправить дату/время/стоимость). Возвращает Appointment или None, если
    мастеров в системе нет.
    """
    from cabinet.models import Appointment, Specialist

    spec = specialist or booking.specialist or Specialist.objects.first()
    if spec is None:
        return None

    if cost is None:
        cost = booking.service.price if booking.service else Decimal("0")

    appointment = Appointment.objects.create(
        specialist=spec,
        client_name=booking.client_name,
        client_phone=booking.phone,
        address=booking.address,
        is_travel=bool(booking.address),
        service=booking.service,
        date=date or booking.preferred_date,
        time_start=time_start or booking.preferred_time,
        cost=cost,
        status=Appointment.SCHEDULED,
        notes=booking.comment,
    )
    booking.status = BookingRequest.Status.CONFIRMED
    booking.specialist = spec
    booking.appointment = appointment
    booking.save(update_fields=["status", "specialist", "appointment", "updated_at"])
    return appointment


def decline_booking(booking):
    booking.status = BookingRequest.Status.DECLINED
    booking.save(update_fields=["status", "updated_at"])
