from django.shortcuts import render
from main.models import Certificate
from services.models import Massage

from .models import SiteSettings


def index(request):
    # about = About.objects.first()
    child_massages = Massage.objects.filter(
        massage_type=Massage.CHILD, is_archived=False
    )
    adult_massages = Massage.objects.filter(
        massage_type=Massage.ADULT, is_archived=False
    )
    certificates = Certificate.objects.filter(is_archived=False).order_by("order")

    # Есть ли массажи с запланированной новой ценой (для плашки об изменении цен)
    has_upcoming_prices = Massage.objects.filter(
        is_archived=False, new_price__isnull=False
    ).exists()

    context = {
        # 'about': about,
        "site_settings": SiteSettings.objects.first(),
        "child_massages": child_massages,
        "adult_massages": adult_massages,
        "certificates": certificates,
        "has_upcoming_prices": has_upcoming_prices,
        # 'banner': MainBanner.objects.first(),
    }
    return render(request, "main/index.html", context=context)


def cookies(request):
    return render(request, "main/cookies.html")


def privacy(request):
    return render(request, "main/privacy.html")


def custom_404(request, exception):
    """Обработчик ошибки 404"""
    return render(request, "errors/404.html", status=404)


def custom_500(request):
    """Обработчик ошибки 500"""
    return render(request, "errors/500.html", status=500)
