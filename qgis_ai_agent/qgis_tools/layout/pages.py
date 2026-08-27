from typing import Any

from qgis.core import QgsProject

PAGE_SIZES_MM = {
    "a5": (148.0, 210.0),
    "a4": (210.0, 297.0),
    "a3": (297.0, 420.0),
    "a2": (420.0, 594.0),
    "letter": (215.9, 279.4),
}
PORTRAIT = "portrait"
LANDSCAPE = "landscape"
ORIENTATIONS = (PORTRAIT, LANDSCAPE)
DEFAULT_PAGE = "a4"
DEFAULT_ORIENTATION = LANDSCAPE


def layout_manager() -> Any:
    return QgsProject.instance().layoutManager()


def find_layout(name: str) -> Any:
    wanted = (name or "").strip()
    layout = layout_manager().layoutByName(wanted) if wanted else None
    if layout is None:
        names = [item.name() for item in layout_manager().printLayouts()]
        hint = ", ".join(f"'{title}'" for title in names) or "the project has no layouts"
        raise ValueError(f"Layout not found: '{wanted}'. Available: {hint}.")
    return layout


def layout_names() -> list[str]:
    try:
        return [item.name() for item in layout_manager().printLayouts()]
    except Exception:
        return []


def page_size_mm(page: str, orientation: str) -> tuple[float, float]:
    wanted = (page or DEFAULT_PAGE).strip().lower()
    if wanted not in PAGE_SIZES_MM:
        raise ValueError(f"Unknown page size '{page}'. Available: {', '.join(sorted(PAGE_SIZES_MM))}.")
    direction = (orientation or DEFAULT_ORIENTATION).strip().lower()
    if direction not in ORIENTATIONS:
        raise ValueError(f"Unknown orientation '{orientation}'. Available: {', '.join(ORIENTATIONS)}.")
    width, height = PAGE_SIZES_MM[wanted]
    if direction == LANDSCAPE:
        return height, width
    return width, height


def current_page_mm(layout: Any) -> tuple[float, float]:
    try:
        size = layout.pageCollection().page(0).pageSize()
        return float(size.width()), float(size.height())
    except Exception:
        return PAGE_SIZES_MM[DEFAULT_PAGE]
