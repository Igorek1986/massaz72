"""Бизнес-логика обработки заявок: подтверждение создаёт cabinet.Appointment.

Используется и кабинетом мастера, и Telegram-ботом, чтобы поведение совпадало.
"""

from datetime import timedelta
from decimal import Decimal

from .models import BookingRequest


def confirm_booking(booking, specialist=None, *, date=None, time_start=None,
                    cost=None):
    """Подтверждает заявку и создаёт запись(и).

    Если в заявке выбран курс (`sessions` > 1) — создаётся серия
    (`AppointmentSeries`) из N записей по рабочим дням. Иначе — одна запись.
    `specialist`/`date`/`time_start`/`cost` — переопределения. Возвращает первую
    созданную запись или None, если активных мастеров нет.
    """
    from cabinet.models import (
        Appointment, AppointmentSeries, Specialist, WorkSchedule,
    )

    # По умолчанию — выбранный/из заявки мастер, иначе первый АКТИВНЫЙ.
    spec = (
        specialist or booking.specialist
        or Specialist.objects.filter(is_active=True).first()
    )
    if spec is None:
        return None

    if cost is None:
        cost = booking.service.price if booking.service else Decimal("0")

    start_date = date or booking.preferred_date
    sessions_count = booking.sessions.count if booking.sessions else 1

    common = dict(
        specialist=spec,
        client_name=booking.client_name,
        client_phone=booking.phone,
        address=booking.address,
        is_travel=bool(booking.address),
        service=booking.service,
        time_start=time_start or booking.preferred_time,
        cost=cost,
        status=Appointment.SCHEDULED,
        notes=booking.comment,
    )

    if sessions_count > 1:
        from cabinet.views import _series_dates

        schedule = WorkSchedule.for_specialist(spec)
        dates = _series_dates(start_date, sessions_count, schedule, spec)
        # Фолбэк, если рабочих дней не хватило — добиваем подряд идущими днями.
        while len(dates) < sessions_count:
            dates.append((dates[-1] if dates else start_date) + timedelta(days=1))

        series = AppointmentSeries.objects.create(
            specialist=spec, service=booking.service, total_sessions=sessions_count,
        )
        first = None
        for d in dates:
            apt = Appointment.objects.create(date=d, series=series, **common)
            if first is None:
                first = apt
        appointment = first
    else:
        appointment = Appointment.objects.create(date=start_date, **common)

    booking.status = BookingRequest.Status.CONFIRMED
    booking.specialist = spec
    booking.appointment = appointment
    booking.save(update_fields=["status", "specialist", "appointment", "updated_at"])
    return appointment


def decline_booking(booking):
    booking.status = BookingRequest.Status.DECLINED
    booking.save(update_fields=["status", "updated_at"])


def cancel_appointment(appointment):
    """Отменяет сеанс (клиент отменил будущий сеанс)."""
    from cabinet.models import Appointment
    appointment.status = Appointment.CANCELLED
    appointment.save(update_fields=["status"])


def request_reschedule(appointment, new_date, new_time):
    """Создаёт запрос на перенос сеанса (подтверждает мастер)."""
    from .models import RescheduleRequest
    return RescheduleRequest.objects.create(
        appointment=appointment, new_date=new_date, new_time=new_time,
    )


def apply_reschedule(req):
    """Применяет перенос: меняет дату/время записи."""
    from .models import RescheduleRequest
    appt = req.appointment
    appt.date = req.new_date
    appt.time_start = req.new_time
    appt.save(update_fields=["date", "time_start"])
    req.status = RescheduleRequest.Status.APPROVED
    req.save(update_fields=["status"])


def decline_reschedule(req):
    from .models import RescheduleRequest
    req.status = RescheduleRequest.Status.DECLINED
    req.save(update_fields=["status"])
