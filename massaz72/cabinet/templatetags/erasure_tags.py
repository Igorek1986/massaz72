from django import template

from accounts.models import AccountErasureRequest

register = template.Library()


@register.simple_tag
def pending_erasure_count():
    return AccountErasureRequest.objects.filter(completed_at__isnull=True).count()
