import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock
from urllib.parse import unquote

from qgis.PyQt.QtWidgets import QWidget

from ai_agent.config import connectors as connectors_config
from ai_agent.config import geocoder as geocoder_config
from ai_agent.core import connectors as core_connectors
from ai_agent.core import settings
from ai_agent.core.agent import prompts
from ai_agent.qgis_tools.data import catalogue, load_service
from ai_agent.qgis_tools.data.connectors import CONNECTORS, SOURCES, connector_of, load
from ai_agent.ui.connector_detail import caption
from ai_agent.ui.connectors_settings import ConnectorsSettings
from ai_agent.ui.personalisation_settings import PersonalisationSettings
from ai_agent.ui.settings_dialog import SettingsDialog
from tests.test_credentials import MemorySettings

TOOLS = pathlib.Path(__file__).resolve().parent.parent / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import update_translations  # noqa: E402


def row(identifier: str, title: str, category: str, summary: str, enabled: bool = True) -> dict:
    return {
        "id": identifier,
        "title": title,
        "category": category,
        "summary": summary,
        "description": f"All about {title}.",
        "examples": [f"Add {title}", f"Show {title} here"],
        "licence": "Public domain",
        "monogram": "",
        "items": [{"title": "Layer", "kind": "xyz", "zmax": 12}],
        "count": 1,
        "hosts": ["example.org"],
        "enabled": enabled,
    }


def minimal(identifier: str = "demo", **changes: object) -> dict:
    connector = {
        "id": identifier,
        "title": "Demo",
        "category": "world",
        "order": 1,
        "summary": "A demo",
        "description": "A demo source.",
        "examples": ["Add the demo"],
        "licence": "Public domain",
        "hosts": ["example.org"],
        "datasets": [
            {
                "id": f"{identifier}-tiles",
                "title": "Demo tiles",
                "kind": "service",
                "summary": "Tiles",
                "coverage": "world",
                "license": "public domain",
                "keywords": ["demo"],
                "service": "xyz",
                "layers": [{"key": "map", "title": "Map", "source": "https://example.org/{z}/{x}/{y}.png"}],
            }
        ],
    }
    connector.update(changes)
    return connector


class CatalogueIntegrityTest(unittest.TestCase):
    def test_every_dataset_belongs_to_the_connector_whose_file_holds_it(self):
        self.assertEqual(len(CONNECTORS), len(list(SOURCES.glob("*.json"))))
        for connector in CONNECTORS:
            for item in connector.datasets:
                self.assertIs(connector_of(item.id), connector)
                self.assertIs(catalogue.BY_ID[item.id], item)

    def test_every_connector_tells_the_person_what_it_is_and_what_to_ask(self):
        for connector in CONNECTORS:
            self.assertGreater(len(connector.description), len(connector.summary), connector.id)
            self.assertTrue(connector.examples, connector.id)
            self.assertTrue(connector.licence, connector.id)

    def test_natural_earth_notes_list_every_layer_the_loader_knows(self):
        notes = " ".join(catalogue.BY_ID["natural-earth"].notes)
        for key in catalogue.NATURAL_EARTH_LAYERS:
            self.assertIn(key, notes)


class SourceFileTest(unittest.TestCase):
    def load_files(self, *connectors: dict) -> object:
        with tempfile.TemporaryDirectory() as folder:
            for connector in connectors:
                path = pathlib.Path(folder) / f"{connector['id']}.json"
                path.write_text(json.dumps(connector), encoding="utf-8")
            return load(pathlib.Path(folder))

    def test_a_well_formed_file_loads_into_typed_datasets(self):
        (connector,) = self.load_files(minimal())
        self.assertEqual(connector.datasets[0].keywords, ("demo",))
        self.assertEqual(connector.datasets[0].layers[0].zmax, 19)

    def test_mistakes_are_refused_with_the_file_named(self):
        broken = (
            minimal(colour="blue"),
            minimal(category="space"),
            minimal(examples="Add the demo"),
            minimal(datasets=[]),
            minimal(datasets=[{**minimal()["datasets"][0], "layers": []}]),
            minimal(datasets=[{**minimal()["datasets"][0], "service": "ftp"}]),
        )
        for connector in broken:
            with self.assertRaisesRegex(ValueError, "^demo.json: "):
                self.load_files(connector)
        with tempfile.TemporaryDirectory() as folder:
            (pathlib.Path(folder) / "renamed.json").write_text(json.dumps(minimal()), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "^renamed.json: id 'demo' must match the file name"):
                load(pathlib.Path(folder))

    def test_a_dataset_id_used_twice_is_refused(self):
        twin = minimal("twin")
        twin["datasets"] = minimal()["datasets"]
        with self.assertRaisesRegex(ValueError, "repeated dataset id: demo-tiles"):
            self.load_files(minimal(), twin)

    def test_the_person_facing_texts_reach_the_translation_catalogue_with_their_file(self):
        found = {text: (location, line) for text, location, line, _plural in update_translations.data_sources()}
        osm = next(connector for connector in CONNECTORS if connector.id == "openstreetmap")
        location, line = found[osm.description]
        self.assertTrue(location.endswith("sources/openstreetmap.json"))
        self.assertIn(osm.description, (SOURCES / "openstreetmap.json").read_text().splitlines()[line - 1])
        for text in (*osm.examples, osm.summary, osm.licence, *osm.labels.values()):
            self.assertIn(text, found)
        self.assertNotIn("Sentinel-2 Level-2A", found)

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
        page = connectors_page()
        self.assertEqual(page.enabled_ids(), ["a"])
        page._filter("dutch")
        self.assertTrue(page.cards[0].isHidden())
        self.assertFalse(page.cards[1].isHidden())
        self.assertFalse(page._empty.isVisible())
        page._filter("")
        page._choose("imagery")
        self.assertFalse(page.cards[0].isHidden())
        self.assertTrue(page.cards[1].isHidden())
        page._filter("zzz")
        self.assertTrue(page._empty.isVisible())


def connectors_page() -> ConnectorsSettings:
    rows = [row("a", "NASA GIBS", "imagery", "daily"), row("b", "PDOK", "national", "Dutch", enabled=False)]
    with mock.patch("ai_agent.ui.connectors_settings.connector_rows", return_value=rows):
        return ConnectorsSettings(QWidget().palette())


class ConnectorDetailTest(unittest.TestCase):
    def test_a_card_opens_its_page_and_back_returns_to_the_list(self):
        page = connectors_page()
        page.cards[1].opened.emit()
        detail = page.details["b"]
        self.assertIs(page.current, detail.widget)
        self.assertTrue(page.list.isHidden())
        page.cards[1].opened.emit()
        self.assertEqual(list(page.details), ["b"])
        detail.back.emit()
        self.assertIs(page.current, page.list)
        self.assertTrue(detail.widget.isHidden())

    def test_the_page_switch_and_the_card_switch_are_one_setting(self):
        page = connectors_page()
        page.open("b")
        detail = page.details["b"]
        self.assertFalse(detail.switch.isChecked())
        detail.switch.setChecked(True)
        self.assertTrue(page.cards[1].switch.isChecked())
        page.cards[1].switch.setChecked(False)
        self.assertFalse(detail.switch.isChecked())

    def test_an_example_is_handed_on_with_its_connector(self):
        page = connectors_page()
        page.open("a")
        chosen = []
        page.prompt_chosen.connect(lambda identifier, text: chosen.append((identifier, text)))
        self.assertEqual(len(page.details["a"].examples), 2)
        page.details["a"].prompt_chosen.emit("Show NASA GIBS here")
        self.assertEqual(chosen, [("a", "Show NASA GIBS here")])

    def test_captions_name_the_kind_of_layer(self):
        self.assertIn("12", caption({"kind": "xyz", "zmax": 12}))
        self.assertIn("WFS", caption({"kind": "wfs", "zmax": 19}))
        self.assertEqual(caption({"kind": "unknown", "zmax": 0}), "")

    def test_every_real_connector_opens(self):
        page = ConnectorsSettings(QWidget().palette())
        for card in page.cards:
            page.open(card.identifier)
            self.assertEqual(len(page.details[card.identifier].examples), len(card.row["examples"]))


class ExampleFromSettingsTest(unittest.TestCase):
    def setUp(self):
        MemorySettings.values = {}
        for module in (settings, geocoder_config, connectors_config):
            patcher = mock.patch.object(module, "QgsSettings", MemorySettings)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_an_example_turns_its_connector_on_saves_and_closes_with_the_prompt(self):
        connectors_config.set_disabled_connectors(["pdok"])
        dialog = SettingsDialog()
        dialog.connectors.open("pdok")
        dialog.connectors.details["pdok"].prompt_chosen.emit("Add Dutch aerial photos")
        self.assertEqual(dialog.chosen_prompt, "Add Dutch aerial photos")
        self.assertNotIn("pdok", connectors_config.disabled_connectors())


if __name__ == "__main__":
    unittest.main()
