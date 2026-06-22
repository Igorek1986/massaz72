from django import forms
from django.utils import timezone

from cabinet.models import Specialist, WorkSchedule
from reviews.spam import make_timestamp_token
from services.models import Massage

from .models import BookingRequest, BookingSessionOption


class BookingForm(forms.ModelForm):
    # Honeypot + time-trap (как в форме отзывов).
    website = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            "tabindex": "-1", "autocomplete": "off", "class": "booking-hp",
        }),
        label="",
    )
    ts = forms.CharField(required=False, widget=forms.HiddenInput)
    consent = forms.BooleanField(
        required=True,
        error_messages={
            "required": "Необходимо согласие на обработку персональных данных.",
        },
    )

    class Meta:
        model = BookingRequest
        fields = [
            "client_name", "service", "specialist", "sessions",
            "preferred_date", "preferred_time", "phone", "address", "comment",
        ]
        widgets = {
            "client_name": forms.TextInput(attrs={
                "maxlength": 255, "placeholder": "Как вас зовут",
                "class": "booking-form__input",
            }),
            "service": forms.Select(attrs={"class": "booking-form__input"}),
            "specialist": forms.Select(attrs={"class": "booking-form__input"}),
            "sessions": forms.Select(attrs={"class": "booking-form__input"}),
            # Дата выбирается календарём, время — пикером часы→минуты;
            # сами значения — скрытые поля.
            "preferred_date": forms.HiddenInput(),
            "preferred_time": forms.HiddenInput(),
            "phone": forms.TextInput(attrs={
                "type": "tel", "maxlength": 20, "placeholder": "Телефон (необязательно)",
                "class": "booking-form__input",
            }),
            "address": forms.TextInput(attrs={
                "maxlength": 500, "placeholder": "Адрес (для выезда на дом)",
                "class": "booking-form__input",
            }),
            "comment": forms.Textarea(attrs={
                "maxlength": 2000, "rows": 3, "placeholder": "Комментарий (необязательно)",
                "class": "booking-form__textarea",
            }),
        }
        labels = {
            "client_name": "Имя",
            "service": "Услуга",
            "specialist": "Мастер",
            "sessions": "Количество сеансов",
            "preferred_date": "Желаемая дата",
            "preferred_time": "Желаемое время",
            "phone": "Телефон",
            "comment": "Комментарий",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["service"].queryset = Massage.objects.filter(is_archived=False)
        self.fields["service"].required = True
        self.fields["client_name"].required = True
        self.fields["preferred_date"].required = True
        self.fields["preferred_time"].required = True
        self.fields["phone"].required = False

        # Выбор мастера показываем только если активных больше одного.
        specialists = Specialist.objects.filter(is_active=True)
        single_specialist = specialists.first() if specialists.count() == 1 else None
        if specialists.count() <= 1:
            self.fields.pop("specialist")
        else:
            self.fields["specialist"].queryset = specialists
            self.fields["specialist"].required = True

        # Онлайн-запись — только курсом: количество сеансов обязательно.
        # Варианты сеансов теперь у каждого специалиста свои.
        # Один мастер → его варианты; несколько → все активные (JS сузит список
        # под выбранного мастера, clean() проверит соответствие).
        all_options = BookingSessionOption.objects.filter(is_active=True)
        if single_specialist is not None:
            session_options = all_options.filter(specialist=single_specialist)
        else:
            session_options = all_options
        if not session_options.exists():
            self.fields.pop("sessions")
        else:
            self.fields["sessions"].queryset = session_options
            self.fields["sessions"].required = True
            self.fields["sessions"].empty_label = "Выберите количество сеансов"

        if not self.is_bound:
            self.fields["ts"].initial = make_timestamp_token()

    def clean_client_name(self):
        name = (self.cleaned_data.get("client_name") or "").strip()
        if not name:
            raise forms.ValidationError("Укажите имя.")
        return name

    def clean_phone(self):
        """Телефон необязателен; если указан — проверяем и нормализуем (РФ)."""
        from .phone import normalize_ru_phone

        try:
            return normalize_ru_phone(self.cleaned_data.get("phone"))
        except ValueError:
            raise forms.ValidationError("Укажите корректный номер телефона.")

    def clean_preferred_date(self):
        d = self.cleaned_data.get("preferred_date")
        if d and d < timezone.localdate():
            raise forms.ValidationError("Дата не может быть в прошлом.")
        return d

    def clean(self):
        cleaned = super().clean()
        d = cleaned.get("preferred_date")
        t = cleaned.get("preferred_time")
        service = cleaned.get("service")
        if not (d and t):
            return cleaned

        # Мастер из формы (если выбор есть) или единственный активный.
        spec = cleaned.get("specialist") or Specialist.objects.filter(
            is_active=True
        ).first()
        if not spec:
            return cleaned

        # Вариант сеансов должен принадлежать выбранному мастеру.
        sessions_opt = cleaned.get("sessions")
        if sessions_opt and sessions_opt.specialist_id != spec.pk:
            self.add_error("sessions", "Выберите количество сеансов для этого мастера.")
            return cleaned

        from cabinet.views import _is_working_day

        from .availability import free_starts

        schedule = WorkSchedule.for_specialist(spec)
        if not _is_working_day(d, schedule, spec):
            self.add_error(
                "preferred_date",
                "В этот день мастер не работает — выберите рабочий день.",
            )
            return cleaned

        # Количество сеансов курса (вариант A: одно время на все дни).
        sessions = sessions_opt.count if sessions_opt else 1
        # Адрес → выездной массаж (увеличенный перерыв после сеанса).
        is_travel = bool((cleaned.get("address") or "").strip())

        # Единая проверка: время должно быть свободно (занятость, обед, брони,
        # рабочие часы, запас перед записью) во ВСЕ дни курса.
        if t not in free_starts(spec, d, service, sessions, is_travel=is_travel):
            self.add_error(
                "preferred_time",
                "Это время недоступно (занято, перерыв или вне рабочих часов). "
                "Выберите свободное время из предложенных.",
            )
        return cleaned
