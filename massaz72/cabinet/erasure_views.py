from django.contrib.auth.decorators import permission_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from accounts.erasure import complete_account_erasure
from accounts.models import AccountErasureRequest

from .views import specialist_required


@require_GET
@never_cache
@specialist_required
@permission_required("accounts.process_account_erasure", raise_exception=True)
def erasure_requests(request):
    return _render_requests(request)


@require_POST
@never_cache
@specialist_required
@permission_required("accounts.process_account_erasure", raise_exception=True)
def process_erasure(request, pk):
    get_object_or_404(AccountErasureRequest, pk=pk)
    if request.POST.get("confirmed") != "on":
        return _render_requests(request, "Подтвердите проверку перед удалением.", status=400)
    try:
        complete_account_erasure(pk)
    except ValidationError as error:
        return _render_requests(request, error.messages[0], status=409)
    return redirect("cabinet:erasure_requests")


def _render_requests(request, error=None, status=200):
    pending = AccountErasureRequest.objects.filter(
        completed_at__isnull=True,
    ).select_related("user").order_by("created_at", "pk")
    return render(request, "cabinet/erasure_requests.html", {
        "erasure_requests": pending,
        "erasure_error": error,
    }, status=status)
