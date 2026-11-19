from pathlib import Path

from django import forms
from django.core.files.uploadedfile import UploadedFile

from massaz72.utils import validate_file_size

from .models import SiteSettings


SITE_SETTINGS_SECTIONS = {
    "Главная страница": (
        "main_title", "main_subtitle", "background", "child_massage_title",
        "massage_title", "about_title", "contact_title",
    ),
    "Поиск и карточка ссылки": (
        "head_title", "meta_description", "meta_keywords", "social_cover",
        "yandex_verification", "google_verification",
    ),
    "Запись и отзывы": (
        "reviews_enabled", "online_booking_enabled", "client_cabinet_enabled",
        "price_change_date", "booking_hold_minutes", "notify_start", "notify_end",
    ),
    "Политика обработки персональных данных": (
        "operator_name", "operator_inn", "operator_address", "operator_email",
        "retention_text", "privacy_updated_at", "privacy_body",
    ),
}


class SiteSettingsForm(forms.ModelForm):
    class Meta:
        model = SiteSettings
        fields = [name for section in SITE_SETTINGS_SECTIONS.values() for name in section]

    def clean_social_cover(self):
        cover = self.cleaned_data["social_cover"]
        if isinstance(cover, UploadedFile):
            validate_file_size(cover)
            formats = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG"}
            if formats.get(Path(cover.name).suffix.lower()) != cover.image.format:
                raise forms.ValidationError("Загрузите файл JPEG или PNG с подходящим расширением.")
            if max(cover.image.size) > 4096:
                raise forms.ValidationError("Стороны изображения должны быть не больше 4096 пикселей.")
        return cover


class CabinetSiteSettingsForm(SiteSettingsForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if not isinstance(field.widget, (forms.CheckboxInput, forms.ClearableFileInput)):
                field.widget.attrs["class"] = "form-input"

    class Meta(SiteSettingsForm.Meta):
        widgets = {
            "price_change_date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "privacy_body": forms.Textarea(attrs={"rows": 16}),
            "privacy_updated_at": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "notify_start": forms.TimeInput(attrs={"type": "time"}),
            "notify_end": forms.TimeInput(attrs={"type": "time"}),
        }


class SitePaletteForm(forms.Form):
    def __init__(self, *args, palette=None, **kwargs):
        from .palette import HEX_COLOR, PALETTE_FIELDS, THEMES, valid_palette

        super().__init__(*args, **kwargs)
        palette = valid_palette(palette)
        for index, theme in enumerate(THEMES, start=1):
            for key, definition in PALETTE_FIELDS.items():
                label, _, _, variable = definition
                name = f"{theme}_{key}"
                self.fields[name] = forms.RegexField(
                    regex=HEX_COLOR,
                    label=label,
                    initial=palette.get(theme, {}).get(key, definition[index]),
                    widget=forms.TextInput(attrs={
                        "type": "color", "hidden": True, "data-theme-color": theme,
                        "data-css-variable": variable,
                        "data-default-color": definition[index],
                    }),
                )

    def palette(self):
        from .palette import PALETTE_FIELDS, THEMES

        return {
            theme: {key: self.cleaned_data[f"{theme}_{key}"].lower() for key in PALETTE_FIELDS}
            for theme in THEMES
        }
