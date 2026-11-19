from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_GET, require_POST

from accounts.erasure import complete_account_erasure, erasure_scope
from accounts.models import AccountErasureRequest
from accounts.permissions import ERASURE_PERMISSION


@require_GET
@never_cache
@login_required
@permission_required(ERASURE_PERMISSION, raise_exception=True)
def erasure_requests(request):
    return _render_requests(request)


@require_POST
@never_cache
@login_required
@permission_required(ERASURE_PERMISSION, raise_exception=True)
@sensitive_post_parameters("erasure_scope")
def process_erasure(request, pk):
    get_object_or_404(AccountErasureRequest, pk=pk)
    if request.POST.get("confirmed") != "on":
        return _render_requests(request, "Подтвердите проверку перед удалением.", status=400)
    try:
        complete_account_erasure(pk, request.POST.get("erasure_scope", ""))
    except ValidationError as error:
        return _render_requests(request, error.messages[0], status=409)
    return redirect("cabinet:erasure_requests")


def _render_requests(request, error=None, status=200):
    pending = AccountErasureRequest.objects.filter(
        completed_at__isnull=True,
    ).select_related("user").order_by("created_at", "pk")
    for item in pending:
        item.scope = erasure_scope(item.user)
        if item.scope is not None:
            item.confirmation = item.scope.confirmation(item.pk)
    return render(request, "cabinet/erasure_requests.html", {
        "erasure_requests": pending,
        "erasure_error": error,
    }, status=status)
