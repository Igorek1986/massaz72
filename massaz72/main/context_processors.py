from datetime import datetime

from .models import About, SiteSettings


def common_context(request):
    therapists = About.objects.filter(is_active=True).order_by("order")
    primary = therapists.first()
    has_contacts = any(
        (t.telegram_username and t.telegram_active)
        or (t.whatsapp_number and t.whatsapp_active)
        or (t.max_messanger and t.max_messanger_active)
        for t in therapists
    )
    return {
        "therapists": therapists,
        "about": primary,  # backward compat
        "telegram_username": primary.telegram_username if primary else "",
        "whatsapp_number": primary.whatsapp_number if primary else "",
        "max_messanger": primary.max_messanger if primary else "",
        "has_contacts": has_contacts,
        "year": datetime.now().year,
    }


def site_settings(request):
    site_setting = SiteSettings.objects.first()
    return {
        "site_settings": site_setting,
    }
