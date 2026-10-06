"""Connectors: the sources of the open-data catalogue, one JSON file each in sources/.

A connector is one provider — NASA, IGN France — with the datasets it serves.
Turning one off hides its datasets from the agent and refuses loading them.
The files are data, not code, so a new source is a new file; they are checked
strictly on load because a typo would otherwise surface only as a broken layer.
The person-facing texts (summary, description, examples, titles) are extracted
into the translation catalogue by tools/update_translations.py.
"""

import json
import pathlib
from dataclasses import dataclass, field, fields
from typing import Any

from ai_agent.qgis_tools.data.dataset import (
    KIND_IMAGERY,
    KIND_POINTER,
    KIND_SERVICE,
    KIND_VECTOR,
    SERVICE_WFS,
    SERVICE_WMS,
    SERVICE_XYZ,
    Dataset,
    ServiceLayer,
)

SOURCES = pathlib.Path(__file__).resolve().parent / "sources"
CATEGORY_WORLD = "world"
CATEGORY_IMAGERY = "imagery"
CATEGORY_TERRAIN = "terrain"
CATEGORY_PEOPLE = "people"
CATEGORY_NATIONAL = "national"
CATEGORIES = (CATEGORY_WORLD, CATEGORY_IMAGERY, CATEGORY_TERRAIN, CATEGORY_PEOPLE, CATEGORY_NATIONAL)
KINDS = (KIND_VECTOR, KIND_IMAGERY, KIND_SERVICE, KIND_POINTER)
PROTOCOLS = ("", SERVICE_XYZ, SERVICE_WMS, SERVICE_WFS)
CONNECTOR_REQUIRED = {
    "id",
    "title",
    "category",
    "order",
    "summary",
    "description",
    "examples",
    "licence",
    "hosts",
    "datasets",
}
CONNECTOR_OPTIONAL = {"monogram"}
DATASET_REQUIRED = {"id", "title", "kind", "summary", "coverage", "license", "keywords"}
# A dataset's title names its layers in QGIS; a label, when a bare name says little, is what the settings page shows.
DATASET_LABEL = "label"
LAYER_REQUIRED = {"key", "title", "source"}


@dataclass(frozen=True)
class Connector:
    id: str
    title: str
    category: str
    summary: str
    description: str
    examples: tuple[str, ...]
    licence: str
    hosts: tuple[str, ...]
    datasets: tuple[Dataset, ...]
    monogram: str = ""
    # Dataset id to its settings-page label, for the datasets that carry one.
    labels: dict[str, str] = field(default_factory=dict)


def load(folder: pathlib.Path = SOURCES) -> tuple[Connector, ...]:
    """Every connector file, ordered by its `order`; ValueError naming the file on the first problem."""
    found = []
    for path in sorted(folder.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            found.append((_order(raw), _connector(raw, path.stem)))
        except (ValueError, TypeError, KeyError) as error:
            raise ValueError(f"{path.name}: {error}") from error
    connectors = tuple(connector for _order_key, connector in sorted(found, key=lambda pair: pair[0]))
    _check_unique([item.id for connector in connectors for item in connector.datasets], "dataset id")
    return connectors


def _order(raw: Any) -> int:
    order = raw.get("order") if isinstance(raw, dict) else None
    if not isinstance(order, int):
        raise ValueError("order must be an integer")
    return order


def _connector(raw: dict[str, Any], stem: str) -> Connector:
    _check_keys(raw, CONNECTOR_REQUIRED, CONNECTOR_OPTIONAL, "connector")
    if raw["id"] != stem:
        raise ValueError(f"id '{raw['id']}' must match the file name")
    if raw["category"] not in CATEGORIES:
        raise ValueError(f"category '{raw['category']}' is not one of {', '.join(CATEGORIES)}")
    entries = _list(raw, "datasets", dict)
    datasets = tuple(_dataset(item) for item in entries)
    if not datasets:
        raise ValueError("a connector needs at least one dataset")
    return Connector(
        id=_text(raw, "id"),
        title=_text(raw, "title"),
        category=raw["category"],
        summary=_text(raw, "summary"),
        description=_text(raw, "description"),
        examples=tuple(_list(raw, "examples", str)),
        licence=_text(raw, "licence"),
        hosts=tuple(_list(raw, "hosts", str)),
        datasets=datasets,
        monogram=str(raw.get("monogram", "")),
        labels={item["id"]: _text(item, DATASET_LABEL) for item in entries if DATASET_LABEL in item},
    )


def _dataset(raw: dict[str, Any]) -> Dataset:
    optional = ({field.name for field in fields(Dataset)} - DATASET_REQUIRED) | {DATASET_LABEL}
    _check_keys(raw, DATASET_REQUIRED, optional, f"dataset {raw.get('id', '?')}")
    if raw["kind"] not in KINDS:
        raise ValueError(f"dataset {raw['id']}: kind '{raw['kind']}' is not one of {', '.join(KINDS)}")
    if raw.get("service", "") not in PROTOCOLS:
        raise ValueError(f"dataset {raw['id']}: unknown service '{raw['service']}'")
    values = {key: value for key, value in raw.items() if key != DATASET_LABEL}
    for key in ("keywords", "assets", "rgb", "notes"):
        if key in values:
            values[key] = tuple(_list(raw, key, str))
    layers = tuple(_layer(item, raw["id"]) for item in _list(raw, "layers", dict)) if "layers" in raw else ()
    values["layers"] = layers
    _check_unique([layer.key for layer in layers], f"layer key in {raw['id']}")
    if raw["kind"] == KIND_SERVICE and not layers:
        raise ValueError(f"dataset {raw['id']}: a service needs layers")
    return Dataset(**values)


def _layer(raw: dict[str, Any], owner: str) -> ServiceLayer:
    _check_keys(raw, LAYER_REQUIRED, {"note", "zmax", "protocol"}, f"layer of {owner}")
    if raw.get("protocol", "") not in PROTOCOLS:
        raise ValueError(f"layer {raw['key']} of {owner}: unknown protocol '{raw['protocol']}'")
    if not isinstance(raw.get("zmax", 0), int):
        raise ValueError(f"layer {raw['key']} of {owner}: zmax must be an integer")
    return ServiceLayer(**raw)


def _check_keys(raw: dict[str, Any], required: set[str], optional: set[str], what: str) -> None:
    missing = sorted(required - raw.keys())
    unknown = sorted(raw.keys() - required - optional)
    if missing or unknown:
        raise ValueError(f"{what}: missing {missing}, unknown {unknown}")


def _text(raw: dict[str, Any], key: str) -> str:
    value = raw[key]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be non-empty text")
    return value


def _list(raw: dict[str, Any], key: str, kind: type) -> list[Any]:
    value = raw[key]
    if not isinstance(value, list) or not all(isinstance(item, kind) for item in value):
        raise ValueError(f"{key} must be a list of {kind.__name__}")
    return value


def _check_unique(values: list[str], what: str) -> None:
    repeated = sorted({value for value in values if values.count(value) > 1})
    if repeated:
        raise ValueError(f"repeated {what}: {', '.join(repeated)}")


CONNECTORS = load()
DATASETS: tuple[Dataset, ...] = tuple(item for connector in CONNECTORS for item in connector.datasets)
_OWNER = {item.id: connector for connector in CONNECTORS for item in connector.datasets}


def connector_of(dataset_id: str) -> Connector | None:
    return _OWNER.get(dataset_id)
