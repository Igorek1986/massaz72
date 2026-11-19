import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.appointments import has_completed_appointment
from accounts.models import AccountErasureRequest
from main.models import SiteSettings

from .forms import ReviewForm
from .models import Review
from .spam import is_rate_limited, timing_is_human

logger = logging.getLogger(__name__)


def _notify_admins(review: Review) -> None:
    """Шлёт уведомление админам в Telegram. Никогда не ломает отправку отзыва."""
    try:
        from tgbot.notifications import notify_new_review

        notify_new_review(review)
    except Exception:  # noqa: BLE001
        logger.exception("Не удалось уведомить админов об отзыве %s", review.pk)


def get_client_ip(request: HttpRequest) -> str | None:
    """IP клиента: левый адрес из X-Forwarded-For (за nginx) либо REMOTE_ADDR."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _redirect_to_reviews(flag: str) -> HttpResponse:
    return redirect(f"{reverse('main:index')}?review={flag}#reviews")


def _reviews_enabled() -> bool:
    settings_obj = SiteSettings.objects.first()
    return bool(settings_obj and settings_obj.reviews_enabled)


@require_POST
def create(request: HttpRequest) -> HttpResponse:
    # Отзывы выключены в настройках сайта — форму не принимаем.
    if not _reviews_enabled():
        return redirect(reverse("main:index"))

    if not has_completed_appointment(request.user):
        return _redirect_to_reviews("visit_required")

    # Honeypot и time-trap: для ботов делаем вид, что всё прошло успешно,
    # чтобы не подсказывать им, как обойти защиту, и ничего не сохраняем.
    if request.POST.get("website"):
        return _redirect_to_reviews("ok")
    if not timing_is_human(request.POST.get("ts", "")):
        return _redirect_to_reviews("ok")

    # Троттлинг по IP — это уже легитимный пользователь, говорим прямо.
    ip = get_client_ip(request)
    if is_rate_limited(ip):
        return _redirect_to_reviews("throttled")

    form = ReviewForm(request.POST)
    if form.is_valid():
        with transaction.atomic():
            author = get_user_model().objects.select_for_update().filter(pk=request.user.pk).first()
            if not author or AccountErasureRequest.objects.filter(user=author).exists():
                return _redirect_to_reviews("visit_required")
            review: Review = form.save(commit=False)
            review.author = author
            review.name = "Клиент"
            review.ip_address = ip
            review.consent_at = timezone.now()
            review.status = Review.Status.PENDING
            review.save()
        _notify_admins(review)
        return _redirect_to_reviews("ok")

    # Ошибки валидации — перерисовываем главную с заполненной формой.
    from main.views import home_context

    context = home_context(request, review_form=form)
    return render(request, "main/index.html", context)
