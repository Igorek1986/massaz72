from django.http import HttpResponse
from django.template.loader import render_to_string
from django.views.decorators.http import require_safe


@require_safe
def service_worker(request):
    response = HttpResponse(
        render_to_string("main/service-worker.js"), content_type="text/javascript; charset=utf-8",
    )
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response
