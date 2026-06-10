import json
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.http import require_POST

from main.models import SiteSettings
from services.models import Massage

from massaz72.utils import _slugify_ru

from .forms import (
    AppointmentForm, BlockedSlotForm, DiscountForm, MassageForm,
    ScheduleExceptionForm, WorkScheduleForm,
    find_time_conflicts, _conflict_message,
)
from .models import (
    Appointment, AppointmentSeries, BlockedSlot,
    Discount, ScheduleException, Specialist, WorkSchedule,
)


# ---------------------------------------------------------------------------
# Decorator
# ---------------------------------------------------------------------------

def specialist_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapper(request: HttpRequest, *args, **kwargs):
        try:
            request.specialist = request.user.specialist
        except Specialist.DoesNotExist:
            return redirect("admin:index")
        return view_func(request, *args, **kwargs)
    return wrapper


def prices_manager_required(view_func):
    @wraps(view_func)
    @specialist_required
    def wrapper(request: HttpRequest, *args, **kwargs):
        if not request.specialist.can_manage_prices:
            return HttpResponse("Нет доступа к управлению ценами", status=403)
        return view_func(request, *args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_working_day(d: date, schedule: WorkSchedule, specialist: Specialist) -> bool:
    if d.weekday() not in schedule.working_weekdays():
        return False
    return not ScheduleException.objects.filter(
        specialist=specialist, date_from__lte=d, date_to__gte=d
    ).exists()


def _series_dates(start: date, count: int, schedule: WorkSchedule, specialist: Specialist) -> list[date]:
    dates: list[date] = []
    current = start
    limit = start + timedelta(days=365)
    while len(dates) < count and current <= limit:
        if _is_working_day(current, schedule, specialist):
            dates.append(current)
        current += timedelta(days=1)
    return dates


def _day_context(selected_date: date, specialist: Specialist) -> dict:
    appointments = (
        Appointment.objects.filter(date=selected_date, specialist=specialist, parent__isnull=True)
        .select_related("service", "series")
        .prefetch_related("additional_services__service")
        .order_by("time_start")
    )
    blocked_slots = BlockedSlot.objects.filter(date=selected_date, specialist=specialist)
    schedule = WorkSchedule.for_specialist(specialist)
    is_working = _is_working_day(selected_date, schedule, specialist)
    exceptions = ScheduleException.objects.filter(
        specialist=specialist, date_from__lte=selected_date, date_to__gte=selected_date
    )
    # compute total_visit_cost for each appointment
    for apt in appointments:
        extra = sum(c.cost for c in apt.additional_services.all())
        apt.total_visit_cost = apt.cost + extra + (apt.transport_cost or Decimal("0"))
    return {
        "selected_date": selected_date,
        "date_str": selected_date.isoformat(),
        "appointments": appointments,
        "blocked_slots": blocked_slots,
        "is_working": is_working,
        "exceptions": exceptions,
    }


def _parse_extra_services(post_data):
    """Parse extra_service_N/extra_cost_N/extra_pk_N from POST."""
    services = []
    i = 0
    while i < 20:
        service_id = post_data.get(f"extra_service_{i}", "").strip()
        cost_raw = post_data.get(f"extra_cost_{i}", "").strip()
        if not service_id and not cost_raw:
            break
        if service_id:
            try:
                service_obj = Massage.objects.get(pk=int(service_id), is_archived=False)
                pk_raw = post_data.get(f"extra_pk_{i}", "").strip()
                try:
                    cost_dec = Decimal(cost_raw) if cost_raw else Decimal("0")
                except InvalidOperation:
                    cost_dec = Decimal("0")
                services.append({
                    "pk": int(pk_raw) if pk_raw else None,
                    "service": service_obj,
                    "cost": cost_dec,
                })
            except (Massage.DoesNotExist, ValueError):
                pass
        i += 1
    return services


def _compute_extra_duration(extra_services):
    total = 0
    for es in extra_services:
        svc = es.get("service")
        if svc:
            total += svc.duration_max or svc.duration_min or 0
    return total


def _create_additional_services(parent_apt, extra_services, specialist):
    """Create child Appointment records for additional services."""
    cumulative = 0
    if parent_apt.service:
        cumulative += parent_apt.service.duration_max or parent_apt.service.duration_min or 0
    for es in extra_services:
        child_dt = datetime.combine(parent_apt.date, parent_apt.time_start) + timedelta(minutes=cumulative)
        Appointment.objects.create(
            parent=parent_apt,
            specialist=specialist,
            client_name=parent_apt.client_name,
            client_phone=parent_apt.client_phone,
            address=parent_apt.address,
            is_travel=parent_apt.is_travel,
            service=es["service"],
            date=parent_apt.date,
            time_start=child_dt.time(),
            cost=es["cost"],
            discount_percent=parent_apt.discount_percent,
            notes=parent_apt.notes,
            status=parent_apt.status,
            series=parent_apt.series,
        )
        cumulative += es["service"].duration_max or es["service"].duration_min or 0


def _recompute_children_times(parent_apt):
    """Recompute time_start for all children of a parent appointment."""
    cumulative = 0
    if parent_apt.service:
        cumulative += parent_apt.service.duration_max or parent_apt.service.duration_min or 0
    for child in parent_apt.additional_services.select_related("service").order_by("time_start", "pk"):
        child_dt = datetime.combine(parent_apt.date, parent_apt.time_start) + timedelta(minutes=cumulative)
        child.time_start = child_dt.time()
        child.save(update_fields=["time_start"])
        if child.service:
            cumulative += child.service.duration_max or child.service.duration_min or 0


def _next_series_working_day(series_pk, specialist):
    """Returns the next working day after the last parent appointment in the series."""
    last_apt = Appointment.objects.filter(series_id=series_pk, parent__isnull=True).order_by("-date").first()
    if not last_apt:
        return None
    schedule = WorkSchedule.for_specialist(specialist)
    candidate = last_apt.date + timedelta(days=1)
    limit = candidate + timedelta(days=180)
    while candidate <= limit:
        if _is_working_day(candidate, schedule, specialist):
            return candidate
        candidate += timedelta(days=1)
    return None



def _apt_form_context(specialist, date_str, form, appointment=None, extra_services_data=None):
    """Build shared context for appointment form."""
    today = timezone.localdate()
    active_discount = Discount.objects.filter(date_from__lte=today, date_to__gte=today).first()
    service_prices = {}
    for m in Massage.objects.filter(is_archived=False):
        price = int(m.price)
        if active_discount:
            price = int(active_discount.apply_to(m.price))
        service_prices[m.pk] = price
    available_services = list(
        Massage.objects.filter(is_archived=False).values("pk", "name").order_by("name")
    )
    available_services_json = json.dumps([{"id": s["pk"], "name": s["name"]} for s in available_services])
    return {
        "form": form,
        "date_str": date_str,
        "appointment": appointment,
        "service_prices": json.dumps(service_prices),
        "available_services_json": available_services_json,
        "extra_services_data": json.dumps(extra_services_data or []),
    }


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@specialist_required
def index(request):
    today = date.today()
    return render(request, "cabinet/index.html", {"today": today.isoformat()})


@specialist_required
def settings(request):
    specialist = request.specialist
    schedule = WorkSchedule.for_specialist(specialist)
    return render(request, "cabinet/settings.html", {
        "schedule_form": WorkScheduleForm(instance=schedule),
        "exceptions": ScheduleException.objects.filter(specialist=specialist),
        "blocked_slots": BlockedSlot.objects.filter(specialist=specialist).order_by("date", "time_start"),
    })


# ---------------------------------------------------------------------------
# HTMX partials
# ---------------------------------------------------------------------------

def _appointment_saved_response(request, apt_date: date, specialist: Specialist):
    """Закрывает модалку и обновляет панель дня после сохранения записи."""
    day_html = render_to_string(
        "cabinet/partials/day_schedule.html",
        _day_context(apt_date, specialist),
        request=request,
    )
    oob_close = '<div id="cabinet-modal" hx-swap-oob="innerHTML"></div>'
    response = HttpResponse(day_html + oob_close)
    response["HX-Retarget"] = "#day-panel"
    response["HX-Reswap"] = "innerHTML"
    response["HX-Trigger"] = "appointmentChanged"
    return response

@specialist_required
def day_schedule(request, date_str: str):
    try:
        selected_date = date.fromisoformat(date_str)
    except ValueError:
        return render(request, "cabinet/partials/day_schedule.html", {"error": True})
    return render(
        request, "cabinet/partials/day_schedule.html",
        _day_context(selected_date, request.specialist),
    )


@specialist_required
def appointment_add(request):
    specialist = request.specialist
    date_str = request.GET.get("date") or request.POST.get("date", "")
    try:
        initial_date = date.fromisoformat(date_str)
    except ValueError:
        initial_date = date.today()
        date_str = initial_date.isoformat()

    if request.method == "POST":
        extra_services = _parse_extra_services(request.POST)
        extra_duration = _compute_extra_duration(extra_services)

        form = AppointmentForm(request.POST, specialist=specialist)
        form._extra_duration = extra_duration

        if form.is_valid():
            sessions = form.cleaned_data.pop("sessions")
            apt: Appointment = form.save(commit=False)
            apt.specialist = specialist
            schedule = WorkSchedule.for_specialist(specialist)

            if sessions > 1:
                dates = _series_dates(apt.date, sessions, schedule, specialist)
                break_minutes = schedule.break_between_minutes
                conflict_dates = []
                for d in dates:
                    day_conflicts = find_time_conflicts(
                        d, apt.time_start, apt.service, break_minutes,
                        specialist=specialist,
                        extra_duration=extra_duration,
                    )
                    if day_conflicts:
                        conflict_dates.append((d, day_conflicts))
                if conflict_dates:
                    lines = []
                    for d, day_conflicts in conflict_dates:
                        lines.append(
                            f"{d.strftime('%d.%m')}: " + _conflict_message(d, day_conflicts, break_minutes)
                        )
                    form.add_error(None, " | ".join(lines))
                    extra_services_data = [
                        {"pk": None, "service_id": es["service"].pk, "cost": str(int(es["cost"]))}
                        for es in extra_services
                    ]
                    return render(request, "cabinet/partials/appointment_form.html",
                                  _apt_form_context(specialist, date_str, form,
                                                    extra_services_data=extra_services_data))

                series = AppointmentSeries.objects.create(
                    specialist=specialist,
                    service=apt.service,
                    total_sessions=sessions,
                )
                for d in dates:
                    parent_apt = Appointment.objects.create(
                        specialist=specialist,
                        client_name=apt.client_name,
                        client_phone=apt.client_phone,
                        address=apt.address,
                        is_travel=apt.is_travel,
                        service=apt.service,
                        date=d,
                        time_start=apt.time_start,
                        cost=apt.cost,
                        transport_cost=apt.transport_cost,
                        notes=apt.notes,
                        discount_percent=apt.discount_percent,
                        series=series,
                    )
                    _create_additional_services(parent_apt, extra_services, specialist)
            else:
                apt.save()
                _create_additional_services(apt, extra_services, specialist)

            return _appointment_saved_response(request, apt.date, specialist)

        extra_services_data = [
            {"pk": None, "service_id": es["service"].pk, "cost": str(int(es["cost"]))}
            for es in extra_services
        ]
        return render(request, "cabinet/partials/appointment_form.html",
                      _apt_form_context(specialist, date_str, form,
                                        extra_services_data=extra_services_data))

    form = AppointmentForm(initial={"date": initial_date}, specialist=specialist)
    return render(request, "cabinet/partials/appointment_form.html",
                  _apt_form_context(specialist, date_str, form))


@specialist_required
def appointment_edit(request, pk: int):
    specialist = request.specialist
    appointment = get_object_or_404(
        Appointment.objects.prefetch_related("additional_services__service"),
        pk=pk, specialist=specialist, parent__isnull=True,
    )
    date_str = appointment.date.isoformat()

    extra_services_data = [
        {"pk": c.pk, "service_id": c.service_id, "cost": str(int(c.cost))}
        for c in appointment.additional_services.order_by("time_start", "pk")
    ]

    if request.method == "POST":
        extra_services = _parse_extra_services(request.POST)
        extra_duration = _compute_extra_duration(extra_services)

        form = AppointmentForm(request.POST, instance=appointment, specialist=specialist)
        form._extra_duration = extra_duration

        if form.is_valid():
            form.cleaned_data.pop("sessions", None)
            form.save()

            # Sync additional services
            submitted_pks = {es["pk"] for es in extra_services if es["pk"]}
            # Delete removed children
            appointment.additional_services.exclude(pk__in=submitted_pks).delete()
            # Update existing and create new
            for es in extra_services:
                if es["pk"]:
                    try:
                        child = appointment.additional_services.get(pk=es["pk"])
                        child.service = es["service"]
                        child.cost = es["cost"]
                        child.discount_percent = appointment.discount_percent
                        child.save(update_fields=["service", "cost", "discount_percent"])
                    except Appointment.DoesNotExist:
                        # create instead
                        _create_additional_services(appointment, [es], specialist)
                else:
                    _create_additional_services(appointment, [es], specialist)
            _recompute_children_times(appointment)

            # Apply to following in series if requested
            apply_to_following = request.POST.get("apply_to_following") == "1"
            if apply_to_following and appointment.series_id:
                following = Appointment.objects.filter(
                    series=appointment.series,
                    parent__isnull=True,
                    date__gt=appointment.date,
                ).order_by("date")
                for sibling in following:
                    sibling.time_start = appointment.time_start
                    sibling.cost = appointment.cost
                    sibling.transport_cost = appointment.transport_cost
                    sibling.notes = appointment.notes
                    sibling.discount_percent = appointment.discount_percent
                    sibling.is_travel = appointment.is_travel
                    sibling.save(update_fields=[
                        "time_start", "cost", "transport_cost", "notes",
                        "discount_percent", "is_travel",
                    ])
                    # Sync additional services for each sibling
                    sibling.additional_services.all().delete()
                    _create_additional_services(sibling, extra_services, specialist)

            return _appointment_saved_response(request, appointment.date, specialist)

        extra_services_data = [
            {"pk": es["pk"], "service_id": es["service"].pk, "cost": str(int(es["cost"]))}
            for es in extra_services
        ]
        return render(request, "cabinet/partials/appointment_form.html",
                      _apt_form_context(specialist, date_str, form, appointment,
                                        extra_services_data=extra_services_data))

    return render(request, "cabinet/partials/appointment_form.html",
                  _apt_form_context(specialist, date_str, form=AppointmentForm(instance=appointment, specialist=specialist),
                                    appointment=appointment, extra_services_data=extra_services_data))


@specialist_required
@require_POST
def appointment_status(request, pk: int):
    specialist = request.specialist
    appointment = get_object_or_404(Appointment, pk=pk, specialist=specialist)
    new_status = request.POST.get("status")
    allowed = {
        Appointment.SCHEDULED: (Appointment.COMPLETED,),
        Appointment.COMPLETED: (Appointment.SCHEDULED,),
    }
    if new_status in allowed.get(appointment.status, ()):
        appointment.status = new_status
        appointment.save()
        # Also update children
        appointment.additional_services.all().update(status=new_status)
    response = render(
        request, "cabinet/partials/day_schedule.html",
        _day_context(appointment.date, specialist),
    )
    response["HX-Trigger"] = "appointmentChanged"
    return response


@specialist_required
def appointment_confirm_delete(request, pk: int):
    appointment = get_object_or_404(Appointment, pk=pk, specialist=request.specialist)
    if appointment.series_id and not appointment.parent_id:
        return render(request, "cabinet/partials/series_cancel_modal.html", {"appointment": appointment})
    return render(request, "cabinet/partials/appointment_confirm_delete.html", {"appointment": appointment})


@specialist_required
@require_POST
def appointment_delete(request, pk: int):
    specialist = request.specialist
    appointment = get_object_or_404(Appointment, pk=pk, specialist=specialist)
    saved_date = appointment.date
    appointment.delete()
    day_html = render_to_string(
        "cabinet/partials/day_schedule.html",
        _day_context(saved_date, specialist),
        request=request,
    )
    oob_close = '<div id="cabinet-modal" hx-swap-oob="innerHTML"></div>'
    response = HttpResponse(day_html + oob_close)
    response["HX-Retarget"] = "#day-panel"
    response["HX-Reswap"] = "innerHTML"
    response["HX-Trigger"] = "appointmentChanged"
    return response


@specialist_required
@require_POST
def series_cancel_following(request, pk: int):
    specialist = request.specialist
    appointment = get_object_or_404(Appointment, pk=pk, specialist=specialist, parent__isnull=True)
    saved_date = appointment.date
    Appointment.objects.filter(
        series=appointment.series, parent__isnull=True, date__gte=appointment.date
    ).delete()  # CASCADE handles children
    day_html = render_to_string(
        "cabinet/partials/day_schedule.html",
        _day_context(saved_date, specialist),
        request=request,
    )
    oob_close = '<div id="cabinet-modal" hx-swap-oob="innerHTML"></div>'
    response = HttpResponse(day_html + oob_close)
    response["HX-Retarget"] = "#day-panel"
    response["HX-Reswap"] = "innerHTML"
    response["HX-Trigger"] = "appointmentChanged"
    return response


@specialist_required
@require_POST
def series_cancel_action(request, pk: int):
    specialist = request.specialist
    appointment = get_object_or_404(
        Appointment.objects.select_related("series").prefetch_related("additional_services__service"),
        pk=pk, specialist=specialist, parent__isnull=True,
    )
    saved_date = appointment.date
    action = request.POST.get("action", "cancel_one")
    include_main = "include_main" in request.POST

    # Collect additional service_ids that were checked
    extra_service_ids = set()
    for child in appointment.additional_services.all():
        if request.POST.get(f"include_service_{child.service_id}"):
            extra_service_ids.add(child.service_id)

    def _detach_kept_children(parent):
        """Unlink children NOT selected for cancellation so CASCADE won't delete them."""
        keep_ids = [
            c.pk for c in parent.additional_services.all()
            if c.service_id not in extra_service_ids
        ]
        if keep_ids:
            Appointment.objects.filter(pk__in=keep_ids).update(parent=None)

    if action == "cancel_one":
        if include_main:
            _detach_kept_children(appointment)
            appointment.delete()
        else:
            appointment.additional_services.filter(service_id__in=extra_service_ids).delete()
    else:  # cancel_following
        if include_main:
            affected = list(
                Appointment.objects.filter(
                    series=appointment.series, parent__isnull=True, date__gte=appointment.date
                ).prefetch_related("additional_services")
            )
            for parent in affected:
                _detach_kept_children(parent)
            Appointment.objects.filter(pk__in=[p.pk for p in affected]).delete()
        else:
            Appointment.objects.filter(
                parent__series=appointment.series,
                parent__date__gte=appointment.date,
                service_id__in=extra_service_ids,
            ).delete()

    day_html = render_to_string(
        "cabinet/partials/day_schedule.html",
        _day_context(saved_date, specialist),
        request=request,
    )
    oob_close = '<div id="cabinet-modal" hx-swap-oob="innerHTML"></div>'
    response = HttpResponse(day_html + oob_close)
    response["HX-Retarget"] = "#day-panel"
    response["HX-Reswap"] = "innerHTML"
    response["HX-Trigger"] = "appointmentChanged"
    return response


def _series_reschedule_context(appointment, specialist, target_date, check_time, existing_conflicts):
    """Build context for series reschedule form, checking conflicts."""
    schedule = WorkSchedule.for_specialist(specialist)
    break_minutes = schedule.break_between_minutes
    travel_break_minutes = schedule.break_between_travel_minutes

    extra_duration = 0
    try:
        extra_duration = _compute_extra_duration([
            {"service": c.service} for c in appointment.additional_services.all()
        ])
    except Exception:
        pass

    if not existing_conflicts:
        conflicts = find_time_conflicts(
            target_date, check_time, appointment.service, break_minutes,
            specialist=specialist,
            is_travel=appointment.is_travel,
            travel_break_minutes=travel_break_minutes,
            extra_duration=extra_duration,
        )
    else:
        conflicts = existing_conflicts

    shift_count = Appointment.objects.filter(
        series=appointment.series, parent__isnull=True, date__gte=appointment.date
    ).count()

    return {
        "appointment": appointment,
        "target_date": target_date,
        "target_time": check_time,
        "has_conflict": bool(conflicts),
        "shift_count": shift_count,
        "conflict_info": conflicts[0] if conflicts else None,
    }


@specialist_required
def series_reschedule(request, pk: int):
    specialist = request.specialist
    appointment = get_object_or_404(
        Appointment.objects.prefetch_related("additional_services__service"),
        pk=pk, specialist=specialist, parent__isnull=True,
    )

    if request.method == "POST":
        target_date_str = request.POST.get("target_date", "")
        new_time_str = request.POST.get("new_time", "").strip()
        try:
            target_date = date.fromisoformat(target_date_str)
        except ValueError:
            return HttpResponse("Неверная дата", status=400)

        delta = target_date - appointment.date

        parents = list(
            Appointment.objects.filter(
                series=appointment.series, parent__isnull=True, date__gte=appointment.date
            ).prefetch_related("additional_services").order_by("date")
        )

        new_time = None
        if new_time_str:
            from datetime import time as time_type
            try:
                h, m = new_time_str.split(":")
                new_time = time_type(int(h), int(m))
            except (ValueError, AttributeError):
                pass

        if new_time:
            schedule = WorkSchedule.for_specialist(specialist)
            break_minutes = schedule.break_between_minutes
            travel_break_minutes = schedule.break_between_travel_minutes
            extra_duration = _compute_extra_duration([
                {"service": c.service} for c in appointment.additional_services.all()
            ])
            conflicts = find_time_conflicts(
                target_date, new_time, appointment.service, break_minutes,
                specialist=specialist,
                exclude_pk=appointment.pk,
                is_travel=appointment.is_travel,
                travel_break_minutes=travel_break_minutes,
                extra_duration=extra_duration,
            )
            if conflicts:
                form_ctx = _series_reschedule_context(appointment, specialist, target_date, new_time, conflicts)
                return render(request, "cabinet/partials/series_reschedule_form.html", form_ctx)

        for parent in parents:
            new_date = parent.date + delta
            if new_time and parent.pk == appointment.pk:
                parent.time_start = new_time
                parent.date = new_date
                parent.save(update_fields=["date", "time_start"])
                _recompute_children_times(parent)
            else:
                parent.date = new_date
                parent.save(update_fields=["date"])
            parent.additional_services.all().update(date=new_date)

        day_html = render_to_string(
            "cabinet/partials/day_schedule.html",
            _day_context(target_date, specialist),
            request=request,
        )
        oob_close = '<div id="cabinet-modal" hx-swap-oob="innerHTML"></div>'
        response = HttpResponse(day_html + oob_close)
        response["HX-Retarget"] = "#day-panel"
        response["HX-Reswap"] = "innerHTML"
        response["HX-Trigger"] = "appointmentChanged"
        return response

    # GET: compute target date and check for conflicts
    target_date = _next_series_working_day(appointment.series_id, specialist)
    if not target_date:
        return HttpResponse("Не удалось определить дату переноса", status=400)

    ctx = _series_reschedule_context(appointment, specialist, target_date, appointment.time_start, [])
    return render(request, "cabinet/partials/series_reschedule_form.html", ctx)


# ---------------------------------------------------------------------------
# Settings helpers
# ---------------------------------------------------------------------------

def _exception_section_ctx(specialist: Specialist) -> dict:
    return {"exceptions": ScheduleException.objects.filter(specialist=specialist)}


def _blocked_slot_section_ctx(specialist: Specialist) -> dict:
    return {"blocked_slots": BlockedSlot.objects.filter(specialist=specialist).order_by("date", "time_start")}


def _exception_section_response(request):
    response = render(
        request, "cabinet/partials/exception_section.html",
        _exception_section_ctx(request.specialist),
    )
    response["HX-Retarget"] = "#exceptions-section"
    response["HX-Reswap"] = "innerHTML"
    return response


def _blocked_slot_section_response(request):
    response = render(
        request, "cabinet/partials/blocked_slot_section.html",
        _blocked_slot_section_ctx(request.specialist),
    )
    response["HX-Retarget"] = "#blocked-slots-section"
    response["HX-Reswap"] = "innerHTML"
    return response


# ---------------------------------------------------------------------------
# Settings views
# ---------------------------------------------------------------------------

@specialist_required
@require_POST
def schedule_save(request):
    specialist = request.specialist
    schedule = WorkSchedule.for_specialist(specialist)
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


@specialist_required
def exception_add(request):
    specialist = request.specialist
    if request.method == "POST":
        form = ScheduleExceptionForm(request.POST)
        if form.is_valid():
            exc = form.save(commit=False)
            exc.specialist = specialist
            exc.save()
            return _exception_section_response(request)
        response = render(request, "cabinet/partials/exception_form.html", {"form": form})
        response["HX-Retarget"] = "#exception-form-container"
        return response
    return render(request, "cabinet/partials/exception_form.html", {"form": ScheduleExceptionForm()})


@specialist_required
def exception_edit(request, pk: int):
    exc = get_object_or_404(ScheduleException, pk=pk, specialist=request.specialist)
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


@specialist_required
@require_POST
def exception_delete(request, pk: int):
    get_object_or_404(ScheduleException, pk=pk, specialist=request.specialist).delete()
    return _exception_section_response(request)


@specialist_required
def blocked_slot_add(request):
    specialist = request.specialist
    if request.method == "POST":
        form = BlockedSlotForm(request.POST)
        if form.is_valid():
            slot = form.save(commit=False)
            slot.specialist = specialist
            slot.save()
            return _blocked_slot_section_response(request)
        response = render(request, "cabinet/partials/blocked_slot_form.html", {"form": form})
        response["HX-Retarget"] = "#blocked-slot-form-container"
        return response
    return render(request, "cabinet/partials/blocked_slot_form.html", {"form": BlockedSlotForm()})


@specialist_required
def blocked_slot_edit(request, pk: int):
    slot = get_object_or_404(BlockedSlot, pk=pk, specialist=request.specialist)
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


@specialist_required
@require_POST
def blocked_slot_delete(request, pk: int):
    get_object_or_404(BlockedSlot, pk=pk, specialist=request.specialist).delete()
    return _blocked_slot_section_response(request)


# ---------------------------------------------------------------------------
# Prices helpers
# ---------------------------------------------------------------------------

def _prices_ctx(specialist: Specialist) -> dict:
    massages = Massage.objects.filter(is_archived=False).order_by("-massage_type", "order")
    all_massages = Massage.objects.order_by("-massage_type", "order", "name")
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
        "all_massages": all_massages,
        "site_settings": site_settings,
        "prices_due": prices_due,
        "active_discount": active_discount,
        "discounts": discounts,
        "can_manage": specialist.can_manage_prices,
    }


def _generate_unique_slug(name: str, exclude_pk: int | None = None) -> str:
    base = _slugify_ru(name) or "usluga"
    slug = base
    i = 2
    while True:
        qs = Massage.objects.filter(slug=slug)
        if exclude_pk:
            qs = qs.exclude(pk=exclude_pk)
        if not qs.exists():
            return slug
        slug = f"{base}-{i}"
        i += 1



def _discount_section_response(request):
    ctx = _prices_ctx(request.specialist)
    discount_html = render_to_string("cabinet/partials/discount_section.html", ctx, request=request)
    price_list_html = render_to_string("cabinet/partials/price_list_section.html", ctx, request=request)
    price_change_html = render_to_string("cabinet/partials/price_change_section.html", ctx, request=request)
    oob_close = '<div id="cabinet-modal" hx-swap-oob="innerHTML"></div>'
    oob_price_list = f'<div id="price-list-section" class="settings-card" hx-swap-oob="innerHTML">{price_list_html}</div>'
    oob_price_change = f'<div id="price-change-section" class="settings-card" hx-swap-oob="innerHTML">{price_change_html}</div>'
    response = HttpResponse(discount_html + oob_close + oob_price_list + oob_price_change)
    response["HX-Retarget"] = "#discounts-section"
    response["HX-Reswap"] = "innerHTML"
    return response


def _massage_section_response(request):
    ctx = _prices_ctx(request.specialist)
    massage_list_html = render_to_string("cabinet/partials/massage_list_section.html", ctx, request=request)
    price_list_html = render_to_string("cabinet/partials/price_list_section.html", ctx, request=request)
    price_change_html = render_to_string("cabinet/partials/price_change_section.html", ctx, request=request)
    oob_close = '<div id="cabinet-modal" hx-swap-oob="innerHTML"></div>'
    oob_price_list = f'<div id="price-list-section" class="settings-card" hx-swap-oob="innerHTML">{price_list_html}</div>'
    oob_price_change = f'<div id="price-change-section" class="settings-card" hx-swap-oob="innerHTML">{price_change_html}</div>'
    response = HttpResponse(massage_list_html + oob_close + oob_price_list + oob_price_change)
    response["HX-Retarget"] = "#massage-list-section"
    response["HX-Reswap"] = "innerHTML"
    return response


# ---------------------------------------------------------------------------
# Prices views
# ---------------------------------------------------------------------------

@specialist_required
def prices(request):
    return render(request, "cabinet/prices.html", _prices_ctx(request.specialist))


@prices_manager_required
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

    ctx = _prices_ctx(request.specialist)
    price_list_html = render_to_string(
        "cabinet/partials/price_list_section.html", ctx, request=request
    )
    price_change_html = render_to_string(
        "cabinet/partials/price_change_section.html", ctx, request=request
    )
    oob = f'<div id="price-change-section" class="settings-card" hx-swap-oob="innerHTML">{price_change_html}</div>'
    response = HttpResponse(price_list_html + oob)
    response["HX-Retarget"] = "#price-list-section"
    response["HX-Reswap"] = "innerHTML"
    response["HX-Trigger"] = "pricesChanged"
    return response


@prices_manager_required
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

    response = render(
        request, "cabinet/partials/price_change_section.html",
        _prices_ctx(request.specialist),
    )
    response["HX-Retarget"] = "#price-change-section"
    response["HX-Reswap"] = "innerHTML"
    return response


@prices_manager_required
@require_POST
def prices_apply_change(request):
    massages = Massage.objects.filter(is_archived=False, new_price__isnull=False)
    for massage in massages:
        massage.price = massage.new_price
        massage.new_price = None
        massage.save(update_fields=["price", "new_price"])
    site_settings = SiteSettings.objects.first()
    site_settings.price_change_date = None
    site_settings.save(update_fields=["price_change_date"])

    return render(request, "cabinet/prices.html", _prices_ctx(request.specialist))


@prices_manager_required
def discount_add(request):
    if request.method == "POST":
        form = DiscountForm(request.POST)
        if form.is_valid():
            form.save()
            return _discount_section_response(request)
        response = render(request, "cabinet/partials/discount_form.html", {"form": form})
        response["HX-Retarget"] = "#cabinet-modal"
        return response
    return render(request, "cabinet/partials/discount_form.html", {"form": DiscountForm()})


@prices_manager_required
def discount_edit(request, pk: int):
    discount = get_object_or_404(Discount, pk=pk)
    if request.method == "POST":
        form = DiscountForm(request.POST, instance=discount)
        if form.is_valid():
            form.save()
            return _discount_section_response(request)
        response = render(request, "cabinet/partials/discount_form.html", {"form": form, "discount": discount})
        response["HX-Retarget"] = "#cabinet-modal"
        return response
    return render(request, "cabinet/partials/discount_form.html", {
        "form": DiscountForm(instance=discount), "discount": discount,
    })


@prices_manager_required
@require_POST
def discount_delete(request, pk: int):
    get_object_or_404(Discount, pk=pk).delete()
    return _discount_section_response(request)


@prices_manager_required
def massage_add(request):
    if request.method == "POST":
        form = MassageForm(request.POST, request.FILES)
        if form.is_valid():
            massage = form.save(commit=False)
            if not massage.slug:
                massage.slug = _generate_unique_slug(massage.name)
            massage.save()
            return _massage_section_response(request)
        response = render(request, "cabinet/partials/massage_form.html", {"form": form})
        response["HX-Retarget"] = "#cabinet-modal"
        response["HX-Reswap"] = "innerHTML"
        return response
    return render(request, "cabinet/partials/massage_form.html", {"form": MassageForm()})


@prices_manager_required
def massage_edit(request, pk: int):
    massage = get_object_or_404(Massage, pk=pk)
    if request.method == "POST":
        form = MassageForm(request.POST, request.FILES, instance=massage)
        if form.is_valid():
            form.save()
            return _massage_section_response(request)
        response = render(request, "cabinet/partials/massage_form.html", {"form": form, "massage": massage})
        response["HX-Retarget"] = "#cabinet-modal"
        response["HX-Reswap"] = "innerHTML"
        return response
    return render(request, "cabinet/partials/massage_form.html", {
        "form": MassageForm(instance=massage), "massage": massage,
    })


@prices_manager_required
def massage_confirm_archive(request, pk: int):
    massage = get_object_or_404(Massage, pk=pk)
    return render(request, "cabinet/partials/massage_confirm_archive.html", {"massage": massage})


@prices_manager_required
@require_POST
def massage_toggle_archive(request, pk: int):
    massage = get_object_or_404(Massage, pk=pk)
    massage.is_archived = not massage.is_archived
    massage.save(update_fields=["is_archived"])
    return _massage_section_response(request)


# ---------------------------------------------------------------------------
# FullCalendar JSON events
# ---------------------------------------------------------------------------

@specialist_required
def calendar_events(request):
    specialist = request.specialist
    start_str = request.GET.get("start", "")
    end_str = request.GET.get("end", "")
    try:
        start = date.fromisoformat(start_str[:10])
        end = date.fromisoformat(end_str[:10])
    except (ValueError, TypeError):
        return JsonResponse([], safe=False)

    events = []
    schedule = WorkSchedule.for_specialist(specialist)
    working_days = schedule.working_weekdays()
    exceptions = ScheduleException.objects.filter(
        specialist=specialist, date_from__lte=end, date_to__gte=start
    )

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
        Appointment.objects.filter(
            date__gte=start, date__lt=end, specialist=specialist, parent__isnull=True
        )
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
