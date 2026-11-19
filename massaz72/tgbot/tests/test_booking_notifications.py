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
        with patch("tgbot.bot.get_bot", return_value=bot), \
                patch("tgbot.notify.is_open", return_value=True):
            notify_new_booking(self.booking)  # окно открыто → шлём сразу
        self.assertEqual(
            BookingNotification.objects.filter(booking=self.booking).count(), 1
        )

    @patch("tgbot.notifications.abs_url", return_value="https://example.test/cabinet/requests/")
    def test_notices_and_updates_expose_only_cabinet_link(self, abs_url):
        from tgbot.notifications import refresh_booking_messages, send_booking_reminder, send_booking_to_admins

        self.booking.phone = "555"
        self.booking.address = "Адрес для выезда"
        self.booking.messenger_username = "example_client"
        self.booking.comment = "Закрытый комментарий"
        self.booking.save()
        bot = make_bot()
        self.assertEqual(send_booking_to_admins(bot, self.booking), 1)
        self.assertEqual(send_booking_reminder(bot, self.booking), 1)
        for call, title in zip(bot.send_message.call_args_list, (
            "Новая заявка на запись. Откройте кабинет специалиста.",
            "Заявка ждёт обработки. Откройте кабинет специалиста.",
        )):
            self.assertEqual(call.args, (111, f"{title}\n{abs_url.return_value}"))
            self.assertEqual(call.kwargs, {"disable_web_page_preview": True})
        self.booking.status = BookingRequest.Status.CANCELLED
        self.booking.save()
        self.assertEqual(send_booking_reminder(bot, self.booking), 0)
        refresh_booking_messages(bot, self.booking)
        for call in bot.edit_message_text.call_args_list:
            self.assertEqual(call.args[0], f"Заявка на запись отменена.\n{abs_url.return_value}")
            self.assertIsNone(call.kwargs["reply_markup"])

    def test_deferred_outside_window(self):
        from tgbot.models import PendingNotification
        bot = make_bot()
        with patch("tgbot.bot.get_bot", return_value=bot), \
                patch("tgbot.notify.is_open", return_value=False):
            notify_new_booking(self.booking)  # тихие часы → откладываем
        self.assertEqual(BookingNotification.objects.count(), 0)
        self.assertEqual(
            PendingNotification.objects.filter(kind="new_booking", sent=False).count(), 1
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

    def test_legacy_actions_replace_message_without_changing_booking(self):
        for action in ("confirm", "decline"):
            with self.subTest(action=action):
                bot = MagicMock()
                handle_booking_action(bot, make_call(f"br_{action}_{self.booking.pk}", uid=111))
                self.booking.refresh_from_db()
                self.assertEqual(self.booking.status, BookingRequest.Status.PENDING)
                bot.edit_message_text.assert_called_once()
                self.assertIsNone(bot.edit_message_text.call_args.kwargs["reply_markup"])
        self.assertFalse(Appointment.objects.exists())

    def test_non_admin_denied(self):
        bot = MagicMock()
        handle_booking_action(bot, make_call(f"br_confirm_{self.booking.pk}", uid=999))
        bot.answer_callback_query.assert_called_once_with("cb-1", "Нет доступа.")
        bot.edit_message_text.assert_not_called()


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

    def test_bind_does_not_notify_master(self):
        """Привязка к боту мастеру ничего не шлёт — ждём подтверждения клиента."""
        BotAdmin.objects.create(telegram_id=111, name="A", is_active=True)
        from tgbot.bot import _bind_booking_token
        _bind_booking_token(make_bot(), self._msg(), self.booking.link_token)
        self.assertEqual(
            BookingNotification.objects.filter(booking=self.booking).count(), 0
        )

    def test_confirm_sends_deferred_notification(self):
        """Заявка без телефона: мастера уведомляем при нажатии «Подтвердить»."""
        BotAdmin.objects.create(telegram_id=111, name="A", is_active=True)
        from tgbot.notifications import handle_client_booking_confirm
        with patch("tgbot.bot.get_bot", return_value=make_bot()), \
                patch("tgbot.notify.is_open", return_value=True):
            handle_client_booking_confirm(
                make_bot(), make_call(f"cbk_confirm_{self.booking.pk}", uid=555)
            )
        self.assertEqual(
            BookingNotification.objects.filter(booking=self.booking).count(), 1
        )

    def test_bind_refreshes_when_already_notified(self):
        """Если мастера уже уведомляли (был телефон) — обновляем, не дублируем."""
        BotAdmin.objects.create(telegram_id=111, name="A", is_active=True)
        BookingNotification.objects.create(
            booking=self.booking, admin_telegram_id=111, message_id=10
        )
        from tgbot.bot import _bind_booking_token
        bot = make_bot()
        _bind_booking_token(bot, self._msg(), self.booking.link_token)
        self.assertEqual(
            BookingNotification.objects.filter(booking=self.booking).count(), 1
        )
        bot.edit_message_text.assert_called()

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

    def test_confirm_activates_awaiting_contact(self):
        """Заявка без контакта после подтверждения в боте становится PENDING."""
        from tgbot.notifications import handle_client_booking_confirm
        awaiting = BookingRequest.objects.create(
            client_name="Безтел",
            preferred_date=timezone.localdate() + timedelta(days=2),
            preferred_time=time(11, 0),
            status=BookingRequest.Status.AWAITING_CONTACT,
        )
        handle_client_booking_confirm(
            MagicMock(), make_call(f"cbk_confirm_{awaiting.pk}", uid=555)
        )
        awaiting.refresh_from_db()
        self.assertEqual(awaiting.status, BookingRequest.Status.PENDING)
        self.assertTrue(awaiting.client_confirmed)

    def test_summary_has_policy_link(self):
        from tgbot.notifications import client_booking_summary
        self.assertIn("Согласие", client_booking_summary(self.booking))

    def test_client_confirm_unknown(self):
        from tgbot.notifications import handle_client_booking_confirm
        bot = MagicMock()
        handle_client_booking_confirm(bot, make_call("cbk_confirm_999999", uid=555))
        bot.answer_callback_query.assert_called_with("cb-1", "Заявка не найдена.")

    def test_unique_link_token_generated(self):
        other = BookingRequest.objects.create(
            client_name="Второй",
            preferred_date=timezone.localdate() + timedelta(days=2),
            preferred_time=time(11, 0),
        )
        self.assertTrue(self.booking.link_token)
        self.assertNotEqual(self.booking.link_token, other.link_token)


class RescheduleActionTest(TestCase):
    def setUp(self):
        from cabinet.models import Appointment, Specialist
        from booking.models import RescheduleRequest
        BotAdmin.objects.create(telegram_id=111, name="A", is_active=True)
        user = User.objects.create_user("m", password="pw")
        spec = Specialist.objects.create(user=user, name="М")
        self.appt = Appointment.objects.create(
            specialist=spec, client_name="К",
            date=timezone.localdate() + timedelta(days=5), time_start=time(10, 0),
            cost=Decimal("1000"), status="scheduled",
        )
        self.req = RescheduleRequest.objects.create(
            appointment=self.appt,
            new_date=timezone.localdate() + timedelta(days=7), new_time=time(11, 0),
        )

    def test_confirm_applies(self):
        from tgbot.notifications import handle_reschedule_action
        handle_reschedule_action(MagicMock(), make_call(f"rs_confirm_{self.req.pk}", uid=111))
        self.appt.refresh_from_db()
        self.req.refresh_from_db()
        self.assertEqual(self.appt.time_start, time(11, 0))
        self.assertEqual(self.appt.date, self.req.new_date)
        self.assertEqual(self.req.status, "approved")

    def test_decline(self):
        from tgbot.notifications import handle_reschedule_action
        handle_reschedule_action(MagicMock(), make_call(f"rs_decline_{self.req.pk}", uid=111))
        self.req.refresh_from_db()
        self.assertEqual(self.req.status, "declined")

    def test_non_admin_denied(self):
        from tgbot.notifications import handle_reschedule_action
        handle_reschedule_action(MagicMock(), make_call(f"rs_confirm_{self.req.pk}", uid=999))
        self.req.refresh_from_db()
        self.assertEqual(self.req.status, "pending")


class AccountBindTest(TestCase):
    def setUp(self):
        from accounts.models import Client as ClientProfile
        user = User.objects.create_user("c", password="pw")
        self.profile = ClientProfile.objects.create(user=user)

    def _msg(self, uid=777, username="petr"):
        return SimpleNamespace(
            chat=SimpleNamespace(id=uid),
            from_user=SimpleNamespace(id=uid, username=username),
        )

    def test_bind_account(self):
        from tgbot.bot import _bind_account_token
        bot = MagicMock()
        ok = _bind_account_token(bot, self._msg(), self.profile.link_token)
        self.assertTrue(ok)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.telegram_id, 777)
        self.assertEqual(self.profile.telegram_username, "petr")
        self.assertEqual(self.profile.messenger, "telegram")
        bot.send_message.assert_called()

    def test_bind_unknown(self):
        from tgbot.bot import _bind_account_token
        self.assertFalse(_bind_account_token(MagicMock(), self._msg(), "no-such"))


class TargetedNotifyTest(TestCase):
    """Адресная доставка (конкретный мастер + главный) и тихие часы."""

    def setUp(self):
        self.massage = Massage.objects.create(
            name="Спина", price=Decimal("2000"), duration_min=30, duration_max=60,
            location="Кабинет", massage_type=Massage.ADULT, slug="spina",
        )
        self.head = Specialist.objects.create(name="Главный", telegram_id=900)
        self.spec = Specialist.objects.create(name="Мастер", telegram_id=901, head=self.head)

    def _booking(self, **over):
        data = dict(
            client_name="К", service=self.massage, specialist=self.spec,
            preferred_date=timezone.localdate() + timedelta(days=2),
            preferred_time=time(10, 0), status=BookingRequest.Status.PENDING,
        )
        data.update(over)
        return BookingRequest.objects.create(**data)

    def test_recipients_master_and_head(self):
        from tgbot.notifications import booking_recipients
        self.assertEqual(set(booking_recipients(self._booking())), {901, 900})

    def test_recipients_fallback_to_admins(self):
        from tgbot.notifications import booking_recipients
        BotAdmin.objects.create(telegram_id=111, name="A", is_active=True)
        b = self._booking(specialist=Specialist.objects.create(name="Без TG"))
        self.assertEqual(set(booking_recipients(b)), {111})

    def test_quiet_hours_defer_and_flush(self):
        from tgbot.models import PendingNotification
        from tgbot.notify import flush_due
        b = self._booking()
        with patch("tgbot.bot.get_bot", return_value=make_bot()), \
                patch("tgbot.notify.is_open", return_value=False):
            notify_new_booking(b)
        self.assertEqual(PendingNotification.objects.filter(sent=False).count(), 1)
        # наступило время доставки
        PendingNotification.objects.update(available_at=timezone.now() - timedelta(minutes=1))
        # окно открылось — flush доставляет
        with patch("tgbot.bot.get_bot", return_value=make_bot()), \
                patch("tgbot.notify.is_open", return_value=True):
            flush_due()
        self.assertTrue(PendingNotification.objects.get().sent)
        self.assertEqual(BookingNotification.objects.filter(booking=b).count(), 2)  # мастер+главный

    def test_reminder_command(self):
        from cabinet.models import WorkSchedule
        WorkSchedule.objects.create(specialist=self.spec, booking_reminder_minutes=60)
        b = self._booking()
        BookingRequest.objects.filter(pk=b.pk).update(
            created_at=timezone.now() - timedelta(minutes=90)
        )
        from django.core.management import call_command
        with patch("tgbot.bot.get_bot", return_value=make_bot()), \
                patch("tgbot.notify.is_open", return_value=True):
            call_command("remind_unconfirmed_bookings")
        b.refresh_from_db()
        self.assertIsNotNone(b.reminded_at)
        self.assertEqual(BookingNotification.objects.filter(booking=b).count(), 2)

    def test_bind_specialist_token(self):
        from tgbot.bot import _bind_specialist_token
        spec = Specialist.objects.create(name="Новый")
        msg = SimpleNamespace(chat=SimpleNamespace(id=555),
                              from_user=SimpleNamespace(id=555, username="m"))
        self.assertTrue(_bind_specialist_token(make_bot(), msg, spec.tg_link_token))
        spec.refresh_from_db()
        self.assertEqual(spec.telegram_id, 555)

    def test_tokens_unique_and_bind_targets_right_specialist(self):
        """Регрессия: токены разных специалистов не должны совпадать, иначе
        привязка уходит не тому мастеру (баг миграции 0023)."""
        from tgbot.bot import _bind_specialist_token
        s1 = Specialist.objects.create(name="Первый")
        s2 = Specialist.objects.create(name="Второй")
        self.assertNotEqual(s1.tg_link_token, s2.tg_link_token)
        msg = SimpleNamespace(chat=SimpleNamespace(id=777),
                              from_user=SimpleNamespace(id=777, username="u"))
        _bind_specialist_token(make_bot(), msg, s2.tg_link_token)
        s1.refresh_from_db(); s2.refresh_from_db()
        self.assertEqual(s2.telegram_id, 777)
        self.assertIsNone(s1.telegram_id)  # не задело другого


class NativeBotBookingTest(TestCase):
    def setUp(self):
        from booking.models import BookingSessionOption
        from tgbot.models import TelegramUser

        specialist = Specialist.objects.create(name="Мастер")
        service = Massage.objects.create(
            name="Услуга", price=2000, duration_min=30, duration_max=60,
            location="Кабинет", massage_type=Massage.ADULT, slug="test-service",
        )
        option = BookingSessionOption.objects.create(specialist=specialist, count=3)
        self.user = TelegramUser.objects.create(telegram_id=123, consent_at=timezone.now())
        self.state = {
            "therapist_id": specialist.pk, "massage_id": service.pk, "sessions_id": option.pk,
            "date_iso": (timezone.localdate() + timedelta(days=2)).isoformat(),
            "timeslot_label": "10:00",
        }

    @patch("tgbot.bot._bk_free_times", return_value=["10:00"])
    def test_booking_is_saved_for_cabinet(self, free_times):
        from tgbot.bot import _create_bot_booking

        booking = _create_bot_booking(self.user, self.state)
        self.assertEqual(booking.source, BookingRequest.Source.BOT)
        self.assertEqual(booking.status, BookingRequest.Status.PENDING)
        self.assertEqual(booking.sessions_id, self.state["sessions_id"])
        self.assertEqual(booking.messenger_user_id, self.user.telegram_id)
        self.assertEqual(booking.consent_at, self.user.consent_at)

    @patch("tgbot.bot._bk_free_times", return_value=[])
    def test_stale_slot_does_not_create_booking(self, free_times):
        from tgbot.bot import _create_bot_booking

        self.assertIsNone(_create_bot_booking(self.user, self.state))
        self.assertFalse(BookingRequest.objects.exists())

    def test_invalid_service_or_option_does_not_create_booking(self):
        from tgbot.bot import _create_bot_booking

        for field in ("therapist_id", "massage_id", "sessions_id"):
            with self.subTest(field=field):
                self.assertIsNone(_create_bot_booking(self.user, {**self.state, field: 999}))
        self.assertFalse(BookingRequest.objects.exists())
