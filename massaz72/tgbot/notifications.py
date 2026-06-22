"""Уведомления администраторам в Telegram о новых отзывах.

Когда посетитель оставляет отзыв (статус «на модерации»), всем активным
администраторам уходит сообщение с inline-кнопками: одобрить / отклонить /
в архив. Действие выполняется прямо из Telegram, после чего сообщение
удаляется у всех админов (по сохранённым ReviewNotification).

Сообщения отправляет веб-процесс (app), а нажатия кнопок обрабатывает
процесс polling (bot) — оба используют один и тот же код бота.
"""

import html
import logging

from django.utils import timezone
from telebot import types

from .models import BookingNotification, BotAdmin, ReviewNotification


def _policy_url() -> str:
    """Абсолютная ссылка на «Политику обработки ПД» для сообщений в боте."""
    from django.conf import settings
    from django.contrib.sites.models import Site
    from django.urls import reverse

    path = reverse("main:personal_data")
    domain = ""
    try:
        domain = Site.objects.get_current().domain
    except Exception:  # noqa: BLE001
        pass
    # Если домен Site не настроен (example.com) — берём из ALLOWED_HOSTS.
    if not domain or domain == "example.com":
        hosts = [h for h in getattr(settings, "ALLOWED_HOSTS", []) if h not in ("*", "")]
        if hosts:
            domain = hosts[0]
    return f"https://{domain}{path}" if domain and domain != "example.com" else path

logger = logging.getLogger(__name__)

REVIEW_CB_PREFIX = "rv_"

_ACTION_LABELS = {
    "approve": "одобрен",
    "reject": "отклонён",
    "archive": "отправлен в архив",
}


def _is_admin(telegram_id: int) -> bool:
    return BotAdmin.objects.filter(telegram_id=telegram_id, is_active=True).exists()


def _stars(rating: int) -> str:
    return "★" * rating + "☆" * (5 - rating)


def build_review_text(review) -> str:
    name = html.escape(review.name)
    text = html.escape(review.text)
    return (
        "🆕 <b>Новый отзыв</b>\n"
        f"<b>Имя:</b> {name}\n"
        f"<b>Оценка:</b> {_stars(review.rating)} ({review.rating}/5)\n"
        f"<b>Дата:</b> {review.created_at:%d.%m.%Y %H:%M}\n\n"
        f"{text}"
    )


def build_review_keyboard(review) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("✅ Одобрить", callback_data=f"rv_approve_{review.pk}"),
        types.InlineKeyboardButton("❌ Отклонить", callback_data=f"rv_reject_{review.pk}"),
    )
    kb.add(types.InlineKeyboardButton("🗄 В архив", callback_data=f"rv_archive_{review.pk}"))
    return kb


def notify_new_review(review) -> int:
    """Рассылает уведомление о новом отзыве всем активным админам.

    Возвращает число успешно доставленных сообщений. Безопасно: если бот не
    настроен или Telegram недоступен — просто ничего не отправляет."""
    from .bot import get_bot  # ленивый импорт, чтобы избежать цикла

    bot = get_bot()
    if bot is None:
        return 0

    text = build_review_text(review)
    keyboard = build_review_keyboard(review)
    sent = 0
    for admin_id in BotAdmin.objects.filter(is_active=True).values_list(
        "telegram_id", flat=True
    ):
        try:
            msg = bot.send_message(admin_id, text, reply_markup=keyboard)
            ReviewNotification.objects.create(
                review=review, admin_telegram_id=admin_id, message_id=msg.message_id
            )
            sent += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("review %s: не доставлено админу %s: %s",
                           review.pk, admin_id, exc)
    return sent


def delete_review_messages(bot, review) -> None:
    """Удаляет у всех админов сообщения с кнопками по этому отзыву."""
    notifications = list(ReviewNotification.objects.filter(review=review))
    for n in notifications:
        try:
            bot.delete_message(n.admin_telegram_id, n.message_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("review %s: не удалить сообщение %s/%s: %s",
                           review.pk, n.admin_telegram_id, n.message_id, exc)
    ReviewNotification.objects.filter(review=review).delete()


def handle_review_action(bot, call) -> None:
    """Обрабатывает нажатие кнопки модерации отзыва (callback_data rv_*)."""
    from reviews.models import Review

    if not _is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Нет доступа.")
        return

    try:
        _, action, pk = call.data.split("_", 2)
    except ValueError:
        bot.answer_callback_query(call.id)
        return

    review = Review.objects.filter(pk=pk).first()
    if review is None:
        bot.answer_callback_query(call.id, "Отзыв не найден.")
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception:  # noqa: BLE001
            pass
        return

    if action == "approve":
        review.status = Review.Status.APPROVED
        review.is_archived = False
        review.save(update_fields=["status", "is_archived", "updated_at"])
    elif action == "reject":
        review.status = Review.Status.REJECTED
        review.save(update_fields=["status", "updated_at"])
    elif action == "archive":
        review.is_archived = True
        review.save(update_fields=["is_archived", "updated_at"])
    else:
        bot.answer_callback_query(call.id)
        return

    delete_review_messages(bot, review)
    bot.answer_callback_query(call.id, f"Отзыв {_ACTION_LABELS[action]}.")


# ─── Заявки на запись ─────────────────────────────────────────────────────────

_BOOKING_ACTION_LABELS = {
    "confirm": "подтверждена",
    "decline": "отклонена",
}


def build_booking_text(booking) -> str:
    lines = ["📅 <b>Новая заявка на запись</b>", f"<b>Имя:</b> {html.escape(booking.client_name)}"]
    if booking.phone:
        lines.append(f"<b>Телефон:</b> {html.escape(booking.phone)}")
    else:
        lines.append("<b>Телефон:</b> не указан")
    if booking.address:
        lines.append(f"<b>Адрес (выезд):</b> {html.escape(booking.address)}")
    if booking.service:
        lines.append(f"<b>Услуга:</b> {html.escape(booking.service.name)}")
    if booking.specialist:
        lines.append(f"<b>Мастер:</b> {html.escape(booking.specialist.name)}")
    if booking.sessions:
        lines.append(f"<b>Сеансов:</b> {html.escape(booking.sessions.button_label)}")
    lines.append(f"<b>Желаемые дата/время:</b> {booking.preferred_date:%d.%m.%Y} {booking.preferred_time:%H:%M}")
    if booking.messenger_user_id:
        contact = (
            f"@{html.escape(booking.messenger_username)}"
            if booking.messenger_username
            else f"id {booking.messenger_user_id}"
        )
        lines.append(f"<b>На связи в боте:</b> {contact} — можно написать ему здесь")
    if booking.client_confirmed:
        lines.append("<b>✅ Клиент подтвердил заявку и согласие на обработку ПД</b>")
    from booking.models import BookingRequest
    if booking.status == BookingRequest.Status.CANCELLED:
        lines.append("<b>❌ Клиент отменил заявку</b>")
    if booking.comment:
        lines.append(f"\n{html.escape(booking.comment)}")
    return "\n".join(lines)


def client_booking_summary(booking) -> str:
    """Сводка заявки для клиента в боте (после привязки)."""
    lines = ["✅ <b>Вы на связи!</b>\n", "Ваша заявка:"]
    if booking.service:
        lines.append(f"• Услуга: <b>{html.escape(booking.service.name)}</b>")
    if booking.sessions:
        lines.append(f"• Сеансов: <b>{html.escape(booking.sessions.button_label)}</b>")
    lines.append(
        f"• Желаемые дата/время: <b>{booking.preferred_date:%d.%m.%Y} "
        f"{booking.preferred_time:%H:%M}</b>"
    )
    if booking.client_confirmed:
        lines.append("\nЗаявка подтверждена. Ждём подтверждения мастера по времени.")
    else:
        lines.append(
            f"\nНажимая «Подтвердить запись», вы соглашаетесь на обработку "
            f"персональных данных (<a href=\"{_policy_url()}\">Политика</a>):"
        )
    return "\n".join(lines)


def client_confirm_keyboard(booking) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(
        "✅ Подтвердить запись", callback_data=f"cbk_confirm_{booking.pk}"
    ))
    return kb


def handle_client_booking_confirm(bot, call) -> None:
    """Клиент нажал «Подтвердить запись» в боте (callback cbk_*)."""
    from booking.models import BookingRequest

    try:
        _, _action, pk = call.data.split("_", 2)
    except ValueError:
        bot.answer_callback_query(call.id)
        return

    booking = BookingRequest.objects.filter(pk=pk).first()
    if booking is None:
        bot.answer_callback_query(call.id, "Заявка не найдена.")
        return

    if not booking.client_confirmed:
        booking.client_confirmed = True
        booking.consent_at = timezone.now()  # согласие на обработку ПД
        update_fields = ["client_confirmed", "consent_at", "updated_at"]
        # Подтверждение в боте = надёжный контакт: заявка «ожидавшая контакта»
        # становится активной (на подтверждении у мастера).
        if booking.status == BookingRequest.Status.AWAITING_CONTACT:
            booking.status = BookingRequest.Status.PENDING
            update_fields.append("status")
        booking.save(update_fields=update_fields)
        # Уведомляем мастера: если ещё не уведомляли (заявка без телефона) —
        # шлём заявку (с учётом тихих часов); иначе обновляем сообщения.
        if BookingNotification.objects.filter(booking=booking).exists():
            refresh_booking_messages(bot, booking)
        else:
            notify_new_booking(booking)

    bot.answer_callback_query(call.id, "Спасибо! Запись подтверждена.")
    try:
        bot.edit_message_text(
            client_booking_summary(booking), call.message.chat.id,
            call.message.message_id,
        )
    except Exception:  # noqa: BLE001
        pass


def refresh_booking_messages(bot, booking) -> None:
    """Перерисовывает сообщения о заявке у всех админов (напр. после того как
    клиент подключился к боту — чтобы показать контакт)."""
    text = build_booking_text(booking)
    keyboard = build_booking_keyboard(booking)
    for n in BookingNotification.objects.filter(booking=booking):
        try:
            bot.edit_message_text(
                text, n.admin_telegram_id, n.message_id, reply_markup=keyboard
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("booking %s: не обновить сообщение %s/%s: %s",
                           booking.pk, n.admin_telegram_id, n.message_id, exc)


def build_booking_keyboard(booking) -> types.InlineKeyboardMarkup:
    from booking.models import BookingRequest

    kb = types.InlineKeyboardMarkup()
    # Закрытая заявка (отменена клиентом/отклонена) — без кнопок действий.
    if booking.status in (BookingRequest.Status.CANCELLED, BookingRequest.Status.DECLINED):
        return kb
    kb.row(
        types.InlineKeyboardButton("✅ Подтвердить", callback_data=f"br_confirm_{booking.pk}"),
        types.InlineKeyboardButton("❌ Отклонить", callback_data=f"br_decline_{booking.pk}"),
    )
    return kb


def booking_recipients(booking) -> list[int]:
    """Кому слать заявку: конкретному мастеру и его главному (если привязали
    Telegram); иначе — всем активным админам."""
    ids = []
    spec = booking.specialist
    if spec is not None:
        for s in (spec, spec.head):
            if s is not None and s.telegram_id:
                ids.append(s.telegram_id)
    if ids:
        return list(dict.fromkeys(ids))
    return list(
        BotAdmin.objects.filter(is_active=True).values_list("telegram_id", flat=True)
    )


def send_booking_to_admins(bot, booking) -> int:
    """Шлёт заявку адресатам (мастер/главный или все админы)."""
    text = build_booking_text(booking)
    keyboard = build_booking_keyboard(booking)
    sent = 0
    for admin_id in booking_recipients(booking):
        try:
            msg = bot.send_message(admin_id, text, reply_markup=keyboard)
            BookingNotification.objects.create(
                booking=booking, admin_telegram_id=admin_id, message_id=msg.message_id
            )
            sent += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("booking %s: не доставлено %s: %s",
                           booking.pk, admin_id, exc)
    return sent


def send_booking_reminder(bot, booking) -> int:
    """Повторное напоминание мастеру о необработанной заявке."""
    from booking.models import BookingRequest

    if booking.status != BookingRequest.Status.PENDING:
        return 0
    text = "⏰ <b>Напоминание: необработанная заявка</b>\n\n" + build_booking_text(booking)
    keyboard = build_booking_keyboard(booking)
    sent = 0
    for admin_id in booking_recipients(booking):
        try:
            msg = bot.send_message(admin_id, text, reply_markup=keyboard)
            BookingNotification.objects.create(
                booking=booking, admin_telegram_id=admin_id, message_id=msg.message_id
            )
            sent += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("booking %s: напоминание не доставлено %s: %s",
                           booking.pk, admin_id, exc)
    return sent


def notify_new_booking(booking) -> int:
    """Уведомление о новой заявке — с учётом тихих часов (может отложиться)."""
    from .notify import notify
    notify("new_booking", {"booking_id": booking.pk})
    return 0


def notify_booking_cancelled(booking) -> None:
    """Клиент отменил заявку — обновляем сообщения мастера (убираем кнопки)."""
    from .bot import get_bot

    if not BookingNotification.objects.filter(booking=booking).exists():
        return
    bot = get_bot()
    if bot is None:
        return
    refresh_booking_messages(bot, booking)


def delete_booking_messages(bot, booking) -> None:
    for n in list(BookingNotification.objects.filter(booking=booking)):
        try:
            bot.delete_message(n.admin_telegram_id, n.message_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("booking %s: не удалить сообщение %s/%s: %s",
                           booking.pk, n.admin_telegram_id, n.message_id, exc)
    BookingNotification.objects.filter(booking=booking).delete()


def handle_booking_action(bot, call) -> None:
    """Обрабатывает кнопку заявки (callback_data br_*)."""
    from booking.models import BookingRequest
    from booking.services import confirm_booking, decline_booking

    if not _is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Нет доступа.")
        return

    try:
        _, action, pk = call.data.split("_", 2)
    except ValueError:
        bot.answer_callback_query(call.id)
        return

    booking = BookingRequest.objects.filter(pk=pk).first()
    if booking is None:
        bot.answer_callback_query(call.id, "Заявка не найдена.")
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception:  # noqa: BLE001
            pass
        return

    if action == "confirm":
        if booking.status == BookingRequest.Status.CANCELLED:
            bot.answer_callback_query(call.id, "Клиент отменил заявку.")
            delete_booking_messages(bot, booking)
            return
        appointment = confirm_booking(booking)
        if appointment is None:
            bot.answer_callback_query(call.id, "Нет мастера в системе — подтвердите в кабинете.")
            return
    elif action == "decline":
        decline_booking(booking)
    else:
        bot.answer_callback_query(call.id)
        return

    delete_booking_messages(bot, booking)
    bot.answer_callback_query(call.id, f"Заявка {_BOOKING_ACTION_LABELS[action]}.")


# ─── Отмена и перенос сеанса клиентом ─────────────────────────────────────────

def _admins():
    return BotAdmin.objects.filter(is_active=True).values_list("telegram_id", flat=True)


def notify_master_cancel(appointment) -> int:
    """Уведомляет мастеров об отмене сеанса клиентом."""
    from .bot import get_bot

    bot = get_bot()
    if bot is None:
        return 0
    a = appointment
    text = (
        "🚫 <b>Клиент отменил сеанс</b>\n"
        f"<b>Клиент:</b> {html.escape(a.client_name)}\n"
        f"<b>Дата/время:</b> {a.date:%d.%m.%Y} {a.time_start:%H:%M}"
    )
    if a.service:
        text += f"\n<b>Услуга:</b> {html.escape(a.service.name)}"
    sent = 0
    for admin_id in _admins():
        try:
            bot.send_message(admin_id, text)
            sent += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("cancel notify: %s: %s", admin_id, exc)
    return sent


def reschedule_keyboard(req) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("✅ Подтвердить перенос", callback_data=f"rs_confirm_{req.pk}"),
        types.InlineKeyboardButton("❌ Отклонить", callback_data=f"rs_decline_{req.pk}"),
    )
    return kb


def notify_master_reschedule(req) -> int:
    """Уведомляет мастеров о запросе на перенос (с кнопками подтверждения)."""
    from .bot import get_bot

    bot = get_bot()
    if bot is None:
        return 0
    a = req.appointment
    text = (
        "🔁 <b>Запрос на перенос сеанса</b>\n"
        f"<b>Клиент:</b> {html.escape(a.client_name)}\n"
        f"<b>Сейчас:</b> {a.date:%d.%m.%Y} {a.time_start:%H:%M}\n"
        f"<b>Перенести на:</b> {req.new_date:%d.%m.%Y} {req.new_time:%H:%M}"
    )
    if a.service:
        text += f"\n<b>Услуга:</b> {html.escape(a.service.name)}"
    kb = reschedule_keyboard(req)
    sent = 0
    for admin_id in _admins():
        try:
            bot.send_message(admin_id, text, reply_markup=kb)
            sent += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("reschedule notify: %s: %s", admin_id, exc)
    return sent


def handle_reschedule_action(bot, call) -> None:
    """Кнопка переноса (callback rs_*): мастер подтверждает/отклоняет."""
    from booking.models import RescheduleRequest
    from booking.services import apply_reschedule, decline_reschedule

    if not _is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Нет доступа.")
        return
    try:
        _, action, pk = call.data.split("_", 2)
    except ValueError:
        bot.answer_callback_query(call.id)
        return

    req = RescheduleRequest.objects.filter(pk=pk).first()
    if req is None:
        bot.answer_callback_query(call.id, "Запрос не найден.")
        return
    if req.status != RescheduleRequest.Status.PENDING:
        bot.answer_callback_query(call.id, "Уже обработано.")
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception:  # noqa: BLE001
            pass
        return

    if action == "confirm":
        apply_reschedule(req)
        label = "Перенос подтверждён"
    elif action == "decline":
        decline_reschedule(req)
        label = "Перенос отклонён"
    else:
        bot.answer_callback_query(call.id)
        return

    try:
        bot.edit_message_text(f"🔁 {label}.", call.message.chat.id, call.message.message_id)
    except Exception:  # noqa: BLE001
        pass
    bot.answer_callback_query(call.id, label)


def send_password_reset(telegram_id, url) -> bool:
    """Шлёт клиенту в Telegram ссылку для установки нового пароля."""
    from .bot import get_bot

    bot = get_bot()
    if bot is None:
        return False
    try:
        bot.send_message(
            telegram_id,
            "🔑 <b>Сброс пароля</b>\n\nЧтобы задать новый пароль, перейдите по ссылке:\n"
            f"{url}\n\nЕсли вы не запрашивали сброс — просто игнорируйте это сообщение.",
            disable_web_page_preview=True,
        )
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("password reset: не отправлено %s: %s", telegram_id, exc)
        return False


def _abs_url(path: str) -> str:
    """Абсолютный URL сайта по пути (домен из Site/ALLOWED_HOSTS)."""
    from django.conf import settings
    from django.contrib.sites.models import Site

    domain = ""
    try:
        domain = Site.objects.get_current().domain
    except Exception:  # noqa: BLE001
        pass
    if not domain or domain == "example.com":
        hosts = [h for h in getattr(settings, "ALLOWED_HOSTS", []) if h not in ("*", "")]
        if hosts:
            domain = hosts[0]
    return f"https://{domain}{path}" if domain and domain != "example.com" else path


def send_reminder(telegram_id) -> bool:
    """Напоминание клиенту записаться на массаж."""
    from django.urls import reverse

    from .bot import get_bot

    bot = get_bot()
    if bot is None:
        return False
    url = _abs_url(reverse("booking:page"))
    text = "🌿 <b>Давно не виделись!</b>\nНе пора ли записаться на массаж?"
    if url:
        text += f"\n\nЗаписаться: {url}"
    try:
        bot.send_message(telegram_id, text, disable_web_page_preview=True)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("reminder: не отправлено %s: %s", telegram_id, exc)
        return False


def send_deletion_warning(telegram_id, days: int) -> bool:
    """Предупреждение клиенту, что неактивный аккаунт будет удалён."""
    from django.urls import reverse

    from .bot import get_bot

    bot = get_bot()
    if bot is None:
        return False
    url = _abs_url(reverse("accounts:login"))
    text = (
        "⚠️ <b>Ваш аккаунт давно неактивен</b>\n"
        f"Если не войти в течение {days} дней, аккаунт будет удалён "
        "вместе с данными профиля."
    )
    if url:
        text += f"\n\nВойти: {url}"
    try:
        bot.send_message(telegram_id, text, disable_web_page_preview=True)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("deletion_warning: не отправлено %s: %s", telegram_id, exc)
        return False
