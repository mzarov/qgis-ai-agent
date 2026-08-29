import os
from collections.abc import Iterable

from qgis_ai_agent.qgis_tools.base import SAFETY_DESTRUCTIVE, SAFETY_WRITE

SHAPEFILE_SUFFIXES = (
    ".shp",
    ".shx",
    ".dbf",
    ".prj",
    ".qpj",
    ".cpg",
    ".sbn",
    ".sbx",
    ".qix",
    ".idm",
    ".ind",
    ".shp.xml",
)
CSV_SUFFIXES = (".csv", ".csvt")
GPKG_SUFFIXES = ("", "-wal", "-shm", "-journal")


def physical_path(path: str) -> str:
    return (path or "").split("|", 1)[0].strip()


def same_path(left: str, right: str) -> bool:
    if not left or not right:
        return False
    return _identity(left) == _identity(right)


def requires_overwrite(path: str, exempt_paths: Iterable[str] = ()) -> bool:
    return requires_any_overwrite(related_output_paths(path), exempt_paths)


def requires_any_overwrite(paths: Iterable[str], exempt_paths: Iterable[str] = ()) -> bool:
    exemptions = [related for exempt in exempt_paths for related in related_output_paths(exempt)]
    return any(
        target and os.path.lexists(target) and not any(same_path(target, exempt) for exempt in exemptions if exempt)
        for target in (physical_path(path) for path in paths)
    )


def check_overwrite(path: str, overwrite: bool, exempt_paths: Iterable[str] = ()) -> str:
    check_overwrites(related_output_paths(path), overwrite, exempt_paths)
    return path


def check_overwrites(paths: Iterable[str], overwrite: bool, exempt_paths: Iterable[str] = ()) -> list[str]:
    targets = [physical_path(path) for path in paths if physical_path(path)]
    if requires_any_overwrite(targets, exempt_paths) and not overwrite:
        existing = [target for target in targets if os.path.lexists(target)]
        shown = ", ".join(f"'{target}'" for target in existing[:3])
        raise ValueError(
            f"{shown} already exists. Refusing to replace output files unless overwrite=true is explicitly approved."
        )
    return targets


def output_safety(path: str, overwrite: bool, exempt_paths: Iterable[str] = ()) -> str:
    return outputs_safety(related_output_paths(path), overwrite, exempt_paths)


def outputs_safety(paths: Iterable[str], overwrite: bool, exempt_paths: Iterable[str] = ()) -> str:
    if overwrite:
        exemptions = [related for exempt in exempt_paths for related in related_output_paths(exempt)]
        if any(not any(same_path(path, exempt) for exempt in exemptions) for path in paths):
            return SAFETY_DESTRUCTIVE
    return SAFETY_WRITE


def related_output_paths(path: str) -> list[str]:
    target = physical_path(path)
    root, suffix = os.path.splitext(target)
    lowered = suffix.lower()
    if lowered == ".shp":
        return [root + item for item in SHAPEFILE_SUFFIXES]
    if lowered == ".csv":
        return [root + item for item in CSV_SUFFIXES]
    if lowered == ".gpkg":
        return [target + item for item in GPKG_SUFFIXES]
    if lowered == ".qgs":
        return [target, root + ".qgd", root + "_attachments.zip"]
    return [target] if target else []


def numbered_output_paths(path: str, count: int) -> list[str]:
    target = physical_path(path)
    root, suffix = os.path.splitext(target)
    return [target] + [f"{root}_{index}{suffix}" for index in range(2, max(1, count) + 1)]


def _identity(path: str) -> str:
    return os.path.normcase(os.path.realpath(os.path.abspath(os.path.expanduser(path))))
