from datetime import datetime

from .models import About, SiteSettings


def common_context(request):
    about = About.objects.filter(is_active=True).first()
    return {
        "telegram_username": about.telegram_username if about else "",
        "whatsapp_number": about.whatsapp_number if about else "",
        "max_messanger": about.max_messanger if about else "",
        "year": datetime.now().year,
        "about": about,
    }


def site_settings(request):
    site_setting = SiteSettings.objects.first()
    return {
        "site_settings": site_setting,
    }
