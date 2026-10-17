"""Finding and installing another plugin, in live QGIS: the repository XML, the unpacking, the start.

The network is not used: the repository list and the plugin's zip are handed in,
and the plugin folder is a temporary one on the plugin path, so nothing reaches
the real profile.
"""

import io
import os
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

import qgis.utils
from qgis.core import QgsSettings

from ai_agent.qgis_tools.plugins import find_plugin, install_plugin, repository

KEY = "aiagenttestplugin"
REPOSITORY_XML = f"""<?xml version="1.0"?>
<plugins>
  <pyqgis_plugin name="AI Agent Test Plugin" version="1.0.0" plugin_id="1">
    <description>Isochrones for testing the installer</description>
    <about>Nothing real.</about>
    <file_name>{KEY}.1.0.0.zip</file_name>
    <author_name>Tests</author_name>
    <download_url>https://plugins.qgis.org/plugins/{KEY}/version/1.0.0/download/</download_url>
    <experimental>False</experimental>
    <deprecated>False</deprecated>
    <trusted>False</trusted>
    <tags>isochrones,testing</tags>
    <downloads>12</downloads>
  </pyqgis_plugin>
  <pyqgis_plugin name="Gone" version="0.1" plugin_id="2">
    <description>Isochrones, deprecated</description>
    <file_name>Gone.0.1.zip</file_name>
    <download_url>https://plugins.qgis.org/plugins/Gone/version/0.1/download/</download_url>
    <deprecated>True</deprecated>
    <downloads>999999</downloads>
  </pyqgis_plugin>
</plugins>""".encode()
PLUGIN_INIT = """
class _Plugin:
    def __init__(self, iface):
        self.iface = iface

    def initGui(self):
        pass

    def unload(self):
        pass


def classFactory(iface):
    return _Plugin(iface)
"""
METADATA = (
    "[general]\nname=AI Agent Test Plugin\nqgisMinimumVersion=4.0\ndescription=test\nversion=1.0.0\nauthor=Tests\n"
)


def plugin_archive() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(f"{KEY}/__init__.py", PLUGIN_INIT)
        archive.writestr(f"{KEY}/metadata.txt", METADATA)
    return buffer.getvalue()


class PluginInstallTest(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = tempfile.mkdtemp(prefix="ai-agent-plugins-")
        patches = [
            mock.patch.object(install_plugin, "plugins_folder", lambda: self.folder),
            mock.patch.object(qgis.utils, "plugin_paths", [self.folder, *qgis.utils.plugin_paths]),
            mock.patch.object(sys, "path", [self.folder, *sys.path]),
            mock.patch.object(qgis.utils, "available_plugins", list(qgis.utils.available_plugins)),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.addCleanup(repository._CACHE.update, {"entries": None, "fetched": 0.0})
        self.addCleanup(self._remove_plugin)

    def _remove_plugin(self) -> None:
        if KEY in qgis.utils.active_plugins:
            qgis.utils.unloadPlugin(KEY)
        sys.modules.pop(KEY, None)
        QgsSettings().remove(repository.ENABLED_SETTING.format(KEY))

    def test_the_repository_xml_is_read_and_searched(self) -> None:
        with mock.patch.object(find_plugin, "get_bytes", return_value=REPOSITORY_XML):
            found = find_plugin.FindPluginTool().execute({"query": "isochrones"})["plugins"]
        self.assertEqual([plugin["plugin"] for plugin in found], [KEY], "a deprecated plugin was offered")
        self.assertEqual((found[0]["author"], found[0]["downloads"], found[0]["installed"]), ("Tests", 12, False))

    def test_a_plugin_is_installed_started_and_kept_enabled(self) -> None:
        with mock.patch.object(find_plugin, "get_bytes", return_value=REPOSITORY_XML):
            find_plugin.FindPluginTool().execute({"query": "isochrones"})
        tool = install_plugin.InstallPluginTool()
        prepared = tool.prepare({"plugin": KEY})
        with mock.patch.object(install_plugin, "get_bytes", return_value=plugin_archive()):
            payload = tool.execute(prepared)
        self.assertEqual(payload["installed"], KEY)
        self.assertTrue(os.path.isfile(os.path.join(self.folder, KEY, "metadata.txt")))
        self.assertIn(KEY, qgis.utils.active_plugins)
        self.assertTrue(QgsSettings().value(repository.ENABLED_SETTING.format(KEY), False, type=bool))
        self.assertTrue(tool.confirm_applied(prepared, payload))
        with self.assertRaisesRegex(ValueError, "already installed and active"):
            tool.prepare({"plugin": KEY})


if __name__ == "__main__":
    unittest.main()
