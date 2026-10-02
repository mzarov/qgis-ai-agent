"""The plugin's colours: the approved mockup's two palettes, light and dark.

`design/mockups/index.html` defines these tokens in CSS; here they are the same
hex values. The QGIS palette still decides which set applies, by its lightness,
so the plugin follows the light and the dark theme. This module is the only
place in the plugin that spells a colour; everything else asks `style`.
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
    bg="#f6f6f4",
    surface="#ffffff",
    surface_2="#f1f1ee",
    sunken="#ececE8",
    border="#e3e3de",
    border_strong="#cfcfc8",
    text="#1d1d1b",
    text_2="#5f5f5a",
    text_3="#8b8b85",
    accent="#2f6fde",
    accent_hover="#2560c8",
    accent_soft="#e8f0fd",
    accent_text="#ffffff",
    ok="#1f8a4c",
    ok_soft="#e5f4ea",
    warn="#b26b00",
    warn_soft="#fbf0dd",
    bad="#c4362c",
    bad_soft="#fbe7e5",
)

DARK = Tokens(
    bg="#1b1c1e",
    surface="#242528",
    surface_2="#2b2c30",
    sunken="#1f2023",
    border="#36383c",
    border_strong="#46484d",
    text="#ececea",
    text_2="#a9a9a4",
    text_3="#7d7d78",
    accent="#5b8ff0",
    accent_hover="#6f9df2",
    accent_soft="#263552",
    accent_text="#0f1420",
    ok="#4cc27f",
    ok_soft="#1f3a2b",
    warn="#e2a33d",
    warn_soft="#3d3020",
    bad="#ef6b60",
    bad_soft="#432523",
)


def is_dark(palette: QPalette) -> bool:
    return palette.base().color().lightness() < DARK_LIGHTNESS


def tokens(palette: QPalette) -> Tokens:
    return DARK if is_dark(palette) else LIGHT


def colour(value: str) -> QColor:
    """A hex token as a QColor, parsed by hand so the value type works in the test stubs too."""
    digits = value.lstrip("#")
    return QColor(int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16))
