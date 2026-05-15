from django import template

register = template.Library()


@register.filter
def initials(name: str) -> str:
    """Return up to 2 uppercase initials from a name."""
    words = (name or "").split()
    return "".join(w[0].upper() for w in words[:2] if w)
