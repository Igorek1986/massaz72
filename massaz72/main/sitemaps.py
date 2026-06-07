from django.contrib.sitemaps import Sitemap
from django.urls import reverse


class StaticViewSitemap(Sitemap):
    """Статические страницы сайта (главная и т.п.)."""

    changefreq = "weekly"
    priority = 1.0
    protocol = "https"

    def items(self):
        return ["main:index"]

    def location(self, item):
        return reverse(item)
