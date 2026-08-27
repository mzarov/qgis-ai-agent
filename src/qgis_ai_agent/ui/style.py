from qgis.PyQt.QtGui import QColor, QIcon, QPalette
from qgis.core import QgsApplication

CARD_RADIUS = 10
BUBBLE_RADIUS = 12
HAIRLINE = 1
USER_TINT = 0.26
CARD_TINT = 0.5
ELEVATED_TINT = 0.9
BORDER_TINT = 0.8
MUTED_TINT = 0.38
PANEL_LIFT = 0.11


def theme_icon(name: str) -> QIcon:
    try:
        icon = QgsApplication.getThemeIcon(name)
    except Exception:
        return QIcon()
    return icon


def blend(first: QColor, second: QColor, ratio: float) -> QColor:
    keep = 1.0 - ratio
    return QColor(
        int(first.red() * keep + second.red() * ratio),
        int(first.green() * keep + second.green() * ratio),
        int(first.blue() * keep + second.blue() * ratio),
    )


def is_dark(palette: QPalette) -> bool:
    return palette.base().color().lightness() < 128


def surface(palette: QPalette) -> QColor:
    return palette.base().color()


def card(palette: QPalette) -> QColor:
    base = palette.base().color()
    target = QColor(255, 255, 255) if not is_dark(palette) else QColor(0, 0, 0)
    lifted = blend(base, palette.window().color(), CARD_TINT)
    return blend(lifted, target, 0.06 if is_dark(palette) else 0.0)


def elevated(palette: QPalette) -> QColor:
    base = palette.base().color()
    lift = QColor(255, 255, 255) if is_dark(palette) else QColor(0, 0, 0)
    return blend(base, lift, 0.07)


def panel(palette: QPalette) -> QColor:
    base = palette.base().color()
    if not is_dark(palette):
        return base
    return blend(base, QColor(255, 255, 255), PANEL_LIFT)


def hairline(palette: QPalette) -> QColor:
    return blend(palette.base().color(), palette.mid().color(), BORDER_TINT)


def success(palette: QPalette) -> QColor:
    return QColor(106, 191, 142) if is_dark(palette) else QColor(31, 122, 71)


def danger(palette: QPalette) -> QColor:
    return QColor(226, 116, 116) if is_dark(palette) else QColor(176, 48, 48)


def warning(palette: QPalette) -> QColor:
    return QColor(230, 178, 90) if is_dark(palette) else QColor(160, 105, 15)


def accent(palette: QPalette) -> QColor:
    return palette.highlight().color()


def user_bubble(palette: QPalette) -> QColor:
    return blend(palette.base().color(), palette.highlight().color(), USER_TINT)


def text(palette: QPalette) -> QColor:
    return palette.text().color()


def muted(palette: QPalette) -> QColor:
    return blend(palette.text().color(), palette.base().color(), MUTED_TINT)


def css_color(color: QColor) -> str:
    return f"rgb({color.red()}, {color.green()}, {color.blue()})"
