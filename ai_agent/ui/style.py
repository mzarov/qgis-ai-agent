from qgis.PyQt.QtGui import QColor, QPalette

CARD_RADIUS = 10
BUBBLE_RADIUS = 12
HAIRLINE = 1
USER_TINT = 0.26
CARD_TINT = 0.5
ELEVATED_TINT = 0.9
BORDER_TINT = 0.8
MUTED_TINT = 0.38
PANEL_LIFT = 0.11
SOFT_TINT = 0.14
ACCENT_LIFT_DARK = 0.28
COOL_TINT = 0.035
SIDEBAR_LIFT = 0.055
CONTENT_LIFT = 0.025
FIELD_LIFT = 0.035
SOFT_TINT_DARK = 0.24


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
    return cool(palette, blend(base, QColor(255, 255, 255), PANEL_LIFT))


def hairline(palette: QPalette) -> QColor:
    return blend(palette.base().color(), palette.mid().color(), BORDER_TINT)


def success(palette: QPalette) -> QColor:
    return QColor(106, 191, 142) if is_dark(palette) else QColor(31, 122, 71)


def danger(palette: QPalette) -> QColor:
    return QColor(226, 116, 116) if is_dark(palette) else QColor(176, 48, 48)


def warning(palette: QPalette) -> QColor:
    return QColor(230, 178, 90) if is_dark(palette) else QColor(160, 105, 15)


def system_accent(palette: QPalette) -> QColor:
    """The OS accent colour (Qt 6.6+ `Accent` role); the selection highlight where there is none.

    On macOS the highlight is the muted text-selection fill, not the accent the system draws
    buttons and focus rings with, so it made every accent in the plugin look dull.
    """
    role = getattr(getattr(QPalette, "ColorRole", None), "Accent", None)
    if role is not None:
        try:
            found = palette.color(role)
        except Exception:
            found = None
        if isinstance(found, QColor) and found.isValid() and found.alpha() > 0:
            return found
    return palette.highlight().color()


def accent(palette: QPalette) -> QColor:
    """The accent for fills, borders and rings: the system accent, softened on a dark palette."""
    found = system_accent(palette)
    return blend(found, QColor(255, 255, 255), ACCENT_LIFT_DARK) if is_dark(palette) else found


def on_accent(palette: QPalette) -> QColor:
    """Text and glyphs on an accent fill: dark on the softened dark-theme accent, white otherwise."""
    return palette.base().color() if is_dark(palette) else QColor(255, 255, 255)


def cool(palette: QPalette, colour: QColor) -> QColor:
    """Nudge a dark surface towards the accent so greys read cool rather than flat."""
    return blend(colour, system_accent(palette), COOL_TINT) if is_dark(palette) else colour


def field(palette: QPalette) -> QColor:
    """Input fill: recessed below the cards, but not a black hole on a dark palette."""
    base = surface(palette)
    if not is_dark(palette):
        return base
    return cool(palette, blend(base, QColor(255, 255, 255), FIELD_LIFT))


def sidebar(palette: QPalette) -> QColor:
    """The settings sidebar: a step above the content, the way the window chrome sits."""
    window = palette.window().color()
    if not is_dark(palette):
        return blend(window, QColor(0, 0, 0), 0.03)
    return cool(palette, blend(window, QColor(255, 255, 255), SIDEBAR_LIFT))


def content(palette: QPalette) -> QColor:
    """The settings page background."""
    window = palette.window().color()
    if not is_dark(palette):
        return palette.base().color()
    return cool(palette, blend(window, QColor(255, 255, 255), CONTENT_LIFT))


def user_bubble(palette: QPalette) -> QColor:
    return blend(palette.base().color(), palette.highlight().color(), USER_TINT)


def text(palette: QPalette) -> QColor:
    return palette.text().color()


def muted(palette: QPalette) -> QColor:
    return blend(palette.text().color(), palette.base().color(), MUTED_TINT)


def soft(palette: QPalette, colour: QColor) -> QColor:
    """A pale wash of `colour` over the base: badge, selection and callout fills."""
    ratio = SOFT_TINT_DARK if is_dark(palette) else SOFT_TINT
    return blend(palette.base().color(), colour, ratio)


def accent_ink(palette: QPalette) -> QColor:
    """Accent text that stays readable on its own soft wash: lifted towards white in the dark."""
    if is_dark(palette):
        return blend(accent(palette), QColor(255, 255, 255), 0.45)
    return accent(palette)


def ring(palette: QPalette) -> QColor:
    """The focus halo around an input: the accent, half way into the base."""
    return blend(palette.base().color(), accent(palette), 0.45)


def css_color(color: QColor) -> str:
    return f"rgb({color.red()}, {color.green()}, {color.blue()})"
