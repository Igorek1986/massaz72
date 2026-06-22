"""Расчёт доступного времени для онлайн-записи (и Telegram-бота).

Единый источник правды о свободных слотах: учитывает рабочие часы дня,
исключения (выходной/отпуск), обед (`BlockedSlot`), занятость мастера
(`cabinet.Appointment` с перерывами и доп. услугами) и мягкие брони —
висящие заявки `BookingRequest` со статусом «на подтверждении».

Длительность услуги берётся по максимуму (duration_max), чтобы резервировать
по худшему случаю. Сетка слотов — 15 минут.

Запись на курс (sessions > 1, вариант A): одно и то же время на каждый из N
рабочих дней подряд. Поэтому клиенту предлагается ПЕРЕСЕЧЕНИЕ свободных времён
по всем дням курса.
"""

from datetime import date as date_cls
from datetime import datetime, time, timedelta

from django.utils import timezone

SLOT_STEP_MINUTES = 15
# Жёсткий потолок поиска ближайшего дня, чтобы не уйти в бесконечный цикл,
# если расписание пустое или всё занято.
MAX_LOOKAHEAD_DAYS = 120


def service_duration(service) -> int:
    """Длительность услуги в минутах (по максимуму). 60 — фолбэк."""
    if not service:
        return 60
    return service.duration_max or service.duration_min or 60


def _hold_minutes() -> int:
    from main.models import SiteSettings

    s = SiteSettings.objects.first()
    return s.booking_hold_minutes if s else 15


def _busy_intervals(specialist, day: date_cls, schedule) -> list[tuple[datetime, datetime]]:
    """Занятые интервалы (с учётом перерывов) на конкретный день.

    Источники: подтверждённые записи мастера, заблокированное время (обед),
    висящие заявки (мягкая бронь). Все длительности — по максимуму услуги.
    """
    from cabinet.forms import _apt_end_dt, _apt_total_extra_duration
    from cabinet.models import Appointment, BlockedSlot

    from .models import BookingRequest

    break_minutes = schedule.break_between_minutes
    travel_break = schedule.break_between_travel_minutes
    intervals: list[tuple[datetime, datetime]] = []

    # 1. Подтверждённые записи (без cancelled), только верхнеуровневые.
    appointments = (
        Appointment.objects.filter(
            date=day, specialist=specialist, parent__isnull=True
        )
        .exclude(status=Appointment.CANCELLED)
        .select_related("service")
        .prefetch_related("additional_services__service")
    )
    for apt in appointments:
        apt_break = travel_break if apt.is_travel else break_minutes
        apt_extra = _apt_total_extra_duration(apt)
        start = datetime.combine(day, apt.time_start)
        end = _apt_end_dt(day, apt.time_start, apt.service, apt_break, extra_duration=apt_extra)
        intervals.append((start, end))

    # 2. Заблокированное время (обед и пр.) — как заданы, без перерыва.
    for slot in BlockedSlot.objects.filter(date=day, specialist=specialist):
        intervals.append((
            datetime.combine(day, slot.time_start),
            datetime.combine(day, slot.time_end),
        ))

    # 3. Висящие заявки — мягкая бронь (по max-длительности услуги + перерыв).
    # Держат слот: PENDING (есть контакт) — бессрочно; AWAITING_CONTACT (нет
    # телефона, ждём подтверждения в боте) — только пока не истёк таймаут
    # удержания, чтобы не подтверждённая бронь освобождала время сама.
    # Заявки без мастера (сайт с одним специалистом) держат слот этого мастера.
    from django.db.models import Q

    cutoff = timezone.now() - timedelta(minutes=_hold_minutes())
    pending = (
        BookingRequest.objects.filter(
            Q(specialist=specialist) | Q(specialist__isnull=True),
            preferred_date=day,
        )
        .filter(
            Q(status=BookingRequest.Status.PENDING)
            | Q(status=BookingRequest.Status.AWAITING_CONTACT, created_at__gte=cutoff)
        )
        .select_related("service")
    )
    for req in pending:
        # Заявка ещё не превращена в Appointment — учитываем её время как занятое.
        if req.appointment_id:
            continue  # уже подтверждена в Appointment — учтена выше
        req_break = travel_break if req.address else break_minutes
        start = datetime.combine(day, req.preferred_time)
        end = start + timedelta(minutes=service_duration(req.service) + req_break)
        intervals.append((start, end))

    return intervals


def _free_starts_one_day(specialist, day: date_cls, service, schedule, *, now, lead, is_travel=False) -> set[time]:
    """Множество свободных времён начала на один день.

    `is_travel` (есть адрес → выездной массаж): после него нужен увеличенный
    перерыв, поэтому слот может конфликтовать со следующей записью, даже если
    сам массаж в неё не упирается.
    """
    from cabinet.views import _is_working_day

    if not _is_working_day(day, schedule, specialist):
        return set()
    hours = schedule.hours_for_weekday(day.weekday())
    if hours is None:
        return set()
    start_h, end_h = hours

    duration = service_duration(service)
    new_break = schedule.break_between_travel_minutes if is_travel else schedule.break_between_minutes

    busy = _busy_intervals(specialist, day, schedule)
    earliest = now + timedelta(minutes=lead)

    free: set[time] = set()
    cursor = datetime.combine(day, start_h)
    day_end = datetime.combine(day, end_h)
    while cursor.time() <= end_h:
        slot_end_service = cursor + timedelta(minutes=duration)
        # Массаж должен уложиться в рабочие часы дня.
        if slot_end_service > day_end:
            break
        if cursor >= earliest:
            slot_end_with_break = slot_end_service + timedelta(minutes=new_break)
            overlaps = any(
                cursor < b_end and slot_end_with_break > b_start
                for b_start, b_end in busy
            )
            if not overlaps:
                free.add(cursor.time())
        cursor += timedelta(minutes=SLOT_STEP_MINUTES)
    return free


def _series_days(specialist, start: date_cls, sessions: int, schedule) -> list[date_cls]:
    from cabinet.views import _series_dates

    if sessions <= 1:
        return [start]
    return _series_dates(start, sessions, schedule, specialist)


def free_starts(specialist, day: date_cls, service, sessions: int = 1, *, now=None, is_travel=False) -> set[time]:
    """Свободные времена начала на день (или пересечение по всем дням курса)."""
    from cabinet.models import WorkSchedule

    if specialist is None:
        return set()
    if now is None:
        now = timezone.localtime()
    if timezone.is_aware(now):
        now = timezone.make_naive(now, timezone.get_current_timezone())
    schedule = WorkSchedule.for_specialist(specialist)
    lead = schedule.lead_time_minutes

    days = _series_days(specialist, day, sessions, schedule)
    if not days:
        return set()

    result: set[time] | None = None
    for d in days:
        day_free = _free_starts_one_day(
            specialist, d, service, schedule, now=now, lead=lead, is_travel=is_travel
        )
        result = day_free if result is None else (result & day_free)
        if not result:
            return set()
    return result or set()


def next_available_day(specialist, from_date: date_cls, service, sessions: int = 1, *, now=None, is_travel=False) -> date_cls | None:
    """Ближайший день (с from_date), где есть хотя бы один свободный слот курса."""
    if specialist is None:
        return None
    current = from_date
    limit = from_date + timedelta(days=MAX_LOOKAHEAD_DAYS)
    while current <= limit:
        if free_starts(specialist, current, service, sessions, now=now, is_travel=is_travel):
            return current
        current += timedelta(days=1)
    return None


def enabled_days(specialist, date_from: date_cls, date_to: date_cls, *, today=None) -> list[date_cls]:
    """Дни диапазона, доступные для выбора даты в календаре: рабочие по
    расписанию, не попавшие в исключение (выходной/отпуск) и не в прошлом.

    Занятость записями НЕ учитывается (гасим только нерабочие дни) — полностью
    забитые рабочие дни остаются на автоперенос при выборе времени.
    """
    from cabinet.models import ScheduleException, WorkSchedule

    if specialist is None:
        return []
    if today is None:
        today = timezone.localdate()
    schedule = WorkSchedule.for_specialist(specialist)
    working = set(schedule.working_weekdays())

    exceptions = list(
        ScheduleException.objects.filter(
            specialist=specialist, date_from__lte=date_to, date_to__gte=date_from,
        ).values_list("date_from", "date_to")
    )

    def in_exception(d: date_cls) -> bool:
        return any(efrom <= d <= eto for efrom, eto in exceptions)

    out: list[date_cls] = []
    current = max(date_from, today)
    while current <= date_to:
        if current.weekday() in working and not in_exception(current):
            out.append(current)
        current += timedelta(days=1)
    return out


def day_availability(specialist, day: date_cls, service, sessions: int = 1, *, now=None, is_travel=False) -> dict:
    """Данные для UI: запрошенный день, эффективный (с автопереносом) и слоты."""
    requested = day
    slots = free_starts(specialist, day, service, sessions, now=now, is_travel=is_travel)
    effective = day
    if not slots:
        nxt = next_available_day(specialist, day, service, sessions, now=now, is_travel=is_travel)
        if nxt is not None:
            effective = nxt
            slots = free_starts(specialist, nxt, service, sessions, now=now, is_travel=is_travel)
    return {
        "requested_date": requested.isoformat(),
        "effective_date": effective.isoformat(),
        "shifted": effective != requested,
        "slots": [t.strftime("%H:%M") for t in sorted(slots)],
    }
