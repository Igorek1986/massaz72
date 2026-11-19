from django.utils.cache import add_never_cache_headers


PREVIEW_PAGES = {
    "main:index": "Главная",
    "main:privacy": "Политика обработки данных",
    "main:consent": "Согласие на обработку данных",
    "main:cookies": "Файлы cookie",
    "booking:page": "Онлайн-запись",
    "accounts:login": "Вход",
    "accounts:register": "Регистрация",
    "accounts:password_reset": "Сброс пароля",
    "services:massage_detail": "Страница услуги",
}


class SiteDesignPreviewMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def process_view(self, request, view_func, view_args, view_kwargs):
        if (
            request.method == "GET"
            and request.GET.get("design_preview") == "1"
            and request.resolver_match.view_name in PREVIEW_PAGES
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
