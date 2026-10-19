from typing import Any

from qgis.PyQt.QtCore import QEvent, QObject
from qgis.PyQt.QtGui import QColor, QPainter, QPalette

from ai_agent.ui import theme

CARD_RADIUS = 10
BUBBLE_RADIUS = 10
HAIRLINE = 1
INK_PROPERTY = "aiInk"


def blend(first: QColor, second: QColor, ratio: float) -> QColor:
    keep = 1.0 - ratio
    return QColor(
        int(first.red() * keep + second.red() * ratio),
        int(first.green() * keep + second.green() * ratio),
        int(first.blue() * keep + second.blue() * ratio),
    )


def _token(palette: QPalette, name: str) -> QColor:
    return theme.colour(getattr(theme.tokens(palette), name))


def background(palette: QPalette) -> QColor:
    return _token(palette, "bg")


def surface(palette: QPalette) -> QColor:
    return _token(palette, "surface")


def field(palette: QPalette) -> QColor:
    return _token(palette, "surface")


def panel(palette: QPalette) -> QColor:
    return _token(palette, "surface")


def content(palette: QPalette) -> QColor:
    return _token(palette, "bg")


def card(palette: QPalette) -> QColor:
    return _token(palette, "surface_2")


def elevated(palette: QPalette) -> QColor:
    return _token(palette, "surface_2")


def sidebar(palette: QPalette) -> QColor:
    return _token(palette, "bg")


def sunken(palette: QPalette) -> QColor:
    return _token(palette, "sunken")


def hairline(palette: QPalette) -> QColor:
    return _token(palette, "border")


def border_strong(palette: QPalette) -> QColor:
    return _token(palette, "border_strong")


def success(palette: QPalette) -> QColor:
    return _token(palette, "ok")


def danger(palette: QPalette) -> QColor:
    return _token(palette, "bad")


def warning(palette: QPalette) -> QColor:
    return _token(palette, "warn")


def accent(palette: QPalette) -> QColor:
    return _token(palette, "accent")


def accent_hover(palette: QPalette) -> QColor:
    return _token(palette, "accent_hover")


def on_accent(palette: QPalette) -> QColor:
    return _token(palette, "accent_text")


def accent_ink(palette: QPalette) -> QColor:
    return _token(palette, "accent")


def user_bubble(palette: QPalette) -> QColor:
    return _token(palette, "accent_soft")


def text(palette: QPalette) -> QColor:
    return _token(palette, "text")


def muted(palette: QPalette) -> QColor:
    return _token(palette, "text_2")


def faint(palette: QPalette) -> QColor:
    return _token(palette, "text_3")


def soft(palette: QPalette, colour: QColor) -> QColor:
    tokens = theme.tokens(palette)
    for strong, wash in (
        (tokens.accent, tokens.accent_soft),
        (tokens.ok, tokens.ok_soft),
        (tokens.warn, tokens.warn_soft),
        (tokens.bad, tokens.bad_soft),
    ):
        if colour.name().lower() == strong.lower():
            return theme.colour(wash)
    return blend(surface(palette), colour, 0.14)


def apply_palette(widget: Any) -> None:
    roles = getattr(QPalette, "ColorRole", None)
    groups = getattr(QPalette, "ColorGroup", None)
    if roles is None or groups is None:
        return
    current = theme.tokens(widget.palette())
    palette = QPalette(widget.palette())
    values = {
        "Window": current.bg,
        "WindowText": current.text,
        "Base": current.surface,
        "AlternateBase": current.surface_2,
        "ToolTipBase": current.surface,
        "ToolTipText": current.text,
        "PlaceholderText": current.text_3,
        "Text": current.text,
        "Button": current.surface,
        "ButtonText": current.text,
        "BrightText": current.accent_text,
        "Light": current.surface,
        "Midlight": current.surface_2,
        "Mid": current.border_strong,
        "Dark": current.border_strong,
        "Shadow": current.border_strong,
        "Highlight": current.accent,
        "HighlightedText": current.accent_text,
        "Link": current.accent,
        "LinkVisited": current.accent_hover,
    }
    for group in ("Active", "Inactive", "Disabled"):
        for name, value in values.items():
            role = getattr(roles, name, None)
            if role is not None:
                palette.setColor(getattr(groups, group), role, theme.colour(value))
    for name in ("Text", "WindowText", "ButtonText"):
        palette.setColor(groups.Disabled, getattr(roles, name), theme.colour(current.text_3))
    widget.setPalette(palette)


class _Backdrop(QObject):
    def __init__(self, widget: Any, colour: QColor):
        super().__init__(widget)
        self.colour = QColor(colour)
        widget.installEventFilter(self)

    def eventFilter(self, watched: Any, event: Any) -> bool:
        if event.type() == QEvent.Type.Paint:
            painter = QPainter(watched)
            painter.fillRect(watched.rect(), self.colour)
            painter.end()
        return False


def fill(widget: Any, colour: QColor) -> None:
    # Not a style sheet (palette reset, crashes) nor autoFillBackground (QGIS dark themes repaint it).
    role = getattr(getattr(QPalette, "ColorRole", None), "Window", None)
    if role is None:
        return
    palette = widget.palette()
    palette.setColor(role, colour)
    widget.setPalette(palette)
    backdrop = next((child for child in widget.children() if isinstance(child, _Backdrop)), None)
    if backdrop is None:
        _Backdrop(widget, colour)
    else:
        backdrop.colour = QColor(colour)
        widget.update()


def ink(widget: Any, colour: QColor) -> None:
    # Its own style sheet too: an ancestor's sheet and QGIS themes' QLabel rules outrank a palette.
    role = getattr(getattr(QPalette, "ColorRole", None), "WindowText", None)
    if role is None:
        return
    palette = widget.palette()
    palette.setColor(role, colour)
    widget.setPalette(palette)
    sheet = f"color: {css_color(colour)};"
    current = widget.styleSheet()
    if current != sheet and current in ("", widget.property(INK_PROPERTY)):
        widget.setProperty(INK_PROPERTY, sheet)
        widget.setStyleSheet(sheet)


def field_inks(widget: Any, palette: QPalette) -> None:
    roles = getattr(QPalette, "ColorRole", None)
    if roles is None:
        return
    inks = widget.palette()
    inks.setColor(roles.Text, text(palette))
    inks.setColor(roles.PlaceholderText, faint(palette))
    widget.setPalette(inks)


def scale_font(widget: Any, ratio: float, bold: bool = False) -> None:
    font = widget.font()
    font.setPointSizeF(max(1.0, font.pointSizeF() * ratio))
    if bold:
        font.setBold(True)
    widget.setFont(font)


def series(palette: QPalette, index: int) -> QColor:
    colours = theme.CHART_DARK if theme.is_dark(palette) else theme.CHART_LIGHT
    return theme.colour(colours[min(index, len(colours) - 1)])


def css_color(color: QColor) -> str:
    return f"rgb({color.red()}, {color.green()}, {color.blue()})"
