from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from main.models import SiteSettings
from services.models import Massage


class StaticPagesTest(TestCase):
    def test_personal_data_redirects_to_privacy(self):
        resp = self.client.get(reverse("main:personal_data"))
        self.assertRedirects(
            resp, reverse("main:privacy"), status_code=301, fetch_redirect_response=False
        )

    def test_privacy_page(self):
        resp = self.client.get(reverse("main:privacy"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Политика в отношении обработки персональных данных")

    def test_cookies_page(self):
        self.assertEqual(self.client.get(reverse("main:cookies")).status_code, 200)

    def test_consent_page(self):
        resp = self.client.get(reverse("main:consent"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Согласие на обработку персональных данных")

    def test_footer_links_to_all_documents(self):
        resp = self.client.get(reverse("main:privacy"))
        for name in ("main:privacy", "main:consent", "main:cookies"):
            self.assertContains(resp, f'href="{reverse(name)}"')


class HomeSocialPreviewTest(TestCase):
    def test_preview_uses_https_and_the_current_host(self):
        response = self.client.get(reverse("main:index"), secure=True)

        self.assertContains(response, 'property="og:url" content="https://testserver/"')
        self.assertContains(
            response,
            'property="og:image" content="https://testserver/static/img/social-cover-logo.jpg"',
        )
        self.assertContains(response, 'name="twitter:card" content="summary_large_image"')

    def test_policy_page_does_not_include_home_preview(self):
        response = self.client.get(reverse("main:privacy"))

        self.assertNotContains(response, 'property="og:image"')


class InstallPromotionTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        SiteSettings.objects.create(online_booking_enabled=True)
        cls.massage = Massage.objects.create(
            name="Тестовая услуга", slug="test-service", price=1000,
            duration_min=30, duration_max=30,
        )

    def test_home_and_service_pages_offer_installation(self):
        for url in (reverse("main:index"), self.massage.get_absolute_url()):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertContains(response, "data-pwa-install hidden", count=1)
                self.assertContains(response, "data-pwa-ios hidden")
                self.assertContains(response, "data-pwa-android hidden")

    def test_booking_and_cabinet_do_not_offer_installation(self):
        for name in ("booking:page", "cabinet:login"):
            with self.subTest(name=name):
                self.assertNotContains(self.client.get(reverse(name)), "data-pwa-install hidden")

    def test_design_preview_does_not_offer_installation(self):
        self.client.force_login(get_user_model().objects.create_superuser(username="preview-admin"))
        response = self.client.get(reverse("main:index"), {"design_preview": "1"})
        self.assertNotContains(response, "data-pwa-install hidden")
