from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, TestCase
from django.urls import reverse

from main.forms import SitePaletteForm
from main.models import SiteSettings
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

    def test_page_list_respects_enabled_features_and_lists_services(self):
        self.grant_access()
        massage = Massage.objects.create(name="Тестовая услуга", price=200, duration_min=30, duration_max=30)
        response = self.client.get(self.url)
        self.assertContains(response, reverse("services:massage_detail", args=[massage.slug]))
        self.assertContains(response, 'type="color"')
        self.assertContains(response, reverse("booking:page"))
        SiteSettings.objects.update(online_booking_enabled=False, client_cabinet_enabled=False)
        response = self.client.get(self.url)
        self.assertNotContains(response, reverse("booking:page"))
        self.assertNotContains(response, reverse("accounts:register"))

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
