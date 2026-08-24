from typing import Any

from qgis.core import QgsFeatureRequest, QgsVectorLayer

from qgis_ai_agent.qgis_tools.base import SAFETY_READ, BaseTool
from qgis_ai_agent.qgis_tools.inspect.utils import find_layer_by_name

DEFAULT_LIMIT = 5
MAX_LIMIT = 20
MAX_VALUE_CHARS = 120


class SampleFeaturesTool(BaseTool):
    name = "sample_features"
    description = (
        "Показать несколько реальных записей слоя со значениями атрибутов. "
        "Нужен, когда схемы полей мало и надо увидеть, что лежит в данных."
    )
    skill = "inspect"
    safety = SAFETY_READ
    constraints = ["Слой должен существовать и быть векторным"]
    examples = ["Покажи пару записей из слоя городов", "Как выглядят данные в этом слое?"]
    params_schema = [
        {
            "name": "layer_name",
            "type": "string",
            "description": "Имя слоя ровно как в проекте",
            "required": True,
        },
        {
            "name": "limit",
            "type": "integer",
            "description": f"Сколько записей вернуть (по умолчанию {DEFAULT_LIMIT})",
            "required": False,
        },
        {
            "name": "fields",
            "type": "array",
            "description": "Какие поля показать. По умолчанию все.",
            "required": False,
        },
    ]

    def summarize_call(self, params: dict[str, Any]) -> str:
        layer_name = (params.get("layer_name") or "").strip()
        return f"Смотрю записи слоя «{layer_name}»."

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        layer = find_layer_by_name(params.get("layer_name") or "")
        if not isinstance(layer, QgsVectorLayer):
            raise ValueError(f"Слой «{layer.name()}» не векторный, записей у него нет.")
        limit = self._resolve_limit(params.get("limit"))
        wanted = self._wanted_fields(layer, params.get("fields"))

        features = []
        for feature in layer.getFeatures(QgsFeatureRequest().setLimit(limit)):
            features.append(self._describe_feature(feature, wanted))
        return {
            "layer_name": layer.name(),
            "shown": len(features),
            "total": self._total(layer),
            "features": features,
        }

    @staticmethod
    def _resolve_limit(raw: Any) -> int:
        try:
            value = int(raw) if raw is not None else DEFAULT_LIMIT
        except (TypeError, ValueError):
            value = DEFAULT_LIMIT
        return max(1, min(value, MAX_LIMIT))

    @staticmethod
    def _wanted_fields(layer: QgsVectorLayer, raw: Any) -> list[str] | None:
        if not isinstance(raw, list) or not raw:
            return None
        available = set(layer.fields().names())
        wanted = [str(name) for name in raw if str(name) in available]
        return wanted or None

    @staticmethod
    def _describe_feature(feature, wanted: list[str] | None) -> dict[str, Any]:
        attributes: dict[str, Any] = {}
        try:
            names = feature.fields().names()
        except Exception:
            names = []
        for name in names:
            if wanted is not None and name not in wanted:
                continue
            attributes[name] = _plain(feature[name])
        entry: dict[str, Any] = {"attributes": attributes}
        geometry_type = _geometry_type(feature)
        if geometry_type:
            entry["geometry"] = geometry_type
        return entry

    @staticmethod
    def _total(layer: QgsVectorLayer) -> int | None:
        try:
            return int(layer.featureCount())
        except Exception:
            return None


def _geometry_type(feature) -> str:
    try:
        geometry = feature.geometry()
        if geometry.isEmpty():
            return "пусто"
        return str(geometry.type()).split(".")[-1]
    except Exception:
        return ""


def _plain(value: Any) -> Any:
    if value is None or isinstance(value, (int, float, bool)):
        return value
    try:
        if value.isNull():
            return None
    except AttributeError:
        pass
    text = value if isinstance(value, str) else str(value)
    return text if len(text) <= MAX_VALUE_CHARS else text[:MAX_VALUE_CHARS] + "…"
