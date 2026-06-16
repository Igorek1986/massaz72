from django.db.models import Avg, Count
from django.shortcuts import render
from main.models import Certificate
from services.models import Massage

from .models import SiteSettings


def home_context(request, review_form=None):
    """Контекст главной страницы. Вынесен отдельно, чтобы view приёма отзывов
    мог перерисовать главную с заполненной формой при ошибке валидации."""
    from reviews.forms import ReviewForm
    from reviews.models import Review

    site_settings = SiteSettings.objects.first()
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

    online_booking_enabled = bool(site_settings and site_settings.online_booking_enabled)
    reviews_enabled = bool(site_settings and site_settings.reviews_enabled)
    reviews = review_stats = None
    if reviews_enabled:
        reviews = Review.objects.public()
        review_stats = reviews.aggregate(avg=Avg("rating"), total=Count("id"))

    context = {
        "site_settings": site_settings,
        "child_massages": child_massages,
        "adult_massages": adult_massages,
        "certificates": certificates,
        "has_upcoming_prices": has_upcoming_prices,
        "online_booking_enabled": online_booking_enabled,
        "reviews_enabled": reviews_enabled,
        "reviews": reviews,
        "review_stats": review_stats,
        "review_form": review_form if review_form is not None else ReviewForm(),
    }
    return context


def index(request):
    return render(request, "main/index.html", context=home_context(request))


def cookies(request):
    return render(request, "main/cookies.html")


def privacy(request):
    return render(request, "main/privacy.html")


def personal_data(request):
    return render(request, "main/personal_data.html")


def custom_404(request, exception):
    """Обработчик ошибки 404"""
    return render(request, "errors/404.html", status=404)


def custom_500(request):
    """Обработчик ошибки 500"""
    return render(request, "errors/500.html", status=500)
