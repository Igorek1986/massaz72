from datetime import datetime
from django.conf import settings
from .models import About, SiteSettings


def common_context(request):
    about = About.objects.filter(is_active=True).first()
    return {
        "telegram_username": settings.TELEGRAM_USERNAME,
        "whatsapp_number": settings.WHATSAPP_NUMBER,
        "year": datetime.now().year,
        'about': about,
    }


def site_settings(request):
    site_setting = SiteSettings.objects.first()
    return {
        "site_settings": site_setting,
    }