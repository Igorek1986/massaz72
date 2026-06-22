"""Нормализация телефона (РФ). Используется формой записи и страницей
подтверждения заявки."""

import re


def normalize_ru_phone(raw: str) -> str:
    """Приводит номер к виду +7XXXXXXXXXX. Пусто → "". Невалидный → ValueError."""
    raw = (raw or "").strip()
    if not raw:
        return ""
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits[0] in "78":
        digits = "7" + digits[1:]
    elif len(digits) == 10:
        digits = "7" + digits
    else:
        raise ValueError("Некорректный номер телефона.")
    return "+" + digits
