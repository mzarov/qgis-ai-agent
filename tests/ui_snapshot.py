"""Screen checks for the plugin's widgets: structure, layout faults, pixels, gallery.

Three layers, from robust to strict:

- `structure()` lists every visible widget with its type, name, text and
  state. Compared with a JSON golden; independent of fonts and platform, so it
  runs everywhere and catches a missing, renamed, hidden or disabled control.
- `layout_faults()` finds text that does not fit its widget and content wider
  than its scroll area. Computed, not compared, so it needs no golden.
- `compare_pixels()` diffs a screenshot against a PNG golden. Fonts render
  differently per platform, so it only runs where `UI_PIXEL_BASELINE=1` is set:
  one CI job on a pinned QGIS image. A mismatch leaves the actual image and a
  diff with the changed pixels in red next to the other artifacts.

`write_gallery()` turns every PNG in the artifact folder into one HTML page.
"""

import html
import json
import os
import pathlib
import re

from qgis.PyQt.QtCore import QRect
from qgis.PyQt.QtGui import QColor, QImage, QPainter
from qgis.PyQt.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QScrollArea,
    QScrollBar,
    QTextEdit,
    QWidget,
)

GOLDENS = pathlib.Path(__file__).resolve().parent / "data" / "ui"
PIXEL_BASELINE = os.environ.get("UI_PIXEL_BASELINE") == "1"
UPDATE_GOLDENS = os.environ.get("UI_UPDATE_GOLDENS") == "1"
CHANNEL_TOLERANCE = 24
MAX_CHANGED_SHARE = 0.001
FIT_SLACK_PX = 1
TEXT_LIMIT = 120
VOLATILE = [
    (re.compile(r"\b\d+(?:[.,]\d+)?\s?(?:ms|s)\b"), "<duration>"),
    (re.compile(r"\b\d+(?:[.,]\d+)?k? tokens\b"), "<tokens>"),
]


def normalize_texts(root: QWidget, replacements: dict[str, str]) -> None:
    """Replace run-specific text (durations, token counts, temporary paths) before any check."""
    for widget in [root, *root.findChildren(QWidget)]:
        if not isinstance(widget, QLabel | QAbstractButton | QLineEdit):
            continue
        text = widget.text()
        clean = _scrub(text, replacements)
        if clean != text:
            widget.setText(clean)


def structure(root: QWidget) -> list[dict[str, object]]:
    """Visible widgets in tree order, without geometry."""
    rows: list[dict[str, object]] = []
    _walk(root, 0, rows)
    return rows


def layout_faults(root: QWidget) -> list[str]:
    """Human-readable faults: clipped text and horizontal overflow."""
    faults: list[str] = []
    for widget in _visible(root):
        fault = _text_fault(widget) or _overflow_fault(widget)
        if fault:
            faults.append(f"{fault}: {_label(widget)}")
    return faults


def _text_fault(widget: QWidget) -> str:
    if isinstance(widget, QLabel) and widget.text():
        if widget.wordWrap():
            needed = widget.heightForWidth(widget.width())
            return (
                f"wrapped text is cut ({needed} > {widget.height()})" if needed > widget.height() + FIT_SLACK_PX else ""
            )
        needed = widget.minimumSizeHint().width()
        if needed > widget.width() + FIT_SLACK_PX and not _elides(widget):
            return f"text does not fit ({needed} > {widget.width()})"
    if isinstance(widget, QAbstractButton) and widget.text():
        needed = widget.sizeHint().width()
        if needed > widget.width() + FIT_SLACK_PX:
            return f"button text does not fit ({needed} > {widget.width()})"
    return ""


def _overflow_fault(widget: QWidget) -> str:
    if not isinstance(widget, QScrollArea) or widget.widget() is None:
        return ""
    content, viewport = widget.widget().width(), widget.viewport().width()
    return f"content wider than its scroll area ({content} > {viewport})" if content > viewport + FIT_SLACK_PX else ""


def compare_structure(name: str, rows: list[dict[str, object]]) -> str | None:
    """None when the structure matches its golden; otherwise a short diff."""
    golden = GOLDENS / "structure" / f"{name}.json"
    text = json.dumps(rows, indent=1, ensure_ascii=False) + "\n"
    if UPDATE_GOLDENS or not golden.exists():
        golden.parent.mkdir(parents=True, exist_ok=True)
        golden.write_text(text, encoding="utf-8")
        return None if UPDATE_GOLDENS else f"new structure golden written: {golden.name}; review and commit it"
    expected = json.loads(golden.read_text(encoding="utf-8"))
    if expected == rows:
        return None
    return _first_difference(expected, rows)


def compare_pixels(name: str, image: QImage, artifacts: pathlib.Path) -> str | None:
    """None when the image matches its golden within tolerance; otherwise why, with artifacts saved."""
    golden_path = GOLDENS / "pixels" / f"{name}.png"
    actual_dir = artifacts / "ui-actual"
    image = image.convertToFormat(QImage.Format.Format_ARGB32)
    if UPDATE_GOLDENS:
        golden_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(str(golden_path))
        return None
    if not golden_path.exists():
        actual_dir.mkdir(parents=True, exist_ok=True)
        image.save(str(actual_dir / f"{name}.png"))
        return f"no pixel golden for {name}; the candidate is in the ui-actual artifact"
    golden = QImage(str(golden_path)).convertToFormat(QImage.Format.Format_ARGB32)
    if golden.size() != image.size():
        actual_dir.mkdir(parents=True, exist_ok=True)
        image.save(str(actual_dir / f"{name}.png"))
        return f"size changed: {golden.width()}x{golden.height()} -> {image.width()}x{image.height()}"
    changed = _changed_pixels(golden, image)
    share = len(changed) / max(1, image.width() * image.height())
    if share <= MAX_CHANGED_SHARE:
        return None
    actual_dir.mkdir(parents=True, exist_ok=True)
    image.save(str(actual_dir / f"{name}.png"))
    _diff_image(image, changed).save(str(artifacts / f"{name}.diff.png"))
    return f"{len(changed)} pixels changed ({share:.2%}); see {name}.diff.png"


def write_gallery(artifacts: pathlib.Path) -> pathlib.Path:
    """One HTML page showing every screenshot in the artifact folder."""
    shots = sorted(path for path in artifacts.rglob("*.png"))
    cards = "\n".join(
        f'<figure><img src="{html.escape(str(path.relative_to(artifacts)))}" loading="lazy">'
        f"<figcaption>{html.escape(str(path.relative_to(artifacts)))}</figcaption></figure>"
        for path in shots
    )
    page = artifacts / "index.html"
    page.write_text(
        "<!doctype html><meta charset=utf-8><title>AI Agent screens</title>"
        "<style>body{font:14px sans-serif;margin:24px;background:#f4f4f4}"
        "figure{display:inline-block;vertical-align:top;margin:0 16px 24px 0;max-width:560px}"
        "img{max-width:560px;border:1px solid #ccc;background:#fff}figcaption{margin-top:4px;color:#444}</style>"
        f"<h1>AI Agent screens ({len(shots)})</h1>\n{cards}\n",
        encoding="utf-8",
    )
    return page


def _scrub(text: str, replacements: dict[str, str]) -> str:
    for old, new in replacements.items():
        if old:
            text = text.replace(old, new)
    for pattern, new in VOLATILE:
        text = pattern.sub(new, text)
    return text


def _walk(widget: QWidget, depth: int, rows: list[dict[str, object]]) -> None:
    if not _counts(widget):
        return
    row: dict[str, object] = {"depth": depth, "type": type(widget).__name__}
    if widget.objectName() and not widget.objectName().startswith("qt_"):
        row["name"] = widget.objectName()
    text = _text(widget)
    if text:
        row["text"] = text[:TEXT_LIMIT]
    if not widget.isEnabled():
        row["enabled"] = False
    if isinstance(widget, QAbstractButton) and widget.isCheckable():
        row["checked"] = widget.isChecked()
    rows.append(row)
    for child in widget.children():
        if isinstance(child, QWidget) and not child.isWindow():
            _walk(child, depth + 1, rows)


def _counts(widget: QWidget) -> bool:
    # Scroll bars come and go with font metrics; Qt's own helpers are not ours to pin.
    if not widget.isVisible() or isinstance(widget, QScrollBar):
        return False
    return not widget.objectName().startswith("qt_scrollarea")


def _text(widget: QWidget) -> str:
    if isinstance(widget, QLabel | QAbstractButton):
        return widget.text()
    if isinstance(widget, QLineEdit):
        return widget.text() or widget.placeholderText()
    if isinstance(widget, QComboBox):
        return widget.currentText()
    if isinstance(widget, QPlainTextEdit | QTextEdit):
        return widget.toPlainText() or widget.placeholderText()
    return ""


def _visible(root: QWidget) -> list[QWidget]:
    return [widget for widget in [root, *root.findChildren(QWidget)] if widget.isVisible()]


def _elides(label: QLabel) -> bool:
    # Labels sized to shrink on purpose (minimum width 0) elide by design.
    return label.minimumWidth() == 0 and label.sizePolicy().horizontalPolicy().name == "Ignored"


def _label(widget: QWidget) -> str:
    text = _text(widget)
    return f"{type(widget).__name__} {widget.objectName() or ''} {text[:40]!r}".replace("  ", " ")


def _first_difference(expected: list, actual: list) -> str:
    for index, (want, got) in enumerate(zip(expected, actual, strict=False)):
        if want != got:
            return f"structure differs at widget {index}: expected {want}, got {got}"
    return f"structure differs in length: expected {len(expected)} widgets, got {len(actual)}"


def _changed_pixels(golden: QImage, image: QImage) -> list[tuple[int, int]]:
    width, height = image.width(), image.height()
    stride = image.bytesPerLine()
    want = bytes(golden.constBits().asstring(golden.sizeInBytes()))
    got = bytes(image.constBits().asstring(image.sizeInBytes()))
    changed = []
    for y in range(height):
        start = y * stride
        row_want, row_got = want[start : start + width * 4], got[start : start + width * 4]
        if row_want == row_got:
            continue
        for x in range(width):
            offset = x * 4
            if any(abs(row_want[offset + c] - row_got[offset + c]) > CHANNEL_TOLERANCE for c in range(4)):
                changed.append((x, y))
    return changed


def _diff_image(image: QImage, changed: list[tuple[int, int]]) -> QImage:
    diff = image.copy()
    painter = QPainter(diff)
    painter.fillRect(QRect(0, 0, diff.width(), diff.height()), QColor(255, 255, 255, 170))
    painter.end()
    red = QColor(220, 0, 0).rgba()
    for x, y in changed:
        diff.setPixel(x, y, red)
    return diff
