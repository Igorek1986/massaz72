from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from django.core.management import CommandError, call_command
from django.db import DatabaseError
from django.test import SimpleTestCase


class RunBotTest(SimpleTestCase):
    def setUp(self):
        module = "tgbot.management.commands.runbot"
        self.calls = Mock()
        connections = self.enterContext(patch(f"{module}.connections"))
        load_settings = self.enterContext(patch(f"{module}.BotSettings.load"))
        get_bot = self.enterContext(patch(f"{module}.get_bot"))
        self.calls.attach_mock(connections.close_all, "close")
        self.calls.attach_mock(load_settings, "load_settings")
        self.calls.attach_mock(get_bot, "get_bot")

        self.settings = load_settings.return_value
        self.settings.token = "test-token"
        self.settings.bot_username = "test_bot"
        self.bot = get_bot.return_value
        self.bot.get_me.return_value = SimpleNamespace(username="test_bot")
        self.process_new_updates = self.bot.process_new_updates
        self.stdout = StringIO()

    def runbot(self):
        call_command("runbot", stdout=self.stdout)

    def test_closes_connections_before_polling_and_after_each_batch(self):
        def poll(**kwargs):
            self.bot.process_new_updates(["first", "second"])
            self.bot.process_new_updates([])

        self.bot.infinity_polling.side_effect = poll
        self.runbot()

        self.assertEqual(self.calls.mock_calls, [
            call.load_settings(),
            call.close(),
            call.get_bot("test-token"),
            call.get_bot().remove_webhook(),
            call.get_bot().get_me(),
            call.get_bot().infinity_polling(
                timeout=30, long_polling_timeout=30,
                allowed_updates=["message", "callback_query"],
            ),
            call.get_bot().process_new_updates(["first", "second"]),
            call.close(),
            call.get_bot().process_new_updates([]),
            call.close(),
        ])
        self.settings.save.assert_not_called()
        self.assertIs(self.bot.process_new_updates, self.process_new_updates)

    def test_closes_connections_after_saving_updated_bot_username(self):
        self.settings.bot_username = "old_username"

        self.runbot()

        self.assertEqual(self.settings.bot_username, "test_bot")
        self.assertEqual(self.calls.mock_calls[-3:-1], [
            call.load_settings().save(update_fields=["bot_username"]),
            call.close(),
        ])
        self.bot.infinity_polling.assert_called_once()

    def test_closes_connections_and_restores_handler_on_processing_error(self):
        self.process_new_updates.side_effect = DatabaseError("handler failed")
        self.bot.infinity_polling.side_effect = lambda **kwargs: self.bot.process_new_updates(["update"])

        with self.assertRaisesMessage(DatabaseError, "handler failed"):
            self.runbot()

        self.assertEqual(self.calls.mock_calls[-2:], [
            call.get_bot().process_new_updates(["update"]),
            call.close(),
        ])
        self.assertIs(self.bot.process_new_updates, self.process_new_updates)

    def test_restores_handler_after_keyboard_interrupt(self):
        self.bot.infinity_polling.side_effect = KeyboardInterrupt

        self.runbot()

        self.assertIn("Остановлено.", self.stdout.getvalue())
        self.assertIs(self.bot.process_new_updates, self.process_new_updates)

    def test_closes_connections_when_token_is_missing(self):
        self.settings.token = ""

        with self.assertRaises(CommandError):
            self.runbot()

        self.assertEqual(self.calls.mock_calls, [call.load_settings(), call.close()])

    def test_closes_connections_when_loading_settings_fails(self):
        self.calls.load_settings.side_effect = DatabaseError("load failed")

        with self.assertRaisesMessage(DatabaseError, "load failed"):
            self.runbot()

        self.assertEqual(self.calls.mock_calls, [call.load_settings(), call.close()])

    def test_closes_connections_when_saving_username_fails(self):
        self.settings.bot_username = ""
        self.settings.save.side_effect = DatabaseError("save failed")

        with self.assertRaisesMessage(DatabaseError, "save failed"):
            self.runbot()

        self.assertEqual(self.calls.mock_calls[-2:], [
            call.load_settings().save(update_fields=["bot_username"]),
            call.close(),
        ])
        self.bot.infinity_polling.assert_not_called()
