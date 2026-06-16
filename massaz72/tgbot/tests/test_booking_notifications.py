import itertools
from datetime import time, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from booking.models import BookingRequest
from cabinet.models import Appointment, Specialist
from services.models import Massage
from tgbot.models import BookingNotification, BotAdmin
from tgbot.notifications import handle_booking_action, notify_new_booking

User = get_user_model()


def make_bot():
    bot = MagicMock()
    counter = itertools.count(1)
    bot.send_message.side_effect = lambda *a, **k: SimpleNamespace(
        message_id=next(counter)
    )
    return bot


def make_call(data, uid, message_id=999):
    return SimpleNamespace(
        id="cb-1",
        from_user=SimpleNamespace(id=uid),
        data=data,
        message=SimpleNamespace(chat=SimpleNamespace(id=uid), message_id=message_id),
    )


class BookingNotifyTest(TestCase):
    def setUp(self):
        BotAdmin.objects.create(telegram_id=111, name="A", is_active=True)
        BotAdmin.objects.create(telegram_id=222, name="B", is_active=False)
        self.booking = BookingRequest.objects.create(
            client_name="Гость", preferred_date=timezone.localdate() + timedelta(days=2),
            preferred_time=time(10, 0),
        )

    def test_sends_to_active_admins(self):
        bot = make_bot()
        with patch("tgbot.bot.get_bot", return_value=bot):
            sent = notify_new_booking(self.booking)
        self.assertEqual(sent, 1)
        self.assertEqual(
            BookingNotification.objects.filter(booking=self.booking).count(), 1
        )

    def test_no_bot(self):
        with patch("tgbot.bot.get_bot", return_value=None):
            self.assertEqual(notify_new_booking(self.booking), 0)
        self.assertEqual(BookingNotification.objects.count(), 0)


class BookingActionTest(TestCase):
    def setUp(self):
        BotAdmin.objects.create(telegram_id=111, name="A", is_active=True)
        user = User.objects.create_user("master", password="pw")
        self.specialist = Specialist.objects.create(user=user, name="Мастер")
        self.massage = Massage.objects.create(
            name="Спина", price=Decimal("2000"), duration_min=30, duration_max=60,
            location="Кабинет", massage_type=Massage.ADULT, slug="spina",
        )
        self.booking = BookingRequest.objects.create(
            client_name="Гость", service=self.massage,
            preferred_date=timezone.localdate() + timedelta(days=2),
            preferred_time=time(10, 0),
        )
        BookingNotification.objects.create(
            booking=self.booking, admin_telegram_id=111, message_id=10
        )

    def test_confirm_creates_appointment_and_clears(self):
        bot = MagicMock()
        handle_booking_action(bot, make_call(f"br_confirm_{self.booking.pk}", uid=111))
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, BookingRequest.Status.CONFIRMED)
        self.assertEqual(Appointment.objects.count(), 1)
        self.assertEqual(BookingNotification.objects.count(), 0)
        bot.delete_message.assert_called_once()
        bot.answer_callback_query.assert_called_once()

    def test_decline(self):
        bot = MagicMock()
        handle_booking_action(bot, make_call(f"br_decline_{self.booking.pk}", uid=111))
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, BookingRequest.Status.DECLINED)
        self.assertEqual(Appointment.objects.count(), 0)
        self.assertEqual(BookingNotification.objects.count(), 0)

    def test_non_admin_denied(self):
        bot = MagicMock()
        handle_booking_action(bot, make_call(f"br_confirm_{self.booking.pk}", uid=999))
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, BookingRequest.Status.PENDING)
        self.assertEqual(Appointment.objects.count(), 0)
        bot.answer_callback_query.assert_called_once_with("cb-1", "Нет доступа.")

    def test_unknown_booking(self):
        bot = MagicMock()
        handle_booking_action(bot, make_call("br_confirm_999999", uid=111))
        self.assertEqual(Appointment.objects.count(), 0)
        bot.delete_message.assert_called_once()


class BookingBindTest(TestCase):
    def setUp(self):
        self.booking = BookingRequest.objects.create(
            client_name="Гость",
            preferred_date=timezone.localdate() + timedelta(days=2),
            preferred_time=time(10, 0),
        )

    def _msg(self, uid=555, username="ivan"):
        return SimpleNamespace(
            chat=SimpleNamespace(id=uid),
            from_user=SimpleNamespace(id=uid, username=username),
        )

    def test_bind_by_token(self):
        from tgbot.bot import _bind_booking_token
        bot = MagicMock()
        ok = _bind_booking_token(bot, self._msg(), self.booking.link_token)
        self.assertTrue(ok)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.messenger, "telegram")
        self.assertEqual(self.booking.messenger_user_id, 555)
        self.assertEqual(self.booking.messenger_username, "ivan")
        bot.send_message.assert_called()

    def test_bind_unknown_token(self):
        from tgbot.bot import _bind_booking_token
        bot = MagicMock()
        self.assertFalse(_bind_booking_token(bot, self._msg(), "no-such-token"))

    def test_booking_text_shows_contact_when_bound(self):
        from tgbot.notifications import build_booking_text
        self.booking.messenger = "telegram"
        self.booking.messenger_user_id = 999
        self.booking.messenger_username = "ivan"
        self.booking.save()
        self.assertIn("@ivan", build_booking_text(self.booking))

    def test_client_confirm(self):
        from tgbot.notifications import handle_client_booking_confirm
        bot = MagicMock()
        handle_client_booking_confirm(
            bot, make_call(f"cbk_confirm_{self.booking.pk}", uid=555)
        )
        self.booking.refresh_from_db()
        self.assertTrue(self.booking.client_confirmed)
        self.assertIsNotNone(self.booking.consent_at)  # согласие зафиксировано
        bot.answer_callback_query.assert_called()

    def test_summary_has_policy_link(self):
        from tgbot.notifications import client_booking_summary
        self.assertIn("Политика", client_booking_summary(self.booking))

    def test_client_confirm_unknown(self):
        from tgbot.notifications import handle_client_booking_confirm
        bot = MagicMock()
        handle_client_booking_confirm(bot, make_call("cbk_confirm_999999", uid=555))
        bot.answer_callback_query.assert_called_with("cb-1", "Заявка не найдена.")

    def test_booking_text_shows_client_confirmed(self):
        from tgbot.notifications import build_booking_text
        self.booking.client_confirmed = True
        self.booking.save()
        self.assertIn("Клиент подтвердил", build_booking_text(self.booking))

    def test_booking_text_shows_sessions(self):
        from booking.models import BookingSessionOption
        from tgbot.notifications import build_booking_text
        opt = BookingSessionOption.objects.create(count=5, label="5 сеансов")
        self.booking.sessions = opt
        self.booking.save()
        self.assertIn("5 сеансов", build_booking_text(self.booking))

    def test_unique_link_token_generated(self):
        other = BookingRequest.objects.create(
            client_name="Второй",
            preferred_date=timezone.localdate() + timedelta(days=2),
            preferred_time=time(11, 0),
        )
        self.assertTrue(self.booking.link_token)
        self.assertNotEqual(self.booking.link_token, other.link_token)
