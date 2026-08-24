from dataclasses import dataclass

from qgis.PyQt.QtGui import QColor, QPalette


@dataclass
class ChatTheme:
    """Тема чата на основе системной палитры QGIS."""
    user_bg: QColor
    user_border: QColor
    user_accent: QColor
    model_bg: QColor
    model_border: QColor
    preface_bg: QColor
    preface_border: QColor
    plan_bg: QColor
    plan_border: QColor
    plan_accent: QColor
    system_bg: QColor
    system_border: QColor
    result_bg: QColor
    result_border: QColor
    text_color: QColor
    bubble_radius: int = 14
    bubble_padding_x: int = 14
    bubble_padding_y: int = 10
    outer_margin_x: int = 12
    outer_margin_y: int = 10
    side_offset_ratio: float = 0.22


def build_theme_from_palette(palette: QPalette) -> ChatTheme:
    """Собирает цветовую тему чата из текущей палитры приложения."""
    base = palette.base().color()
    is_dark = base.lightness() < 128
    if is_dark:
        plan_bg = QColor(92, 88, 56)
        plan_border = QColor(176, 168, 108)
        plan_accent = QColor(198, 188, 98)
    else:
        plan_bg = QColor(245, 243, 214)
        plan_border = QColor(196, 184, 112)
        plan_accent = QColor(176, 164, 92)
    return ChatTheme(
        user_bg=palette.alternateBase().color(),
        user_border=palette.mid().color(),
        user_accent=palette.highlight().color(),
        model_bg=base,
        model_border=palette.mid().color(),
        preface_bg=palette.base().color(),
        preface_border=palette.mid().color(),
        plan_bg=plan_bg,
        plan_border=plan_border,
        plan_accent=plan_accent,
        system_bg=palette.window().color(),
        system_border=palette.dark().color(),
        result_bg=palette.alternateBase().color(),
        result_border=palette.mid().color(),
        text_color=palette.text().color(),
    )
