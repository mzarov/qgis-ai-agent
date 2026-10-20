from typing import Any

from qgis.core import QgsFeatureRequest

MISSING = (
    "{count} feature(s) selected during planning no longer exist. Nothing was {done}; review the layer and plan again."
)
STALE = (
    "{count} feature(s) selected during planning no longer match the filter: an earlier step changed them, "
    "or renumbered the layer's features (a shapefile renumbers them after a deletion). Nothing was {done}; "
    "plan this step again once the earlier steps are applied."
)


def pinned_features(layer: Any, pinned: list[Any], request: Any, done: str) -> list[Any]:
    wanted = {int(identifier) for identifier in pinned}
    by_id = QgsFeatureRequest()
    by_id.setFilterFids(list(wanted))
    features = [feature for feature in layer.getFeatures(by_id) if feature.id() in wanted]
    missing = wanted - {feature.id() for feature in features}
    if missing:
        raise ValueError(MISSING.format(count=len(missing), done=done))
    if request is not None:
        # Ids are only stable until the source renumbers: the filter must still pick every pinned feature.
        stale = wanted - {feature.id() for feature in layer.getFeatures(request)}
        if stale:
            raise ValueError(STALE.format(count=len(stale), done=done))
    return features
