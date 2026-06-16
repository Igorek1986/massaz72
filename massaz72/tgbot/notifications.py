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

from telebot import types

from .models import BookingNotification, BotAdmin, ReviewNotification

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
    if booking.service:
        lines.append(f"<b>Услуга:</b> {html.escape(booking.service.name)}")
    if booking.specialist:
        lines.append(f"<b>Мастер:</b> {html.escape(booking.specialist.name)}")
    lines.append(f"<b>Желаемые дата/время:</b> {booking.preferred_date:%d.%m.%Y} {booking.preferred_time:%H:%M}")
    if booking.comment:
        lines.append(f"\n{html.escape(booking.comment)}")
    return "\n".join(lines)


def build_booking_keyboard(booking) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("✅ Подтвердить", callback_data=f"br_confirm_{booking.pk}"),
        types.InlineKeyboardButton("❌ Отклонить", callback_data=f"br_decline_{booking.pk}"),
    )
    return kb


def notify_new_booking(booking) -> int:
    """Рассылает уведомление о новой заявке всем активным админам."""
    from .bot import get_bot

    bot = get_bot()
    if bot is None:
        return 0

    text = build_booking_text(booking)
    keyboard = build_booking_keyboard(booking)
    sent = 0
    for admin_id in BotAdmin.objects.filter(is_active=True).values_list(
        "telegram_id", flat=True
    ):
        try:
            msg = bot.send_message(admin_id, text, reply_markup=keyboard)
            BookingNotification.objects.create(
                booking=booking, admin_telegram_id=admin_id, message_id=msg.message_id
            )
            sent += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("booking %s: не доставлено админу %s: %s",
                           booking.pk, admin_id, exc)
    return sent


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
