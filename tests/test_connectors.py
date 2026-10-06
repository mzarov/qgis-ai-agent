import unittest
from unittest import mock
from urllib.parse import unquote

from qgis.PyQt.QtWidgets import QWidget

from ai_agent.core import connectors as core_connectors
from ai_agent.core.agent import prompts
from ai_agent.qgis_tools.data import catalogue, load_service
from ai_agent.qgis_tools.data.connectors import CONNECTORS, connector_of
from ai_agent.ui.connectors_settings import ConnectorsSettings
from ai_agent.ui.personalisation_settings import PersonalisationSettings


class CatalogueIntegrityTest(unittest.TestCase):
    def test_every_dataset_has_exactly_one_connector_and_every_connector_lists_real_datasets(self):
        for item in catalogue.DATASETS:
            self.assertIsNotNone(connector_of(item.id), item.id)
        for connector in CONNECTORS:
            for dataset_id in connector.datasets:
                self.assertIn(dataset_id, catalogue.BY_ID, connector.id)

    def test_service_layers_are_complete(self):
        for item in catalogue.DATASETS:
            if item.kind != catalogue.KIND_SERVICE:
                continue
            self.assertTrue(item.layers, item.id)
            for layer in item.layers:
                self.assertTrue(layer.source, layer.key)
                if (layer.protocol or item.service) in ("wms", "wfs"):
                    self.assertTrue(item.endpoint.startswith("https://"), item.id)


class SwitchedOffTest(unittest.TestCase):
    def test_a_switched_off_connector_hides_and_refuses_its_datasets(self):
        with mock.patch.object(catalogue, "disabled_connectors", return_value=frozenset({"nasa-gibs"})):
            self.assertNotIn("nasa-gibs", [item.id for item in catalogue.search("satellite")])
            with self.assertRaisesRegex(ValueError, "turned off in Settings"):
                catalogue.dataset("nasa-gibs", catalogue.KIND_SERVICE)
            self.assertEqual(catalogue.dataset("gebco").id, "gebco")

    def test_rows_and_saving_go_through_the_shared_setting(self):
        with mock.patch.object(core_connectors, "disabled_connectors", return_value=frozenset({"pdok"})):
            rows = {row["id"]: row for row in core_connectors.connector_rows()}
        self.assertFalse(rows["pdok"]["enabled"])
        self.assertTrue(rows["nasa-gibs"]["enabled"])
        self.assertEqual(rows["nasa-gibs"]["count"], 3)
        self.assertEqual(rows["planetary-computer"]["count"], 7)
        with mock.patch.object(core_connectors, "set_disabled_connectors") as stored:
            core_connectors.save_enabled([connector.id for connector in CONNECTORS if connector.id != "eox"])
        self.assertEqual(list(stored.call_args.args[0]), ["eox"])


class LoadServiceTest(unittest.TestCase):
    def test_daily_imagery_fills_the_date_and_defaults_to_yesterday(self):
        tool = load_service.LoadServiceTool()
        prepared = tool.prepare({"dataset": "nasa-gibs", "layer": "modis_true_color", "date": "2026-07-01"})
        layer = catalogue.BY_ID["nasa-gibs"].layers[0]
        source = unquote(load_service._xyz_source(layer, prepared))
        self.assertIn("/2026-07-01/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg", source)
        self.assertIn("zmax=9", source)
        self.assertEqual(len(tool.prepare({"dataset": "nasa-gibs", "layer": "modis_true_color"})["date"]), 10)
        with self.assertRaisesRegex(ValueError, "not a day"):
            tool.prepare({"dataset": "nasa-gibs", "layer": "modis_true_color", "date": "July"})
        with self.assertRaisesRegex(ValueError, "Its layers"):
            tool.prepare({"dataset": "nasa-gibs", "layer": "radar"})

    def test_wms_and_wfs_sources_point_at_the_catalogued_endpoints(self):
        gebco = catalogue.BY_ID["gebco"]
        self.assertIn("layers=GEBCO_LATEST", load_service._wms_source(gebco, gebco.layers[0]))
        params = {}
        fake_uri = mock.Mock(setParam=lambda key, value: params.__setitem__(key, value), uri=lambda expand: "uri")
        ign = catalogue.BY_ID["ign-france"]
        communes = next(layer for layer in ign.layers if layer.key == "communes")
        with mock.patch.object(load_service, "QgsDataSourceUri", return_value=fake_uri):
            load_service._wfs_source(ign, communes)
        self.assertEqual(params["url"], "https://data.geopf.fr/wfs")
        self.assertEqual(params["typename"], "ADMINEXPRESS-COG-CARTO.LATEST:commune")
        self.assertEqual(params["restrictToRequestBBOX"], "1")


class PersonalisationTest(unittest.TestCase):
    def test_instructions_join_the_cached_prompt_only_when_written(self):
        plain, _live = prompts.build_system_parts("", [])
        self.assertNotIn(prompts.CUSTOM_INSTRUCTIONS_HEADER, plain)
        written, _live = prompts.build_system_parts("", [], custom_instructions="Answer in metres.")
        self.assertIn(prompts.CUSTOM_INSTRUCTIONS_HEADER, written)
        self.assertIn("Answer in metres.", written)

    def test_the_page_counts_and_trims(self):
        with mock.patch("ai_agent.ui.personalisation_settings.get_custom_instructions", return_value="Be brief."):
            page = PersonalisationSettings(QWidget().palette())
        self.assertEqual(page.text(), "Be brief.")
        self.assertTrue(page.counter.text().startswith("9 / "))

    def test_the_connectors_page_filters_and_reports_switches(self):
        with mock.patch(
            "ai_agent.ui.connectors_settings.connector_rows",
            return_value=[
                {
                    "id": "a",
                    "title": "NASA GIBS",
                    "category": "imagery",
                    "summary": "daily",
                    "count": 3,
                    "hosts": ["x"],
                    "enabled": True,
                },
                {
                    "id": "b",
                    "title": "PDOK",
                    "category": "national",
                    "summary": "Dutch",
                    "count": 4,
                    "hosts": ["y"],
                    "enabled": False,
                },
            ],
        ):
            page = ConnectorsSettings(QWidget().palette())
        self.assertEqual(page.enabled_ids(), ["a"])
        page._filter("dutch")
        self.assertTrue(page._rows[0][0].isHidden())
        self.assertFalse(page._rows[1][0].isHidden())
        self.assertFalse(page._empty.isVisible())
        page._filter("zzz")
        self.assertTrue(page._empty.isVisible())


if __name__ == "__main__":
    unittest.main()
