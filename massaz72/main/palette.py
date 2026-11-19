import re


PALETTE_FIELDS = {
    "canvas": ("Фон страницы", "#fbf4ed", "#21191f", "--color-canvas"),
    "card": ("Фон карточек и полей", "#fffaf5", "#2e222b", "--color-canvas-card"),
    "surface": ("Фон вторичных блоков", "#f3e4dc", "#33252f", "--color-surface-soft"),
    "ink": ("Заголовки и основной текст", "#422735", "#f8e8e4", "--color-ink"),
    "body": ("Вторичный текст", "#573d47", "#e2cdd2", "--color-body"),
    "muted": ("Подсказки", "#725761", "#c8adb7", "--color-muted"),
    "primary": ("Акцент и кнопки", "#803650", "#d991ac", "--color-primary"),
    "on_primary": ("Текст на кнопках", "#ffffff", "#281820", "--color-on-primary"),
    "header": ("Фон шапки", "#f5e7dc", "#281c26", "--color-header-bg"),
    "hero": ("Фон первого экрана", "#582d40", "#3b2634", "--redesign-hero-bg"),
    "navigation": ("Фон кнопок направлений", "#f0dfd4", "#392934", "--redesign-navigation"),
    "booking_glow": ("Градиент кнопки записи", "#efb1c6", "#efb1c6", "--redesign-booking-glow"),
    "booking_text": ("Текст кнопки записи", "#391d2b", "#391d2b", "--redesign-booking-text"),
    "hero_text": ("Текст первого экрана", "#fff5ec", "#fff5ec", "--redesign-hero-text"),
}
THEMES = ("light", "dark")
HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}\Z")


def valid_palette(value):
    if not isinstance(value, dict):
        return {}
    return {
        theme: {
            key: color
            for key, color in value[theme].items()
            if key in PALETTE_FIELDS and isinstance(color, str) and HEX_COLOR.fullmatch(color)
        }
        for theme in THEMES if isinstance(value.get(theme), dict)
    }


def theme_variables(value):
    return {
        theme: [(PALETTE_FIELDS[key][3], color) for key, color in colors.items()]
        for theme, colors in valid_palette(value).items()
    }
