from dataclasses import dataclass
from typing import Any

from qgis.core import Qgis, QgsFeature, QgsMessageLog, QgsProject

LOG_TAG = "AI Agent"
MEMORY_PROVIDER = "memory"
# Shared by all scratch layers of one snapshot: the copies stay in RAM for as
# long as the snapshot is undoable.
MAX_PRESERVED_FEATURES = 200_000


@dataclass(frozen=True)
class ScratchLayerCopy:
    layer_id: str
    name: str
    field_names: tuple[str, ...]
    features: list[Any]


@dataclass(frozen=True)
class ScratchCopies:
    """Features of memory layers kept beside a project snapshot.

    A project file stores a memory layer's schema but not its features, so
    reading the snapshot back would recreate every scratch layer empty.
    """

    layers: tuple[ScratchLayerCopy, ...] = ()
    not_copied: tuple[str, ...] = ()


def is_memory_layer(layer: Any) -> bool:
    try:
        return str(layer.providerType()) == MEMORY_PROVIDER
    except Exception:
        return False


def scratch_layers_over_budget(project: QgsProject) -> set[str]:
    """Ids of the memory layers a snapshot taken now could not copy."""
    return {str(layer.id()) for layer, fits in _budgeted(project) if not fits}


def copy_scratch_layers(project: QgsProject) -> ScratchCopies:
    copies: list[ScratchLayerCopy] = []
    not_copied: list[str] = []
    for layer, fits in _budgeted(project):
        name = _layer_name(layer)
        if not fits:
            not_copied.append(name)
            continue
        try:
            provider = layer.dataProvider()
            field_names = tuple(str(item.name()) for item in provider.fields())
            features = list(provider.getFeatures())
        except Exception as failure:
            QgsMessageLog.logMessage(
                f"Could not copy scratch layer '{name}': {failure}", LOG_TAG, Qgis.MessageLevel.Warning
            )
            not_copied.append(name)
            continue
        copies.append(ScratchLayerCopy(str(layer.id()), name, field_names, features))
    return ScratchCopies(tuple(copies), tuple(not_copied))


def restore_scratch_layers(project: QgsProject, copies: ScratchCopies) -> list[str]:
    """Refill memory layers recreated empty by a snapshot read; return names not refilled."""
    failed: list[str] = []
    for copy in copies.layers:
        if not copy.features:
            continue
        layer = _map_layer(project, copy.layer_id)
        # A layer that came back with features needs nothing; refilling it
        # would duplicate them.
        if layer is None or not is_memory_layer(layer) or _feature_count(layer):
            continue
        try:
            _refill(layer, copy)
        except Exception as failure:
            QgsMessageLog.logMessage(
                f"Could not refill scratch layer '{copy.name}': {failure}", LOG_TAG, Qgis.MessageLevel.Warning
            )
            failed.append(copy.name)
    return failed


def _budgeted(project: QgsProject) -> list[tuple[Any, bool]]:
    budget = MAX_PRESERVED_FEATURES
    planned = []
    for layer in _project_layers(project):
        if not is_memory_layer(layer):
            continue
        count = _feature_count(layer)
        fits = count <= budget
        if fits:
            budget -= count
        planned.append((layer, fits))
    return planned


def _refill(layer: Any, copy: ScratchLayerCopy) -> None:
    provider = layer.dataProvider()
    target_fields = provider.fields()
    positions = [
        copy.field_names.index(name) if name in copy.field_names else None
        for name in (str(item.name()) for item in target_fields)
    ]
    rebuilt = []
    for source in copy.features:
        values = list(source.attributes())
        feature = QgsFeature(target_fields)
        if source.hasGeometry():
            feature.setGeometry(source.geometry())
        feature.setAttributes(
            [values[index] if index is not None and index < len(values) else None for index in positions]
        )
        rebuilt.append(feature)
    added = provider.addFeatures(rebuilt)
    if isinstance(added, tuple):
        added = added[0]
    if not added:
        raise ValueError("the memory provider refused the features")
    layer.updateExtents()
    layer.triggerRepaint()


def _feature_count(layer: Any) -> int:
    try:
        return max(0, int(layer.featureCount()))
    except Exception:
        return 0


def _project_layers(project: QgsProject) -> list[Any]:
    try:
        return list(project.mapLayers().values())
    except Exception:
        return []


def _map_layer(project: QgsProject, layer_id: str) -> Any:
    try:
        return project.mapLayer(layer_id)
    except Exception:
        return None


def _layer_name(layer: Any) -> str:
    try:
        return (layer.name() or "Unnamed").strip()
    except Exception:
        return "Unnamed"
