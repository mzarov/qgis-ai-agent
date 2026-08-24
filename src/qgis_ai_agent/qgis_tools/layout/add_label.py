import unicodedata
from typing import Any

from qgis.PyQt.QtCore import Qt
from qgis.core import QgsLayoutItemLabel

from qgis_ai_agent.qgis_tools.base import SAFETY_WRITE, BaseTool
from qgis_ai_agent.qgis_tools.layout.layout_composer import apply_label_geometry, compose_label_box
from qgis_ai_agent.qgis_tools.layout.utils import get_layout


class AddLabelTool(BaseTool):
    """Добавление текстовой надписи на макет (заголовок, подпись и т.д.)."""
    name = "add_label"
    description = "Добавить надпись (текст) на макет. Можно выровнять по центру страницы."
    skill = "layout"
    safety = SAFETY_WRITE
    capabilities = ["layout:label:add"]
    examples = ["Добавь заголовок по центру сверху"]
    constraints = ["layout_name должен существовать"]
    params_schema = [
        {"name": "layout_name", "type": "string", "description": "Имя макета", "required": True},
        {"name": "x", "type": "number", "description": "X позиции в мм (для center можно 0)", "required": False},
        {"name": "y", "type": "number", "description": "Y позиции в мм от верхнего края", "required": False},
        {"name": "text", "type": "string", "description": "Текст надписи", "required": True},
        {"name": "alignment", "type": "string", "description": "Выравнивание: left, center, right. Для center надпись центрируется по ширине страницы.", "required": False},
        {"name": "font_size", "type": "number", "description": "Размер шрифта в пунктах (опционально)", "required": False},
        {"name": "role", "type": "string", "description": "Смысловая роль: title, subtitle, footer, label", "required": False},
    ]

    _INVISIBLE_CHARS = (
        "\u200b",  # zero-width space
        "\u200c",  # zero-width non-joiner
        "\u200d",  # zero-width joiner
        "\ufeff",  # BOM
    )

    _ROLE_NAMES = {
        "title": "заголовок",
        "subtitle": "подзаголовок",
        "footer": "подпись внизу",
    }

    def summarize_call(self, params: dict[str, Any]) -> str:
        """Описание шага добавления надписи для чата."""
        text = (params.get("text") or "").strip()
        role = (params.get("role") or "label").strip().lower()
        role_name = self._ROLE_NAMES.get(role, "надпись")
        shown = text[:40] + ("…" if len(text) > 40 else "")
        return f"Добавить {role_name} «{shown}»."

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layout_name = params.get("layout_name") or "Макет ИИ"
        x_raw = params.get("x")
        y_raw = params.get("y")
        x = float(x_raw) if x_raw is not None else None
        y = float(y_raw) if y_raw is not None else None
        text = self._normalize_text(params.get("text") or "")
        alignment = (params.get("alignment") or "left").lower().strip()
        if alignment in {"top-center", "middle", "centre"}:
            alignment = "center"
        role = (params.get("role") or "label").strip().lower()
        font_size = params.get("font_size")

        # Если модель не указала роль, но текст похож на заголовок,
        # автоматически делаем title по центру сверху.
        if role == "label" and x is None and y is None and alignment in ("left", "center"):
            clean = text.strip()
            if clean and len(clean) <= 40:
                role = "title"
                alignment = "center"
        if role == "title":
            # Для заголовков всегда используем top-center:
            # выравнивание принудительно по центру, координаты x/y не задаём вручную.
            alignment = "center"
            x = None
            y = None
            text = self._fit_title_text(text)
        if role == "subtitle":
            text = self._fit_subtitle_text(text)

        layout = get_layout(layout_name)
        label = QgsLayoutItemLabel(layout)
        label.setText(text)
        box = compose_label_box(
            layout=layout,
            role=role,
            text=text,
            alignment=alignment,
            x=x,
            y=y,
        )
        final_font_size = float(font_size) if font_size is not None and font_size > 0 else box["font_size"]
        if final_font_size > 0:
            fmt = label.textFormat()
            fmt.setSize(final_font_size)
            label.setTextFormat(fmt)
        try:
            if alignment == "center":
                label.setHAlign(Qt.AlignHCenter)
            elif alignment == "right":
                label.setHAlign(Qt.AlignRight)
            else:
                label.setHAlign(Qt.AlignLeft)
            if hasattr(label, "setVAlign"):
                label.setVAlign(Qt.AlignTop)
        except AttributeError:
            pass

        apply_label_geometry(label, box)
        layout.addLayoutItem(label)
        return {"layout_name": layout_name}

    @classmethod
    def _normalize_text(cls, value: str) -> str:
        """Удаляет невидимые символы и крайние пробелы, сохраняя переносы строк."""
        text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
        for ch in cls._INVISIBLE_CHARS:
            text = text.replace(ch, "")
        # Неразрывные пробелы переводим в обычные.
        text = text.replace("\u00a0", " ")

        sanitized_chars: list[str] = []
        for char in text:
            if char in {"\n", "\t"}:
                sanitized_chars.append(char)
                continue
            if unicodedata.category(char) in {"Cf", "Cc"}:
                continue
            sanitized_chars.append(char)

        normalized = "".join(sanitized_chars)
        # Убираем лишние пробелы на краях строк для стабильной геометрии текста.
        lines = [line.strip() for line in normalized.split("\n")]
        return "\n".join(lines).strip()

    @staticmethod
    def _fit_title_text(text: str) -> str:
        """Мягко ограничивает заголовок двумя строками для top-band."""
        clean = (text or "").strip()
        if not clean or "\n" in clean:
            return clean
        if len(clean) <= 42:
            return clean
        words = clean.split()
        if len(words) < 3:
            return clean
        total = len(clean)
        target = total // 2
        best_idx = 1
        best_delta = abs(len(words[0]) - target)
        prefix = words[0]
        for idx in range(1, len(words) - 1):
            prefix = prefix + " " + words[idx]
            delta = abs(len(prefix) - target)
            if delta < best_delta:
                best_delta = delta
                best_idx = idx + 1
        first = " ".join(words[:best_idx]).strip()
        second = " ".join(words[best_idx:]).strip()
        if not first or not second:
            return clean
        return f"{first}\n{second}"

    @staticmethod
    def _fit_subtitle_text(text: str) -> str:
        """Мягко ограничивает subtitle двумя строками без обрезки смысла."""
        clean = (text or "").strip()
        if not clean or "\n" in clean:
            return clean
        if len(clean) <= 52:
            return clean
        words = clean.split()
        if len(words) < 4:
            return clean
        target = len(clean) // 2
        best_idx = 1
        best_delta = abs(len(words[0]) - target)
        acc = words[0]
        for idx in range(1, len(words) - 1):
            acc = acc + " " + words[idx]
            delta = abs(len(acc) - target)
            if delta < best_delta:
                best_delta = delta
                best_idx = idx + 1
        first = " ".join(words[:best_idx]).strip()
        second = " ".join(words[best_idx:]).strip()
        if not first or not second:
            return clean
        return f"{first}\n{second}"
