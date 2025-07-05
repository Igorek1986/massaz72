from django.contrib.sitemaps import Sitemap
from .models import Massage


class MassageSitemap(Sitemap):
    changefreq = "monthly"
    priority = 0.9

    def items(self):
        return Massage.objects.all()

    def lastmod(self, item):
        return item.updated_at
