from types import SimpleNamespace

from cabinet.models import Specialist
from tgbot.models import BotSettings

from .models import SiteSettings

# Мессенджеры, серверы которых находятся за пределами РФ.
FOREIGN_MESSENGERS = ("Telegram", "WhatsApp")


def build_policy_context() -> SimpleNamespace:
    """Данные для Политики обработки ПД: реквизиты из SiteSettings и перечень
    активных функций/мессенджеров — чтобы текст соответствовал реальной обработке."""
    cfg = SiteSettings.objects.first() or SiteSettings()
    therapists = Specialist.objects.filter(is_active=True)
    bot = BotSettings.objects.first()
    bot_enabled = bool(bot and bot.is_enabled and bot.bot_username)

    telegram = bot_enabled or any(
        t.telegram_username and t.telegram_active for t in therapists
    )
    whatsapp = any(t.whatsapp_number and t.whatsapp_active for t in therapists)
    max_ = any(t.max_messanger and t.max_messanger_active for t in therapists)

    names = []
    if telegram:
        names.append("Telegram")
    if whatsapp:
        names.append("WhatsApp")
    if max_:
        names.append("MAX")
    foreign = [n for n in names if n in FOREIGN_MESSENGERS]

    return SimpleNamespace(
        operator_name=cfg.operator_name,
        operator_inn=cfg.operator_inn,
        operator_address=cfg.operator_address,
        operator_email=cfg.operator_email,
        retention_text=cfg.retention_text,
        updated_at=cfg.privacy_updated_at,
        body=cfg.privacy_body,
        booking_enabled=cfg.online_booking_enabled,
        cabinet_enabled=cfg.client_cabinet_enabled,
        reviews_enabled=cfg.reviews_enabled,
        messengers=", ".join(names),
        foreign_transfer=bool(foreign),
        foreign_services=", ".join(foreign),
    )
