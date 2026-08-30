from typing import Any

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import SAFETY_DESTRUCTIVE, SAFETY_WRITE, BaseTool
from ai_agent.qgis_tools.common.paths import check_overwrite, output_safety
from ai_agent.qgis_tools.project.tree import project

QGZ = ".qgz"


class SaveProjectTool(BaseTool):
    name = "save_project"
    description = (
        "Save the QGIS project. Without a path it saves where the project was opened from; "
        "with a path it saves as a new file."
    )
    skill = "project"
    safety = SAFETY_WRITE
    external_effect = True
    constraints = [
        "A never-saved project requires a path",
        "An existing Save As target is never replaced unless overwrite=true",
    ]
    examples = ["Save the project", "Save the project as /data/cities.qgz"]
    params_schema = [
        {
            "name": "path",
            "type": "string",
            "description": f"Path to the project file. The {QGZ} extension is added on its own.",
            "required": False,
        },
        {
            "name": "overwrite",
            "type": "boolean",
            "description": (
                "Replace an existing Save As target. The current project file is exempt; "
                "replacing another file requires an additional destructive confirmation."
            ),
            "required": False,
        },
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        path = (params.get("path") or "").strip()
        if not path and not _current_path():
            raise ValueError("The project has never been saved, so a path is needed: give it in the path parameter.")
        prepared = dict(params)
        if path:
            target = _with_suffix(path)
            check_overwrite(target, bool(params.get("overwrite")), [_current_path()])
            prepared["path"] = target
        return prepared

    def safety_for(self, params: dict[str, Any]) -> str:
        path = (params.get("path") or "").strip()
        if not path:
            return SAFETY_WRITE
        target = _with_suffix(path)
        return output_safety(target, bool(params.get("overwrite")), [_current_path()])

    def summarize_call(self, params: dict[str, Any]) -> str:
        path = (params.get("path") or "").strip()
        if not path:
            return tr("Saving the project.")
        if self.safety_for(params) == SAFETY_DESTRUCTIVE:
            return tr("Overwriting '{0}' with the current project.").format(_with_suffix(path))
        return tr("Saving the project as '{0}'.").format(_with_suffix(path))

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        path = (params.get("path") or "").strip()
        target = _with_suffix(path) if path else _current_path()
        if not target:
            raise ValueError("Could not work out where to save the project.")
        check_overwrite(target, bool(params.get("overwrite")), [_current_path()])
        if not project().write(target):
            raise ValueError(f"QGIS could not write the project to '{target}'.")
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
