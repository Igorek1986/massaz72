import logging

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

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
        review: Review = form.save(commit=False)
        review.ip_address = ip
        review.status = Review.Status.PENDING
        review.save()
        _notify_admins(review)
        return _redirect_to_reviews("ok")

    # Ошибки валидации — перерисовываем главную с заполненной формой.
    from main.views import home_context

    context = home_context(request, review_form=form)
    return render(request, "main/index.html", context)
