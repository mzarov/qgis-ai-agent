from typing import Any

from qgis.PyQt.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from qgis_ai_agent.ui import style

HINT_SCALE = 0.86
SECTION_SCALE = 0.9
CARD_MARGINS = (14, 12, 14, 13)
CARD_SPACING = 11
FIELD_SPACING = 3
LABEL_SPACING = 2


def card(palette: Any) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setStyleSheet(
        f"QFrame {{ background: {style.css_color(style.card(palette))};"
        f"border: {style.HAIRLINE}px solid {style.css_color(style.hairline(palette))};"
        f"border-radius: {style.CARD_RADIUS}px; }}"
    )
    column = QVBoxLayout(frame)
    column.setContentsMargins(*CARD_MARGINS)
    column.setSpacing(CARD_SPACING)
    return frame, column


def section(title: str, palette: Any) -> QLabel:
    label = QLabel(title.upper())
    font = label.font()
    font.setBold(True)
    font.setPointSizeF(max(1.0, font.pointSizeF() * SECTION_SCALE))
    label.setFont(font)
    label.setStyleSheet(
        f"color: {style.css_color(style.muted(palette))}; border: none; letter-spacing: 1px;"
    )
    return label


def field(title: str, widget: QWidget, hint: str, palette: Any) -> QWidget:
    holder = QWidget()
    holder.setStyleSheet("border: none; background: transparent;")
    column = QVBoxLayout(holder)
    column.setContentsMargins(0, 0, 0, 0)
    column.setSpacing(FIELD_SPACING)

    label = QLabel(title)
    label.setStyleSheet("border: none;")
    column.addWidget(label)
    column.addWidget(widget)
    if hint:
        column.addSpacing(LABEL_SPACING)
        column.addWidget(_hint(hint, palette))
    return holder


def status(palette: Any) -> QLabel:
    label = QLabel("")
    label.setWordWrap(True)
    label.setVisible(False)
    font = label.font()
    font.setPointSizeF(max(1.0, font.pointSizeF() * HINT_SCALE))
    label.setFont(font)
    label.setStyleSheet(f"color: {style.css_color(style.muted(palette))}; border: none;")
    return label


def paint_status(label: QLabel, text: str, colour: Any) -> None:
    label.setText(text)
    label.setStyleSheet(f"color: {style.css_color(colour)}; border: none;")
    label.setVisible(bool(text))


def accent_button(palette: Any) -> str:
    fill = style.css_color(style.accent(palette))
    return (
        f"QPushButton {{ background: {fill};"
        f"color: {style.css_color(palette.highlightedText().color())};"
        f"border: {style.HAIRLINE}px solid {fill}; border-radius: 6px;"
        "padding: 5px 16px; font-weight: 600; }"
        f"QPushButton:hover {{ background: {style.css_color(style.accent(palette).lighter(112))}; }}"
    )


def plain_button(palette: Any) -> str:
    border = style.css_color(style.hairline(palette))
    return (
        f"QPushButton {{ background: transparent; color: {style.css_color(style.text(palette))};"
        f"border: {style.HAIRLINE}px solid {border}; border-radius: 6px; padding: 5px 14px; }}"
        f"QPushButton:hover {{ background: {style.css_color(style.card(palette))}; }}"
        "QPushButton:disabled { color: palette(mid); }"
    )


def _hint(text: str, palette: Any) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    font = label.font()
    font.setPointSizeF(max(1.0, font.pointSizeF() * HINT_SCALE))
    label.setFont(font)
    label.setStyleSheet(f"color: {style.css_color(style.muted(palette))}; border: none;")
    return label
