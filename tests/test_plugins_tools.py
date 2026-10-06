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
        self.triggered = 0

    def text(self):
        return self._text

    def menu(self):
        return self._menu

    def isSeparator(self):
        return self._separator

    def trigger(self):
        self.triggered += 1


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
