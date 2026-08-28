from typing import Any

from qgis.core import (
    QgsColorRampShader,
    QgsHillshadeRenderer,
    QgsRasterBandStats,
    QgsRasterShader,
    QgsSingleBandGrayRenderer,
    QgsSingleBandPseudoColorRenderer,
)

from qgis_ai_agent.qgis_tools.style.apply import resolve_ramp

MODE_PSEUDOCOLOR = "pseudocolor"
MODE_GRAY = "gray"
MODE_HILLSHADE = "hillshade"
MODES = (MODE_PSEUDOCOLOR, MODE_GRAY, MODE_HILLSHADE)
INTERPOLATION = {
    "discrete": QgsColorRampShader.Type.Discrete,
    "linear": QgsColorRampShader.Type.Interpolated,
    "exact": QgsColorRampShader.Type.Exact,
}
DEFAULT_INTERPOLATION = "linear"
DEFAULT_CLASSES = 5
MIN_CLASSES = 2
MAX_CLASSES = 30
DEFAULT_RAMPS = ("Viridis", "Spectral", "Blues")
DEFAULT_AZIMUTH = 315.0
DEFAULT_ALTITUDE = 45.0


def band_range(layer: Any, band: int) -> tuple[float, float]:
    provider = layer.dataProvider()
    stats = provider.bandStatistics(band, QgsRasterBandStats.Stats.All)
    minimum = float(stats.minimumValue)
    maximum = float(stats.maximumValue)
    if maximum <= minimum:
        raise ValueError(
            f"Band {band} has no value range (min equals max) — a colour ramp over it would be meaningless."
        )
    return minimum, maximum


def checked_band(layer: Any, raw: Any) -> int:
    try:
        count = int(layer.bandCount())
    except Exception:
        count = 1
    try:
        band = int(raw) if raw is not None else 1
    except (TypeError, ValueError):
        raise ValueError(f"band must be a whole number from 1 to {count}.") from None
    if band < 1 or band > count:
        raise ValueError(f"This raster has {count} band(s), so band {band} does not exist.")
    return band


def checked_classes(raw: Any) -> int:
    if raw is None:
        return DEFAULT_CLASSES
    try:
        classes = int(raw)
    except (TypeError, ValueError):
        raise ValueError(f"classes must be a whole number from {MIN_CLASSES} to {MAX_CLASSES}.") from None
    if classes < MIN_CLASSES or classes > MAX_CLASSES:
        raise ValueError(f"classes must run from {MIN_CLASSES} to {MAX_CLASSES}.")
    return classes


def checked_interpolation(raw: Any) -> str:
    name = str(raw or DEFAULT_INTERPOLATION).strip().lower()
    if name not in INTERPOLATION:
        raise ValueError(f"Unknown interpolation '{raw}'. Available: {', '.join(sorted(INTERPOLATION))}.")
    return name


def build_pseudocolor(layer: Any, band: int, ramp_name: str, classes: int, interpolation: str) -> Any:
    minimum, maximum = band_range(layer, band)
    ramp = resolve_ramp(ramp_name, DEFAULT_RAMPS)
    shader_function = QgsColorRampShader(minimum, maximum, ramp, INTERPOLATION[interpolation])
    shader_function.setClassificationMode(QgsColorRampShader.ClassificationMode.EqualInterval)
    shader_function.classifyColorRamp(classes, -1, None, None)
    shader = QgsRasterShader()
    shader.setRasterShaderFunction(shader_function)
    renderer = QgsSingleBandPseudoColorRenderer(layer.dataProvider(), band, shader)
    return renderer, {"min": round(minimum, 4), "max": round(maximum, 4), "classes": classes}


def build_gray(layer: Any, band: int) -> Any:
    minimum, maximum = band_range(layer, band)
    renderer = QgsSingleBandGrayRenderer(layer.dataProvider(), band)
    return renderer, {"min": round(minimum, 4), "max": round(maximum, 4)}


def build_hillshade(layer: Any, band: int, azimuth: Any, altitude: Any) -> Any:
    angle = _angle(azimuth, DEFAULT_AZIMUTH, "azimuth", 0.0, 360.0)
    height = _angle(altitude, DEFAULT_ALTITUDE, "altitude", 0.0, 90.0)
    renderer = QgsHillshadeRenderer(layer.dataProvider(), band, angle, height)
    return renderer, {"azimuth": angle, "altitude": height}


def apply_no_data(layer: Any, values: Any) -> list[float]:
    if values is None:
        return []
    if not isinstance(values, list):
        raise ValueError("no_data_values must be a list of numbers to hide.")
    numbers = []
    for value in values:
        try:
            numbers.append(float(value))
        except (TypeError, ValueError):
            raise ValueError(f"'{value}' is not a number — no_data_values takes numbers only.") from None
    if numbers:
        provider = layer.dataProvider()
        for band in range(1, int(layer.bandCount()) + 1):
            provider.setUserNoDataValue(band, [_range(value) for value in numbers])
    return numbers


def _range(value: float) -> Any:
    from qgis.core import QgsRasterRange

    return QgsRasterRange(value, value)


def _angle(raw: Any, default: float, name: str, low: float, high: float) -> float:
    if raw is None:
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number of degrees from {low:g} to {high:g}.") from None
    if not low <= value <= high:
        raise ValueError(f"{name} must run from {low:g} to {high:g} degrees, got {value:g}.")
    return value
