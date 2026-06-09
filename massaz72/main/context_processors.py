from datetime import datetime

from django.utils import timezone

from tgbot.models import BotSettings

from .models import About, SiteSettings


def common_context(request):
    therapists = About.objects.filter(is_active=True).order_by("order")
    primary = therapists.first()

    # Ссылка на Telegram-бота (один на сайт): показываем, если бот включён.
    bot = BotSettings.objects.first()
    telegram_bot_username = (
        bot.bot_username if bot and bot.is_enabled and bot.bot_username else ""
    )

    has_contacts = bool(telegram_bot_username) or any(
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
        "telegram_bot_username": telegram_bot_username,
        "has_contacts": has_contacts,
        "year": datetime.now().year,
    }


def site_settings(request):
    site_setting = SiteSettings.objects.first()
    change_date = site_setting.price_change_date if site_setting else None
    today = timezone.localdate()

    try:
        from cabinet.models import Discount
        active_discount = Discount.objects.filter(date_from__lte=today, date_to__gte=today).first()
    except Exception:
        active_discount = None

    return {
        "site_settings": site_setting,
        "price_change_date": change_date,
        "new_prices_active": bool(change_date and change_date <= today),
        "price_change_pending": bool(change_date and change_date > today),
        "active_discount": active_discount,
    }
