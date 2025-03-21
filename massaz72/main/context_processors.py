from datetime import datetime
from django.conf import settings


def common_context(request):
    return {
        "telegram_username": settings.TELEGRAM_USERNAME,
        "whatsapp_number": settings.WHATSAPP_NUMBER,
        "year": datetime.now().year,
    }
