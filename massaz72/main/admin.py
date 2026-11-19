from django.contrib import admin

from .forms import SiteSettingsForm
from .models import SiteSettings


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    form = SiteSettingsForm
    list_display = [
        "head_title",
        "price_change_date",
    ]
