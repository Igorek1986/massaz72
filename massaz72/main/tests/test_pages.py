from django.test import TestCase
from django.urls import reverse


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
            'property="og:image" content="https://testserver/static/img/social-cover-embroidered.jpg"',
        )
        self.assertContains(response, 'name="twitter:card" content="summary_large_image"')

    def test_policy_page_does_not_include_home_preview(self):
        response = self.client.get(reverse("main:privacy"))

        self.assertNotContains(response, 'property="og:image"')
