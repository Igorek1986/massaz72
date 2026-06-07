from django.test import TestCase

from services.models import Massage


class SitemapTest(TestCase):
    def _create(self, slug, archived=False):
        return Massage.objects.create(
            name=slug,
            price=1000,
            duration_min=30,
            duration_max=60,
            location="Тюмень",
            massage_type="adult",
            slug=slug,
            is_archived=archived,
        )

    def test_sitemap_available(self):
        resp = self.client.get("/sitemap.xml")
        self.assertEqual(resp.status_code, 200)

    def test_homepage_included(self):
        resp = self.client.get("/sitemap.xml")
        # StaticViewSitemap задаёт приоритет 1.0 — только у главной
        self.assertContains(resp, "<priority>1.0</priority>")

    def test_archived_massage_excluded(self):
        self._create("active-massage")
        self._create("archived-massage", archived=True)
        resp = self.client.get("/sitemap.xml")
        self.assertContains(resp, "active-massage")
        self.assertNotContains(resp, "archived-massage")
