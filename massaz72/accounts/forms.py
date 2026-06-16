from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import Client

_INPUT = {"class": "account-form__input"}


class RegisterForm(UserCreationForm):
    phone = forms.CharField(
        label="Телефон (необязательно)", max_length=20, required=False,
        widget=forms.TextInput(attrs={**_INPUT, "type": "tel",
                                      "placeholder": "Телефон"}),
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Логин"
        self.fields["username"].widget.attrs.update({**_INPUT, "placeholder": "Логин"})
        self.fields["username"].help_text = ""
        self.fields["password1"].label = "Пароль"
        self.fields["password1"].widget.attrs.update(_INPUT)
        self.fields["password2"].label = "Повтор пароля"
        self.fields["password2"].widget.attrs.update(_INPUT)


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ["phone"]
        widgets = {
            "phone": forms.TextInput(attrs={**_INPUT, "type": "tel"}),
        }
