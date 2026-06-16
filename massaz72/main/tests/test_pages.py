from django.test import TestCase
from django.urls import reverse


class StaticPagesTest(TestCase):
    def test_personal_data_page(self):
        resp = self.client.get(reverse("main:personal_data"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Политика в отношении обработки персональных данных")

    def test_privacy_page(self):
        self.assertEqual(self.client.get(reverse("main:privacy")).status_code, 200)

    def test_cookies_page(self):
        self.assertEqual(self.client.get(reverse("main:cookies")).status_code, 200)
