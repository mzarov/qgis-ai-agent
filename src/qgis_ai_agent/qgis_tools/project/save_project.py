from typing import Any

from qgis_ai_agent.qgis_tools.base import SAFETY_WRITE, BaseTool
from qgis_ai_agent.qgis_tools.project.tree import project

QGZ = ".qgz"


class SaveProjectTool(BaseTool):
    name = "save_project"
    description = (
        "Сохранить проект QGIS. Без пути сохраняет туда, откуда проект открыт; "
        "с путём сохраняет как новый файл."
    )
    skill = "project"
    safety = SAFETY_WRITE
    constraints = ["Для несохранённого проекта путь обязателен"]
    examples = ["Сохрани проект", "Сохрани проект как /data/города.qgz"]
    params_schema = [
        {
            "name": "path",
            "type": "string",
            "description": f"Путь к файлу проекта. Расширение {QGZ} добавится само.",
            "required": False,
        },
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        path = (params.get("path") or "").strip()
        if not path and not _current_path():
            raise ValueError(
                "Проект ещё ни разу не сохранён, поэтому нужен путь: "
                "укажите его в параметре path."
            )
        prepared = dict(params)
        if path:
            prepared["path"] = _with_suffix(path)
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        path = (params.get("path") or "").strip()
        return f"Сохраняю проект как «{_with_suffix(path)}»." if path else "Сохраняю проект."

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        path = (params.get("path") or "").strip()
        target = _with_suffix(path) if path else _current_path()
        if not target:
            raise ValueError("Не удалось определить, куда сохранять проект.")
        if not project().write(target):
            raise ValueError(f"QGIS не смог записать проект в «{target}».")
        return {"saved": target}


def _current_path() -> str:
    try:
        name = project().fileName()
    except Exception:
        return ""
    return name if isinstance(name, str) else ""


def _with_suffix(path: str) -> str:
    clean = (path or "").strip()
    if not clean:
        return clean
    return clean if clean.lower().endswith((QGZ, ".qgs")) else clean + QGZ
