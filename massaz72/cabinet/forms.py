from datetime import datetime, timedelta

from django import forms

from .models import Appointment, BlockedSlot, Discount, ScheduleException, WorkSchedule


def _apt_end_dt(apt_date, time_start, service, break_minutes):
    """Возвращает datetime окончания записи с учётом перерыва."""
    duration = 0
    if service:
        duration = service.duration_max or service.duration_min or 0
    return datetime.combine(apt_date, time_start) + timedelta(minutes=duration + break_minutes)


def _apt_end_time(apt_date, time_start, service):
    """Datetime окончания записи без перерыва."""
    duration = 0
    if service:
        duration = service.duration_max or service.duration_min or 0
    return datetime.combine(apt_date, time_start) + timedelta(minutes=duration)


def _conflict_message(apt_date, conflicts, break_minutes):
    """Строит человекочитаемое сообщение об ошибке с подсказкой."""
    # Главный конфликт — первый по времени
    conflict = min(conflicts, key=lambda a: a.time_start)
    conflict_end_dt = _apt_end_time(apt_date, conflict.time_start, conflict.service)

    # Ближайшее свободное = максимальный конец всех конфликтов + перерыв
    latest_end_dt = max(
        _apt_end_time(apt_date, c.time_start, c.service) for c in conflicts
    )
    free_from_dt = latest_end_dt + timedelta(minutes=break_minutes)

    msg = (
        f"Пересечение с записью в {conflict.time_start.strftime('%H:%M')} "
        f"({conflict.client_name})"
    )
    duration = 0
    if conflict.service:
        duration = conflict.service.duration_max or conflict.service.duration_min or 0
    if duration:
        msg += f" — массаж до {conflict_end_dt.strftime('%H:%M')}"
    msg += f". Ближайшее свободное время: {free_from_dt.strftime('%H:%M')}."
    return msg


def find_time_conflicts(apt_date, time_start, service, break_minutes, exclude_pk=None):
    """Возвращает список записей, пересекающихся по времени с новым слотом."""
    existing = (
        Appointment.objects.filter(date=apt_date)
        .exclude(status="cancelled")
        .select_related("service")
    )
    if exclude_pk:
        existing = existing.exclude(pk=exclude_pk)

    new_start_dt = datetime.combine(apt_date, time_start)
    new_end_dt = _apt_end_dt(apt_date, time_start, service, break_minutes)

    conflicts = []
    for apt in existing:
        apt_start_dt = datetime.combine(apt_date, apt.time_start)
        apt_end_dt = _apt_end_dt(apt_date, apt.time_start, apt.service, break_minutes)
        if new_start_dt < apt_end_dt and new_end_dt > apt_start_dt:
            conflicts.append(apt)
    return conflicts


class AppointmentForm(forms.ModelForm):
    sessions = forms.IntegerField(
        min_value=1,
        max_value=60,
        initial=1,
        label="Количество сеансов",
        widget=forms.NumberInput(attrs={"min": "1", "max": "60", "class": "form-input"}),
        help_text="Больше 1 — запись создаётся на каждый рабочий день подряд",
    )

    def clean(self):
        cleaned_data = super().clean()
        apt_date = cleaned_data.get("date")
        time_start = cleaned_data.get("time_start")
        service = cleaned_data.get("service")
        if apt_date and time_start:
            schedule = WorkSchedule.get_solo()
            break_minutes = schedule.break_between_minutes
            conflicts = find_time_conflicts(
                apt_date, time_start, service, break_minutes,
                exclude_pk=self.instance.pk if self.instance.pk else None,
            )
            if conflicts:
                raise forms.ValidationError(
                    _conflict_message(apt_date, conflicts, break_minutes)
                )
        return cleaned_data

    class Meta:
        model = Appointment
        fields = [
            "client_name", "client_phone", "address",
            "service", "date", "time_start",
            "cost", "transport_cost", "notes",
        ]
        widgets = {
            "client_name": forms.TextInput(attrs={"class": "form-input"}),
            "client_phone": forms.TextInput(attrs={"class": "form-input", "type": "tel"}),
            "address": forms.TextInput(attrs={"class": "form-input"}),
            "service": forms.Select(attrs={"class": "form-input", "id": "id_service"}),
            "date": forms.DateInput(attrs={"type": "date", "class": "form-input"}, format="%Y-%m-%d"),
            "time_start": forms.TimeInput(attrs={"type": "time", "class": "form-input"}, format="%H:%M"),
            "cost": forms.NumberInput(attrs={"class": "form-input", "step": "50", "min": "0", "id": "id_cost", "readonly": True}),
            "transport_cost": forms.NumberInput(attrs={"class": "form-input", "step": "10", "min": "0"}),
            "notes": forms.Textarea(attrs={"class": "form-input", "rows": "2"}),
        }


class WorkScheduleForm(forms.ModelForm):
    class Meta:
        model = WorkSchedule
        fields = [
            "monday", "tuesday", "wednesday", "thursday",
            "friday", "saturday", "sunday",
            "break_between_minutes",
        ]
        widgets = {
            "break_between_minutes": forms.NumberInput(
                attrs={"class": "form-input", "min": "0", "max": "120", "style": "width:80px"}
            ),
        }


class ScheduleExceptionForm(forms.ModelForm):
    class Meta:
        model = ScheduleException
        fields = ["date_from", "date_to", "exception_type", "note"]
        widgets = {
            "date_from": forms.DateInput(attrs={"type": "date", "class": "form-input"}, format="%Y-%m-%d"),
            "date_to": forms.DateInput(attrs={"type": "date", "class": "form-input"}, format="%Y-%m-%d"),
            "exception_type": forms.Select(attrs={"class": "form-input"}),
            "note": forms.TextInput(attrs={"class": "form-input"}),
        }


class BlockedSlotForm(forms.ModelForm):
    class Meta:
        model = BlockedSlot
        fields = ["date", "time_start", "time_end", "note"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date", "class": "form-input"}, format="%Y-%m-%d"),
            "time_start": forms.TimeInput(attrs={"type": "time", "class": "form-input"}, format="%H:%M"),
            "time_end": forms.TimeInput(attrs={"type": "time", "class": "form-input"}, format="%H:%M"),
            "note": forms.TextInput(attrs={"class": "form-input"}),
        }


class DiscountForm(forms.ModelForm):
    class Meta:
        model = Discount
        fields = ["discount_type", "value", "date_from", "date_to", "description"]
        widgets = {
            "discount_type": forms.Select(attrs={"class": "form-input"}),
            "value": forms.NumberInput(attrs={"class": "form-input", "step": "1", "min": "0"}),
            "date_from": forms.DateInput(attrs={"type": "date", "class": "form-input"}, format="%Y-%m-%d"),
            "date_to": forms.DateInput(attrs={"type": "date", "class": "form-input"}, format="%Y-%m-%d"),
            "description": forms.TextInput(attrs={"class": "form-input"}),
        }
