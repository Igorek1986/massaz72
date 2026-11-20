from django.core.management.base import BaseCommand, CommandError
from django.db import connections

from tgbot.bot import ALLOWED_UPDATES, get_bot
from tgbot.models import BotSettings


class Command(BaseCommand):
    help = "Запускает Telegram-бота в режиме polling (long polling)."

    def handle(self, *args, **options):
        try:
            settings = BotSettings.load()
        finally:
            connections.close_all()
        if not settings.token:
            raise CommandError(
                "Токен бота не задан. Укажите его в админке: «Telegram-бот → Настройки»."
            )

        bot = get_bot(settings.token)
        # Снимаем webhook, иначе getUpdates вернёт ошибку конфликта.
        try:
            bot.remove_webhook()
        except Exception as exc:  # noqa: BLE001
            self.stderr.write(f"remove_webhook: {exc}")

        me = bot.get_me()
        if settings.bot_username != me.username:
            settings.bot_username = me.username
            try:
                settings.save(update_fields=["bot_username"])
            finally:
                connections.close_all()

        self.stdout.write(
            self.style.SUCCESS(
                f"Бот @{me.username} запущен в режиме polling. Нажмите Ctrl+C для остановки."
            )
        )
        process_new_updates = bot.process_new_updates

        def process_polling_updates(updates):
            try:
                return process_new_updates(updates)
            finally:
                connections.close_all()

        # Синхронные обработчики работают в потоке polling, без цикла запроса Django.
        bot.process_new_updates = process_polling_updates
        try:
            bot.infinity_polling(
                timeout=30,
                long_polling_timeout=30,
                allowed_updates=ALLOWED_UPDATES,
            )
        except KeyboardInterrupt:
            self.stdout.write("Остановлено.")
        finally:
            bot.process_new_updates = process_new_updates
