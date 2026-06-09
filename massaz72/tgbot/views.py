import logging

import telebot
from django.http import (
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
)
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .bot import get_bot
from .models import BotSettings

logger = logging.getLogger(__name__)

SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"


@csrf_exempt
@require_POST
def webhook(request, secret_path):
    """Принимает обновления Telegram в режиме webhook."""
    settings = BotSettings.load()

    if not settings.token or not settings.is_enabled or settings.mode != BotSettings.MODE_WEBHOOK:
        return HttpResponseForbidden("bot disabled")
    if secret_path != settings.secret_path:
        return HttpResponseForbidden("bad path")
    if request.headers.get(SECRET_HEADER) != settings.secret_token:
        return HttpResponseForbidden("bad secret")

    bot = get_bot(settings.token)
    if bot is None:
        return HttpResponseForbidden("no bot")

    try:
        update = telebot.types.Update.de_json(request.body.decode("utf-8"))
    except Exception:  # noqa: BLE001
        return HttpResponseBadRequest("bad update")

    try:
        bot.process_new_updates([update])
    except Exception:  # noqa: BLE001
        logger.exception("tgbot: ошибка обработки webhook-обновления")

    return HttpResponse("ok")
