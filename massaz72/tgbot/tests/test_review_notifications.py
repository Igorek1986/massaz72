import itertools
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import TestCase

from reviews.models import Review
from tgbot.models import BotAdmin, ReviewNotification
from tgbot.notifications import (
    handle_review_action,
    notify_new_review,
)


def make_bot():
    bot = MagicMock()
    counter = itertools.count(1)
    bot.send_message.side_effect = lambda *a, **k: SimpleNamespace(
        message_id=next(counter)
    )
    return bot


def make_call(data, uid, chat_id=None, message_id=999):
    return SimpleNamespace(
        id="cb-1",
        from_user=SimpleNamespace(id=uid),
        data=data,
        message=SimpleNamespace(
            chat=SimpleNamespace(id=chat_id or uid), message_id=message_id
        ),
    )


class NotifyNewReviewTest(TestCase):
    def setUp(self):
        BotAdmin.objects.create(telegram_id=111, name="A", is_active=True)
        BotAdmin.objects.create(telegram_id=222, name="B", is_active=True)
        BotAdmin.objects.create(telegram_id=333, name="C", is_active=False)
        self.review = Review.objects.create(name="Гость", rating=5, text="супер")

    def test_sends_to_active_admins_and_records(self):
        bot = make_bot()
        with patch("tgbot.bot.get_bot", return_value=bot):
            sent = notify_new_review(self.review)
        self.assertEqual(sent, 2)
        self.assertEqual(bot.send_message.call_count, 2)
        recipients = set(
            ReviewNotification.objects.filter(review=self.review).values_list(
                "admin_telegram_id", flat=True
            )
        )
        self.assertEqual(recipients, {111, 222})

    def test_no_bot_no_send(self):
        with patch("tgbot.bot.get_bot", return_value=None):
            sent = notify_new_review(self.review)
        self.assertEqual(sent, 0)
        self.assertEqual(ReviewNotification.objects.count(), 0)

    def test_keyboard_has_three_actions(self):
        bot = make_bot()
        with patch("tgbot.bot.get_bot", return_value=bot):
            notify_new_review(self.review)
        kwargs = bot.send_message.call_args.kwargs
        keyboard = kwargs["reply_markup"]
        datas = [b.callback_data for row in keyboard.keyboard for b in row]
        self.assertIn(f"rv_approve_{self.review.pk}", datas)
        self.assertIn(f"rv_reject_{self.review.pk}", datas)
        self.assertIn(f"rv_archive_{self.review.pk}", datas)


class HandleReviewActionTest(TestCase):
    def setUp(self):
        BotAdmin.objects.create(telegram_id=111, name="A", is_active=True)
        BotAdmin.objects.create(telegram_id=222, name="B", is_active=True)
        self.review = Review.objects.create(name="Гость", rating=4, text="ок")
        # Имитируем уже разосланные сообщения обоим админам.
        ReviewNotification.objects.create(
            review=self.review, admin_telegram_id=111, message_id=10
        )
        ReviewNotification.objects.create(
            review=self.review, admin_telegram_id=222, message_id=20
        )

    def test_approve_updates_and_deletes_all_messages(self):
        bot = MagicMock()
        handle_review_action(bot, make_call(f"rv_approve_{self.review.pk}", uid=111))
        self.review.refresh_from_db()
        self.assertEqual(self.review.status, Review.Status.APPROVED)
        self.assertFalse(self.review.is_archived)
        # Сообщения удалены у обоих админов, записи стёрты.
        self.assertEqual(bot.delete_message.call_count, 2)
        self.assertEqual(ReviewNotification.objects.filter(review=self.review).count(), 0)
        bot.answer_callback_query.assert_called_once()

    def test_reject(self):
        bot = MagicMock()
        handle_review_action(bot, make_call(f"rv_reject_{self.review.pk}", uid=222))
        self.review.refresh_from_db()
        self.assertEqual(self.review.status, Review.Status.REJECTED)
        self.assertEqual(ReviewNotification.objects.count(), 0)

    def test_archive(self):
        bot = MagicMock()
        handle_review_action(bot, make_call(f"rv_archive_{self.review.pk}", uid=111))
        self.review.refresh_from_db()
        self.assertTrue(self.review.is_archived)
        self.assertEqual(ReviewNotification.objects.count(), 0)

    def test_non_admin_denied(self):
        bot = MagicMock()
        handle_review_action(bot, make_call(f"rv_approve_{self.review.pk}", uid=999))
        self.review.refresh_from_db()
        self.assertEqual(self.review.status, Review.Status.PENDING)
        self.assertEqual(ReviewNotification.objects.count(), 2)
        bot.delete_message.assert_not_called()
        bot.answer_callback_query.assert_called_once_with("cb-1", "Нет доступа.")

    def test_unknown_review_deletes_only_this_message(self):
        bot = MagicMock()
        handle_review_action(bot, make_call("rv_approve_999999", uid=111))
        # Сам отзыв не тронут, но «осиротевшее» сообщение убираем.
        self.assertEqual(ReviewNotification.objects.count(), 2)
        bot.delete_message.assert_called_once()
