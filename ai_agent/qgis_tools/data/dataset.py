from dataclasses import dataclass, field

KIND_VECTOR = "vector"
KIND_IMAGERY = "imagery"
KIND_SERVICE = "service"
KIND_POINTER = "pointer"
TRUE_COLOR = "true_color"
SERVICE_XYZ = "xyz"
SERVICE_WMS = "wms"
SERVICE_WFS = "wfs"


@dataclass(frozen=True)
class ServiceLayer:
    key: str
    title: str
    source: str
    note: str = ""
    zmax: int = 19
    protocol: str = ""


@dataclass(frozen=True)
class Dataset:
    id: str
    title: str
    kind: str
    summary: str
    coverage: str
    license: str
    keywords: tuple[str, ...]
    load_with: str = ""
    default_asset: str = ""
    assets: tuple[str, ...] = ()
    cloudy: bool = False
    rgb: tuple[str, ...] = ()
    nodata: float | None = None
    notes: tuple[str, ...] = field(default=())
    service: str = ""
    endpoint: str = ""
    layers: tuple[ServiceLayer, ...] = ()
    attribution: str = ""
    # West, south, east, north in degrees.
    bbox: tuple[float, ...] = ()
