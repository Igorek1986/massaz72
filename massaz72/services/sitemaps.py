from django.contrib.sitemaps import Sitemap
from .models import Massage


class MassageSitemap(Sitemap):
    changefreq = "monthly"
    protocol = "https"
    priority = 0.9

    def items(self):
        return Massage.objects.filter(is_archived=False)

    def lastmod(self, item):
        return item.updated_at
