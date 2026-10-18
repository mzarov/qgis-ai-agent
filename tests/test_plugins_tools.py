import unittest
from unittest import mock

from ai_agent.qgis_tools.plugins import describe_plugin, discovery, list_plugins, run_plugin_command

META = {
    ("geoai", "name"): "GeoAI",
    ("geoai", "description"): "AI segmentation of satellite imagery",
    ("geoai", "version"): "1.8.1",
    ("qgis2web", "name"): "qgis2web",
    ("qgis2web", "description"): "Export to an OpenLayers or Leaflet web map",
}


class Action:
    def __init__(self, text, menu=None, separator=False):
        self._text, self._menu, self._separator = text, menu, separator

    def text(self):
        return self._text

    def menu(self):
        return self._menu

    def isSeparator(self):
        return self._separator

    def trigger(self):
        pass


class Menu:
    def __init__(self, *actions):
        self._actions = list(actions)

    def actions(self):
        return self._actions


class Provider:
    def __init__(self, identifier, algorithms):
        self._id, self._algorithms = identifier, algorithms

    def id(self):
        return self._id

    def algorithms(self):
        return [
            mock.Mock(id=lambda a=a: f"{self._id}:{a}", displayName=lambda a=a: a.title()) for a in self._algorithms
        ]


EXPORT = Action("&Create web map from project…")
MENU_BAR = [
    Action("&Web", Menu(Action("qgis2web", Menu(EXPORT, Action("", separator=True))), Action("Other", Menu()))),
    Action("&Plugins", Menu(Action("Python Console"))),
]


class DiscoveryTest(unittest.TestCase):
    def setUp(self):
        utils = mock.Mock(active_plugins=["geoai", "ai_agent", "qgis2web"])
        utils.pluginMetadata.side_effect = lambda plugin, key: META.get((plugin, key), "__error__")
        utils.iface.mainWindow.return_value.menuBar.return_value.actions.return_value = MENU_BAR
        patcher = mock.patch.object(discovery, "qgis_utils", return_value=utils)
        patcher.start()
        self.addCleanup(patcher.stop)
        provider = type("GeoAiProvider", (Provider,), {"__module__": "geoai.provider"})("geoai", ["segment", "detect"])
        other = Provider("native", ["buffer"])
        registry = mock.patch.object(
            discovery.QgsApplication, "processingRegistry", return_value=mock.Mock(providers=lambda: [provider, other])
        )
        registry.start()
        self.addCleanup(registry.stop)

    def test_the_list_skips_this_plugin_and_filters_by_words(self):
        listed = list_plugins.ListPluginsTool().execute({})
        self.assertEqual([entry["plugin"] for entry in listed["plugins"]], ["geoai", "qgis2web"])
        self.assertEqual(listed["plugins"][0]["processing_providers"], ["geoai"])
        self.assertEqual(listed["plugins"][1]["menu_commands"], 1)
        found = list_plugins.ListPluginsTool().execute({"query": "segmentation"})
        self.assertEqual([entry["plugin"] for entry in found["plugins"]], ["geoai"])

    def test_a_plugin_is_found_by_display_name_and_described(self):
        described = describe_plugin.DescribePluginTool().execute({"plugin": "GeoAI"})
        self.assertEqual(described["plugin"], "geoai")
        self.assertEqual([item["id"] for item in described["processing_algorithms"]], ["geoai:segment", "geoai:detect"])
        web = describe_plugin.DescribePluginTool().execute({"plugin": "qgis2web"})
        self.assertEqual(web["menu_commands"], ["Web › qgis2web › Create web map from project"])
        with self.assertRaisesRegex(ValueError, "Active plugins: geoai, qgis2web"):
            discovery.require_plugin("mapflow")

    def test_a_command_is_started_after_the_step_returns(self):
        tool = run_plugin_command.RunPluginCommandTool()
        prepared = tool.prepare({"plugin": "qgis2web", "command": "Create web map from project"})
        self.assertEqual(tool.safety_for(prepared), "destructive")
        self.assertIn("not of AI Agent", tool.detail_call(prepared))
        with mock.patch.object(run_plugin_command.QTimer, "singleShot") as later:
            result = tool.execute(prepared)
        self.assertEqual(result["started"], "Web › qgis2web › Create web map from project")
        self.assertEqual(later.call_args.args, (0, EXPORT.trigger))
        with self.assertRaisesRegex(ValueError, "Its commands"):
            tool.prepare({"plugin": "qgis2web", "command": "Delete everything"})

    def test_the_confirmation_shows_a_warning_not_a_code_listing(self):
        from ai_agent.core.llm.turns import ToolCall
        from ai_agent.core.orchestrator.planning import CodeDetails, destructive_lines
        from ai_agent.ui.confirmations import destructive_confirmation_text

        call = ToolCall("1", "run_plugin_command", {"plugin": "qgis2web", "command": "Create web map from project"})
        lines, details = destructive_lines([call])
        self.assertNotIsInstance(details, CodeDetails)
        text = destructive_confirmation_text(lines, details)
        self.assertNotIn("Exact code", text)
        self.assertIn("not of AI Agent", text)
        python = ToolCall("2", "run_python", {"code": "print(1)", "intent": "smoke"})
        self.assertIsInstance(destructive_lines([python])[1], CodeDetails)

    def test_menu_text_loses_mnemonics_and_ellipses(self):
        self.assertEqual(discovery._clean("&Save && Close…"), "Save & Close")

    def test_a_menu_counts_as_the_plugins_own_only_when_it_carries_most_of_its_name(self):
        names = {"quickmapservices", "nextgisquickmapservices"}
        self.assertTrue(discovery._matches("Quick&MapServices", names))
        self.assertFalse(discovery._matches("Processing", {"grassprovider", "grassprocessingprovider"}))
        self.assertFalse(discovery._matches("Geoprocessing Tools", {"processing"}))


if __name__ == "__main__":
    unittest.main()


ORS = {
    "key": "ORStools",
    "name": "ORS Tools",
    "version": "2.2.0",
    "description": "openrouteservice routing, isochrones and matrix calculations for QGIS",
    "about": "",
    "tags": ["isochrones", "route", "openrouteservice"],
    "author": "HeiGIT gGmbH",
    "downloads": 415495,
    "experimental": False,
    "deprecated": False,
    "download_url": "https://plugins.qgis.org/plugins/ORStools/version/2.2.0/download/",
}
QNEAT = {
    **ORS,
    "key": "QNEAT",
    "name": "QNEAT",
    "description": "QGIS Network Analysis Toolbox",
    "tags": ["network analysis", "isochrones"],
    "downloads": 786,
}
OLD = {**ORS, "key": "OldRoute", "name": "Old Route", "deprecated": True, "downloads": 10**7}


def plugin_zip(files):
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in files.items():
            archive.writestr(name, text)
    return buffer.getvalue()


class RepositoryTest(unittest.TestCase):
    def setUp(self):
        from ai_agent.qgis_tools.plugins import repository

        self.repository = repository
        self.addCleanup(repository._CACHE.update, {"entries": None, "fetched": 0.0})

    def test_the_package_key_is_the_zip_name_without_its_version(self):
        self.assertEqual(self.repository.plugin_key("ORStools.2.2.0.zip", "2.2.0"), "ORStools")
        self.assertEqual(self.repository.plugin_key("qgis2web.3.24.0.zip", "3.24.0"), "qgis2web")
        self.assertEqual(self.repository.plugin_key("Weird.zip", ""), "Weird")

    def test_search_ranks_by_fit_then_downloads_and_hides_deprecated(self):
        from ai_agent.qgis_tools.plugins import find_plugin

        self.repository.remember([QNEAT, ORS, OLD])
        with (
            mock.patch.object(find_plugin, "installed_plugins", return_value={"QNEAT"}),
            mock.patch.object(find_plugin, "active_plugins", return_value=[]),
        ):
            found = find_plugin.FindPluginTool().execute({"query": "isochrones"})["plugins"]
        self.assertEqual([plugin["plugin"] for plugin in found], ["ORStools", "QNEAT"])
        self.assertEqual((found[1]["installed"], found[1]["active"]), (True, False))

    def test_a_name_with_its_qgis_version_or_a_plural_still_finds_the_plugin(self):
        from ai_agent.qgis_tools.plugins import find_plugin

        self.repository.remember([QNEAT, ORS])
        with (
            mock.patch.object(find_plugin, "installed_plugins", return_value=set()),
            mock.patch.object(find_plugin, "active_plugins", return_value=[]),
        ):
            found = find_plugin.FindPluginTool().execute({"query": "QNEAT3"})
            self.assertEqual([plugin["plugin"] for plugin in found["plugins"]], ["QNEAT"])
            self.assertEqual(find_plugin.variants("isochrones"), {"isochrones", "isochrone", "isochron"})
            nothing = find_plugin.FindPluginTool().execute({"query": "segmentation"})
        self.assertEqual((nothing["plugins"], nothing["listed"]), ([], 2))
        self.assertIn("do not tell the user a reason", nothing["note"])

    def test_an_empty_query_is_refused(self):
        from ai_agent.qgis_tools.plugins import find_plugin

        with self.assertRaisesRegex(ValueError, "query="):
            find_plugin.FindPluginTool().execute({"query": "  "})

    def test_a_zip_with_one_folder_is_unpacked_and_a_traversal_is_refused(self):
        import os
        import tempfile

        folder = tempfile.mkdtemp()
        key = self.repository.unpacked(plugin_zip({"demo/__init__.py": "", "demo/metadata.txt": "[general]"}), folder)
        self.assertEqual(key, "demo")
        self.assertTrue(os.path.isfile(os.path.join(folder, "demo", "metadata.txt")))
        for files in ({"../evil.py": ""}, {"one/a.py": "", "two/b.py": ""}, {"/abs/a.py": ""}):
            with self.subTest(files), self.assertRaisesRegex(ValueError, "one plugin folder"):
                self.repository.unpacked(plugin_zip(files), folder)
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.repository.unpacked(plugin_zip({"demo/__init__.py": ""}), folder)
        with self.assertRaisesRegex(ValueError, "not a zip"):
            self.repository.unpacked(b"<html>", folder)


class InstallPluginTest(unittest.TestCase):
    def setUp(self):
        from ai_agent.qgis_tools.plugins import install_plugin, repository

        self.module = install_plugin
        self.tool = install_plugin.InstallPluginTool()
        repository.remember([ORS, QNEAT, OLD])
        self.addCleanup(repository._CACHE.update, {"entries": None, "fetched": 0.0})

    def prepared(self, plugin, installed=(), active=()):
        with (
            mock.patch.object(self.module, "installed_plugins", return_value=set(installed)),
            mock.patch.object(self.module, "active_plugins", return_value=list(active)),
        ):
            return self.tool.prepare({"plugin": plugin})

    def test_install_needs_the_repository_list_first(self):
        from ai_agent.qgis_tools.plugins import repository

        repository._CACHE.update({"entries": None, "fetched": 0.0})
        with self.assertRaisesRegex(ValueError, "find_plugin first"):
            self.tool.prepare({"plugin": "ORStools"})

    def test_a_plugin_is_found_by_key_or_name_and_carries_its_facts(self):
        prepared = self.prepared("ors tools")
        facts = (prepared["plugin"], prepared["version"], prepared["enable_only"])
        self.assertEqual(facts, ("ORStools", "2.2.0", False))
        detail = self.tool.detail_call(prepared)
        self.assertIn("HeiGIT", detail)
        self.assertIn("undo cannot remove it", detail)

    def test_a_download_outside_the_official_repository_is_refused(self):
        from ai_agent.qgis_tools.plugins import repository

        repository.remember([{**ORS, "download_url": "http://example.com/ORStools.zip"}])
        with self.assertRaisesRegex(ValueError, "not downloaded from plugins.qgis.org"):
            self.prepared("ORStools")

    def test_deprecated_active_and_unknown_plugins_are_refused(self):
        with self.assertRaisesRegex(ValueError, "deprecated"):
            self.prepared("OldRoute")
        with self.assertRaisesRegex(ValueError, "already installed and active"):
            self.prepared("QNEAT", installed={"QNEAT"}, active={"QNEAT"})
        with self.assertRaisesRegex(ValueError, "No plugin 'Nope'"):
            self.prepared("Nope")

    def test_an_installed_but_switched_off_plugin_is_only_switched_on(self):
        prepared = self.prepared("QNEAT", installed={"QNEAT"})
        self.assertTrue(prepared["enable_only"])
        self.assertIsNone(self.tool.start(prepared), "nothing to download")
        enabled = []
        with mock.patch.object(self.module, "enable", side_effect=enabled.append):
            payload = self.tool.execute(prepared)
        self.assertEqual((enabled, payload["enabled"]), (["QNEAT"], "QNEAT"))
        with mock.patch.object(self.module, "active_plugins", return_value=["QNEAT"]):
            self.assertTrue(self.tool.confirm_applied(prepared, payload))
        with mock.patch.object(self.module, "active_plugins", return_value=[]):
            self.assertFalse(self.tool.confirm_applied(prepared, payload))
