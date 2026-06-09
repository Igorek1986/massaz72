from django.core.management.base import BaseCommand, CommandError

from tgbot.bot import ALLOWED_UPDATES, get_bot
from tgbot.models import BotSettings


class Command(BaseCommand):
    help = "Запускает Telegram-бота в режиме polling (long polling)."

    def handle(self, *args, **options):
        settings = BotSettings.load()
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
            settings.save(update_fields=["bot_username"])

        self.stdout.write(
            self.style.SUCCESS(
                f"Бот @{me.username} запущен в режиме polling. Нажмите Ctrl+C для остановки."
            )
        )
        try:
            bot.infinity_polling(
                timeout=30,
                long_polling_timeout=30,
                allowed_updates=ALLOWED_UPDATES,
            )
        except KeyboardInterrupt:
            self.stdout.write("Остановлено.")
