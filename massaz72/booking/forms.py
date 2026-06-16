from django import forms
from django.utils import timezone

from cabinet.models import Specialist
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
            "preferred_date": forms.DateInput(attrs={
                "type": "date", "class": "booking-form__input",
            }),
            "preferred_time": forms.TimeInput(attrs={
                "type": "time", "class": "booking-form__input",
            }),
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
        if specialists.count() <= 1:
            self.fields.pop("specialist")
        else:
            self.fields["specialist"].queryset = specialists
            self.fields["specialist"].required = True

        # Онлайн-запись — только курсом: количество сеансов обязательно.
        # Показываем поле, только если варианты заданы в админке.
        session_options = BookingSessionOption.objects.filter(is_active=True)
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

    def clean_preferred_date(self):
        d = self.cleaned_data.get("preferred_date")
        if d and d < timezone.localdate():
            raise forms.ValidationError("Дата не может быть в прошлом.")
        return d
