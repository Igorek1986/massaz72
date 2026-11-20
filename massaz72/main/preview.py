from collections.abc import Callable
from dataclasses import dataclass
from datetime import time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.cache import add_never_cache_headers
from django.views.decorators.http import require_GET

from accounts.forms import ProfileForm
from services.models import Massage


@dataclass(frozen=True)
class PreviewPage:
    title: str
    sample_template: str = ""
    sample_context: Callable[[], dict] = dict


def _profile_sample():
    password_form = PasswordChangeForm(get_user_model()())
    password_form.fields["old_password"].widget.attrs.pop("autofocus", None)
    return {
        "profile_form": ProfileForm(),
        "password_form": password_form,
        "can_request_erasure": True,
    }


def _new_password_sample():
    return {"form": SetPasswordForm(get_user_model()())}


def _booking_sample():
    return {
        "state": "awaiting",
        "booking": {
            "preferred_date": timezone.localdate() + timedelta(days=1),
            "preferred_time": time(12),
        },
    }


def _service_sample():
    return {"massage": Massage(
        name="Пример услуги",
        description="Описание массажной услуги",
        price=Decimal("1500"),
        duration_min=30,
        duration_max=45,
        location="В кабинете",
    )}


PREVIEW_PAGES = {
    "main:index": PreviewPage("Главная"),
    "main:privacy": PreviewPage("Политика обработки данных"),
    "main:consent": PreviewPage("Согласие на обработку данных"),
    "main:cookies": PreviewPage("Файлы cookie"),
    "booking:page": PreviewPage("Онлайн-запись"),
    "booking:confirm": PreviewPage("Подтверждение записи", "booking/confirm.html", _booking_sample),
    "accounts:login": PreviewPage("Вход"),
    "accounts:register": PreviewPage("Регистрация"),
    "accounts:password_reset": PreviewPage("Сброс пароля"),
    "accounts:password_reset_confirm": PreviewPage(
        "Новый пароль", "accounts/password_reset_confirm.html", _new_password_sample,
    ),
    "accounts:dashboard": PreviewPage("Личный кабинет клиента", "accounts/dashboard.html"),
    "accounts:profile": PreviewPage("Профиль клиента", "accounts/profile.html", _profile_sample),
    "accounts:notifications": PreviewPage("Уведомления", "accounts/notifications.html"),
    "services:massage_detail": PreviewPage("Страница услуги", "services/massage_detail.html", _service_sample),
    "404": PreviewPage("Страница не найдена (404)", "errors/404.html"),
    "500": PreviewPage("Ошибка сервера (500)", "errors/500.html"),
}


def preview_page_urls():
    for route, page in PREVIEW_PAGES.items():
        if route == "services:massage_detail":
            slug = (
                Massage.objects.filter(is_archived=False, slug__isnull=False)
                .exclude(slug="").order_by("name", "pk").values_list("slug", flat=True).first()
            )
            if slug:
                yield reverse(route, kwargs={"slug": slug}), page.title
                continue
        if page.sample_template:
            yield reverse("cabinet:site_design_sample", kwargs={"page_name": route}), page.title
        else:
            yield reverse(route), page.title


@require_GET
def preview_sample(request, page_name):
    if not getattr(request, "site_design_preview", False):
        raise PermissionDenied
    page = PREVIEW_PAGES.get(page_name)
    if not page or not page.sample_template:
        raise Http404
    return render(request, page.sample_template, page.sample_context())


class SiteDesignPreviewMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def process_view(self, request, view_func, view_args, view_kwargs):
        route = request.resolver_match.view_name
        page = PREVIEW_PAGES.get(route)
        can_preview_route = (
            route == "cabinet:site_design_sample"
            or page and (not page.sample_template or route == "services:massage_detail")
        )
        if (
            request.method == "GET"
            and request.GET.get("design_preview") == "1"
            and can_preview_route
            and request.user.has_perm("main.manage_site_in_cabinet")
            and (request.user.is_superuser or hasattr(request.user, "specialist"))
        ):
            request.site_design_preview = True

    def __call__(self, request):
        response = self.get_response(request)
        if getattr(request, "site_design_preview", False) and response.status_code == 200:
            response.headers["X-Frame-Options"] = "SAMEORIGIN"
            add_never_cache_headers(response)
        return response
