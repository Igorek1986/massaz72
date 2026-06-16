from django import forms

from .models import Review
from .spam import make_timestamp_token


class ReviewForm(forms.ModelForm):
    # Honeypot: настоящие пользователи поле не видят и не заполняют.
    website = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            "tabindex": "-1",
            "autocomplete": "off",
            "class": "review-hp",
        }),
        label="",
    )
    # Time-trap: подписанная метка момента рендера формы.
    ts = forms.CharField(required=False, widget=forms.HiddenInput)
    consent = forms.BooleanField(
        required=True,
        error_messages={
            "required": "Необходимо согласие на обработку персональных данных.",
        },
    )

    class Meta:
        model = Review
        fields = ["name", "rating", "text"]
        widgets = {
            "name": forms.TextInput(attrs={
                "maxlength": 100,
                "placeholder": "Как вас зовут",
                "class": "review-form__input",
            }),
            "rating": forms.RadioSelect,
            "text": forms.Textarea(attrs={
                "maxlength": 2000,
                "rows": 4,
                "placeholder": "Расскажите о вашем опыте",
                "class": "review-form__textarea",
            }),
        }
        labels = {
            "name": "Имя",
            "rating": "Оценка",
            "text": "Отзыв",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].required = True
        self.fields["text"].required = True
        self.fields["rating"].required = True
        # Свежий токен time-trap для незаполненной (GET) формы.
        if not self.is_bound:
            self.fields["ts"].initial = make_timestamp_token()

    def clean_text(self):
        text = (self.cleaned_data.get("text") or "").strip()
        if not text:
            raise forms.ValidationError("Напишите текст отзыва.")
        return text

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            raise forms.ValidationError("Укажите имя.")
        return name
