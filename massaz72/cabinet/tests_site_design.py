from datetime import time
from html import escape

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, TestCase
from django.urls import URLResolver, get_resolver, reverse
from django.utils import timezone
from django.views.static import serve

from accounts.models import Client as ClientProfile
from booking.models import BookingRequest
from main.forms import SitePaletteForm
from main.models import SiteSettings
from main.preview import PREVIEW_PAGES
from services.models import Massage

from .models import Specialist


class SiteDesignTest(TestCase):
    def setUp(self):
        self.site = SiteSettings.objects.create(online_booking_enabled=True, client_cabinet_enabled=True)
        self.user = get_user_model().objects.create_user("palette-editor")
        Specialist.objects.create(user=self.user, name="Редактор")
        self.url = reverse("cabinet:site_design")
        self.home = reverse("main:index")

    def grant_access(self):
        self.user.user_permissions.add(Permission.objects.get(
            content_type__app_label="main", codename="manage_site_in_cabinet",
        ))
        self.client.force_login(self.user)

    def form_data(self, **changes):
        data = {key: field.initial for key, field in SitePaletteForm().fields.items()}
        data.update(changes)
        return data

    def test_site_routes_are_accounted_for_in_preview(self):
        def site_routes(patterns, namespace=""):
            for pattern in patterns:
                if isinstance(pattern, URLResolver):
                    if pattern.namespace not in {"admin", "cabinet", "tgbot"}:
                        prefix = f"{namespace}{pattern.namespace}:" if pattern.namespace else namespace
                        yield from site_routes(pattern.url_patterns, prefix)
                elif pattern.callback is not serve:
                    yield f"{namespace}{pattern.name or pattern.pattern}"

        routes_without_pages = {
            "pwa-worker", "pwa-subscription", "django.contrib.sitemaps.views.sitemap",
            "main:personal_data", "reviews:create",
            "booking:slots", "booking:month", "booking:sessions", "booking:status",
            "accounts:logout", "accounts:revoke_push_device", "accounts:request_account_erasure",
            "accounts:events", "accounts:day_sessions", "accounts:session_cancel",
            "accounts:session_reschedule", "accounts:cancel_booking",
        }
        self.assertEqual(
            set(site_routes(get_resolver().url_patterns)) - routes_without_pages,
            PREVIEW_PAGES.keys() - {"404", "500"},
            "Добавьте новую страницу в PREVIEW_PAGES.",
        )

    def test_anonymous_and_unauthorized_users_cannot_manage_palette(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, self.form_data()).status_code, 403)
        self.assertEqual(self.client.get(self.home, {"design_preview": "1"})["X-Frame-Options"], "DENY")
        self.site.refresh_from_db()
        self.assertEqual(self.site.design_palette, {})

    def test_preview_has_same_origin_policy_only_for_authorized_views(self):
        self.grant_access()
        for route in ("main:index", "main:privacy", "main:consent", "main:cookies",
                      "accounts:login", "accounts:register", "accounts:password_reset", "booking:page"):
            url = reverse(route)
            preview = self.client.get(url, {"design_preview": "1"})
            self.assertEqual(preview.status_code, 200, route)
            self.assertEqual(preview["X-Frame-Options"], "SAMEORIGIN", route)
            self.assertIn("no-store", preview["Cache-Control"])
        self.assertEqual(self.client.get(self.home)["X-Frame-Options"], "DENY")
        self.assertEqual(self.client.get(self.url, {"design_preview": "1"})["X-Frame-Options"], "DENY")

    def test_all_pages_render_even_when_features_are_disabled(self):
        self.grant_access()
        SiteSettings.objects.update(online_booking_enabled=False, client_cabinet_enabled=False)
        response = self.client.get(self.url)
        self.assertContains(response, 'type="color"')
        self.assertContains(response, 'aria-controls="design-gallery"')
        self.assertEqual(
            [title for _, title in response.context["page_urls"]],
            [page.title for page in PREVIEW_PAGES.values()],
        )
        for url, title in response.context["page_urls"]:
            with self.subTest(page=title):
                self.assertContains(response, f'<option value="{escape(url)}">{title}</option>')
                preview = self.client.get(url, {"design_preview": "1"})
                self.assertContains(preview, 'id="site-palette"')
                self.assertNotContains(preview, "data-worker=")
                self.assertEqual(preview["X-Frame-Options"], "SAMEORIGIN")
                self.assertIn("no-store", preview["Cache-Control"])
        for route in ("accounts:register", "accounts:password_reset", "booking:page"):
            with self.subTest(route=route):
                self.assertRedirects(self.client.get(reverse(route)), self.home)
                self.assertRedirects(self.client.post(reverse(route) + "?design_preview=1"), self.home)
        self.site.refresh_from_db()
        self.assertFalse(self.site.online_booking_enabled)
        self.assertFalse(self.site.client_cabinet_enabled)

    def test_service_details_use_one_public_service_or_a_sample(self):
        self.grant_access()
        service_fields = {"price": 200, "duration_min": 30, "duration_max": 30}
        Massage.objects.create(name="А Архивная", slug="archived", is_archived=True, **service_fields)
        Massage.objects.create(name="Б Без адреса", **service_fields)
        sample_url = reverse("cabinet:site_design_sample", args=["services:massage_detail"])
        response = self.client.get(self.url)
        self.assertIn((sample_url, "Страница услуги"), response.context["page_urls"])
        self.assertContains(self.client.get(sample_url, {"design_preview": "1"}), "Пример услуги")

        later = Massage.objects.create(name="Г Вторая услуга", slug="second", **service_fields)
        first = Massage.objects.create(name="В Первая услуга", slug="first", **service_fields)
        response = self.client.get(self.url)
        self.assertContains(response, first.get_absolute_url())
        self.assertNotContains(response, later.get_absolute_url())
        self.assertNotContains(response, "/services/archived/")
        self.assertNotContains(response, sample_url)
        preview = self.client.get(first.get_absolute_url(), {"design_preview": "1"})
        self.assertContains(preview, first.name)
        self.assertEqual(preview["X-Frame-Options"], "SAMEORIGIN")

    def test_sample_pages_require_permission_role_and_preview_get(self):
        profile = reverse("cabinet:site_design_sample", args=["accounts:profile"])
        unknown = reverse("cabinet:site_design_sample", args=["accounts:unknown"])
        live = reverse("cabinet:site_design_sample", args=["main:index"])
        preview_query = "?design_preview=1"
        self.assertEqual(self.client.get(profile + preview_query).status_code, 403)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(profile + preview_query).status_code, 403)
        self.grant_access()
        self.user.specialist.delete()
        self.assertEqual(self.client.get(profile + preview_query).status_code, 403)
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        self.assertEqual(self.client.get(profile).status_code, 403)
        self.assertEqual(self.client.post(profile + preview_query).status_code, 405)
        self.assertEqual(self.client.get(unknown + preview_query).status_code, 404)
        self.assertEqual(self.client.get(live + preview_query).status_code, 404)
        self.assertContains(self.client.get(profile + preview_query), "Смена пароля")

    def test_private_samples_use_empty_forms_and_keep_real_routes_protected(self):
        self.grant_access()
        client_profile = ClientProfile.objects.create(user=self.user, phone="+70000000123")
        profile = reverse("accounts:profile")
        booking = BookingRequest.objects.create(
            preferred_date=timezone.localdate(), preferred_time=time(12),
            link_token="fixture-booking-marker",
        )
        booking_url = reverse("booking:confirm", args=[booking.link_token])
        screens = {
            "accounts:dashboard": "Пока нет записей",
            "accounts:profile": "Смена пароля",
            "accounts:notifications": "Устройства с push",
            "accounts:password_reset_confirm": "Сохранить пароль",
            "booking:confirm": "Подтвердите запись",
            "404": "Ошибка 404",
            "500": "Ошибка 500",
        }
        for route, heading in screens.items():
            with self.subTest(route=route):
                url = reverse("cabinet:site_design_sample", args=[route])
                response = self.client.get(url, {"design_preview": "1"})
                self.assertContains(response, heading)
                self.assertNotContains(response, client_profile.phone)
                self.assertNotContains(response, booking.link_token)
                self.assertNotContains(response, "massaz_bookings")
        self.assertContains(self.client.get(profile), client_profile.phone)
        self.assertNotContains(self.client.get(reverse("booking:page"), {"design_preview": "1"}), client_profile.phone)
        self.assertEqual(self.client.get(profile, {"design_preview": "1"})["X-Frame-Options"], "DENY")
        self.assertEqual(self.client.get(booking_url, {"design_preview": "1"})["X-Frame-Options"], "DENY")
        self.assertEqual(BookingRequest.objects.count(), 1)
        self.assertEqual(ClientProfile.objects.count(), 1)

    def test_notifications_preview_shows_inert_pwa_controls_and_sample_devices(self):
        self.grant_access()
        url = reverse("cabinet:site_design_sample", args=["accounts:notifications"])
        response = self.client.get(url, {"design_preview": "1"})

        self.assertContains(response, '<html lang="ru" class="redesign-page">')
        self.assertContains(response, 'data-push-section aria-labelledby="admin-push-title"')
        self.assertContains(response, "Уведомления включены на этом устройстве.")
        self.assertContains(response, "Отправить тест")
        self.assertContains(response, "iPhone · Это устройство")
        self.assertContains(response, 'class="push-devices__row"', count=2)
        self.assertNotContains(response, "data-push-url")
        self.assertNotContains(response, 'type="submit" aria-label="Отключить push')
        self.assertNotContains(response, "/revoke/")

    def test_publish_applies_both_themes_to_public_pages(self):
        self.grant_access()
        self.assertRedirects(self.client.post(self.url, self.form_data(
            dark_canvas="#123456", light_canvas="#fafafb",
        )), self.url)
        self.site.refresh_from_db()
        self.assertEqual(self.site.design_palette["dark"]["canvas"], "#123456")
        for route in ("main:index", "main:privacy"):
            response = self.client.get(reverse(route))
            self.assertContains(response, "--color-canvas: #123456")
            self.assertContains(response, "--color-canvas: #fafafb")

    def test_rejects_invalid_colors_and_filters_untrusted_stored_values(self):
        self.grant_access()
        self.assertContains(self.client.post(self.url, self.form_data(
            dark_canvas="red; background: yellow",
        )), "Проверьте значения цветов")
        self.site.refresh_from_db()
        self.assertEqual(self.site.design_palette, {})
        SiteSettings.objects.update(design_palette={"light": {"primary": "</style>", "unknown": "#abcdef"}})
        self.assertNotContains(self.client.get(self.home), "#abcdef")

    def test_publish_requires_csrf(self):
        self.grant_access()
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(self.url, self.form_data()).status_code, 403)
