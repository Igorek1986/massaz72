"""
Сборка экземпляра Telegram-бота (pyTelegramBotAPI) и регистрация обработчиков.

Схема работы (как в movies-go):
- клиент пишет боту → сообщение пересылается всем активным администраторам
  с пометкой, кто написал; для каждого доставленного сообщения сохраняется
  связь AdminForward (admin_message_id → клиент);
- администратор отвечает реплаем (Reply) на пересланное сообщение → ответ
  уходит клиенту.

Бот синхронный (threaded=False): один и тот же код обслуживает и polling
(manage.py runbot), и webhook (process_new_updates в Django-view).
"""

import html
import logging

import telebot
from telebot import types

from .models import AdminForward, BotAdmin, BotSettings, DialogMessage, TelegramUser

logger = logging.getLogger(__name__)

# Кнопки меню
BTN_SERVICES = "💰 Услуги и цены"
BTN_BOOK = "📝 Записаться"

# Типы обновлений, которые запрашиваем у Telegram (и для polling, и для webhook).
# Важно: без callback_query не приходят нажатия инлайн-кнопок.
ALLOWED_UPDATES = ["message", "callback_query"]

# Типы сообщений, которые принимаем от клиента/админа
CONTENT_TYPES = [
    "text",
    "photo",
    "document",
    "audio",
    "voice",
    "video",
    "video_note",
    "sticker",
    "animation",
    "contact",
    "location",
]

CONFIRMATION = "✅ Спасибо! Сообщение передано массажисту — он свяжется с вами в ближайшее время."
NO_ADMINS = "✅ Спасибо! Сообщение получено."
DELIVERY_FAILED = "⚠️ Не удалось передать сообщение. Пожалуйста, попробуйте позже."
ADMIN_HINT = (
    "Чтобы ответить клиенту, нажмите «Ответить» (Reply) на пересланном "
    "сообщении этого клиента и напишите текст ответа."
)

# Кэш экземпляров бота по токену (на процесс/воркер)
_bots: dict[str, telebot.TeleBot] = {}


def get_bot(token: str | None = None) -> telebot.TeleBot | None:
    """Возвращает настроенный TeleBot для токена (или None, если токена нет)."""
    if token is None:
        token = BotSettings.load().token
    if not token:
        return None
    bot = _bots.get(token)
    if bot is None:
        bot = telebot.TeleBot(token, parse_mode="HTML", threaded=False)
        _register_handlers(bot)
        _bots[token] = bot
    return bot


# ─── Вспомогательные функции ──────────────────────────────────────────────────


def _is_admin(telegram_id: int) -> bool:
    return BotAdmin.objects.filter(telegram_id=telegram_id, is_active=True).exists()


def _active_admin_ids() -> list[int]:
    return list(
        BotAdmin.objects.filter(is_active=True).values_list("telegram_id", flat=True)
    )


def _upsert_user(from_user) -> TelegramUser:
    user, _ = TelegramUser.objects.update_or_create(
        telegram_id=from_user.id,
        defaults={
            "username": from_user.username or "",
            "first_name": from_user.first_name or "",
            "last_name": from_user.last_name or "",
        },
    )
    return user


def _message_text(message) -> str:
    return message.text or message.caption or ""


def _has_media(message) -> bool:
    return message.content_type != "text"


def main_keyboard() -> types.ReplyKeyboardMarkup:
    """Постоянная нижняя клавиатура с кнопками меню (всегда видна под полем ввода)."""
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton(BTN_SERVICES))
    kb.add(types.KeyboardButton(BTN_BOOK))
    return kb


def build_services_text() -> str:
    """Формирует прайс из активных услуг (services.Massage)."""
    from services.models import Massage

    massages = list(
        Massage.objects.filter(is_archived=False).order_by("-massage_type", "order")
    )
    if not massages:
        return (
            "Список услуг пока не заполнен.\n\n"
            "Напишите сообщение — массажист ответит вам лично."
        )

    labels = {
        Massage.CHILD: "🧒 <b>Детский массаж</b>",
        Massage.ADULT: "💆 <b>Массаж для взрослых</b>",
    }
    parts = ["<b>Услуги и цены</b>"]
    current_type = None
    for m in massages:
        if m.massage_type != current_type:
            current_type = m.massage_type
            parts.append("\n" + labels.get(current_type, "<b>Массаж</b>"))
        price = f"{int(m.price)} ₽"
        if m.duration_min == m.duration_max:
            duration = f"{m.duration_min} мин"
        else:
            duration = f"{m.duration_min}–{m.duration_max} мин"
        parts.append(f"• {html.escape(m.name)} — {price} · {duration}")

    parts.append('\nЧтобы записаться, нажмите «📝 Записаться» или просто напишите сообщение.')
    return "\n".join(parts)


def _build_header(user: TelegramUser, text: str) -> str:
    name = html.escape(user.display_name)
    username = f" (@{html.escape(user.username)})" if user.username else ""
    body = html.escape(text) if text else "<i>[вложение]</i>"
    return (
        "💬 <b>Сообщение от клиента</b>\n"
        f"{name}{username}\n"
        f"ID: <code>{user.telegram_id}</code>\n\n"
        f"{body}\n\n"
        "↩️ Ответьте на это сообщение (Reply), чтобы написать клиенту."
    )


# ─── Логика пересылки и ответов ───────────────────────────────────────────────


def _forward_to_admins(bot: telebot.TeleBot, message) -> None:
    user = _upsert_user(message.from_user)
    text = _message_text(message)
    DialogMessage.objects.create(user=user, direction=DialogMessage.IN, text=text)

    admin_ids = _active_admin_ids()
    if not admin_ids:
        logger.warning("tgbot: нет активных администраторов для пересылки (клиент %s)", user.telegram_id)
        bot.send_message(message.chat.id, NO_ADMINS)
        return

    header = _build_header(user, text)
    delivered = False
    for admin_id in admin_ids:
        try:
            sent = bot.send_message(admin_id, header)
            AdminForward.objects.create(
                user=user, admin_telegram_id=admin_id, admin_message_id=sent.message_id
            )
            if _has_media(message):
                copied = bot.copy_message(admin_id, message.chat.id, message.message_id)
                AdminForward.objects.create(
                    user=user,
                    admin_telegram_id=admin_id,
                    admin_message_id=copied.message_id,
                )
            delivered = True
        except Exception as exc:  # noqa: BLE001
            logger.warning("tgbot: не доставлено админу %s: %s", admin_id, exc)

    bot.send_message(message.chat.id, CONFIRMATION if delivered else DELIVERY_FAILED)


def _handle_admin_reply(bot: telebot.TeleBot, message) -> None:
    admin_id = message.from_user.id
    reply_to_id = message.reply_to_message.message_id
    forward = (
        AdminForward.objects.filter(
            admin_telegram_id=admin_id, admin_message_id=reply_to_id
        )
        .select_related("user")
        .first()
    )
    if forward is None:
        # Реплай не на пересланное сообщение клиента — игнорируем тихо.
        return

    user = forward.user
    text = _message_text(message)
    out = "✉️ <b>Ответ массажиста:</b>"
    if text:
        out += f"\n\n{html.escape(text)}"

    try:
        bot.send_message(user.telegram_id, out)
        if _has_media(message):
            bot.copy_message(user.telegram_id, admin_id, message.message_id)
        DialogMessage.objects.create(
            user=user,
            direction=DialogMessage.OUT,
            text=text,
            admin_telegram_id=admin_id,
        )
        bot.send_message(
            admin_id, "✅ Отправлено клиенту.", reply_to_message_id=message.message_id
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("tgbot: ответ клиенту %s не доставлен: %s", user.telegram_id, exc)
        bot.send_message(
            admin_id,
            f"⚠️ Не удалось отправить клиенту: {exc}",
            reply_to_message_id=message.message_id,
        )


# ─── Регистрация обработчиков (порядок важен) ────────────────────────────────


def _register_handlers(bot: telebot.TeleBot) -> None:
    @bot.message_handler(commands=["start"])
    def on_start(message):
        settings = BotSettings.load()
        _upsert_user(message.from_user)
        bot.send_message(
            message.chat.id,
            settings.welcome_text or "",
            reply_markup=main_keyboard(),
        )

    @bot.message_handler(func=lambda m: m.text == BTN_SERVICES)
    def on_services(message):
        bot.send_message(
            message.chat.id, build_services_text(), reply_markup=main_keyboard()
        )

    @bot.message_handler(func=lambda m: m.text == BTN_BOOK)
    def on_book(message):
        settings = BotSettings.load()
        bot.send_message(message.chat.id, settings.request_prompt or "")

    @bot.callback_query_handler(func=lambda c: c.data == "services")
    def cb_services(call):
        bot.answer_callback_query(call.id)
        bot.send_message(
            call.message.chat.id, build_services_text(), reply_markup=main_keyboard()
        )

    @bot.callback_query_handler(func=lambda c: c.data == "book")
    def cb_book(call):
        bot.answer_callback_query(call.id)
        settings = BotSettings.load()
        bot.send_message(call.message.chat.id, settings.request_prompt or "")

    @bot.message_handler(
        func=lambda m: m.reply_to_message is not None and _is_admin(m.from_user.id),
        content_types=CONTENT_TYPES,
    )
    def on_admin_reply(message):
        _handle_admin_reply(bot, message)

    @bot.message_handler(func=lambda m: True, content_types=CONTENT_TYPES)
    def on_message(message):
        if message.chat.type != "private":
            return
        if _is_admin(message.from_user.id):
            bot.send_message(message.chat.id, ADMIN_HINT)
            return
        _forward_to_admins(bot, message)
