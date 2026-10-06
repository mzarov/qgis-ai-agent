"""What a catalogue entry is: one dataset the agent can load, and for web services the layers it offers."""

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
    """One layer of a web service: an XYZ URL template, a WMS layer name or a WFS type name."""

    key: str
    title: str
    source: str
    note: str = ""
    zmax: int = 19
    # Overrides the dataset's protocol: IGN France serves tiles and WFS vectors under one connector.
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
    # Imagery: the STAC asset loaded by default, the ones offered, and whether scenes carry cloud cover.
    default_asset: str = ""
    assets: tuple[str, ...] = ()
    cloudy: bool = False
    # Assets stacked into one RGB layer for TRUE_COLOR when the collection has no ready-made picture.
    rgb: tuple[str, ...] = ()
    # The pixel value that means "no data here": drawn transparent instead of a black frame.
    nodata: float | None = None
    notes: tuple[str, ...] = field(default=())
    # Web services: the protocol, the endpoint for WMS/WFS, the layers offered and the credit to show.
    service: str = ""
    endpoint: str = ""
    layers: tuple[ServiceLayer, ...] = ()
    attribution: str = ""
