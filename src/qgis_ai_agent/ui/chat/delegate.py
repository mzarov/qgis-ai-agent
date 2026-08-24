from qgis.PyQt.QtCore import QRect, QSize, Qt
from qgis.PyQt.QtGui import QBrush, QFont, QFontMetrics, QPainter, QPen
from qgis.PyQt.QtWidgets import QStyledItemDelegate

from qgis_ai_agent.ui.chat.model import ChatMessageModel
from qgis_ai_agent.ui.chat.theme import ChatTheme

_ALIGNMENT_FLAG = getattr(Qt, "AlignmentFlag", Qt)
_TEXT_FLAG = getattr(Qt, "TextFlag", Qt)
_ALIGN_LEFT = getattr(_ALIGNMENT_FLAG, "AlignLeft", getattr(Qt, "AlignLeft", 0))
_ALIGN_TOP = getattr(_ALIGNMENT_FLAG, "AlignTop", getattr(Qt, "AlignTop", 0))
_TEXT_WORD_WRAP = getattr(_TEXT_FLAG, "TextWordWrap", getattr(Qt, "TextWordWrap", 0))
_RENDER_HINT_CLASS = getattr(QPainter, "RenderHint", QPainter)
_ANTIALIASING = getattr(
    _RENDER_HINT_CLASS,
    "Antialiasing",
    getattr(QPainter, "Antialiasing", None),
)


class ChatMessageDelegate(QStyledItemDelegate):
    """Отрисовка пузырей чата (модель слева, пользователь справа)."""

    def __init__(self, theme_provider, parent=None):
        super().__init__(parent)
        self._theme_provider = theme_provider

    def paint(self, painter: QPainter, option, index):
        theme: ChatTheme = self._theme_provider()
        role = index.data(ChatMessageModel.ROLE_ROLE) or "system"
        text = index.data(ChatMessageModel.ROLE_TEXT) or ""
        bubble_rect = self._bubble_rect(option.rect, role, theme)

        painter.save()
        try:
            if _ANTIALIASING is not None:
                painter.setRenderHint(_ANTIALIASING, True)

            bg, border = self._bubble_colors(role, theme)
            painter.setPen(QPen(border, 1))
            painter.setBrush(QBrush(bg))
            painter.drawRoundedRect(bubble_rect, theme.bubble_radius, theme.bubble_radius)

            painter.setPen(QPen(theme.text_color))
            font = QFont(option.font)
            painter.setFont(font)
            text_rect = bubble_rect.adjusted(
                theme.bubble_padding_x,
                theme.bubble_padding_y,
                -theme.bubble_padding_x,
                -theme.bubble_padding_y,
            )
            align = _ALIGN_LEFT | _ALIGN_TOP
            painter.drawText(text_rect, align | _TEXT_WORD_WRAP, text)
        except Exception:
            # Аварийный fallback: даже при проблемах enum/рендера показываем текст
            painter.setPen(QPen(theme.text_color))
            painter.drawText(option.rect, _ALIGN_LEFT | _ALIGN_TOP | _TEXT_WORD_WRAP, str(text))
        finally:
            painter.restore()

    def sizeHint(self, option, index):
        theme: ChatTheme = self._theme_provider()
        role = index.data(ChatMessageModel.ROLE_ROLE) or "system"
        text = index.data(ChatMessageModel.ROLE_TEXT) or ""
        width = option.rect.width()
        if width <= 0 and self.parent() is not None and hasattr(self.parent(), "viewport"):
            width = self.parent().viewport().width()
        if width <= 0:
            width = 420
        temp_rect = QRect(0, 0, width, 200)
        bubble_rect = self._bubble_rect(temp_rect, role, theme)
        text_width = max(80, bubble_rect.width() - theme.bubble_padding_x * 2)
        fm = QFontMetrics(option.font)
        text_height = fm.boundingRect(0, 0, text_width, 10_000, _TEXT_WORD_WRAP, text).height()
        total_h = text_height + theme.bubble_padding_y * 2 + theme.outer_margin_y * 2 + 6
        return QSize(width, max(48, total_h))

    def _bubble_rect(self, full_rect: QRect, role: str, theme: ChatTheme) -> QRect:
        rect = QRect(full_rect)
        rect.adjust(
            theme.outer_margin_x,
            theme.outer_margin_y,
            -theme.outer_margin_x,
            -theme.outer_margin_y,
        )
        offset = int(rect.width() * theme.side_offset_ratio)
        if role == "user":
            rect.setLeft(rect.left() + offset)
        elif role == "assistant_preface":
            rect.setRight(rect.right() - offset)
        elif role == "plan":
            rect.setRight(rect.right() - int(offset * 0.35))
        elif role == "tool":
            # Служебные сообщения о работе тулов делаем узкой полосой, чтобы не отвлекать.
            rect.setRight(rect.right() - int(offset * 1.4))
        elif role == "assistant":
            rect.setRight(rect.right() - offset)
        return rect

    @staticmethod
    def _bubble_colors(role: str, theme: ChatTheme):
        if role == "user":
            return theme.user_bg, theme.user_border
        if role == "assistant_preface":
            return theme.preface_bg, theme.preface_border
        if role == "plan":
            return theme.plan_bg, theme.plan_border
        if role == "assistant":
            return theme.model_bg, theme.model_border
        if role == "result":
            return theme.result_bg, theme.result_border
        if role == "tool":
            return theme.tool_bg, theme.tool_border
        return theme.system_bg, theme.system_border
