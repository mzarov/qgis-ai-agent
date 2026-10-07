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


def apply_palette(widget: Any) -> None:
    """Give a top-level panel the theme's own palette, so its children follow it rather than QGIS.

    With a panel theme other than QGIS's, plain labels, line edits and scroll areas would
    still draw with the QGIS palette — white text on the light panel inside a dark QGIS.
    Every role a stock widget reads is set from the tokens; children inherit it.
    """
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


def ink(widget: Any, colour: QColor) -> None:
    """Set a label's text colour through its palette: safe to call from a hover event."""
    role = getattr(getattr(QPalette, "ColorRole", None), "WindowText", None)
    if role is None:
        return
    palette = widget.palette()
    palette.setColor(role, colour)
    widget.setPalette(palette)


def field_inks(widget: Any, palette: QPalette) -> None:
    """Typed text and placeholder colours for an editor whose style sheet froze another palette."""
    roles = getattr(QPalette, "ColorRole", None)
    if roles is None:
        return
    inks = widget.palette()
    inks.setColor(roles.Text, text(palette))
    inks.setColor(roles.PlaceholderText, faint(palette))
    widget.setPalette(inks)


def scale_font(widget: Any, ratio: float, bold: bool = False) -> None:
    """Resize a widget's font relative to the one it inherited, optionally bold."""
    font = widget.font()
    font.setPointSizeF(max(1.0, font.pointSizeF() * ratio))
    if bold:
        font.setBold(True)
    widget.setFont(font)


def series(palette: QPalette, index: int) -> QColor:
    """Categorical chart colour `index` in the fixed order; the spec folds past eight, so no cycling happens."""
    colours = theme.CHART_DARK if is_dark(palette) else theme.CHART_LIGHT
    return theme.colour(colours[min(index, len(colours) - 1)])


def css_color(color: QColor) -> str:
    return f"rgb({color.red()}, {color.green()}, {color.blue()})"
