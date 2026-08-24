from typing import Any

from qgis.core import QgsProject

from qgis_ai_agent.qgis_tools.base import SAFETY_READ, BaseTool
from qgis_ai_agent.qgis_tools.layout.utils import get_page_size_mm


class ListLayoutsTool(BaseTool):
    """Перечисление макетов проекта с размерами страницы."""
    name = "list_layouts"
    description = (
        "Показать макеты печати в проекте: имя, размер страницы в мм, ориентация, "
        "число элементов. Нужен, чтобы понять, куда добавлять элементы."
    )
    skill = "inspect"
    safety = SAFETY_READ
    capabilities = ["layout:list"]
    examples = ["Какие макеты уже есть?", "Есть ли готовый макет A3?"]
    constraints = []
    params_schema = []

    def summarize_call(self, params: dict[str, Any]) -> str:
        """Описание шага чтения списка макетов."""
        return "Смотрю макеты проекта."

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        manager = QgsProject.instance().layoutManager()
        layouts: list[dict[str, Any]] = []
        for layout in manager.layouts():
            width, height = get_page_size_mm(layout)
            layouts.append(
                {
                    "name": layout.name(),
                    "page_width_mm": round(width, 1),
                    "page_height_mm": round(height, 1),
                    "orientation": "landscape" if width > height else "portrait",
                    "item_count": self._item_count(layout),
                }
            )
        return {"layouts": layouts, "count": len(layouts)}

    @staticmethod
    def _item_count(layout) -> int:
        """Считает элементы макета, игнорируя служебные объекты сцены."""
        from qgis.core import QgsLayoutItem

        try:
            return sum(1 for item in layout.items() if isinstance(item, QgsLayoutItem))
        except Exception:
            return 0
