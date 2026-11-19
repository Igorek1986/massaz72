"""Конфигурация Web Push и доставка через Apple Push Notification service."""

import base64
import binascii
import json
import logging
import re
from functools import lru_cache
from urllib.parse import urlsplit

import requests
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from django.conf import settings
from py_vapid import Vapid
from pywebpush import WebPushException, webpush

logger = logging.getLogger(__name__)

ENDPOINT = re.compile(
    r"https://(?:[a-z0-9-]+\.)+push\.apple\.com/[A-Za-z0-9._~/%=+:-]+",
    re.ASCII,
)
KEY = re.compile(r"[A-Za-z0-9_-]+")
AUTH_LENGTH = 16
P256_LENGTH = 65


def encode_key(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def decode_key(value, size):
    if not isinstance(value, str) or not KEY.fullmatch(value):
        raise ValueError("Некорректный ключ")
    raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    if len(raw) != size or encode_key(raw) != value:
        raise ValueError("Некорректный ключ")
    return raw


def public_key(vapid):
    return encode_key(vapid.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint))


@lru_cache(maxsize=2)
def _vapid_config(private_key, subject):
    if not private_key or not subject:
        return None
    try:
        url = urlsplit(subject)
        if (
            url.scheme != "https" or not url.hostname
            or url.username or url.password or url.query or url.fragment
            or url.hostname in {"localhost", "127.0.0.1", "::1"}
        ):
            raise ValueError("Некорректный адрес VAPID")
        scalar = int.from_bytes(decode_key(private_key, 32), "big")
        vapid = Vapid(ec.derive_private_key(scalar, ec.SECP256R1()))
        return vapid, public_key(vapid), subject
    except (ValueError, binascii.Error):
        logger.warning("Web Push отключён. Проверьте параметры VAPID.")
        return None


def config():
    return _vapid_config(settings.WEB_PUSH_VAPID_PRIVATE_KEY, settings.WEB_PUSH_VAPID_SUBJECT)


def allowed_endpoint(value):
    return isinstance(value, str) and len(value) <= 2048 and bool(ENDPOINT.fullmatch(value))


def validate_subscription(data):
    if not isinstance(data, dict) or not allowed_endpoint(data.get("endpoint")):
        raise ValueError("Некорректный адрес подписки")
    keys = data.get("keys")
    if not isinstance(keys, dict):
        raise ValueError("Некорректная подписка")
    auth, p256dh = keys.get("auth"), keys.get("p256dh")
    decode_key(auth, AUTH_LENGTH)
    point = decode_key(p256dh, P256_LENGTH)
    if point[0] != 4:
        raise ValueError("Некорректный открытый ключ")
    ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), point)
    return {"endpoint": data["endpoint"], "auth": auth, "p256dh": p256dh}


class AppleSession(requests.Session):
    def __init__(self):
        super().__init__()
        self.trust_env = False

    def post(self, url, *args, **kwargs):
        if not allowed_endpoint(url):
            raise ValueError("Недопустимый адрес доставки")
        return super().post(url, *args, **kwargs, allow_redirects=False)


def send(subscription, kind, vapid, subject, ttl):
    """Возвращает HTTP-статус APNs, либо 0 при сетевом сбое."""
    try:
        with AppleSession() as session:
            response = webpush(
                subscription_info={
                    "endpoint": subscription.endpoint,
                    "keys": {"auth": subscription.auth, "p256dh": subscription.p256dh},
                },
                data=json.dumps({"kind": kind}),
                vapid_private_key=vapid,
                vapid_claims={"sub": subject},
                requests_session=session,
                timeout=5,
                ttl=ttl,
            )
        return response.status_code
    except WebPushException as exc:
        return 0 if exc.response is None else exc.response.status_code
    except requests.RequestException:
        return 0
    except (ValueError, binascii.Error):
        return 400
