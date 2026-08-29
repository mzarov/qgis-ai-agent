import os
import sys
import tempfile
import zipfile
from pathlib import PurePosixPath

PLUGIN_NAME = "qgis_ai_agent"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE_DIR = os.path.join(REPO_ROOT, PLUGIN_NAME)
DIST_DIR = os.path.join(REPO_ROOT, "dist")
EXTRA_FILES = ("LICENSE",)
PACKAGE_ROOT_FILES = {".bandit", "__init__.py", "i18n.py", "icon.svg", "metadata.txt", "plugin.py"}
TREE_SUFFIXES = {
    "core": {".py"},
    "qgis_tools": {".py"},
    "skills": {".md", ".py"},
    "translations": {".qm"},
    "ui": {".py"},
}
BLOCKED_PARTS = {"__pycache__", ".git", ".mypy_cache", ".ruff_cache"}
REQUIRED_INSIDE = (
    "skills/edit/SKILL.md",
    "skills/fields/SKILL.md",
    "skills/inspect/SKILL.md",
    "skills/layout/SKILL.md",
    "skills/osm/SKILL.md",
    "skills/processing/SKILL.md",
    "skills/project/SKILL.md",
    "skills/python/SKILL.md",
    "skills/style/SKILL.md",
    "translations/qgis_ai_agent_ru.qm",
)
ARCHIVE_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
ARCHIVE_MODE = 0o100644


def read_version() -> str:
    path = os.path.join(PACKAGE_DIR, "metadata.txt")
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("version="):
                return line.split("=", 1)[1].strip()
    raise SystemExit("metadata.txt has no version= line")


def is_package_file_allowed(relative: str) -> bool:
    normalized = relative.replace(os.sep, "/").strip("/")
    parts = PurePosixPath(normalized).parts
    if not parts or any(part in BLOCKED_PARTS or part.startswith(".") for part in parts[1:]):
        return False
    if len(parts) == 1:
        return parts[0] in PACKAGE_ROOT_FILES
    suffixes = TREE_SUFFIXES.get(parts[0])
    if suffixes is None or PurePosixPath(normalized).suffix not in suffixes:
        return False
    return parts[0] != "skills" or PurePosixPath(normalized).suffix == ".py" or parts[-1] == "SKILL.md"


def collect() -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    for name in EXTRA_FILES:
        absolute = os.path.join(REPO_ROOT, name)
        if not os.path.isfile(absolute):
            raise SystemExit(f"Required file {name} not found")
        entries.append((absolute, f"{PLUGIN_NAME}/{name}"))
    for folder, dirs, names in os.walk(PACKAGE_DIR):
        relative_folder = os.path.relpath(folder, PACKAGE_DIR)
        dirs[:] = sorted(
            item
            for item in dirs
            if any(
                is_package_file_allowed(os.path.join(relative_folder, item, placeholder))
                for placeholder in ("placeholder.py", "placeholder.md", "placeholder.qm")
            )
        )
        for name in sorted(names):
            absolute = os.path.join(folder, name)
            relative = os.path.relpath(absolute, PACKAGE_DIR)
            if not is_package_file_allowed(relative):
                continue
            if os.path.islink(absolute):
                raise SystemExit(f"Refusing to package symlink: {relative}")
            arcname = f"{PLUGIN_NAME}/{relative.replace(os.sep, '/')}"
            entries.append((absolute, arcname))
    return sorted(entries, key=lambda entry: entry[1])


def verify(entries: list[tuple[str, str]]) -> None:
    packed = {arc for _, arc in entries}
    missing = [tail for tail in REQUIRED_INSIDE if not any(arc.endswith(tail) for arc in packed)]
    if missing:
        raise SystemExit("Required content missing from the build: " + ", ".join(missing))
    for tail in (f"{PLUGIN_NAME}/plugin.py", f"{PLUGIN_NAME}/metadata.txt"):
        if tail not in packed:
            raise SystemExit(f"{tail} missing from the build")


def build(output_dir: str | os.PathLike[str] | None = None) -> str:
    entries = collect()
    verify(entries)
    destination = os.fspath(output_dir) if output_dir is not None else DIST_DIR
    os.makedirs(destination, exist_ok=True)
    target = os.path.join(destination, f"{PLUGIN_NAME}-{read_version()}.zip")
    descriptor, temporary = tempfile.mkstemp(prefix=f".{PLUGIN_NAME}-", suffix=".zip", dir=destination)
    os.close(descriptor)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for absolute, arcname in entries:
                _write_entry(archive, absolute, arcname)
        os.replace(temporary, target)
    except Exception:
        try:
            os.remove(temporary)
        except OSError:
            pass
        raise
    return target


def _write_entry(archive: zipfile.ZipFile, absolute: str, arcname: str) -> None:
    info = zipfile.ZipInfo(arcname, ARCHIVE_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = ARCHIVE_MODE << 16
    with open(absolute, "rb") as handle:
        archive.writestr(info, handle.read(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def main() -> None:
    target = build()
    size_kb = os.path.getsize(target) / 1024
    with zipfile.ZipFile(target) as archive:
        count = len(archive.namelist())
    print(f"Built: {os.path.relpath(target, REPO_ROOT)}")
    print(f"Files: {count}, size: {size_kb:.0f} KB")
    print(f"Top-level folder in the archive: {PLUGIN_NAME}/")


if __name__ == "__main__":
    sys.exit(main())
