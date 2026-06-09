from decimal import Decimal

from django import template

register = template.Library()


@register.filter
def initials(name: str) -> str:
    """Return up to 2 uppercase initials from a name."""
    words = (name or "").split()
    return "".join(w[0].upper() for w in words[:2] if w)


@register.filter
def apply_discount(price, discount):
    """Вернуть цену после скидки. Использование: {{ price|apply_discount:discount }}"""
    if not discount or price is None:
        return price
    return discount.apply_to(Decimal(str(price)))
