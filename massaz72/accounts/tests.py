from datetime import time, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Client as ClientProfile
from booking.models import BookingRequest
from main.models import SiteSettings
from services.models import Massage

PWD = "Sup3rSecret!2026"


def future_date():
    return timezone.localdate() + timedelta(days=2)


def make_massage(name="Спина"):
    return Massage.objects.create(
        name=name, price=Decimal("2000"), duration_min=30, duration_max=60,
        location="Кабинет", massage_type=Massage.ADULT, slug=name.lower(),
    )


class RegistrationTest(TestCase):
    def setUp(self):
        self.settings = SiteSettings.objects.create(client_cabinet_enabled=True)

    def test_register_creates_user_and_client(self):
        resp = self.client.post(reverse("accounts:register"), {
            "username": "ivan", "password1": PWD, "password2": PWD,
            "phone": "+70000000000", "consent": "on",
        })
        self.assertRedirects(resp, reverse("accounts:dashboard"))
        user = User.objects.get(username="ivan")
        self.assertTrue(hasattr(user, "client_profile"))
        self.assertEqual(user.client_profile.phone, "+70000000000")

    def test_register_links_past_bookings_by_phone(self):
        booking = BookingRequest.objects.create(
            client_name="Иван", phone="+70000000000",
            preferred_date=future_date(), preferred_time=time(10, 0),
        )
        self.client.post(reverse("accounts:register"), {
            "username": "ivan", "password1": PWD, "password2": PWD,
            "phone": "+70000000000", "consent": "on",
        })
        booking.refresh_from_db()
        self.assertEqual(booking.user, User.objects.get(username="ivan"))

    def test_register_disabled_redirects(self):
        self.settings.client_cabinet_enabled = False
        self.settings.save()
        resp = self.client.get(reverse("accounts:register"))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(User.objects.count(), 0)


class CabinetTest(TestCase):
    def setUp(self):
        self.settings = SiteSettings.objects.create(client_cabinet_enabled=True)
        self.user = User.objects.create_user("ivan", password=PWD)
        self.profile = ClientProfile.objects.create(user=self.user, phone="111")
        self.massage = make_massage("МойМассаж")
        self.booking = BookingRequest.objects.create(
            client_name="Иван", user=self.user, phone="111", service=self.massage,
            preferred_date=future_date(), preferred_time=time(10, 0),
        )

    def test_login(self):
        resp = self.client.post(reverse("accounts:login"), {
            "username": "ivan", "password": PWD,
        })
        self.assertRedirects(resp, reverse("accounts:dashboard"))

    def test_dashboard_requires_login(self):
        resp = self.client.get(reverse("accounts:dashboard"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/account/login", resp["Location"])

    def test_dashboard_shows_only_own(self):
        other = User.objects.create_user("petr", password=PWD)
        ClientProfile.objects.create(user=other)
        BookingRequest.objects.create(
            client_name="Чужой", user=other, service=make_massage("ЧужойМассаж"),
            preferred_date=future_date(), preferred_time=time(9, 0),
        )
        self.client.force_login(self.user)
        body = self.client.get(reverse("accounts:dashboard")).content.decode()
        self.assertIn("МойМассаж", body)
        self.assertNotIn("ЧужойМассаж", body)

    def test_cancel_pending(self):
        self.client.force_login(self.user)
        resp = self.client.post(
            reverse("accounts:cancel_booking", args=[self.booking.pk])
        )
        self.assertRedirects(resp, reverse("accounts:dashboard"))
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, BookingRequest.Status.CANCELLED)

    def test_cannot_cancel_others(self):
        other = User.objects.create_user("petr", password=PWD)
        ClientProfile.objects.create(user=other)
        ob = BookingRequest.objects.create(
            client_name="X", user=other,
            preferred_date=future_date(), preferred_time=time(9, 0),
        )
        self.client.force_login(self.user)
        resp = self.client.post(reverse("accounts:cancel_booking", args=[ob.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_cancel_only_pending(self):
        self.booking.status = BookingRequest.Status.CONFIRMED
        self.booking.save()
        self.client.force_login(self.user)
        self.client.post(reverse("accounts:cancel_booking", args=[self.booking.pk]))
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, BookingRequest.Status.CONFIRMED)

    def test_profile_update_phone(self):
        self.client.force_login(self.user)
        self.client.post(reverse("accounts:profile"), {
            "save_profile": "1", "phone": "+70000000001",
        })
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.phone, "+70000000001")

    def test_change_password(self):
        self.client.force_login(self.user)
        new = "N3wSecret!2026"
        self.client.post(reverse("accounts:profile"), {
            "change_password": "1", "old_password": PWD,
            "new_password1": new, "new_password2": new,
        })
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(new))
