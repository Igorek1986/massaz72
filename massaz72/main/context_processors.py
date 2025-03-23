from datetime import datetime
from django.conf import settings
from .models import About


def common_context(request):
    about = About.objects.filter(is_active=True).first()
    return {
        "telegram_username": settings.TELEGRAM_USERNAME,
        "whatsapp_number": settings.WHATSAPP_NUMBER,
        "year": datetime.now().year,
        'about': about,
    }
