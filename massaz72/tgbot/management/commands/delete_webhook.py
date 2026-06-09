from django.core.management.base import BaseCommand, CommandError

from tgbot.bot import get_bot
from tgbot.models import BotSettings


class Command(BaseCommand):
    help = "Удаляет webhook бота в Telegram (для перехода на polling)."

    def handle(self, *args, **options):
        settings = BotSettings.load()
        if not settings.token:
            raise CommandError("Токен бота не задан.")

        bot = get_bot(settings.token)
        if bot.remove_webhook():
            self.stdout.write(self.style.SUCCESS("Webhook удалён."))
        else:
            raise CommandError("Не удалось удалить webhook.")
