from django.core.management.base import BaseCommand, CommandError

from tgbot.bot import ALLOWED_UPDATES, get_bot
from tgbot.models import BotSettings


class Command(BaseCommand):
    help = "Регистрирует webhook бота в Telegram по адресу из настроек."

    def handle(self, *args, **options):
        settings = BotSettings.load()
        if not settings.token:
            raise CommandError("Токен бота не задан.")
        if not settings.public_url:
            raise CommandError("Не задан публичный адрес сайта (public_url).")

        bot = get_bot(settings.token)
        url = settings.webhook_url
        bot.remove_webhook()
        ok = bot.set_webhook(
            url=url,
            secret_token=settings.secret_token,
            allowed_updates=ALLOWED_UPDATES,
            drop_pending_updates=False,
        )
        if ok:
            self.stdout.write(self.style.SUCCESS(f"Webhook установлен: {url}"))
        else:
            raise CommandError("Telegram отклонил установку webhook.")
