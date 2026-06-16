"""Анти-спам для публичной формы отзывов (без сторонних сервисов).

Три независимых барьера:
  * honeypot   — скрытое поле, заполняемое только ботами (проверяется во view);
  * time-trap  — подписанный токен с моментом рендера формы; слишком быстрый
                 или просроченный сабмит отбраковывается;
  * throttle   — ограничение числа отзывов с одного IP за окно времени (по БД,
                 чтобы работать корректно при нескольких gunicorn-воркерах).
"""

from datetime import timedelta

from django.core import signing
from django.utils import timezone

# Раньше этого числа секунд после загрузки формы — это бот.
MIN_FILL_SECONDS = 3
# Токен формы старше суток считаем протухшим.
MAX_FORM_AGE_SECONDS = 24 * 60 * 60

# Не больше стольких отзывов с одного IP за окно.
THROTTLE_LIMIT = 3
THROTTLE_WINDOW_SECONDS = 60 * 60

_SALT = "reviews.timing"
_signer = signing.Signer(salt=_SALT)


def make_timestamp_token() -> str:
    """Подписанная метка момента рендера формы (для скрытого поля)."""
    return _signer.sign(str(int(timezone.now().timestamp())))


def timing_is_human(token: str) -> bool:
    """True, если форму заполнил человек: токен валиден, прошло >= MIN_FILL_SECONDS
    и токен не протух."""
    if not token:
        return False
    try:
        issued_at = int(_signer.unsign(token))
    except (signing.BadSignature, ValueError):
        return False
    elapsed = int(timezone.now().timestamp()) - issued_at
    if elapsed < MIN_FILL_SECONDS:
        return False
    if elapsed > MAX_FORM_AGE_SECONDS:
        return False
    return True


def is_rate_limited(ip_address: str | None) -> bool:
    """True, если с этого IP уже оставлено >= THROTTLE_LIMIT отзывов за окно."""
    if not ip_address:
        return False
    from .models import Review

    since = timezone.now() - timedelta(seconds=THROTTLE_WINDOW_SECONDS)
    count = Review.objects.filter(
        ip_address=ip_address, created_at__gte=since
    ).count()
    return count >= THROTTLE_LIMIT
