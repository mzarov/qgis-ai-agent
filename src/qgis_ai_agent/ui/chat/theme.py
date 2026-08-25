from dataclasses import dataclass

from qgis.PyQt.QtGui import QColor, QPalette


@dataclass
class ChatTheme:
    user_bg: QColor
    user_border: QColor
    plan_bg: QColor
    plan_border: QColor
    system_bg: QColor
    system_border: QColor
    result_bg: QColor
    result_border: QColor
    tool_bg: QColor
    tool_border: QColor
    text_color: QColor
    bubble_radius: int = 14
    bubble_padding_x: int = 14
    bubble_padding_y: int = 10
    outer_margin_x: int = 12
    outer_margin_y: int = 10
    side_offset_ratio: float = 0.22


def build_theme_from_palette(palette: QPalette) -> ChatTheme:
    is_dark = palette.base().color().lightness() < 128
    if is_dark:
        plan_bg = QColor(92, 88, 56)
        plan_border = QColor(176, 168, 108)
        tool_bg = QColor(48, 60, 76)
        tool_border = QColor(96, 122, 152)
    else:
        plan_bg = QColor(245, 243, 214)
        plan_border = QColor(196, 184, 112)
        tool_bg = QColor(233, 240, 248)
        tool_border = QColor(168, 190, 214)
    return ChatTheme(
        user_bg=palette.alternateBase().color(),
        user_border=palette.mid().color(),
        plan_bg=plan_bg,
        plan_border=plan_border,
        system_bg=palette.window().color(),
        system_border=palette.dark().color(),
        result_bg=palette.alternateBase().color(),
        result_border=palette.mid().color(),
        tool_bg=tool_bg,
        tool_border=tool_border,
        text_color=palette.text().color(),
    )
