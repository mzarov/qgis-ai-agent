from typing import Any

from qgis_ai_agent.i18n import tr
from qgis_ai_agent.qgis_tools.base import SAFETY_READ, BaseTool
from qgis_ai_agent.qgis_tools.style.label_catalogue import LABELS
from qgis_ai_agent.qgis_tools.style.symbol_catalogue import SYMBOLS

KINDS = {"labels": LABELS, "symbol": SYMBOLS}
USAGE_NOTE = (
    "The properties are passed as a single properties object to set_labels or set_symbol. "
    "Pass only the ones you want to change: the rest keep their defaults."
)


class DescribeStyleOptionsTool(BaseTool):
    name = "describe_style_options"
    description = (
        "Show which properties of the labels or of the layer symbol can be controlled: "
        "names, types, allowed values, units of measurement. Call it before "
        "set_labels or set_symbol when you are unsure of a property name."
    )
    skill = "style"
    safety = SAFETY_READ
    constraints = []
    examples = ["Which label settings are available?", "How do I offset the labels?"]
    params_schema = [
        {
            "name": "kind",
            "type": "string",
            "enum": sorted(KINDS),
            "description": "labels for label properties, symbol for the layer symbol properties",
            "required": True,
        },
    ]

    def summarize_call(self, params: dict[str, Any]) -> str:
        kind = (params.get("kind") or "").strip()
        if not kind:
            return tr("Reading the available properties.")
        return tr("Reading the available properties: {0}.").format(kind)

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        known = _resolve(params.get("kind"))
        described = known.catalogue()
        return {
            "kind": (params.get("kind") or "").strip().lower(),
            "properties": described,
            "property_count": len(described),
            "usage": USAGE_NOTE,
        }


def _resolve(kind: Any) -> Any:
    name = str(kind or "").strip().lower()
    if name not in KINDS:
        raise ValueError(f"Unknown kind '{kind}'. Available: {', '.join(sorted(KINDS))}.")
    return KINDS[name]
