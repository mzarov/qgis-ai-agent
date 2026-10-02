"""Named colours for the widgets, all read from the mockup tokens in `theme`.

Widgets ask for a role (`panel`, `hairline`, `muted`, `accent`…), never for a
hex value; `theme.tokens(palette)` picks the light or the dark set from the
QGIS palette, so the plugin still follows the theme's lightness.
"""

from typing import Any

from qgis.PyQt.QtGui import QColor, QPalette

from ai_agent.ui import theme

CARD_RADIUS = 10
BUBBLE_RADIUS = 12
HAIRLINE = 1
USER_TINT = 0.26
RING_TINT = 0.5


def blend(first: QColor, second: QColor, ratio: float) -> QColor:
    keep = 1.0 - ratio
    return QColor(
        int(first.red() * keep + second.red() * ratio),
        int(first.green() * keep + second.green() * ratio),
        int(first.blue() * keep + second.blue() * ratio),
    )


def is_dark(palette: QPalette) -> bool:
    return theme.is_dark(palette)


def _token(palette: QPalette, name: str) -> QColor:
    return theme.colour(getattr(theme.tokens(palette), name))


def background(palette: QPalette) -> QColor:
    """The page behind everything: the dock body and the feed."""
    return _token(palette, "bg")


def surface(palette: QPalette) -> QColor:
    """Inputs and the composer."""
    return _token(palette, "surface")


def field(palette: QPalette) -> QColor:
    return _token(palette, "surface")


def panel(palette: QPalette) -> QColor:
    """Cards, tiles, the status card: the raised level."""
    return _token(palette, "surface")


def content(palette: QPalette) -> QColor:
    """The settings page background."""
    return _token(palette, "surface")


def card(palette: QPalette) -> QColor:
    """A quiet fill one step off the surface: hover, strips, chips at rest."""
    return _token(palette, "surface_2")


def elevated(palette: QPalette) -> QColor:
    return _token(palette, "surface_2")


def sidebar(palette: QPalette) -> QColor:
    return _token(palette, "bg")


def nav_selected(palette: QPalette) -> QColor:
    """The chosen sidebar entry: a step lighter on dark, a step darker on light."""
    return _token(palette, "surface_2" if is_dark(palette) else "sunken")


def nav_hover(palette: QPalette) -> QColor:
    return _token(palette, "surface" if is_dark(palette) else "surface_2")


def sunken(palette: QPalette) -> QColor:
    """Below the surface: segmented-control tracks, sidebar hover."""
    return _token(palette, "sunken")


def hairline(palette: QPalette) -> QColor:
    return _token(palette, "border")


def border_strong(palette: QPalette) -> QColor:
    """Input and plain-button outlines."""
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
    """Text and glyphs on an accent fill."""
    return _token(palette, "accent_text")


def accent_ink(palette: QPalette) -> QColor:
    """Accent text on its own soft wash."""
    return _token(palette, "accent")


def user_bubble(palette: QPalette) -> QColor:
    return _token(palette, "accent_soft")


def text(palette: QPalette) -> QColor:
    return _token(palette, "text")


def muted(palette: QPalette) -> QColor:
    return _token(palette, "text_2")


def faint(palette: QPalette) -> QColor:
    """Placeholders and the least important captions."""
    return _token(palette, "text_3")


def soft(palette: QPalette, colour: QColor) -> QColor:
    """The pale wash that belongs to a status colour: badge, selection and callout fills."""
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


def ring(palette: QPalette) -> QColor:
    """The focus halo around an input."""
    return blend(surface(palette), accent(palette), RING_TINT)


def fill(widget: Any, colour: QColor) -> None:
    """Paint a container's background through its palette, not a style sheet.

    A style sheet on a container switches its whole subtree to QStyleSheetStyle;
    with children that restyle and delete themselves often (the composer's hint
    bar) that crashed QGIS inside event processing.
    """
    role = getattr(getattr(QPalette, "ColorRole", None), "Window", None)
    if role is None:
        return
    palette = widget.palette()
    palette.setColor(role, colour)
    widget.setPalette(palette)
    widget.setAutoFillBackground(True)


def css_color(color: QColor) -> str:
    return f"rgb({color.red()}, {color.green()}, {color.blue()})"
