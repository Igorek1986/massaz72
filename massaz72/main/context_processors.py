from datetime import datetime

from django.utils import timezone

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
    change_date = site_setting.price_change_date if site_setting else None
    today = timezone.localdate()
    return {
        "site_settings": site_setting,
        "price_change_date": change_date,
        # Новые цены уже вступили в силу
        "new_prices_active": bool(change_date and change_date <= today),
        # Изменение цен запланировано, но дата ещё не наступила
        "price_change_pending": bool(change_date and change_date > today),
    }
