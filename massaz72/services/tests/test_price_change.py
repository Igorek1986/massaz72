from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from main.context_processors import site_settings as site_settings_ctx
from main.models import SiteSettings
from services.models import Massage


class NewPriceModelTest(TestCase):
    def test_negative_new_price_rejected(self):
        massage = Massage(
            name="Массаж",
            price=1000,
            new_price=-100,
            duration_min=30,
            duration_max=60,
            massage_type="adult",
        )
        with self.assertRaises(ValidationError):
            massage.full_clean()

    def test_new_price_optional(self):
        massage = Massage(
            name="Массаж",
            price=1000,
            duration_min=30,
            duration_max=60,
            location="Тюмень",
            massage_type="adult",
            slug="m",
        )
        massage.full_clean()  # не должно бросать исключение


class PriceContextProcessorTest(TestCase):
    def _ctx(self):
        return site_settings_ctx(request=None)

    def test_no_date_means_no_change(self):
        SiteSettings.objects.create()
        ctx = self._ctx()
        self.assertFalse(ctx["new_prices_active"])
        self.assertFalse(ctx["price_change_pending"])

    def test_future_date_is_pending(self):
        SiteSettings.objects.create(
            price_change_date=timezone.localdate() + timedelta(days=5)
        )
        ctx = self._ctx()
        self.assertTrue(ctx["price_change_pending"])
        self.assertFalse(ctx["new_prices_active"])

    def test_past_or_today_date_is_active(self):
        SiteSettings.objects.create(price_change_date=timezone.localdate())
        ctx = self._ctx()
        self.assertTrue(ctx["new_prices_active"])
        self.assertFalse(ctx["price_change_pending"])


class MassageDetailPriceTest(TestCase):
    def setUp(self):
        self.massage = Massage.objects.create(
            name="Массаж",
            price=Decimal("1000"),
            new_price=Decimal("1500"),
            duration_min=30,
            duration_max=60,
            massage_type="adult",
            slug="test-massage",
        )

    def test_shows_old_price_while_pending(self):
        SiteSettings.objects.create(
            price_change_date=timezone.localdate() + timedelta(days=3)
        )
        resp = self.client.get(
            reverse("services:massage_detail", kwargs={"slug": "test-massage"})
        )
        self.assertContains(resp, "1000")
        # будущая цена тоже показана как анонс
        self.assertContains(resp, "1500")

    def test_shows_new_price_when_active(self):
        SiteSettings.objects.create(price_change_date=timezone.localdate())
        resp = self.client.get(
            reverse("services:massage_detail", kwargs={"slug": "test-massage"})
        )
        self.assertContains(resp, "1500")


class ApplyPriceChangesCommandTest(TestCase):
    def setUp(self):
        self.massage = Massage.objects.create(
            name="Массаж",
            price=Decimal("1000"),
            new_price=Decimal("1500"),
            duration_min=30,
            duration_max=60,
            massage_type="adult",
            slug="test-massage",
        )

    def _run(self, **kwargs):
        out = StringIO()
        call_command("apply_price_changes", stdout=out, **kwargs)
        return out.getvalue()

    def test_skips_when_date_in_future(self):
        SiteSettings.objects.create(
            price_change_date=timezone.localdate() + timedelta(days=3)
        )
        self._run()
        self.massage.refresh_from_db()
        self.assertEqual(self.massage.price, Decimal("1000"))
        self.assertEqual(self.massage.new_price, Decimal("1500"))

    def test_promotes_when_date_reached(self):
        settings_obj = SiteSettings.objects.create(
            price_change_date=timezone.localdate()
        )
        self._run()
        self.massage.refresh_from_db()
        settings_obj.refresh_from_db()
        self.assertEqual(self.massage.price, Decimal("1500"))
        self.assertIsNone(self.massage.new_price)
        self.assertIsNone(settings_obj.price_change_date)

    def test_force_ignores_date(self):
        SiteSettings.objects.create()  # дата не задана
        self._run(force=True)
        self.massage.refresh_from_db()
        self.assertEqual(self.massage.price, Decimal("1500"))
        self.assertIsNone(self.massage.new_price)
