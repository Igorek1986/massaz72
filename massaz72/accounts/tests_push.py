import json
import tempfile
from datetime import time, timedelta
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

import http_ece
import requests
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.sessions.models import Session
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client as Browser
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from booking.models import BookingRequest
from booking.services import confirm_booking, decline_booking
from cabinet.models import Specialist
from main.models import SiteSettings
from tgbot.notifications import notify_new_booking

from . import push_delivery, web_push
from .models import AccountErasureRequest, Client, PushDelivery, PushSubscription

Kind = PushDelivery.Kind
User = get_user_model()
SUBJECT = "https://example.test"
VAPID = web_push.encode_key(
    ec.generate_private_key(ec.SECP256R1()).private_numbers().private_value.to_bytes(32, "big"),
)


def client_keys():
    private = ec.generate_private_key(ec.SECP256R1())
    point = private.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    return private, {"auth": web_push.encode_key(bytes(16)), "p256dh": web_push.encode_key(point)}


@override_settings(WEB_PUSH_VAPID_PRIVATE_KEY=VAPID, WEB_PUSH_VAPID_SUBJECT=SUBJECT)
class PushTransportTest(SimpleTestCase):
    def test_encrypts_payload_and_disables_redirects(self):
        private, keys = client_keys()
        endpoint = "https://web.push.apple.com/synthetic"
        subscription = Mock(endpoint=endpoint, **keys)
        vapid, _, subject = web_push.config()
        response = requests.Response()
        response.status_code = 201
        response._content = b""
        with patch("requests.Session.post", return_value=response) as post:
            self.assertEqual(web_push.send(subscription, Kind.TEST, vapid, subject, 60), 201)
        self.assertFalse(post.call_args.kwargs["allow_redirects"])
        self.assertEqual(post.call_args.args, (endpoint,))
        self.assertTrue(post.call_args.kwargs["headers"]["Authorization"].startswith("vapid "))
        message = http_ece.decrypt(
            post.call_args.kwargs["data"], private_key=private, auth_secret=bytes(16),
        )
        self.assertEqual(json.loads(message), {"kind": "test"})

    def test_refuses_non_apple_endpoints_and_handles_provider_errors(self):
        _, keys = client_keys()
        subscription = Mock(endpoint="https://web.push.apple.com/synthetic", **keys)
        vapid, _, subject = web_push.config()
        with patch("requests.Session.post", side_effect=requests.Timeout):
            self.assertEqual(web_push.send(subscription, Kind.TEST, vapid, subject, 60), 0)
        response = requests.Response()
        response.status_code = 410
        response._content = b""
        with patch("requests.Session.post", return_value=response):
            self.assertEqual(web_push.send(subscription, Kind.TEST, vapid, subject, 60), 410)
        subscription.endpoint = "https://example.test/synthetic"
        with patch("requests.Session.post") as post:
            self.assertEqual(web_push.send(subscription, Kind.TEST, vapid, subject, 60), 400)
        post.assert_not_called()

    def test_worker_is_root_scoped_and_never_caches_account_pages(self):
        response = self.client.get("/service-worker.js")
        self.assertEqual(response.status_code, 200)
        self.assertIn("javascript", response.headers["Content-Type"])
        self.assertEqual(response.headers["Cache-Control"], "no-cache")
        self.assertContains(response, "showNotification")
        self.assertContains(response, reverse("cabinet:booking_requests"))
        self.assertContains(response, reverse("admin:booking_bookingrequest_changelist"))
        self.assertContains(response, reverse("cabinet:erasure_requests"))
        self.assertNotContains(response, "caches.open")
        self.assertEqual(self.client.post("/service-worker.js").status_code, 405)

    def test_generates_key_without_printing_or_overwriting_it(self):
        with tempfile.TemporaryDirectory() as directory:
            key_file = Path(directory) / ".env.web-push"
            output = StringIO()
            call_command("generate_push_key", str(key_file), stdout=output)
            self.assertEqual(key_file.stat().st_mode & 0o777, 0o600)
            key = key_file.read_text().strip().split("=", 1)[1]
            self.assertTrue(bool(web_push._vapid_config(key, SUBJECT)))
            self.assertFalse(key in output.getvalue())
            with self.assertRaises(CommandError):
                call_command("generate_push_key", str(key_file), stdout=output)
            self.assertTrue(key in key_file.read_text())


@override_settings(WEB_PUSH_VAPID_PRIVATE_KEY=VAPID, WEB_PUSH_VAPID_SUBJECT=SUBJECT)
class PushWorkflowTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.site = SiteSettings.objects.create(client_cabinet_enabled=True)
        cls.customer = User.objects.create_user(username="push-customer")
        Client.objects.create(user=cls.customer)
        cls.head = Specialist.objects.create(
            name="Руководитель", user=User.objects.create_user(username="push-head"),
        )
        cls.specialist = Specialist.objects.create(
            name="Мастер", user=User.objects.create_user(username="push-specialist"), head=cls.head,
        )
        cls.other = Specialist.objects.create(
            name="Другой", user=User.objects.create_user(username="push-other"),
        )

    def setUp(self):
        self.url = reverse("pwa-subscription")
        self.client.force_login(self.customer)
        _, keys = client_keys()
        self.web_subscription = {"endpoint": "https://web.push.apple.com/synthetic", "keys": keys}

    def post(self, browser=None, action="subscribe", **data):
        return (browser or self.client).post(
            self.url, {"action": action, **data}, content_type="application/json",
        )

    def subscribe(self, browser=None, suffix="synthetic", device=None):
        payload = {**self.web_subscription, "endpoint": f"https://web.push.apple.com/{suffix}"}
        self.assertEqual(self.post(browser, consent=True, subscription=payload, device=device).status_code, 200)
        return PushSubscription.objects.get(endpoint=payload["endpoint"])

    def booking(self, **fields):
        return BookingRequest.objects.create(
            preferred_date=timezone.localdate() + timedelta(days=1),
            preferred_time=time(10), **fields,
        )

    def test_enrollment_requires_auth_csrf_consent_and_eligible_role(self):
        self.assertEqual(Browser().get(self.url).status_code, 403)
        self.assertEqual(Browser().post(self.url).status_code, 403)
        strict = Browser(enforce_csrf_checks=True)
        strict.force_login(self.customer)
        self.assertContains(strict.get(reverse("accounts:profile")), 'name="csrfmiddlewaretoken"')
        self.assertEqual(self.post(strict, consent=True, subscription=self.web_subscription).status_code, 403)
        response = strict.post(
            self.url,
            {"action": "subscribe", "consent": True, "subscription": self.web_subscription},
            content_type="application/json", headers={"X-CSRFToken": strict.cookies["csrftoken"].value},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.post(subscription=self.web_subscription).status_code, 400)
        outsider = Browser()
        outsider.force_login(User.objects.create_user(username="push-no-role"))
        self.assertEqual(self.post(outsider, consent=True, subscription=self.web_subscription).status_code, 403)
        with self.settings(WEB_PUSH_VAPID_PRIVATE_KEY=""):
            self.assertEqual(self.post(consent=True, subscription=self.web_subscription).status_code, 503)
        self.assertEqual(PushSubscription.objects.count(), 1)

    def test_status_distinguishes_missing_configuration_from_ineligible_account(self):
        available = self.client.get(self.url)
        self.assertTrue(available.json()["configured"])
        self.assertTrue(bool(available.json()["key"]))
        self.assertIn("no-store", available.headers["Cache-Control"])

        self.client.force_login(User.objects.create_user(username="push-unassigned-admin", is_staff=True))
        self.assertEqual(self.client.get(self.url).json(), {"configured": True, "key": "", "active": False})

        with self.settings(WEB_PUSH_VAPID_PRIVATE_KEY=""):
            self.assertEqual(self.client.get(self.url).json(), {"configured": False, "key": "", "active": False})

    def test_admin_without_specialist_can_open_settings_and_subscribe(self):
        url = reverse("accounts:notifications")
        guest = Browser()
        self.assertRedirects(guest.get(url), f"{reverse('accounts:login')}?next={url}")
        self.assertContains(self.client.get(url), "Устройства с push")

        admin = User.objects.create_superuser(username="push-admin")
        self.client.force_login(admin)
        page = self.client.get(url)
        self.assertContains(page, "data-push-url", count=1)
        self.assertContains(page, f'href="{url}"', count=2)
        self.assertIn("no-store", page.headers["Cache-Control"])
        self.assertEqual(self.client.post(url).status_code, 405)
        self.assertTrue(bool(self.client.get(self.url).json()["key"]))
        subscription = self.subscribe()
        self.assertEqual(subscription.user_id, admin.pk)
        self.assertEqual(self.post(action="test").status_code, 202)

    def test_device_list_marks_current_subscription_and_revokes_only_the_owners_device(self):
        mine = self.subscribe(device="iphone")
        tablet_browser = Browser()
        tablet_browser.force_login(self.customer)
        tablet = self.subscribe(tablet_browser, "tablet", device="ipad")
        expired_browser = Browser()
        expired_browser.force_login(self.customer)
        expired = self.subscribe(expired_browser, "expired")
        Session.objects.filter(pk=expired.session_id).update(expire_date=timezone.now())
        other_browser = Browser()
        other_browser.force_login(self.other.user)
        other = self.subscribe(other_browser, "someone-else", device="unsupported")
        self.assertEqual(other.device, PushSubscription.Device.UNKNOWN)

        url = reverse("accounts:notifications")
        page = self.client.get(url)
        self.assertCountEqual([device.pk for device in page.context["push_devices"]], [mine.pk, tablet.pk])
        self.assertContains(page, "iPhone · Это устройство", count=1)
        self.assertContains(page, "iPad")
        self.assertFalse(tablet.endpoint.encode() in page.content)
        self.assertFalse(tablet.session_id.encode() in page.content)
        revoke = reverse("accounts:revoke_push_device", args=[tablet.pk])
        self.assertEqual(self.client.get(revoke).status_code, 405)
        self.assertIn("/login/", Browser().post(revoke)["Location"])
        self.assertEqual(other_browser.post(revoke).status_code, 404)
        strict = Browser(enforce_csrf_checks=True)
        strict.force_login(self.customer)
        self.assertEqual(strict.post(revoke).status_code, 403)
        self.assertEqual(self.post(tablet_browser, action="test").status_code, 202)
        self.assertRedirects(self.client.post(revoke), url)
        self.assertFalse(PushSubscription.objects.filter(pk=tablet.pk).exists())
        self.assertFalse(PushDelivery.objects.filter(subscription_id=tablet.pk).exists())
        self.assertTrue(PushSubscription.objects.filter(pk=other.pk).exists())
        self.assertTrue(self.client.get(self.url).json()["active"])

    def test_new_bookings_reach_admins_with_permissions_and_stop_after_revocation(self):
        view = Permission.objects.get(content_type__app_label="booking", codename="view_bookingrequest")
        change = Permission.objects.get(content_type__app_label="booking", codename="change_bookingrequest")
        group = Group.objects.create(name="Push test booking readers")
        group.permissions.add(view)
        reader = User.objects.create_user(username="booking-reader", is_staff=True)
        editor = User.objects.create_user(username="booking-editor", is_staff=True)
        outsider = User.objects.create_user(username="booking-nonstaff")
        reader.groups.add(group)
        editor.user_permissions.add(change)
        outsider.user_permissions.add(view)
        reader_browser = Browser()
        reader_browser.force_login(reader)
        reader_device = self.subscribe(reader_browser, suffix="reader")
        editor_browser = Browser()
        editor_browser.force_login(editor)
        editor_device = self.subscribe(editor_browser, suffix="editor")
        self.client.force_login(outsider)
        self.assertFalse(self.client.get(self.url).json()["key"])
        self.assertEqual(self.client.get(reverse("accounts:notifications")).status_code, 403)

        booking = self.booking(specialist=self.specialist)
        with self.captureOnCommitCallbacks(execute=True):
            push_delivery.queue_booking(booking, Kind.NEW_BOOKING)
        self.assertCountEqual(
            PushDelivery.objects.values_list("subscription_id", flat=True),
            [reader_device.pk, editor_device.pk],
        )
        reader.groups.remove(group)
        with patch("accounts.push_delivery.is_open", return_value=True), patch("accounts.web_push.send", return_value=201) as send:
            push_delivery.flush()
        send.assert_called_once()
        self.assertEqual(send.call_args.args[:2], (editor_device, "new_booking_admin"))
        self.assertFalse(PushDelivery.objects.exists())

    def test_promotion_on_first_launch_and_dashboard_for_both_roles(self):
        marker = "data-push-promotion hidden"
        home = reverse("main:index")
        guest = Browser().get(home)
        self.assertContains(guest, marker)
        self.assertContains(guest, "После входа вы сможете включить уведомления о записи.")
        self.assertNotContains(guest, "data-push-url")
        self.assertNotContains(guest, "data-push-login-dialog")
        with self.settings(WEB_PUSH_VAPID_PRIVATE_KEY=""):
            self.assertNotContains(Browser().get(home), marker)

        for url in (home, reverse("accounts:dashboard")):
            response = self.client.get(url)
            self.assertContains(response, marker, count=1)
            self.assertContains(response, "data-push-url", count=1)
            self.assertContains(response, "data-push-login-dialog", count=1)

        self.client.force_login(self.specialist.user)
        self.assertContains(self.client.get(reverse("cabinet:index")), marker, count=1)
        self.assertNotContains(self.client.get(reverse("cabinet:settings")), marker)

    def test_both_sign_in_pages_mark_the_form_for_push_offer_after_login(self):
        for name in ("accounts:login", "cabinet:login"):
            with self.subTest(name=name):
                self.assertContains(Browser().get(reverse(name)), "data-push-login-form", count=1)

    def test_rejects_unsafe_endpoints_and_bad_keys(self):
        urls = [
            "http://web.push.apple.com/path",
            "https://web.push.apple.com.example.test/path",
            "https://web.push.apple.com@localhost/path",
            "https://web.push.apple.com:444/path",
            "https://web.push.apple.com/path?query",
            "https://127.0.0.1/path",
        ]
        for url in urls:
            with self.subTest(url=url):
                data = {**self.web_subscription, "endpoint": url}
                self.assertEqual(self.post(consent=True, subscription=data).status_code, 400)
        self.assertEqual(self.post(consent=True, subscription={**self.web_subscription, "keys": {}}).status_code, 400)
        self.assertEqual(self.client.post(self.url, " " * 4097, content_type="application/json").status_code, 400)
        self.assertFalse(PushSubscription.objects.exists())

    def test_binding_is_per_session_and_logout_clears_it(self):
        enrolled = self.subscribe()
        self.assertEqual(self.subscribe().pk, enrolled.pk)
        self.assertTrue(self.client.get(self.url).json()["active"])
        second = Browser()
        second.force_login(self.other.user)
        self.assertEqual(self.post(second, consent=True, subscription=self.web_subscription).status_code, 409)
        self.assertEqual(self.post(second, action="unsubscribe").status_code, 200)
        self.assertTrue(PushSubscription.objects.filter(pk=enrolled.pk).exists())
        other_device = self.subscribe(second, "other-device")
        self.assertEqual(self.post(action="test").status_code, 202)
        self.assertEqual(self.post(action="test").status_code, 429)
        self.client.post(reverse("accounts:logout"))
        self.assertEqual(list(PushSubscription.objects.values_list("pk", flat=True)), [other_device.pk])
        self.assertFalse(PushDelivery.objects.exists())

    def test_erasure_revokes_push(self):
        self.subscribe()
        self.post(action="test")
        self.client.post(reverse("accounts:request_account_erasure"), {"confirm_erasure": "on"})
        self.assertFalse(PushSubscription.objects.exists())
        self.assertFalse(PushDelivery.objects.exists())

    def test_erasure_push_requires_permission_and_ignores_specialist_activity(self):
        submit = reverse("accounts:request_account_erasure")
        group = Group.objects.get(name="Ответственный за удаление ПД")
        operator = User.objects.create_user(username="push-erasure-operator")
        operator.groups.add(group)
        self.specialist.user.groups.add(group)
        self.specialist.is_active = False
        self.specialist.save(update_fields=["is_active"])

        devices = {}
        for recipient, label in (
            (operator, "operator"), (self.specialist.user, "inactive-profile"),
            (self.other.user, "other-specialist"),
        ):
            browser = Browser()
            browser.force_login(recipient)
            devices[label] = self.subscribe(browser, label)
            if recipient == operator:
                self.assertContains(browser.get(reverse("accounts:notifications")), "Запросы на удаление ПД")

        with self.captureOnCommitCallbacks(execute=True):
            for _ in range(2):
                self.assertEqual(self.client.post(submit, {"confirm_erasure": "on"}).status_code, 302)
        request = AccountErasureRequest.objects.get(user=self.customer)
        self.assertCountEqual(
            PushDelivery.objects.values_list("subscription_id", "kind", "erasure_request_id"),
            [(devices[label].pk, Kind.ERASURE_REQUEST, request.pk) for label in ("operator", "inactive-profile")],
        )
        operator.groups.remove(group)
        with patch("accounts.web_push.send", return_value=201) as send:
            push_delivery.flush()
        send.assert_called_once()
        self.assertEqual(send.call_args.args[:2], (devices["inactive-profile"], Kind.ERASURE_REQUEST))
        self.assertFalse(PushDelivery.objects.exists())

    def test_erasure_push_is_discarded_if_request_already_processed(self):
        operator = User.objects.create_superuser(username="push-erasure-admin")
        browser = Browser()
        browser.force_login(operator)
        self.subscribe(browser)
        submit = reverse("accounts:request_account_erasure")
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.post(submit, {"confirm_erasure": "on"}).status_code, 302)
        self.assertTrue(PushDelivery.objects.filter(kind=Kind.ERASURE_REQUEST).exists())
        AccountErasureRequest.objects.update(completed_at=timezone.now())
        with patch("accounts.web_push.send") as send:
            push_delivery.flush()
        send.assert_not_called()
        self.assertFalse(PushDelivery.objects.exists())

    def test_new_booking_targets_specialist_and_head_and_is_queued_once(self):
        self.subscribe()
        expected = []
        for specialist in (self.head, self.specialist, self.other):
            browser = Browser()
            browser.force_login(specialist.user)
            subscription = self.subscribe(browser, f"device-{specialist.pk}")
            if specialist != self.other:
                expected.append(subscription.pk)
        booking = self.booking(specialist=self.specialist, source=BookingRequest.Source.BOT)
        with patch("tgbot.notify.notify"), self.captureOnCommitCallbacks(execute=True):
            notify_new_booking(booking)
            notify_new_booking(booking)
        self.assertCountEqual(
            PushDelivery.objects.values_list("subscription_id", "kind"),
            [(pk, Kind.NEW_BOOKING) for pk in expected],
        )

    def test_status_updates_queue_only_for_clients_own_account_booking(self):
        customer = self.subscribe()
        outsider = Browser()
        outsider.force_login(self.specialist.user)
        self.subscribe(outsider, "specialist")
        owned = self.booking(user=self.customer, source=BookingRequest.Source.ACCOUNT, specialist=self.specialist)
        guest = self.booking(user=self.customer, specialist=self.specialist)
        another = self.booking(user=self.customer, source=BookingRequest.Source.ACCOUNT)
        with self.captureOnCommitCallbacks(execute=True):
            confirm_booking(owned)
            decline_booking(guest)
            decline_booking(another)
            decline_booking(another)
        self.assertCountEqual(PushDelivery.objects.values_list("subscription_id", "booking_id", "kind"), [
            (customer.pk, owned.pk, Kind.BOOKING_CONFIRMED),
            (customer.pk, another.pk, Kind.BOOKING_DECLINED),
        ])
        with patch("accounts.web_push.send", return_value=201) as send, patch(
            "accounts.push_delivery.is_open", return_value=True,
        ):
            push_delivery.flush()
        self.assertEqual(send.call_count, 2)
        self.assertFalse(PushDelivery.objects.exists())

    def test_quiet_hours_stale_booking_and_expired_subscription(self):
        browser = Browser()
        browser.force_login(self.specialist.user)
        subscription = self.subscribe(browser)
        booking = self.booking(specialist=self.specialist)
        with self.captureOnCommitCallbacks(execute=True):
            push_delivery.queue_booking(booking, Kind.NEW_BOOKING)
        now = timezone.localtime().replace(hour=3)
        PushDelivery.objects.update(available_at=now)
        with patch("accounts.web_push.send") as send, patch("accounts.push_delivery.timezone.now", return_value=now):
            push_delivery.flush()
            send.assert_not_called()
        queued = PushDelivery.objects.get()
        self.assertGreater(queued.available_at, now)
        booking.status = BookingRequest.Status.CANCELLED
        booking.save()
        PushDelivery.objects.update(available_at=timezone.now())
        with patch("accounts.web_push.send") as send:
            push_delivery.flush()
            send.assert_not_called()
        self.assertFalse(PushDelivery.objects.exists())
        Session.objects.filter(pk=subscription.session_id).update(expire_date=timezone.now())
        push_delivery.flush()
        self.assertFalse(PushSubscription.objects.exists())

    def test_retries_transient_failure_and_discards_gone_device(self):
        enrolled = self.subscribe()
        self.assertEqual(self.post(action="test").status_code, 202)
        with patch("accounts.web_push.send", return_value=503):
            push_delivery.flush()
        queued = PushDelivery.objects.get()
        self.assertEqual(queued.attempts, 1)
        self.assertGreater(queued.available_at, timezone.now())
        PushDelivery.objects.update(available_at=timezone.now())
        with patch("accounts.web_push.send", return_value=410):
            push_delivery.flush()
        self.assertFalse(PushDelivery.objects.exists())
        self.assertFalse(PushSubscription.objects.filter(pk=enrolled.pk).exists())
