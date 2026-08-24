from typing import Any

from qgis.core import (
    QgsLayoutItemPage,
    QgsPrintLayout,
    QgsProject,
)

from qgis_ai_agent.qgis_tools.base import BaseTool


class CreateLayoutTool(BaseTool):
    """Создание нового печатного макета с заданной страницей."""
    name = "create_layout"
    description = "Создать новый макет печати с одной страницей без автодобавления текста."
    capabilities = ["layout:create", "layout:page"]
    examples = ["Создай макет A4 «Карта района»", "Сделай альбомный A3 макет"]
    constraints = ["Не создавать новый макет, если имя уже существует"]
    params_schema = [
        {"name": "layout_name", "type": "string", "description": "Уникальное имя макета", "required": True},
        {"name": "page_size", "type": "string", "description": "Размер страницы: A4, A3, A5, A0", "required": False},
        {"name": "orientation", "type": "string", "description": "portrait или landscape", "required": False},
    ]

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layout_name = (params.get("layout_name") or "").strip() or "Макет ИИ"
        page_size = (params.get("page_size") or "A4").strip().upper()[:2]
        orientation = (params.get("orientation") or "portrait").lower()

        project = QgsProject.instance()
        manager = project.layoutManager()
        if manager.layoutByName(layout_name):
            return {"layout_name": layout_name}

        layout = QgsPrintLayout(project)
        layout.setName(layout_name)
        layout.initializeDefaults()
        page = layout.pageCollection().page(0)
        if page:
            try:
                orient = QgsLayoutItemPage.Landscape if orientation == "landscape" else QgsLayoutItemPage.Portrait
                page.setPageSize(page_size, orient)
            except Exception:
                pass
        manager.addLayout(layout)

        return {"layout_name": layout_name}
