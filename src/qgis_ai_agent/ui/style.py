from qgis.PyQt.QtGui import QColor, QIcon, QPalette
from qgis.core import QgsApplication

CARD_RADIUS = 10
BUBBLE_RADIUS = 12
HAIRLINE = 1
USER_TINT = 0.16
CARD_TINT = 0.5
MUTED_TINT = 0.45


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
    return blend(palette.base().color(), palette.window().color(), CARD_TINT)


def hairline(palette: QPalette) -> QColor:
    return blend(palette.base().color(), palette.mid().color(), 0.55)


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
