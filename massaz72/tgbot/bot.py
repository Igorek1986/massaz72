"""
Сборка экземпляра Telegram-бота (pyTelegramBotAPI) и регистрация обработчиков.

Схема работы:
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

# Состояние мастера записи: telegram_id → state dict
# state: {msg_id, type?, massage_id?, massage_name?, massage_price?,
#         therapist_id?, therapist_name?, awaiting_message?}
_pending_bookings: dict[int, dict] = {}


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


# ─── Мастер записи: инлайн-клавиатуры ───────────────────────────────────────


def _bk_type_keyboard() -> types.InlineKeyboardMarkup | None:
    from services.models import Massage

    available = set(
        Massage.objects.filter(is_archived=False).values_list("massage_type", flat=True)
    )
    if not available:
        return None
    kb = types.InlineKeyboardMarkup()
    labels = {Massage.CHILD: "🧒 Детский массаж", Massage.ADULT: "💆 Массаж для взрослых"}
    for t in [Massage.CHILD, Massage.ADULT]:
        if t in available:
            kb.add(types.InlineKeyboardButton(labels[t], callback_data=f"bk_t_{t}"))
    kb.add(types.InlineKeyboardButton("❌ Отмена", callback_data="bk_cancel"))
    return kb


def _bk_massage_keyboard(massage_type: str) -> types.InlineKeyboardMarkup | None:
    from services.models import Massage

    massages = list(
        Massage.objects.filter(is_archived=False, massage_type=massage_type).order_by("order")
    )
    if not massages:
        return None
    kb = types.InlineKeyboardMarkup()
    for m in massages:
        price = f"{int(m.price)} ₽"
        dur = (
            f"{m.duration_min} мин"
            if m.duration_min == m.duration_max
            else f"{m.duration_min}–{m.duration_max} мин"
        )
        kb.add(types.InlineKeyboardButton(
            f"{m.name} — {price} · {dur}", callback_data=f"bk_m_{m.id}"
        ))
    kb.add(types.InlineKeyboardButton("◀️ Назад", callback_data="bk_back_type"))
    kb.add(types.InlineKeyboardButton("❌ Отмена", callback_data="bk_cancel"))
    return kb


def _bk_therapist_keyboard() -> types.InlineKeyboardMarkup | None:
    """Возвращает клавиатуру выбора массажиста, или None если он один."""
    from main.models import About

    therapists = list(About.objects.filter(is_active=True).order_by("order"))
    if len(therapists) <= 1:
        return None
    kb = types.InlineKeyboardMarkup()
    for t in therapists:
        kb.add(types.InlineKeyboardButton(t.name, callback_data=f"bk_a_{t.id}"))
    kb.add(types.InlineKeyboardButton("◀️ Назад", callback_data="bk_back_massage"))
    kb.add(types.InlineKeyboardButton("❌ Отмена", callback_data="bk_cancel"))
    return kb


def _bk_cancel_keyboard() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("❌ Отмена", callback_data="bk_cancel"))
    return kb


def _bk_prompt_text(state: dict) -> str:
    lines = ["📝 <b>Запись на массаж</b>\n"]
    if state.get("massage_name"):
        line = f"Массаж: <b>{html.escape(state['massage_name'])}</b>"
        if state.get("massage_price"):
            line += f" — {int(float(state['massage_price']))} ₽"
        lines.append(line)
    if state.get("therapist_name"):
        lines.append(f"Массажист: <b>{html.escape(state['therapist_name'])}</b>")
    lines.append(
        "\nНапишите <b>удобные дату и время</b> для записи "
        "— или любую информацию для связи."
    )
    return "\n".join(lines)


def _bk_delete_or_edit(bot: telebot.TeleBot, chat_id: int, msg_id: int, text: str = "Запись отменена.") -> None:
    try:
        bot.delete_message(chat_id, msg_id)
    except Exception:
        try:
            bot.edit_message_text(text, chat_id, msg_id, reply_markup=None)
        except Exception:
            pass


def _bk_proceed_after_massage(bot: telebot.TeleBot, uid: int, chat_id: int, msg_id: int, state: dict) -> None:
    """Общая логика после выбора массажа: показать выбор массажиста или финальный запрос."""
    kb = _bk_therapist_keyboard()
    if kb:
        bot.edit_message_text(
            "📝 <b>Запись на массаж</b>\n\nВыберите массажиста:",
            chat_id, msg_id, reply_markup=kb,
        )
        return
    # Один массажист — автовыбор
    from main.models import About

    therapist = About.objects.filter(is_active=True).order_by("order").first()
    if therapist:
        state["therapist_id"] = therapist.id
        state["therapist_name"] = therapist.name
    state["awaiting_message"] = True
    _pending_bookings[uid] = state
    bot.edit_message_text(
        _bk_prompt_text(state), chat_id, msg_id, reply_markup=_bk_cancel_keyboard(),
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


def _handle_booking_message(bot: telebot.TeleBot, message, state: dict) -> None:
    """Принимает финальное сообщение из мастера записи и пересылает администраторам."""
    uid = message.from_user.id
    user = _upsert_user(message.from_user)
    text = _message_text(message)

    name = html.escape(user.display_name)
    username = f" (@{html.escape(user.username)})" if user.username else ""
    body = html.escape(text) if text else "<i>[вложение]</i>"

    header = f"📅 <b>Заявка на запись</b>\n{name}{username}\nID: <code>{user.telegram_id}</code>\n\n"
    if state.get("massage_name"):
        line = f"Массаж: <b>{html.escape(state['massage_name'])}</b>"
        if state.get("massage_price"):
            line += f" — {int(float(state['massage_price']))} ₽"
        header += line + "\n"
    if state.get("therapist_name"):
        header += f"Массажист: <b>{html.escape(state['therapist_name'])}</b>\n"
    header += f"\n{body}\n\n↩️ Ответьте на это сообщение (Reply), чтобы написать клиенту."

    DialogMessage.objects.create(user=user, direction=DialogMessage.IN, text=text)
    admin_ids = _active_admin_ids()
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
                    user=user, admin_telegram_id=admin_id, admin_message_id=copied.message_id
                )
            delivered = True
        except Exception as exc:  # noqa: BLE001
            logger.warning("tgbot: заявка не доставлена админу %s: %s", admin_id, exc)

    # Обновляем сообщение мастера: убираем клавиатуру, показываем итог
    msg_id = state.get("msg_id")
    if msg_id:
        try:
            bot.edit_message_text(
                "✅ <b>Заявка отправлена!</b>\n\nМассажист свяжется с вами в ближайшее время.",
                uid, msg_id, reply_markup=None,
            )
        except Exception:  # noqa: BLE001
            pass

    _pending_bookings.pop(uid, None)

    if not admin_ids:
        confirmation = NO_ADMINS
    elif delivered:
        confirmation = CONFIRMATION
    else:
        confirmation = DELIVERY_FAILED
    bot.send_message(message.chat.id, confirmation, reply_markup=main_keyboard())


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
        _pending_bookings.pop(message.from_user.id, None)
        settings = BotSettings.load()
        _upsert_user(message.from_user)
        bot.send_message(
            message.chat.id,
            settings.welcome_text or "",
            reply_markup=main_keyboard(),
        )

    @bot.message_handler(func=lambda m: m.text == BTN_SERVICES)
    def on_services(message):
        _pending_bookings.pop(message.from_user.id, None)
        bot.send_message(
            message.chat.id, build_services_text(), reply_markup=main_keyboard()
        )

    @bot.message_handler(func=lambda m: m.text == BTN_BOOK)
    def on_book(message):
        uid = message.from_user.id
        # Сбрасываем предыдущий мастер, если был открыт
        old = _pending_bookings.pop(uid, None)
        if old and old.get("msg_id"):
            _bk_delete_or_edit(bot, message.chat.id, old["msg_id"])

        kb = _bk_type_keyboard()
        if kb is None:
            bot.send_message(
                message.chat.id,
                "Список услуг пока не заполнен. Напишите нам — ответим лично.",
                reply_markup=main_keyboard(),
            )
            return
        sent = bot.send_message(
            message.chat.id,
            "📝 <b>Запись на массаж</b>\n\nВыберите тип массажа:",
            reply_markup=kb,
        )
        _pending_bookings[uid] = {"msg_id": sent.message_id}

    @bot.callback_query_handler(func=lambda c: c.data.startswith("bk_"))
    def cb_booking(call):
        uid = call.from_user.id
        chat_id = call.message.chat.id
        msg_id = call.message.message_id
        data = call.data
        bot.answer_callback_query(call.id)

        state = _pending_bookings.get(uid) or {}
        state["msg_id"] = msg_id  # актуализируем на случай перезапуска

        if data == "bk_cancel":
            _pending_bookings.pop(uid, None)
            _bk_delete_or_edit(bot, chat_id, msg_id)
            return

        if data == "bk_back_type":
            for key in ("type", "massage_id", "massage_name", "massage_price", "awaiting_message"):
                state.pop(key, None)
            _pending_bookings[uid] = state
            kb = _bk_type_keyboard()
            if kb:
                bot.edit_message_text(
                    "📝 <b>Запись на массаж</b>\n\nВыберите тип массажа:",
                    chat_id, msg_id, reply_markup=kb,
                )
            return

        if data == "bk_back_massage":
            mtype = state.get("type")
            for key in ("massage_id", "massage_name", "massage_price",
                        "therapist_id", "therapist_name", "awaiting_message"):
                state.pop(key, None)
            _pending_bookings[uid] = state
            kb = _bk_massage_keyboard(mtype) if mtype else None
            if kb:
                bot.edit_message_text(
                    "📝 <b>Запись на массаж</b>\n\nВыберите вид массажа:",
                    chat_id, msg_id, reply_markup=kb,
                )
            return

        if data.startswith("bk_t_"):
            mtype = data[5:]
            state["type"] = mtype
            _pending_bookings[uid] = state
            kb = _bk_massage_keyboard(mtype)
            if kb is None:
                bot.edit_message_text(
                    "В этой категории пока нет услуг.",
                    chat_id, msg_id, reply_markup=_bk_type_keyboard(),
                )
                return
            bot.edit_message_text(
                "📝 <b>Запись на массаж</b>\n\nВыберите вид массажа:",
                chat_id, msg_id, reply_markup=kb,
            )
            return

        if data.startswith("bk_m_"):
            try:
                massage_id = int(data[5:])
            except ValueError:
                return
            from services.models import Massage

            try:
                m = Massage.objects.get(id=massage_id, is_archived=False)
            except Massage.DoesNotExist:
                bot.edit_message_text("Услуга не найдена.", chat_id, msg_id, reply_markup=None)
                _pending_bookings.pop(uid, None)
                return
            state["massage_id"] = m.id
            state["massage_name"] = m.name
            state["massage_price"] = str(m.price)
            _pending_bookings[uid] = state
            _bk_proceed_after_massage(bot, uid, chat_id, msg_id, state)
            return

        if data.startswith("bk_a_"):
            try:
                therapist_id = int(data[5:])
            except ValueError:
                return
            from main.models import About

            try:
                t = About.objects.get(id=therapist_id, is_active=True)
                state["therapist_id"] = t.id
                state["therapist_name"] = t.name
            except About.DoesNotExist:
                pass
            state["awaiting_message"] = True
            _pending_bookings[uid] = state
            bot.edit_message_text(
                _bk_prompt_text(state), chat_id, msg_id, reply_markup=_bk_cancel_keyboard(),
            )
            return

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
        uid = message.from_user.id
        if _is_admin(uid):
            bot.send_message(message.chat.id, ADMIN_HINT)
            return
        state = _pending_bookings.get(uid)
        if state and state.get("awaiting_message"):
            _handle_booking_message(bot, message, state)
            return
        _forward_to_admins(bot, message)
