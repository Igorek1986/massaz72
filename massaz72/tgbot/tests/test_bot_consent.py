"""Согласие на обработку ПД в боте: запрос первым сообщением, фиксация даты."""
import itertools
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import telebot
from django.test import TestCase
from django.utils import timezone
from telebot import types

from tgbot import bot as botmod
from tgbot.models import BotAdmin, BotSettings, DialogMessage, TelegramUser

UID = 555
_ids = itertools.count(1)


def make_bot():
    bot = telebot.TeleBot("123:TEST", parse_mode="HTML", threaded=False)
    with patch.object(telebot.TeleBot, "set_my_commands"):  # без сетевого вызова
        botmod._register_handlers(bot)
    counter = itertools.count(1)
    bot.send_message = MagicMock(
        side_effect=lambda *a, **k: SimpleNamespace(message_id=next(counter))
    )
    bot.edit_message_text = MagicMock()
    bot.answer_callback_query = MagicMock()
    bot.delete_message = MagicMock()
    return bot


def _from(uid=UID):
    return {"id": uid, "is_bot": False, "first_name": "Иван", "username": "ivan"}


def message_update(text, uid=UID):
    mid = next(_ids)
    entities = []
    if text.startswith("/"):
        cmd_len = len(text.split()[0])
        entities = [{"type": "bot_command", "offset": 0, "length": cmd_len}]
    return types.Update.de_json({
        "update_id": mid,
        "message": {
            "message_id": mid, "date": 1700000000,
            "chat": {"id": uid, "type": "private", "first_name": "Иван"},
            "from": _from(uid), "text": text,
            **({"entities": entities} if entities else {}),
        },
    })


def callback_update(data, uid=UID):
    mid = next(_ids)
    return types.Update.de_json({
        "update_id": mid,
        "callback_query": {
            "id": str(mid), "from": _from(uid), "chat_instance": "x", "data": data,
            "message": {
                "message_id": 77, "date": 1700000000,
                "chat": {"id": uid, "type": "private", "first_name": "Иван"},
                "from": {"id": 1, "is_bot": True, "first_name": "bot"},
                "text": "prompt",
            },
        },
    })


def sent_texts(bot):
    return [c.args[1] if len(c.args) > 1 else c.kwargs.get("text", "")
            for c in bot.send_message.call_args_list]


class ConsentFlowTest(TestCase):
    def setUp(self):
        botmod._pending_starts.clear()
        botmod._pending_bookings.clear()
        s = BotSettings.load()
        s.welcome_text = "Привет, это бот!"
        s.save()
        self.bot = make_bot()

    def _consent(self, uid=UID):
        TelegramUser.objects.update_or_create(
            telegram_id=uid, defaults={"consent_at": timezone.now()}
        )

    # --- /start

    def test_start_new_user_gets_consent_prompt_only(self):
        self.bot.process_new_updates([message_update("/start")])
        self.assertEqual(self.bot.send_message.call_count, 1)
        args, kwargs = self.bot.send_message.call_args
        self.assertIn("формальностей", args[1])
        self.assertIn("/consent/", args[1])
        self.assertIn("/privacy/", args[1])
        button = kwargs["reply_markup"].keyboard[0][0]
        self.assertEqual(button.callback_data, "cn_accept")
        self.assertIn("Ознакомлен и принимаю", button.text)
        user = TelegramUser.objects.get(telegram_id=UID)
        self.assertIsNone(user.consent_at)  # пока не нажал

    def test_start_consented_user_gets_welcome_directly(self):
        self._consent()
        self.bot.process_new_updates([message_update("/start")])
        self.assertEqual(sent_texts(self.bot), ["Привет, это бот!"])

    def test_accept_records_date_and_shows_welcome(self):
        self.bot.process_new_updates([message_update("/start")])
        self.bot.send_message.reset_mock()
        before = timezone.now()
        self.bot.process_new_updates([callback_update("cn_accept")])
        user = TelegramUser.objects.get(telegram_id=UID)
        self.assertIsNotNone(user.consent_at)
        self.assertGreaterEqual(user.consent_at, before)
        # исходное сообщение заменено подтверждением с датой
        text = self.bot.edit_message_text.call_args.args[0]
        self.assertIn("Согласие на обработку персональных данных принято", text)
        self.assertIn(timezone.localtime(user.consent_at).strftime("%d.%m.%Y %H:%M"), text)
        # после принятия показано приветствие
        self.assertEqual(sent_texts(self.bot), ["Привет, это бот!"])

    def test_second_accept_keeps_first_timestamp(self):
        self.bot.process_new_updates([callback_update("cn_accept")])
        first = TelegramUser.objects.get(telegram_id=UID).consent_at
        self.bot.process_new_updates([callback_update("cn_accept")])
        self.assertEqual(TelegramUser.objects.get(telegram_id=UID).consent_at, first)

    def test_deeplink_runs_after_accept(self):
        with patch("tgbot.bot._bind_booking_token", return_value=True) as bind:
            self.bot.process_new_updates([message_update("/start TOKEN123")])
            bind.assert_not_called()  # до согласия — не привязываем
            self.assertEqual(self.bot.send_message.call_count, 1)  # только запрос
            self.bot.send_message.reset_mock()
            self.bot.process_new_updates([callback_update("cn_accept")])
            bind.assert_called_once()
            self.assertEqual(bind.call_args.args[2], "TOKEN123")
        # привязка отработала — приветствие не дублируется
        self.assertEqual(self.bot.send_message.call_count, 0)

    def test_pending_start_cleared_after_accept(self):
        self.bot.process_new_updates([message_update("/start")])
        self.assertIn(UID, botmod._pending_starts)
        self.bot.process_new_updates([callback_update("cn_accept")])
        self.assertNotIn(UID, botmod._pending_starts)

    # --- остальные действия до согласия

    def test_free_text_not_forwarded_without_consent(self):
        BotAdmin.objects.create(telegram_id=999, is_active=True)
        with patch("tgbot.bot._forward_to_admins") as fwd:
            self.bot.process_new_updates([message_update("Хочу записаться")])
            fwd.assert_not_called()
        self.assertEqual(DialogMessage.objects.count(), 0)
        self.assertIn("формальностей", sent_texts(self.bot)[0])

    def test_free_text_forwarded_with_consent(self):
        self._consent()
        with patch("tgbot.bot._forward_to_admins") as fwd:
            self.bot.process_new_updates([message_update("Хочу записаться")])
            fwd.assert_called_once()

    def test_services_button_requires_consent(self):
        self.bot.process_new_updates([message_update(botmod.BTN_SERVICES)])
        self.assertIn("формальностей", sent_texts(self.bot)[0])
        self._consent()
        self.bot.send_message.reset_mock()
        with patch("tgbot.bot.build_services_text", return_value="ПРАЙС"):
            self.bot.process_new_updates([message_update(botmod.BTN_SERVICES)])
        self.assertEqual(sent_texts(self.bot), ["ПРАЙС"])

    def test_book_button_requires_consent(self):
        self.bot.process_new_updates([message_update(botmod.BTN_BOOK)])
        self.assertIn("формальностей", sent_texts(self.bot)[0])
        self.assertNotIn(UID, botmod._pending_bookings)

    def test_booking_callback_requires_consent(self):
        self.bot.process_new_updates([callback_update("bk_cancel")])
        self.assertIn("формальностей", sent_texts(self.bot)[0])

    def test_booking_callback_passes_with_consent(self):
        self._consent()
        self.bot.process_new_updates([callback_update("bk_x")])  # неактивный элемент
        self.assertEqual(self.bot.send_message.call_count, 0)

    # --- администраторы и изоляция пользователей

    def test_admin_not_gated(self):
        BotAdmin.objects.create(telegram_id=UID, is_active=True)
        self.bot.process_new_updates([message_update("привет")])
        self.assertEqual(sent_texts(self.bot), [botmod.ADMIN_HINT])
        self.assertTrue(botmod._has_consent(UID))

    def test_inactive_admin_is_gated(self):
        BotAdmin.objects.create(telegram_id=UID, is_active=False)
        self.assertFalse(botmod._has_consent(UID))

    def test_consent_is_per_user(self):
        self._consent(uid=111)
        self.assertTrue(botmod._has_consent(111))
        self.assertFalse(botmod._has_consent(222))
