import json
import os
import tempfile
from typing import Any

BACKUP_SUFFIX = ".bak"


def read_json(path: str) -> Any:
    for candidate in (path, backup_path(path)):
        try:
            with open(candidate, encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, ValueError):
            continue
    return None


def atomic_write_json(path: str, payload: Any) -> None:
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    current = _valid_bytes(path)
    if current is not None:
        _atomic_write(backup_path(path), current)
    _atomic_write(path, encoded)


def backup_path(path: str) -> str:
    return path + BACKUP_SUFFIX


def _valid_bytes(path: str) -> bytes | None:
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
        json.loads(raw)
        return raw
    except (OSError, ValueError):
        return None


def _atomic_write(path: str, payload: bytes) -> None:
    folder = os.path.dirname(path) or os.curdir
    os.makedirs(folder, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".qgis-ai-agent-", suffix=".tmp", dir=folder)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _sync_folder(folder)
    except Exception:
        try:
            os.remove(temporary)
        except OSError:
            pass
        raise


def _sync_folder(folder: str) -> None:
    try:
        descriptor = os.open(folder, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)
