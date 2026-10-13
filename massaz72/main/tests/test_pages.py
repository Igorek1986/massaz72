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
