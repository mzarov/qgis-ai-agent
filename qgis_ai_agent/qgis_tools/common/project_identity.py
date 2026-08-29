import hashlib
import os
import uuid
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

UNSAVED_PREFIX = "unsaved:"
STORAGE_PREFIX = "storage:"
UNSAVED_ATTRIBUTE = "_qgis_ai_agent_unsaved_identity"
CONNECTION_ATTRIBUTE = "_qgis_ai_agent_identity_connected"
STORAGE_SCHEMES = {"geopackage", "oracle", "postgresql"}
SENSITIVE_URI_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "authcfg",
    "key",
    "passwd",
    "password",
    "pwd",
    "secret",
    "token",
    "user",
    "username",
}
_UNSAVED_BY_OBJECT: dict[int, str] = {}
_CONNECTED_OBJECTS: set[int] = set()


def project_identity(project: Any) -> str:
    name = _project_name(project)
    if name:
        if _has_project_storage(project):
            return _storage_identity(name)
        absolute = _absolute_file_path(project)
        if absolute:
            return canonical_path(absolute)
        if _looks_like_storage_uri(name):
            return _storage_identity(name)
        return canonical_path(name)
    return UNSAVED_PREFIX + _unsaved_identity(project)


def canonical_path(path: str) -> str:
    expanded = os.path.expanduser(path)
    return os.path.normcase(os.path.realpath(os.path.abspath(expanded)))


def restore_project_identity(project: Any, identity: str) -> None:
    if not isinstance(identity, str) or not identity.startswith(UNSAVED_PREFIX):
        return
    token = identity[len(UNSAVED_PREFIX) :]
    if not token:
        return
    _UNSAVED_BY_OBJECT[id(project)] = token
    _set_attribute(project, UNSAVED_ATTRIBUTE, token)
    _connect_clear(project)


def _project_name(project: Any) -> str:
    try:
        name = project.fileName()
    except Exception:
        return ""
    return name if isinstance(name, str) else ""


def _absolute_file_path(project: Any) -> str:
    try:
        path = project.absoluteFilePath()
    except Exception:
        return ""
    return path if isinstance(path, str) else ""


def _has_project_storage(project: Any) -> bool:
    try:
        return project.projectStorage() is not None
    except Exception:
        return False


def _looks_like_storage_uri(name: str) -> bool:
    try:
        scheme = urlsplit(name).scheme.lower()
    except ValueError:
        return "://" in name
    return bool(scheme) and (scheme in STORAGE_SCHEMES or "://" in name)


def _storage_identity(uri: str) -> str:
    normalized = _normalized_storage_uri(uri)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return STORAGE_PREFIX + digest


def _normalized_storage_uri(uri: str) -> str:
    try:
        parsed = urlsplit(uri)
        netloc = parsed.netloc.rsplit("@", 1)[-1].lower()
        query = [
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if key.strip().lower() not in SENSITIVE_URI_KEYS
        ]
        return urlunsplit((parsed.scheme.lower(), netloc, parsed.path, urlencode(sorted(query)), parsed.fragment))
    except ValueError:
        return uri


def _unsaved_identity(project: Any) -> str:
    token = getattr(project, UNSAVED_ATTRIBUTE, "")
    if not isinstance(token, str) or not token:
        token = _UNSAVED_BY_OBJECT.get(id(project)) or uuid.uuid4().hex
    _UNSAVED_BY_OBJECT[id(project)] = token
    _set_attribute(project, UNSAVED_ATTRIBUTE, token)
    _connect_clear(project)
    return token


def _connect_clear(project: Any) -> None:
    connected = getattr(project, CONNECTION_ATTRIBUTE, False) is True or id(project) in _CONNECTED_OBJECTS
    if connected:
        return
    try:
        project.cleared.connect(lambda: _rotate_unsaved_identity(project))
        _set_attribute(project, CONNECTION_ATTRIBUTE, True)
        _CONNECTED_OBJECTS.add(id(project))
    except Exception:
        return


def _rotate_unsaved_identity(project: Any) -> None:
    token = uuid.uuid4().hex
    _UNSAVED_BY_OBJECT[id(project)] = token
    _set_attribute(project, UNSAVED_ATTRIBUTE, token)


def _set_attribute(project: Any, name: str, value: Any) -> None:
    try:
        setattr(project, name, value)
    except Exception:
        return
