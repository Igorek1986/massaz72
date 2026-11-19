from unittest.mock import Mock, patch

from django.test import TestCase
from django.urls import reverse

from tgbot.models import BotSettings
from tgbot.notifications import send_account_erasure_reminder


class AccountErasureNotificationTest(TestCase):
    @patch("tgbot.bot.get_bot")
    def test_disabled_bot_does_not_send(self, get_bot):
        BotSettings.objects.create(is_enabled=False, token="test-only")
        self.assertFalse(send_account_erasure_reminder(123))
        get_bot.assert_not_called()

    @patch("tgbot.notifications.abs_url")
    @patch("tgbot.bot.get_bot")
    def test_notification_contains_only_generic_text_and_cabinet_url(self, get_bot, abs_url):
        BotSettings.objects.create(is_enabled=True, token="test-only")
        url = "https://example.test" + reverse("cabinet:erasure_requests")
        abs_url.return_value = url
        bot = get_bot.return_value
        self.assertTrue(send_account_erasure_reminder(123))
        bot.send_message.assert_called_once_with(
            123, f"В кабинете есть запросы, требующие проверки.\n{url}",
            disable_web_page_preview=True, timeout=10,
        )

        abs_url.return_value = reverse("cabinet:erasure_requests")
        self.assertFalse(send_account_erasure_reminder(123))
        self.assertEqual(bot.send_message.call_count, 1)

    @patch("tgbot.notifications.abs_url", return_value="https://example.test/cabinet/data-erasure/")
    @patch("tgbot.bot.get_bot")
    def test_delivery_error_returns_false_for_retry(self, get_bot, abs_url):
        BotSettings.objects.create(is_enabled=True, token="test-only")
        get_bot.return_value = Mock()
        get_bot.return_value.send_message.side_effect = RuntimeError
        self.assertFalse(send_account_erasure_reminder(123))
