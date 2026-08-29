import importlib.util
import os
import pathlib
import sys
import tempfile
import zipfile

from qgis.core import Qgis, QgsApplication, QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtNetwork import QNetworkRequest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
MINIMUM_QGIS_VERSION = 40000
EXPECTED_TOOLS = 65
EXPECTED_SKILLS = 12


def main() -> int:
    with tempfile.TemporaryDirectory() as temporary:
        package_root = _build_and_extract(pathlib.Path(temporary))
        sys.path.insert(0, os.fspath(package_root.parent))
        application = QgsApplication([], False)
        application.initQgis()
        try:
            return _run_checks(package_root)
        finally:
            application.exitQgis()


def _build_and_extract(root: pathlib.Path) -> pathlib.Path:
    source = REPO_ROOT / "tools" / "build_plugin.py"
    spec = importlib.util.spec_from_file_location("ai_agent_build_plugin", source)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load the plugin builder at {source}")
    build_plugin = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build_plugin)
    archive_path = pathlib.Path(build_plugin.build(root))
    installation = root / "installation"
    with zipfile.ZipFile(archive_path) as archive:
        archive.extractall(installation)
    return installation / build_plugin.PLUGIN_NAME


def _run_checks(package_root: pathlib.Path) -> int:
    import ai_agent
    from ai_agent.qgis_tools.common.layers import find_layer_by_id, find_layer_by_name
    from ai_agent.qgis_tools.common.project_identity import STORAGE_PREFIX, project_identity
    from ai_agent.qgis_tools.project.snapshots import (
        drop_last,
        ensure_project_read_safe,
        snapshot_error,
        take_snapshot,
    )
    from ai_agent.qgis_tools.registry import ALL_TOOLS
    from ai_agent.qgis_tools.web.http import TIMEOUT_MS, _network_request
    from ai_agent.skills.registry import SKILL_REGISTRY

    plugin = ai_agent.classFactory(object())
    icon = QIcon(os.fspath(package_root / "icon.svg"))
    loaded_package = pathlib.Path(ai_agent.__file__).resolve().parent
    project = QgsProject.instance()
    project.clear()
    first_identity = project_identity(project)
    stable_identity = project_identity(project) == first_identity
    project.clear()
    second_identity = project_identity(project)
    rotated_identity = second_identity != first_identity
    edit_guard, edit_snapshot = _active_edit_buffer_checks(
        project,
        ensure_project_read_safe,
        take_snapshot,
        snapshot_error,
    )
    snapshot_path = take_snapshot()
    snapshot_preserved = bool(snapshot_path) and not project.fileName() and project_identity(project) == second_identity
    duplicate_guard, id_resolution = _duplicate_layer_checks(project, find_layer_by_name, find_layer_by_id)
    web_request_policy = _web_request_policy(_network_request, TIMEOUT_MS)
    tool_names = {tool.name for tool in ALL_TOOLS}
    project.setFileName("geopackage:/tmp/ai-agent-projects.gpkg?projectName=smoke")
    storage_identity = project_identity(project)
    storage_uri_hashed = storage_identity.startswith(STORAGE_PREFIX) and "geopackage" not in storage_identity
    project.clear()
    if snapshot_path:
        drop_last()
        pathlib.Path(snapshot_path).unlink(missing_ok=True)
    checks = {
        "QGIS 4.0+": Qgis.QGIS_VERSION_INT >= MINIMUM_QGIS_VERSION,
        "plugin imported from extracted ZIP": loaded_package == package_root.resolve(),
        "plugin composition root": plugin is not None,
        "brand icon": not icon.isNull(),
        "stable unsaved project identity": stable_identity,
        "new project identity after clear": rotated_identity,
        "active edit buffer blocks project read": edit_guard,
        "active edit buffer blocks snapshot": edit_snapshot,
        "snapshot preserves unsaved identity": snapshot_preserved,
        "project storage URI is hashed": storage_uri_hashed,
        "duplicate layer names are rejected": duplicate_guard,
        "duplicate layers resolve by id": id_resolution,
        "tool registry": len(ALL_TOOLS) == EXPECTED_TOOLS,
        "new tools in registry": {
            "search_web",
            "fetch_url",
            "geocode",
            "add_annotation",
            "list_annotations",
            "remove_annotation",
            "open_3d_view",
        }.issubset(tool_names),
        "web network policy": web_request_policy,
        "skill registry": len(SKILL_REGISTRY.names()) == EXPECTED_SKILLS,
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        print("Real QGIS smoke failed: " + ", ".join(failed), file=sys.stderr)
        return 1
    print(f"Real QGIS smoke passed on {Qgis.QGIS_VERSION}: {EXPECTED_TOOLS} tools, {EXPECTED_SKILLS} skills")
    return 0


def _duplicate_layer_checks(project, find_by_name, find_by_id) -> tuple[bool, bool]:
    layers = [
        QgsVectorLayer("Point?crs=EPSG:4326", "duplicate", "memory"),
        QgsVectorLayer("Point?crs=EPSG:4326", "duplicate", "memory"),
    ]
    project.addMapLayers(layers)
    try:
        try:
            find_by_name("duplicate")
            ambiguous = False
        except ValueError as failure:
            ambiguous = "ambiguous" in str(failure).lower()
        resolved = all(find_by_id(layer.id()).id() == layer.id() for layer in layers)
        return ambiguous, resolved
    finally:
        project.removeMapLayers([layer.id() for layer in layers])


def _active_edit_buffer_checks(project, ensure_read_safe, take_project_snapshot, last_error) -> tuple[bool, bool]:
    layer = QgsVectorLayer("Point?crs=EPSG:4326", "editing", "memory")
    project.addMapLayer(layer)
    feature = QgsFeature(layer.fields())
    feature.setGeometry(QgsGeometry.fromWkt("Point (0 0)"))
    changed = layer.startEditing() and layer.addFeature(feature)
    try:
        try:
            ensure_read_safe(project)
            guarded = False
        except ValueError:
            guarded = True
        rejected = take_project_snapshot() == "" and "edit buffer" in last_error().lower()
        return changed and guarded, rejected
    finally:
        layer.rollBack()
        project.removeMapLayer(layer.id())


def _web_request_policy(build_request, timeout_ms: int) -> bool:
    request = build_request("https://example.com/", {}, address="93.184.216.34")
    return (
        request.url().host() == "93.184.216.34"
        and request.peerVerifyName() == "example.com"
        and bytes(request.rawHeader(b"Host")) == b"example.com"
        and request.attribute(QNetworkRequest.Attribute.RedirectPolicyAttribute)
        == QNetworkRequest.RedirectPolicy.ManualRedirectPolicy
        and request.attribute(QNetworkRequest.Attribute.CacheLoadControlAttribute)
        == QNetworkRequest.CacheLoadControl.AlwaysNetwork
        and request.attribute(QNetworkRequest.Attribute.CacheSaveControlAttribute) is False
        and request.attribute(QNetworkRequest.Attribute.Http2AllowedAttribute) is False
        and request.attribute(QNetworkRequest.Attribute.CookieLoadControlAttribute)
        == QNetworkRequest.LoadControl.Manual
        and request.attribute(QNetworkRequest.Attribute.CookieSaveControlAttribute)
        == QNetworkRequest.LoadControl.Manual
        and request.attribute(QNetworkRequest.Attribute.AuthenticationReuseAttribute)
        == QNetworkRequest.LoadControl.Manual
        and request.transferTimeout() == timeout_ms
    )


if __name__ == "__main__":
    sys.exit(main())
