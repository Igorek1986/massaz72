from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from main.models import SiteSettings
from services.models import Massage

from .forms import AppointmentForm, BlockedSlotForm, DiscountForm, ScheduleExceptionForm, WorkScheduleForm, find_time_conflicts
from .models import Appointment, AppointmentSeries, BlockedSlot, Discount, ScheduleException, WorkSchedule


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_working_day(d: date, schedule: WorkSchedule) -> bool:
    if d.weekday() not in schedule.working_weekdays():
        return False
    return not ScheduleException.objects.filter(date_from__lte=d, date_to__gte=d).exists()


def _series_dates(start: date, count: int, schedule: WorkSchedule) -> list[date]:
    """Возвращает list из count рабочих дней начиная с start (включительно)."""
    dates: list[date] = []
    current = start
    limit = start + timedelta(days=365)
    while len(dates) < count and current <= limit:
        if _is_working_day(current, schedule):
            dates.append(current)
        current += timedelta(days=1)
    return dates


def _day_context(selected_date: date) -> dict:
    appointments = (
        Appointment.objects.filter(date=selected_date)
        .select_related("service", "series")
        .order_by("time_start")
    )
    blocked_slots = BlockedSlot.objects.filter(date=selected_date)
    schedule = WorkSchedule.get_solo()
    is_working = _is_working_day(selected_date, schedule)
    exceptions = ScheduleException.objects.filter(date_from__lte=selected_date, date_to__gte=selected_date)
    return {
        "selected_date": selected_date,
        "date_str": selected_date.isoformat(),
        "appointments": appointments,
        "blocked_slots": blocked_slots,
        "is_working": is_working,
        "exceptions": exceptions,
    }


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@login_required
def index(request):
    today = date.today()
    return render(request, "cabinet/index.html", {"today": today.isoformat()})


@login_required
def settings(request):
    schedule = WorkSchedule.get_solo()
    return render(request, "cabinet/settings.html", {
        "schedule_form": WorkScheduleForm(instance=schedule),
        "exceptions": ScheduleException.objects.all(),
        "blocked_slots": BlockedSlot.objects.order_by("date", "time_start"),
    })


# ---------------------------------------------------------------------------
# HTMX partials
# ---------------------------------------------------------------------------

@login_required
def day_schedule(request, date_str: str):
    try:
        selected_date = date.fromisoformat(date_str)
    except ValueError:
        return render(request, "cabinet/partials/day_schedule.html", {"error": True})
    return render(request, "cabinet/partials/day_schedule.html", _day_context(selected_date))


@login_required
def appointment_add(request):
    date_str = request.GET.get("date") or request.POST.get("date", "")
    try:
        initial_date = date.fromisoformat(date_str)
    except ValueError:
        initial_date = date.today()
        date_str = initial_date.isoformat()

    if request.method == "POST":
        form = AppointmentForm(request.POST)
        if form.is_valid():
            sessions = form.cleaned_data.pop("sessions")
            apt: Appointment = form.save(commit=False)
            schedule = WorkSchedule.get_solo()

            if sessions > 1:
                dates = _series_dates(apt.date, sessions, schedule)
                break_minutes = schedule.break_between_minutes
                conflict_dates = []
                for d in dates:
                    day_conflicts = find_time_conflicts(d, apt.time_start, apt.service, break_minutes)
                    if day_conflicts:
                        conflict_dates.append((d, day_conflicts))
                if conflict_dates:
                    from .forms import _conflict_message
                    lines = []
                    for d, day_conflicts in conflict_dates:
                        lines.append(
                            f"{d.strftime('%d.%m')}: " + _conflict_message(d, day_conflicts, break_minutes)
                        )
                    form.add_error(None, " | ".join(lines))
                    response = render(request, "cabinet/partials/appointment_form.html", {
                        "form": form, "date_str": date_str,
                        "service_prices": {m.pk: int(m.price) for m in Massage.objects.filter(is_archived=False)},
                    })
                    response["HX-Retarget"] = "#add-form-container"
                    return response

                series = AppointmentSeries.objects.create(
                    service=apt.service,
                    total_sessions=sessions,
                )
                for d in dates:
                    Appointment.objects.create(
                        client_name=apt.client_name,
                        client_phone=apt.client_phone,
                        address=apt.address,
                        service=apt.service,
                        date=d,
                        time_start=apt.time_start,
                        cost=apt.cost,
                        transport_cost=apt.transport_cost,
                        notes=apt.notes,
                        series=series,
                    )
            else:
                apt.save()

            response = render(request, "cabinet/partials/day_schedule.html", _day_context(apt.date))
            response["HX-Retarget"] = "#day-panel"
            response["HX-Reswap"] = "innerHTML"
            response["HX-Trigger"] = "appointmentChanged"
            return response

        response = render(request, "cabinet/partials/appointment_form.html", {
            "form": form, "date_str": date_str,
            "service_prices": {m.pk: int(m.price) for m in Massage.objects.filter(is_archived=False)},
        })
        response["HX-Retarget"] = "#add-form-container"
        return response

    form = AppointmentForm(initial={"date": initial_date})
    service_prices = {m.pk: int(m.price) for m in Massage.objects.filter(is_archived=False)}
    return render(request, "cabinet/partials/appointment_form.html", {
        "form": form, "date_str": date_str, "service_prices": service_prices,
    })


@login_required
def appointment_edit(request, pk: int):
    appointment = get_object_or_404(Appointment, pk=pk)
    date_str = appointment.date.isoformat()

    if request.method == "POST":
        form = AppointmentForm(request.POST, instance=appointment)
        if form.is_valid():
            form.cleaned_data.pop("sessions", None)
            form.save()
            response = render(request, "cabinet/partials/day_schedule.html", _day_context(appointment.date))
            response["HX-Retarget"] = "#day-panel"
            response["HX-Reswap"] = "innerHTML"
            response["HX-Trigger"] = "appointmentChanged"
            return response

        response = render(request, "cabinet/partials/appointment_form.html", {
            "form": form, "date_str": date_str, "appointment": appointment,
            "service_prices": {m.pk: int(m.price) for m in Massage.objects.filter(is_archived=False)},
        })
        response["HX-Retarget"] = "#add-form-container"
        return response

    form = AppointmentForm(instance=appointment)
    service_prices = {m.pk: int(m.price) for m in Massage.objects.filter(is_archived=False)}
    return render(request, "cabinet/partials/appointment_form.html", {
        "form": form, "date_str": date_str, "appointment": appointment,
        "service_prices": service_prices,
    })


@login_required
@require_POST
def appointment_status(request, pk: int):
    appointment = get_object_or_404(Appointment, pk=pk)
    new_status = request.POST.get("status")
    if new_status in (Appointment.SCHEDULED, Appointment.COMPLETED, Appointment.CANCELLED):
        appointment.status = new_status
        appointment.save()
    response = render(request, "cabinet/partials/day_schedule.html", _day_context(appointment.date))
    response["HX-Trigger"] = "appointmentChanged"
    return response


@login_required
@require_POST
def appointment_delete(request, pk: int):
    appointment = get_object_or_404(Appointment, pk=pk)
    saved_date = appointment.date
    appointment.delete()
    response = render(request, "cabinet/partials/day_schedule.html", _day_context(saved_date))
    response["HX-Trigger"] = "appointmentChanged"
    return response


# ---------------------------------------------------------------------------
# Settings helpers
# ---------------------------------------------------------------------------

def _exception_section_ctx() -> dict:
    return {"exceptions": ScheduleException.objects.all()}


def _blocked_slot_section_ctx() -> dict:
    return {"blocked_slots": BlockedSlot.objects.order_by("date", "time_start")}


def _exception_section_response(request):
    response = render(request, "cabinet/partials/exception_section.html", _exception_section_ctx())
    response["HX-Retarget"] = "#exceptions-section"
    response["HX-Reswap"] = "innerHTML"
    return response


def _blocked_slot_section_response(request):
    response = render(request, "cabinet/partials/blocked_slot_section.html", _blocked_slot_section_ctx())
    response["HX-Retarget"] = "#blocked-slots-section"
    response["HX-Reswap"] = "innerHTML"
    return response


# ---------------------------------------------------------------------------
# Settings views
# ---------------------------------------------------------------------------

@login_required
@require_POST
def schedule_save(request):
    schedule = WorkSchedule.get_solo()
    form = WorkScheduleForm(request.POST, instance=schedule)
    saved = False
    if form.is_valid():
        form.save()
        saved = True
    response = render(request, "cabinet/partials/schedule_section.html", {
        "schedule_form": form, "saved": saved,
    })
    response["HX-Retarget"] = "#schedule-section"
    response["HX-Reswap"] = "innerHTML"
    return response


@login_required
def exception_add(request):
    if request.method == "POST":
        form = ScheduleExceptionForm(request.POST)
        if form.is_valid():
            form.save()
            return _exception_section_response(request)
        response = render(request, "cabinet/partials/exception_form.html", {"form": form})
        response["HX-Retarget"] = "#exception-form-container"
        return response
    return render(request, "cabinet/partials/exception_form.html", {"form": ScheduleExceptionForm()})


@login_required
def exception_edit(request, pk: int):
    exc = get_object_or_404(ScheduleException, pk=pk)
    if request.method == "POST":
        form = ScheduleExceptionForm(request.POST, instance=exc)
        if form.is_valid():
            form.save()
            return _exception_section_response(request)
        response = render(request, "cabinet/partials/exception_form.html", {"form": form, "exception": exc})
        response["HX-Retarget"] = "#exception-form-container"
        return response
    return render(request, "cabinet/partials/exception_form.html", {
        "form": ScheduleExceptionForm(instance=exc), "exception": exc,
    })


@login_required
@require_POST
def exception_delete(request, pk: int):
    get_object_or_404(ScheduleException, pk=pk).delete()
    return _exception_section_response(request)


@login_required
def blocked_slot_add(request):
    if request.method == "POST":
        form = BlockedSlotForm(request.POST)
        if form.is_valid():
            form.save()
            return _blocked_slot_section_response(request)
        response = render(request, "cabinet/partials/blocked_slot_form.html", {"form": form})
        response["HX-Retarget"] = "#blocked-slot-form-container"
        return response
    return render(request, "cabinet/partials/blocked_slot_form.html", {"form": BlockedSlotForm()})


@login_required
def blocked_slot_edit(request, pk: int):
    slot = get_object_or_404(BlockedSlot, pk=pk)
    if request.method == "POST":
        form = BlockedSlotForm(request.POST, instance=slot)
        if form.is_valid():
            form.save()
            return _blocked_slot_section_response(request)
        response = render(request, "cabinet/partials/blocked_slot_form.html", {"form": form, "slot": slot})
        response["HX-Retarget"] = "#blocked-slot-form-container"
        return response
    return render(request, "cabinet/partials/blocked_slot_form.html", {
        "form": BlockedSlotForm(instance=slot), "slot": slot,
    })


@login_required
@require_POST
def blocked_slot_delete(request, pk: int):
    get_object_or_404(BlockedSlot, pk=pk).delete()
    return _blocked_slot_section_response(request)


# ---------------------------------------------------------------------------
# Prices helpers
# ---------------------------------------------------------------------------

def _prices_ctx() -> dict:
    massages = Massage.objects.filter(is_archived=False).order_by("massage_type", "order")
    site_settings = SiteSettings.objects.first()
    today = timezone.localdate()
    prices_due = bool(
        site_settings
        and site_settings.price_change_date
        and site_settings.price_change_date <= today
        and massages.filter(new_price__isnull=False).exists()
    )
    active_discount = Discount.objects.filter(date_from__lte=today, date_to__gte=today).first()
    discounts = Discount.objects.all()
    return {
        "massages": massages,
        "site_settings": site_settings,
        "prices_due": prices_due,
        "active_discount": active_discount,
        "discounts": discounts,
    }


def _discount_section_ctx() -> dict:
    today = timezone.localdate()
    return {
        "discounts": Discount.objects.all(),
        "active_discount": Discount.objects.filter(date_from__lte=today, date_to__gte=today).first(),
    }


def _discount_section_response(request):
    response = render(request, "cabinet/partials/discount_section.html", _discount_section_ctx())
    response["HX-Retarget"] = "#discounts-section"
    response["HX-Reswap"] = "innerHTML"
    return response


# ---------------------------------------------------------------------------
# Prices views
# ---------------------------------------------------------------------------

@login_required
def prices(request):
    return render(request, "cabinet/prices.html", _prices_ctx())


@login_required
@require_POST
def prices_save_current(request):
    massages = Massage.objects.filter(is_archived=False)
    for massage in massages:
        raw = request.POST.get(f"price_{massage.pk}", "").strip()
        if raw:
            try:
                massage.price = Decimal(raw)
                massage.save(update_fields=["price"])
            except InvalidOperation:
                pass
    response = render(request, "cabinet/partials/price_list_section.html", _prices_ctx())
    response["HX-Retarget"] = "#price-list-section"
    response["HX-Reswap"] = "innerHTML"
    response["HX-Trigger"] = "pricesChanged"
    return response


@login_required
@require_POST
def prices_save_change(request):
    site_settings = SiteSettings.objects.first()
    date_raw = request.POST.get("price_change_date", "").strip()
    if date_raw:
        try:
            site_settings.price_change_date = date.fromisoformat(date_raw)
        except ValueError:
            pass
    else:
        site_settings.price_change_date = None
    site_settings.save(update_fields=["price_change_date"])

    massages = Massage.objects.filter(is_archived=False)
    for massage in massages:
        raw = request.POST.get(f"new_price_{massage.pk}", "").strip()
        if raw:
            try:
                massage.new_price = Decimal(raw)
            except InvalidOperation:
                pass
        else:
            massage.new_price = None
        massage.save(update_fields=["new_price"])

    response = render(request, "cabinet/partials/price_change_section.html", _prices_ctx())
    response["HX-Retarget"] = "#price-change-section"
    response["HX-Reswap"] = "innerHTML"
    return response


@login_required
@require_POST
def prices_apply_change(request):
    """Применить запланированные цены немедленно."""
    massages = Massage.objects.filter(is_archived=False, new_price__isnull=False)
    for massage in massages:
        massage.price = massage.new_price
        massage.new_price = None
        massage.save(update_fields=["price", "new_price"])
    site_settings = SiteSettings.objects.first()
    site_settings.price_change_date = None
    site_settings.save(update_fields=["price_change_date"])

    return render(request, "cabinet/prices.html", _prices_ctx())


@login_required
def discount_add(request):
    if request.method == "POST":
        form = DiscountForm(request.POST)
        if form.is_valid():
            form.save()
            return _discount_section_response(request)
        response = render(request, "cabinet/partials/discount_form.html", {"form": form})
        response["HX-Retarget"] = "#discount-form-container"
        return response
    return render(request, "cabinet/partials/discount_form.html", {"form": DiscountForm()})


@login_required
def discount_edit(request, pk: int):
    discount = get_object_or_404(Discount, pk=pk)
    if request.method == "POST":
        form = DiscountForm(request.POST, instance=discount)
        if form.is_valid():
            form.save()
            return _discount_section_response(request)
        response = render(request, "cabinet/partials/discount_form.html", {"form": form, "discount": discount})
        response["HX-Retarget"] = "#discount-form-container"
        return response
    return render(request, "cabinet/partials/discount_form.html", {
        "form": DiscountForm(instance=discount), "discount": discount,
    })


@login_required
@require_POST
def discount_delete(request, pk: int):
    get_object_or_404(Discount, pk=pk).delete()
    return _discount_section_response(request)


# ---------------------------------------------------------------------------
# FullCalendar JSON events
# ---------------------------------------------------------------------------

@login_required
def calendar_events(request):
    start_str = request.GET.get("start", "")
    end_str = request.GET.get("end", "")
    try:
        start = date.fromisoformat(start_str[:10])
        end = date.fromisoformat(end_str[:10])
    except (ValueError, TypeError):
        return JsonResponse([], safe=False)

    events = []
    schedule = WorkSchedule.get_solo()
    working_days = schedule.working_weekdays()
    exceptions = ScheduleException.objects.filter(date_from__lte=end, date_to__gte=start)

    current = start
    while current < end:
        is_exception = exceptions.filter(date_from__lte=current, date_to__gte=current).exists()
        if current.weekday() not in working_days or is_exception:
            events.append({
                "start": current.isoformat(),
                "display": "background",
                "backgroundColor": "rgba(239,68,68,0.12)",
                "classNames": ["fc-day-off"],
            })
        current += timedelta(days=1)

    apt_counts = (
        Appointment.objects.filter(date__gte=start, date__lt=end)
        .exclude(status=Appointment.CANCELLED)
        .values("date")
        .annotate(count=Count("id"))
    )
    for row in apt_counts:
        count = row["count"]
        events.append({
            "start": row["date"].isoformat(),
            "title": f"{count} зап." if count != 1 else "1 зап.",
            "allDay": True,
            "backgroundColor": "#3b82f6",
            "borderColor": "#2563eb",
            "textColor": "#fff",
            "classNames": ["fc-apt-count"],
        })

    return JsonResponse(events, safe=False)
