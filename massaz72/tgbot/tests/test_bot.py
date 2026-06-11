import itertools
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import Client, TestCase

from tgbot import bot as botmod
from tgbot.models import (
    AdminForward,
    BotAdmin,
    BotSettings,
    DialogMessage,
    TelegramUser,
)
from services.models import Massage


def make_bot():
    """MagicMock-бот, возвращающий объекты с инкрементным message_id."""
    bot = MagicMock()
    counter = itertools.count(1)
    bot.send_message.side_effect = lambda *a, **k: SimpleNamespace(
        message_id=next(counter)
    )
    bot.copy_message.side_effect = lambda *a, **k: SimpleNamespace(
        message_id=next(counter)
    )
    return bot


def client_message(text="Хочу записаться", uid=111, content_type="text", reply_to=None):
    return SimpleNamespace(
        from_user=SimpleNamespace(
            id=uid, username="client", first_name="Иван", last_name="Петров"
        ),
        chat=SimpleNamespace(id=uid, type="private"),
        content_type=content_type,
        text=text if content_type == "text" else None,
        caption=None if content_type == "text" else text,
        message_id=5,
        reply_to_message=reply_to,
    )


class BotSettingsTest(TestCase):
    def test_singleton(self):
        a = BotSettings.load()
        a.public_url = "https://massaz72.ru/"
        a.save()
        b = BotSettings.load()
        self.assertEqual(a.pk, b.pk)
        self.assertEqual(BotSettings.objects.count(), 1)

    def test_webhook_url(self):
        s = BotSettings.load()
        s.public_url = "https://massaz72.ru/"
        s.save()
        self.assertEqual(
            s.webhook_url, f"https://massaz72.ru/tg/webhook/{s.secret_path}/"
        )

    def test_webhook_url_empty_without_public_url(self):
        self.assertEqual(BotSettings.load().webhook_url, "")


class ForwardToAdminsTest(TestCase):
    def test_forward_creates_records_and_notifies(self):
        BotAdmin.objects.create(telegram_id=999, is_active=True)
        bot = make_bot()

        botmod._forward_to_admins(bot, client_message("Запишите меня на массаж"))

        user = TelegramUser.objects.get(telegram_id=111)
        self.assertEqual(user.first_name, "Иван")
        self.assertEqual(
            DialogMessage.objects.filter(user=user, direction=DialogMessage.IN).count(),
            1,
        )
        self.assertTrue(
            AdminForward.objects.filter(user=user, admin_telegram_id=999).exists()
        )
        # Заголовок ушёл админу, подтверждение — клиенту.
        targets = [c.args[0] for c in bot.send_message.call_args_list]
        self.assertIn(999, targets)
        self.assertIn(111, targets)

    def test_inactive_admin_not_notified(self):
        BotAdmin.objects.create(telegram_id=999, is_active=False)
        bot = make_bot()

        botmod._forward_to_admins(bot, client_message())

        self.assertFalse(AdminForward.objects.exists())
        # Клиент получил уведомление об отсутствии админов.
        self.assertEqual(bot.send_message.call_args.args[0], 111)


class AdminReplyTest(TestCase):
    def test_reply_delivered_to_client(self):
        user = TelegramUser.objects.create(telegram_id=111, first_name="Иван")
        BotAdmin.objects.create(telegram_id=999, is_active=True)
        AdminForward.objects.create(
            user=user, admin_telegram_id=999, admin_message_id=50
        )
        bot = make_bot()
        reply = client_message(
            text="Завтра в 10:00 подойдёт?",
            uid=999,
            reply_to=SimpleNamespace(message_id=50),
        )

        botmod._handle_admin_reply(bot, reply)

        # Первое сообщение ушло клиенту (id 111).
        first_call = bot.send_message.call_args_list[0]
        self.assertEqual(first_call.args[0], 111)
        self.assertIn("Ответ массажиста", first_call.args[1])
        self.assertEqual(
            DialogMessage.objects.filter(
                user=user, direction=DialogMessage.OUT
            ).count(),
            1,
        )

    def test_reply_to_unknown_message_ignored(self):
        BotAdmin.objects.create(telegram_id=999, is_active=True)
        bot = make_bot()
        reply = client_message(
            text="что-то", uid=999, reply_to=SimpleNamespace(message_id=12345)
        )

        botmod._handle_admin_reply(bot, reply)

        bot.send_message.assert_not_called()


class ServicesTextTest(TestCase):
    def test_lists_active_massages_with_prices(self):
        Massage.objects.create(
            name="Детский общий",
            price=1500,
            duration_min=30,
            duration_max=40,
            location="Тюмень",
            massage_type=Massage.CHILD,
        )
        Massage.objects.create(
            name="Архивный",
            price=999,
            duration_min=30,
            duration_max=30,
            location="Тюмень",
            massage_type=Massage.ADULT,
            is_archived=True,
        )
        text = botmod.build_services_text()
        self.assertIn("Детский общий", text)
        self.assertIn("1500 ₽", text)
        self.assertIn("30–40 мин", text)
        self.assertNotIn("Архивный", text)

    def test_empty_when_no_services(self):
        self.assertIn("не заполнен", botmod.build_services_text())


class WebhookViewTest(TestCase):
    def setUp(self):
        self.settings_obj = BotSettings.load()
        self.settings_obj.token = "123456:test-token"
        self.settings_obj.is_enabled = True
        self.settings_obj.mode = BotSettings.MODE_WEBHOOK
        self.settings_obj.save()
        self.url = f"/tg/webhook/{self.settings_obj.secret_path}/"

    def _post(self, secret):
        return Client().post(
            self.url,
            data=json.dumps({"update_id": 1}),
            content_type="application/json",
            **{"HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN": secret},
        )

    def test_valid_secret_ok(self):
        # Мокаем бота: get_bot регистрирует обработчики и ходит в живой
        # Telegram API (set_my_commands), что в тестах недоступно.
        with patch("tgbot.views.get_bot", return_value=make_bot()) as mocked:
            resp = self._post(self.settings_obj.secret_token)
        self.assertEqual(resp.status_code, 200)
        mocked.assert_called_once_with(self.settings_obj.token)

    def test_bad_secret_forbidden(self):
        resp = self._post("wrong")
        self.assertEqual(resp.status_code, 403)

    def test_disabled_forbidden(self):
        self.settings_obj.is_enabled = False
        self.settings_obj.save()
        resp = self._post(self.settings_obj.secret_token)
        self.assertEqual(resp.status_code, 403)

    def test_bad_path_forbidden(self):
        resp = Client().post(
            "/tg/webhook/wrong-path/",
            data=json.dumps({"update_id": 1}),
            content_type="application/json",
            **{"HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN": self.settings_obj.secret_token},
        )
        self.assertEqual(resp.status_code, 403)

    def test_missing_secret_header_forbidden(self):
        resp = Client().post(
            self.url,
            data=json.dumps({"update_id": 1}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_polling_mode_forbidden(self):
        self.settings_obj.mode = BotSettings.MODE_POLLING
        self.settings_obj.save()
        resp = self._post(self.settings_obj.secret_token)
        self.assertEqual(resp.status_code, 403)

    def test_get_not_allowed(self):
        resp = Client().get(self.url)
        self.assertEqual(resp.status_code, 405)


class BroadcastFormatTest(TestCase):
    def test_subject_and_text_are_escaped(self):
        msg = botmod._format_broadcast_text("Акция <b>", "Скидка 10% на массаж <спина & шея>")
        self.assertNotIn("<спина", msg)
        self.assertNotIn("<b>\n", msg)  # инъекция тегов из темы не проходит
        self.assertIn("&lt;спина &amp; шея&gt;", msg)
        self.assertIn("<b>Акция &lt;b&gt;</b>", msg)

    def test_without_subject_text_still_escaped(self):
        msg = botmod._format_broadcast_text("", "1 < 2")
        self.assertEqual(msg, "1 &lt; 2")
