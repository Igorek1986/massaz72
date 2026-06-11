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


WEEKDAY_SHORT = {
    "monday": "Пн", "tuesday": "Вт", "wednesday": "Ср", "thursday": "Чт",
    "friday": "Пт", "saturday": "Сб", "sunday": "Вс",
}


@register.filter
def weekday_short(name: str) -> str:
    """Короткое имя дня недели по имени поля: monday → Пн. Иначе вернуть как есть."""
    return WEEKDAY_SHORT.get(name, name)


@register.filter
def russian_plural(n, forms: str) -> str:
    """Выбрать форму слова по числу. Использование:
    {{ n }} {{ n|russian_plural:"массаж,массажа,массажей" }}

    forms — три формы через запятую: для 1, для 2–4, для 0/5–20.
    """
    one, few, many = (f.strip() for f in forms.split(","))
    try:
        n = abs(int(n))
    except (TypeError, ValueError):
        return many
    if n % 100 in (11, 12, 13, 14):
        return many
    if n % 10 == 1:
        return one
    if n % 10 in (2, 3, 4):
        return few
    return many
