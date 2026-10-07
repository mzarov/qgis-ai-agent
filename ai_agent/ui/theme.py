"""The plugin's colours: the brand's two palettes, light and dark.

Cartographic blue on cool neutrals, from the design handoff's token table
(same names as here). The QGIS palette still decides which set applies, by its
lightness, so the plugin follows the light and the dark theme. This module is
the only place in the plugin that spells a colour; everything else asks `style`.
"""

from dataclasses import dataclass

from qgis.PyQt.QtGui import QColor, QPalette

DARK_LIGHTNESS = 128


@dataclass(frozen=True)
class Tokens:
    bg: str
    surface: str
    surface_2: str
    sunken: str
    border: str
    border_strong: str
    text: str
    text_2: str
    text_3: str
    accent: str
    accent_hover: str
    accent_soft: str
    accent_text: str
    ok: str
    ok_soft: str
    warn: str
    warn_soft: str
    bad: str
    bad_soft: str


LIGHT = Tokens(
    bg="#f5f6f8",
    surface="#ffffff",
    surface_2="#eff1f4",
    sunken="#e9ecf0",
    border="#dfe3e8",
    border_strong="#c9cfd7",
    text="#14181f",
    text_2="#535b67",
    text_3="#7c8592",
    accent="#1f6fb2",
    accent_hover="#195d96",
    accent_soft="#e5eff8",
    accent_text="#ffffff",
    ok="#1d7f47",
    ok_soft="#e3f3e9",
    warn="#9a5b08",
    warn_soft="#f8eedd",
    bad="#c2372d",
    bad_soft="#fae6e4",
)

DARK = Tokens(
    bg="#14171c",
    surface="#1b1f26",
    surface_2="#222731",
    sunken="#101318",
    border="#2c323c",
    border_strong="#3a414d",
    text="#e7eaee",
    text_2="#a7aeb8",
    text_3="#7f8793",
    accent="#4c9be8",
    accent_hover="#66abee",
    accent_soft="#182c42",
    accent_text="#08111c",
    ok="#4cc27f",
    ok_soft="#1c3528",
    warn="#e2a33d",
    warn_soft="#3a2e1d",
    bad="#ef6b60",
    bad_soft="#3f2422",
)


# Categorical chart colours in their fixed order, never cycled: the validated reference palette
# (adjacent CVD ΔE ≥ 8.4, normal-vision ΔE ≥ 19 in both modes); the dark column is stepped for
# the dark surface. More categories fold into "Other" before they reach the feed.
CHART_LIGHT = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948")
CHART_DARK = ("#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767")


THEME_AUTO = "auto"
THEME_LIGHT = "light"
THEME_DARK = "dark"
# The user's "panel theme" from Personalisation, set once at start and on Save: read on every
# colour lookup, so it is kept here rather than asked from the settings each time.
_override = [THEME_AUTO]


def set_override(theme: str) -> None:
    _override[0] = theme if theme in (THEME_LIGHT, THEME_DARK) else THEME_AUTO


def override() -> str:
    return _override[0]


def is_dark(palette: QPalette) -> bool:
    """Dark when the user chose the dark panel, or follows QGIS and its palette is dark."""
    if _override[0] != THEME_AUTO:
        return _override[0] == THEME_DARK
    return palette.base().color().lightness() < DARK_LIGHTNESS


def tokens(palette: QPalette) -> Tokens:
    return DARK if is_dark(palette) else LIGHT


def colour(value: str) -> QColor:
    """A hex token as a QColor, parsed by hand so the value type works in the test stubs too."""
    digits = value.lstrip("#")
    return QColor(int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16))
