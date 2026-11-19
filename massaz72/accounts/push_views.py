import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_variables
from django.views.decorators.http import require_http_methods

from . import push_delivery, web_push
from .models import PushSubscription

MAX_BODY_BYTES = 4096


@never_cache
@require_http_methods(["GET", "POST"])
@csrf_protect
@sensitive_variables("body", "data", "details")
def subscription(request):
    if not request.user.is_authenticated or not request.session.session_key:
        return JsonResponse({}, status=403)

    current = PushSubscription.objects.filter(
        user=request.user, session_id=request.session.session_key,
    )
    config = web_push.config()
    if request.method == "GET":
        key = config[1] if config and push_delivery.eligible(request.user) else ""
        active = current.filter(vapid_key=key).exists() if key else current.exists()
        return JsonResponse({"key": key, "active": active, "configured": config is not None})

    try:
        body = request.read(MAX_BODY_BYTES + 1)
        if len(body) > MAX_BODY_BYTES:
            return JsonResponse({}, status=400)
        data = json.loads(body)
    except (ValueError, OSError, RecursionError):
        return JsonResponse({}, status=400)
    if not isinstance(data, dict) or request.content_type != "application/json":
        return JsonResponse({}, status=400)

    action = data.get("action")
    if action == "unsubscribe":
        current.delete()
        return JsonResponse({"active": False})
    if action not in ("subscribe", "test"):
        return JsonResponse({}, status=400)
    if not config:
        return JsonResponse({}, status=503)

    now = timezone.now()
    try:
        with transaction.atomic():
            user = get_user_model().objects.select_for_update().filter(pk=request.user.pk).first()
            if user is None or not push_delivery.eligible(user):
                return JsonResponse({}, status=403)
            if action == "test":
                active = current.filter(vapid_key=config[1]).first()
                if active is None:
                    return JsonResponse({}, status=409)
                if active.last_test_at and active.last_test_at > now - timedelta(minutes=1):
                    return JsonResponse({}, status=429)
                active.last_test_at = now
                active.save(update_fields=["last_test_at"])
                push_delivery.queue_test(active, now)
                return JsonResponse({}, status=202)
            if data.get("consent") is not True:
                return JsonResponse({}, status=400)
            details = web_push.validate_subscription(data.get("subscription"))
            device = data.get("device")
            if device in (PushSubscription.Device.IPHONE, PushSubscription.Device.IPAD):
                details["device"] = device
            current.update_or_create(
                user=user, session_id=request.session.session_key,
                defaults={**details, "vapid_key": config[1], "consent_at": now},
            )
    except ValueError:
        return JsonResponse({}, status=400)
    except IntegrityError:
        return JsonResponse({}, status=409)

    return JsonResponse({"active": True})
