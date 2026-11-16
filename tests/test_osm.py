import json
import os
import pathlib
import stat
import tempfile
import unittest
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from ai_agent.config.geocoder import GEOCODER_NOMINATIM, GEOCODER_PHOTON
from ai_agent.qgis_tools.base import SAFETY_READ
from ai_agent.qgis_tools.common import geocoding
from ai_agent.qgis_tools.common.editing import edit_session
from ai_agent.qgis_tools.common.network import Answer
from ai_agent.qgis_tools.common.paths import file_slug
from ai_agent.qgis_tools.osm import (
    args,
    download_osm,
    extent,
    fetch,
    load,
    overpass,
    run_overpass,
    selectors,
    tags,
    territory,
)
from ai_agent.qgis_tools.osm.run_overpass import RunOverpassTool


class BuildQueryTest(unittest.TestCase):
    def test_nodes_come_before_the_ways_that_use_them(self):
        query = overpass.build_query("leisure", "park", area="Тверь", geometry="polygons")
        self.assertTrue(query.rstrip().endswith("out body;"))
        self.assertIn(overpass.RECURSE_DOWN, query)
        self.assertLess(query.index(overpass.RECURSE_DOWN), query.rindex("out body;"))

    def test_the_skeleton_form_that_ogr_cannot_read_is_gone(self):
        query = overpass.build_query("leisure", "park", area="Тверь", geometry="polygons")
        self.assertNotIn("out skel", query)

    def test_a_bbox_query_recurses_down_as_well(self):
        query = overpass.build_query("building", bbox=(37.0, 55.0, 37.5, 55.5))
        self.assertIn(overpass.RECURSE_DOWN, query)

    def test_area_query_names_the_place(self):
        query = overpass.build_query("amenity", "cafe", area="Москва")
        self.assertIn('area["name"="Москва"]', query)
        self.assertIn('node["amenity"="cafe"](area.searchArea);', query)

    def test_an_english_place_name_is_matched_too(self):
        query = overpass.build_query("amenity", "cafe", area="Tver")
        self.assertIn('area["name"="Tver"]', query)
        self.assertIn('area["name:en"="Tver"]', query)
        self.assertIn('area["int_name"="Tver"]', query)

    def test_every_spelling_lands_in_one_search_area(self):
        query = overpass.build_query("amenity", "cafe", area="Tver")
        self.assertEqual(query.count("->.searchArea"), 1)
        self.assertEqual(query.count("area["), len(overpass.AREA_NAME_KEYS))

    def test_the_place_name_is_still_escaped_in_every_spelling(self):
        query = overpass.build_query("amenity", "cafe", area='Tver"]; out; //')
        self.assertNotIn('"]; out;', query)
        self.assertEqual(query.count("area["), len(overpass.AREA_NAME_KEYS))

    def test_bbox_query_uses_overpass_order(self):
        query = overpass.build_query("highway", "primary", bbox=(37.0, 55.0, 38.0, 56.0))
        self.assertIn("[bbox:55.000000,37.000000,56.000000,38.000000]", query)

    def test_value_may_be_omitted(self):
        query = overpass.build_query("building", area="Тверь")
        self.assertIn('way["building"](area.searchArea);', query)
        self.assertNotIn('=""', query)

    def test_geometry_narrows_the_elements(self):
        points = overpass.build_query("amenity", "cafe", area="Тверь", geometry="points")
        self.assertIn("node", points)
        self.assertNotIn("relation", points)

    def test_polygons_ask_for_ways_and_relations(self):
        query = overpass.build_query("building", area="Тверь", geometry="polygons")
        self.assertIn("way", query)
        self.assertIn("relation", query)
        self.assertNotIn("node[", query)

    def test_missing_territory_is_rejected(self):
        with self.assertRaises(ValueError):
            overpass.build_query("amenity", "cafe")

    def test_missing_key_is_rejected(self):
        with self.assertRaises(ValueError):
            overpass.build_query("", area="Тверь")

    def test_quotes_cannot_escape_the_selector(self):
        query = overpass.build_query('amenity"]; out; //', "cafe", area="Тверь")
        self.assertNotIn("out; //", query.split("\n")[1])
        self.assertEqual(query.count("out body;"), 1)

    def test_timeout_is_declared_to_overpass(self):
        self.assertIn(f"timeout:{overpass.QUERY_TIMEOUT_SEC}", overpass.build_query("shop", area="Тверь"))


class SelectorTest(unittest.TestCase):
    def test_plain_selector_passes(self):
        self.assertEqual(selectors.normalize(['node["amenity"="cafe"]']), ['node["amenity"="cafe"]'])

    def test_single_string_is_accepted(self):
        self.assertEqual(selectors.normalize('way["shop"]'), ['way["shop"]'])

    def test_regex_and_negation_pass(self):
        kept = selectors.normalize(['way["highway"]["highway"!~"track|path"]'])
        self.assertEqual(len(kept), 1)

    def test_semicolon_cannot_smuggle_a_second_statement(self):
        with self.assertRaises(ValueError) as caught:
            selectors.normalize(['node["a"]; out; node["b"]'])
        self.assertIn("not allowed", str(caught.exception))

    def test_a_quoted_value_may_hold_what_a_statement_may_not(self):
        kept = ['node["name"="Lookout Point"]', 'node["website"~"https://"]', 'node["cuisine"="pizza;italian"]']
        self.assertEqual(selectors.normalize(kept), kept)

    def test_an_open_quote_cannot_hide_a_second_statement(self):
        for smuggled in ('node["a"="x]; out; node["b"]', 'node["a"="b\\"]; out; node["c"]'):
            with self.subTest(selector=smuggled), self.assertRaisesRegex(ValueError, "quotes"):
                selectors.normalize([smuggled])

    def test_output_directive_is_refused(self):
        with self.assertRaises(ValueError):
            selectors.normalize(['node["a"]', "out skel qt"])

    def test_assignment_is_refused(self):
        with self.assertRaises(ValueError):
            selectors.normalize(['node["a"]->.x'])

    def test_selector_must_name_an_element_type(self):
        with self.assertRaises(ValueError) as caught:
            selectors.normalize(['["amenity"="cafe"]'])
        self.assertIn("element type", str(caught.exception))

    def test_selector_without_conditions_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            selectors.normalize(["node"])
        self.assertIn("would pull in everything", str(caught.exception))

    def test_unbalanced_brackets_are_refused(self):
        with self.assertRaises(ValueError):
            selectors.normalize(['node["amenity"="cafe"'])

    def test_empty_list_is_refused(self):
        with self.assertRaises(ValueError):
            selectors.normalize([])

    def test_too_many_selectors_suggest_a_regex(self):
        with self.assertRaises(ValueError) as caught:
            selectors.normalize([f'node["k{index}"]' for index in range(20)])
        self.assertIn("regular expression", str(caught.exception))

    def test_wrong_type_is_refused(self):
        with self.assertRaises(ValueError):
            selectors.normalize({"node": "cafe"})


class SelectorQueryTest(unittest.TestCase):
    def test_selectors_get_the_area_binding(self):
        query = overpass.build_query(area="Тверь", selectors=['node["amenity"="cafe"]', 'way["shop"]'])
        self.assertIn('node["amenity"="cafe"](area.searchArea);', query)
        self.assertIn('way["shop"](area.searchArea);', query)

    def test_selectors_in_a_bbox_need_no_binding(self):
        query = overpass.build_query(bbox=(37.0, 55.0, 37.5, 55.5), selectors=['node["shop"]'])
        self.assertIn('node["shop"];', query)
        self.assertNotIn("searchArea", query)

    def test_envelope_is_always_ours(self):
        query = overpass.build_query(area="Тверь", selectors=['node["shop"]'])
        self.assertTrue(query.startswith("[out:xml]"))
        self.assertEqual(query.count("out body;"), 1)

    def test_selectors_win_over_key(self):
        query = overpass.build_query("building", area="Тверь", selectors=['node["shop"]'])
        self.assertNotIn("building", query)


class BboxTest(unittest.TestCase):
    def test_four_numbers_parse(self):
        self.assertEqual(extent.parse_bbox("37.0, 55.0, 37.5, 55.5"), (37.0, 55.0, 37.5, 55.5))

    def test_semicolons_are_tolerated(self):
        self.assertEqual(extent.parse_bbox("37;55;37.5;55.5"), (37.0, 55.0, 37.5, 55.5))

    def test_wrong_count_is_rejected(self):
        with self.assertRaises(ValueError) as caught:
            extent.parse_bbox("37,55,37.5")
        self.assertIn("four numbers", str(caught.exception))

    def test_non_numbers_are_rejected(self):
        with self.assertRaises(ValueError):
            extent.parse_bbox("запад,55,37.5,55.5")

    def test_inverted_corners_are_rejected(self):
        with self.assertRaises(ValueError) as caught:
            extent.parse_bbox("38,55,37,56")
        self.assertIn("less than the east", str(caught.exception))

    def test_out_of_range_is_rejected(self):
        with self.assertRaises(ValueError):
            extent.parse_bbox("37,55,37.5,200")

    def test_huge_box_is_refused_before_the_request(self):
        with self.assertRaises(ValueError) as caught:
            extent.parse_bbox("10,50,30,55")
        self.assertIn("Overpass", str(caught.exception))


class ToolTest(unittest.TestCase):
    def setUp(self):
        self.tool = download_osm.DownloadOsmTool()

    def test_the_switched_off_connector_stops_both_tools_before_any_request(self):
        download = {"key": "amenity", "value": "cafe", "area": "Berlin"}
        query = {"query": "[out:xml];node(1);out body;", "name": "x", "intent": "y"}
        with mock.patch.object(overpass, "disabled_connectors", return_value=frozenset({overpass.CONNECTOR})):
            for call in (
                lambda: self.tool.prepare(download),
                lambda: self.tool.execute(download),
                lambda: self.tool.start(download),
                lambda: RunOverpassTool().prepare(query),
                lambda: RunOverpassTool().execute(query),
                lambda: RunOverpassTool().start(query),
            ):
                with self.assertRaisesRegex(ValueError, "connector is turned off"):
                    call()
        self.assertEqual(self.tool.prepare(download)["area"], "Berlin")

    def test_the_connector_id_is_the_catalogue_one(self):
        sources = pathlib.Path(overpass.__file__).parents[1] / "data" / "sources"
        self.assertTrue((sources / f"{overpass.CONNECTOR}.json").is_file())

    def test_territory_is_required(self):
        with self.assertRaises(ValueError) as caught:
            self.tool.prepare({"key": "amenity", "value": "cafe"})
        self.assertIn("canvas", str(caught.exception))

    def test_area_and_bbox_together_are_rejected(self):
        with self.assertRaises(ValueError) as caught:
            self.tool.prepare({"key": "amenity", "area": "Тверь", "bbox": "37,55,37.5,55.5"})
        self.assertIn("not both at once", str(caught.exception))

    def test_key_or_selectors_is_required(self):
        with self.assertRaises(ValueError) as caught:
            self.tool.prepare({"area": "Тверь"})
        self.assertIn("selectors", str(caught.exception))

    def test_key_and_selectors_together_are_rejected(self):
        with self.assertRaises(ValueError) as caught:
            self.tool.prepare({"key": "shop", "area": "Тверь", "selectors": ['node["amenity"="cafe"]']})
        self.assertIn("not both at once", str(caught.exception))

    def test_selectors_alone_are_enough(self):
        prepared = self.tool.prepare({"area": "Тверь", "selectors": ['node["amenity"~"cafe|bar"]', 'way["shop"]']})
        self.assertEqual(len(prepared["selectors"]), 2)
        self.assertEqual(prepared["key"], "")

    def test_selector_run_gets_a_default_name(self):
        prepared = self.tool.prepare({"area": "Тверь", "selectors": ['node["shop"]']})
        self.assertTrue(prepared["name"].strip())

    def test_broken_selector_is_rejected_before_queueing(self):
        with self.assertRaises(ValueError):
            self.tool.prepare({"area": "Тверь", "selectors": ["node; out;"]})

    def test_unknown_geometry_lists_the_options(self):
        with self.assertRaises(ValueError) as caught:
            self.tool.prepare({"key": "amenity", "area": "Тверь", "geometry": "кружочки"})
        self.assertIn("polygons", str(caught.exception))

    def test_name_defaults_to_the_tag(self):
        prepared = self.tool.prepare({"key": "amenity", "value": "cafe", "area": "Тверь"})
        self.assertEqual(prepared["name"], "amenity=cafe")

    def test_name_without_value_is_the_key(self):
        self.assertEqual(self.tool.prepare({"key": "building", "area": "Тверь"})["name"], "building")

    def test_geometry_defaults_to_all(self):
        self.assertEqual(self.tool.prepare({"key": "shop", "area": "Тверь"})["geometry"], "all")

    def test_bbox_is_normalized_into_the_queue(self):
        prepared = self.tool.prepare({"key": "shop", "bbox": "37,55,37.5,55.5"})
        self.assertEqual(prepared["bbox"], "37.000000,55.000000,37.500000,55.500000")
        self.assertEqual(prepared["area"], "")

    def test_the_canvas_keyword_given_as_area_is_the_current_view(self):
        with mock.patch.object(args, "canvas_bbox", return_value=(37.5, 55.6, 37.7, 55.8)):
            prepared = self.tool.prepare({"key": "amenity", "value": "cafe", "area": " Canvas "})
        self.assertEqual(prepared["area"], "")
        self.assertEqual(prepared["bbox"], "37.500000,55.600000,37.700000,55.800000")
        job = download_osm._job(prepared)
        self.assertEqual((job.area, job.bbox), ("", (37.5, 55.6, 37.7, 55.8)), "no place called canvas is searched")

    def test_bad_bbox_is_rejected_before_queueing(self):
        with self.assertRaises(ValueError):
            self.tool.prepare({"key": "shop", "bbox": "мусор"})

    def test_summary_names_the_tag_and_place(self):
        summary = self.tool.summarize_call({"key": "amenity", "value": "cafe", "area": "Москва"})
        self.assertIn("amenity=cafe", summary)
        self.assertIn("Москва", summary)

    def test_summary_survives_empty_params(self):
        self.assertTrue(self.tool.summarize_call({}).strip())

    def test_it_is_a_write_tool(self):
        self.assertNotEqual(self.tool.safety, SAFETY_READ)


class CountTest(unittest.TestCase):
    def test_known_count_is_used(self):
        self.assertEqual(load._count(_Counting(known=44, features=0)), 44)

    def test_unknown_count_falls_back_to_walking(self):
        self.assertEqual(load._count(_Counting(known=-1, features=44)), 44)

    def test_empty_sublayer_is_recognised_despite_unknown_count(self):
        self.assertEqual(load._count(_Counting(known=-1, features=0)), 0)

    def test_broken_layer_counts_as_empty(self):
        self.assertEqual(load._count(_Broken()), 0)


class PayloadIsolationTest(unittest.TestCase):
    def test_repeated_names_get_distinct_private_folders(self):
        with tempfile.TemporaryDirectory() as root:
            folders = [os.path.join(root, name) for name in ("first", "second")]
            for folder in folders:
                os.mkdir(folder)
            with mock.patch.object(tempfile, "mkdtemp", side_effect=folders):
                first, first_temporary = load.write_payload("<osm/>", "cafes")
                second, _ = load.write_payload("<osm/>", "cafes")

            self.assertTrue(first_temporary)

            self.assertNotEqual(first, second)
            self.assertNotEqual(os.path.dirname(first), os.path.dirname(second))
            self.assertEqual(pathlib.Path(first).read_text(encoding="utf-8"), "<osm/>")
            if os.name != "nt":
                self.assertEqual(stat.S_IMODE(os.stat(first).st_mode), 0o600)
                self.assertEqual(stat.S_IMODE(os.stat(os.path.dirname(first)).st_mode), 0o700)


class ProjectFolderTest(unittest.TestCase):
    def _project(self, home):
        return mock.patch.object(load.QgsProject, "instance", return_value=mock.Mock(homePath=lambda: home))

    def test_a_saved_project_keeps_downloads_beside_itself(self):
        with tempfile.TemporaryDirectory() as home, self._project(home):
            first, temporary = load.write_payload("<osm/>", "cafes")
            pathlib.Path(load._gpkg_path(first, "points")).touch()
            second, _ = load.write_payload("<osm/>", "cafes")
            self.assertFalse(temporary)
            self.assertEqual(os.path.dirname(first), os.path.join(home, "osm"))
            self.assertNotEqual(first, second)
            self.assertEqual(load.storage_note(temporary), {})

    def test_a_temporary_download_is_announced(self):
        self.assertIn("temporary folder", load.storage_note(True)["storage_note"])

    def test_the_raw_file_goes_once_every_layer_reads_its_geopackage(self):
        with tempfile.TemporaryDirectory() as home:
            path = os.path.join(home, "cafes.osm")
            pathlib.Path(path).write_text("<osm/>", encoding="utf-8")
            copy = {"name": "cafes", "kind": "points", "feature_count": 3, "source": load._gpkg_path(path, "points")}
            with mock.patch.object(load, "_load_one", side_effect=[copy, None]):
                loaded = load.load_sublayers(path, "lines", "cafes")
            self.assertEqual(loaded, [copy])
            self.assertFalse(os.path.exists(path))

    def test_the_raw_file_stays_while_a_layer_still_reads_it(self):
        with tempfile.TemporaryDirectory() as home:
            path = os.path.join(home, "cafes.osm")
            pathlib.Path(path).write_text("<osm/>", encoding="utf-8")
            raw = {"name": "cafes", "kind": "points", "feature_count": 3, "source": path}
            with mock.patch.object(load, "_load_one", return_value=raw):
                load.load_sublayers(path, "points", "cafes")
            self.assertTrue(os.path.exists(path))


class SublayerTest(unittest.TestCase):
    def test_every_geometry_maps_to_sublayers(self):
        for name in ("points", "lines", "polygons", "all"):
            self.assertTrue(load.SUBLAYERS[name], name)

    def test_lines_cover_both_ogr_line_layers(self):
        self.assertEqual(load.SUBLAYERS["lines"], ("lines", "multilinestrings"))

    def test_single_sublayer_keeps_the_plain_name(self):
        self.assertEqual(load._title("Кафе", "points", "points"), "Кафе")

    def test_several_sublayers_get_a_suffix(self):
        self.assertEqual(load._title("Roads", "points", "all"), "Roads — points")

    def test_no_two_sublayers_share_a_title(self):
        for geometry, sublayers in load.SUBLAYERS.items():
            titles = [load._title("Bus routes", sublayer, geometry) for sublayer in sublayers]
            self.assertEqual(len(set(titles)), len(titles), geometry)

    def test_file_name_is_safe_for_disk(self):
        self.assertNotIn("/", file_slug("amenity=cafe/../etc", load.FALLBACK_STEM))

    def test_geometry_options_match_the_tool_schema(self):
        schema = {item["name"]: item for item in download_osm.DownloadOsmTool().params_schema}
        self.assertEqual(set(schema["geometry"]["enum"]), set(load.SUBLAYERS))


class _Counting:
    def __init__(self, known, features):
        self._known = known
        self._features = features

    def featureCount(self):
        return self._known

    def getFeatures(self):
        return iter(range(self._features))


class _Broken:
    def featureCount(self):
        raise RuntimeError("провайдер отвалился")


if __name__ == "__main__":
    unittest.main()


class TagLayer:
    def __init__(self, rows, names=("osm_id", "name", "other_tags")):
        self._rows = list(rows)
        self._names = list(names)
        self.added = []

    def fields(self):
        return self

    def names(self):
        return list(self._names)

    def getFeatures(self):
        return list(self._rows)

    def addExpressionField(self, expression, field):
        self.added.append((expression, field))
        self._names.append(getattr(field, "_stub_name", "field"))


class Row(dict):
    pass


class NamedField:
    def __init__(self, name, *rest):
        self._stub_name = name


class PromoteTagsTest(unittest.TestCase):
    def setUp(self):
        self.saved = tags.QgsField
        tags.QgsField = NamedField

    def tearDown(self):
        tags.QgsField = self.saved

    def _layer(self, *hstores):
        return TagLayer([Row({"other_tags": text}) for text in hstores])

    def test_a_tag_becomes_a_field(self):
        layer = self._layer('"amenity"=>"cafe","cuisine"=>"burger"')
        self.assertEqual(tags.promote_tags(layer), ["amenity", "cuisine"])

    def test_the_expression_reads_it_out_of_the_hstore(self):
        layer = self._layer('"cuisine"=>"burger"')
        tags.promote_tags(layer)
        self.assertIn("hstore_to_map", layer.added[0][0])
        self.assertIn("'cuisine'", layer.added[0][0])

    def test_the_commonest_tags_come_first(self):
        layer = self._layer('"a"=>"1"', '"b"=>"1"', '"b"=>"2"')
        self.assertEqual(tags.promote_tags(layer)[0], "b")

    def test_a_layer_without_the_column_is_left_alone(self):
        layer = TagLayer([], names=("osm_id", "name"))
        self.assertEqual(tags.promote_tags(layer), [])
        self.assertEqual(layer.added, [])

    def test_a_tag_that_already_is_a_field_is_not_doubled(self):
        layer = TagLayer([Row({"other_tags": '"name"=>"x","shop"=>"bakery"'})])
        self.assertEqual(tags.promote_tags(layer), ["shop"])

    def test_a_quote_in_a_tag_name_is_refused(self):
        layer = self._layer('"we\'ird"=>"1","fine"=>"2"')
        self.assertEqual(tags.promote_tags(layer), ["fine"])

    def test_the_number_of_fields_is_capped(self):
        many = ",".join(f'"tag{index}"=>"v"' for index in range(tags.MAX_PROMOTED + 10))
        self.assertEqual(len(tags.promote_tags(self._layer(many))), tags.MAX_PROMOTED)

    def test_empty_hstore_values_are_survived(self):
        layer = TagLayer([Row({"other_tags": None}), Row({"other_tags": '"shop"=>"x"'})])
        self.assertEqual(tags.promote_tags(layer), ["shop"])


class RunOverpassTest(unittest.TestCase):
    def setUp(self):
        self.tool = RunOverpassTool()

    def _query(self, tail="(._;>;);\nout body;"):
        return f'[out:xml][timeout:90];\nnode["amenity"="cafe"](55,37,56,38);\n{tail}'

    def _params(self, **overrides):
        params = {"query": self._query(), "name": "Cafes", "intent": "все кафе в прямоугольнике"}
        params.update(overrides)
        return params

    def test_a_whole_query_passes_through_untouched(self):
        prepared = self.tool.prepare(self._params())
        self.assertEqual(prepared["query"], self._query())

    def test_a_missing_intent_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            self.tool.prepare(self._params(intent="  "))
        self.assertIn("intent", str(caught.exception))

    def test_the_summary_shows_the_intent_not_the_query(self):
        summary = self.tool.summarize_call(self._params())
        self.assertIn("все кафе", summary)
        self.assertNotIn("out:xml", summary)

    def test_the_raw_query_moves_to_the_details(self):
        self.assertIn("out:xml", self.tool.detail_call(self._params()))

    def test_an_empty_query_is_refused(self):
        with self.assertRaises(ValueError):
            self.tool.prepare(self._params(query="  "))

    def test_a_query_without_output_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            self.tool.prepare(self._params(query='[out:xml];node["shop"](55,37,56,38);'))
        self.assertIn("out body", str(caught.exception))

    def test_the_skeleton_output_is_refused_with_the_reason(self):
        with self.assertRaises(ValueError) as caught:
            self.tool.prepare(self._params(query=self._query("out body;\n>;\nout skel qt;")))
        self.assertIn("nodes", str(caught.exception))
        self.assertIn("(._;>;);", str(caught.exception))

    def test_an_overlong_query_is_refused(self):
        with self.assertRaises(ValueError):
            self.tool.prepare(self._params(query="out body; " + "x" * run_overpass.MAX_QUERY_CHARS))

    def test_it_is_a_write_tool_so_it_waits_for_the_button(self):
        self.assertNotEqual(self.tool.safety, SAFETY_READ)


class EditableDownloadTest(unittest.TestCase):
    SOURCE = pathlib.Path("ai_agent/qgis_tools/osm/load.py").read_text(encoding="utf-8")

    def test_the_sublayer_is_materialized_into_a_geopackage(self):
        self.assertIn('"GPKG"', self.SOURCE)
        self.assertIn("CreateOrOverwriteFile", self.SOURCE)

    def test_a_failed_conversion_falls_back_to_the_raw_layer(self):
        self.assertIn("layer = materialized or raw", self.SOURCE)

    def test_the_read_only_refusal_names_the_way_out(self):
        layer = mock.Mock()
        layer.name.return_value = "OSM download"
        layer.isEditable.return_value = False
        layer.startEditing.return_value = False
        with self.assertRaisesRegex(ValueError, "editable copy"), edit_session(layer, "the requested edits"):
            self.fail("read-only data must never enter the mutation block")
        layer.commitChanges.assert_not_called()
        layer.rollBack.assert_not_called()


OVERPASS_URL = "https://overpass.test/api/interpreter"
TIMED_OUT_ANSWER = (
    b'<?xml version="1.0" encoding="UTF-8"?>\n<osm version="0.6" generator="Overpass API">\n'
    b'<node id="1" lat="55.75" lon="37.62"><tag k="amenity" v="cafe"/></node>\n'
    b"<remark> runtime error: Query timed out in &quot;query&quot; at line 3 after 91 seconds. </remark>\n"
    b"</osm>\n"
)


class _Overpass:
    answer = b'<?xml version="1.0"?><osm version="0.6"></osm>'

    def __init__(self):
        self.posted = []

    def send(self, request, payload=None, feedback=None, on_progress=None):
        self.posted.append(payload)
        return Answer(status=200, body=self.answer)


class FetchTest(unittest.TestCase):
    def setUp(self):
        self.overpass = _Overpass()
        patcher = mock.patch.object(fetch, "send", self.overpass.send)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_query_reaches_overpass_whole(self):
        query = '[out:xml];node["name"~"A+B&C=D %"](55,37,56,38);out body;'
        fetch.fetch(query, OVERPASS_URL)
        (body,) = self.overpass.posted
        self.assertEqual(parse_qs(body.decode("ascii")), {"data": [query]})

    def test_a_query_overpass_broke_off_is_a_failure_not_a_partial_download(self):
        with mock.patch.object(_Overpass, "answer", TIMED_OUT_ANSWER), self.assertRaises(ValueError) as caught:
            fetch.fetch("[out:xml];node(55,37,56,38);out body;", OVERPASS_URL)
        message = str(caught.exception)
        self.assertIn('runtime error: Query timed out in "query" at line 3 after 91 seconds.', message)
        self.assertIn("nothing was loaded", message)

    def test_a_broken_off_answer_never_becomes_layers(self):
        params = {"query": '[out:xml];node["amenity"="cafe"](55,37,56,38);out body;', "name": "Cafes"}
        with (
            mock.patch.object(_Overpass, "answer", TIMED_OUT_ANSWER),
            mock.patch.object(run_overpass, "endpoints", return_value=(OVERPASS_URL,)),
            mock.patch.object(run_overpass, "load_answer") as load_answer,
            self.assertRaises(ValueError),
        ):
            RunOverpassTool().execute(params)
        load_answer.assert_not_called()


MIRROR_URL = "https://mirror.test/api/interpreter"
CAFES = (
    b'<?xml version="1.0"?><osm version="0.6">'
    b'<node id="1" lat="52.5" lon="13.4"><tag k="amenity" v="cafe"/></node></osm>'
)
BUSY_REMARK = (
    b'<?xml version="1.0"?><osm version="0.6"><remark> runtime error: open64: 0 Success '
    b"/osm3s_osm_base Dispatcher_Client::request_read_and_idx::timeout. The server is probably too busy "
    b"to handle your request. </remark></osm>"
)
OUT_OF_MEMORY = (
    b'<?xml version="1.0"?><osm version="0.6"><remark> runtime error: Query run out of memory '
    b"using about 2048 MB of RAM. </remark></osm>"
)
PARSE_ERROR = (
    b"<html><body><p>The data included in this document is from www.openstreetmap.org.</p>"
    b'<p><strong style="color:#FF0000">Error</strong>: line 1: parse error: Unknown type &quot;nod&quot; </p>'
    b"</body></html>"
)


class _Servers:
    def __init__(self, answers):
        self.answers = answers
        self.asked = []

    def send(self, request, payload=None, feedback=None, on_progress=None):
        self.asked.append(payload)
        return self.answers[len(self.asked) - 1]


class MirrorTest(unittest.TestCase):
    URLS = (OVERPASS_URL, MIRROR_URL)

    def _fetch(self, *answers, urls=URLS, feedback=None):
        servers = _Servers(answers)
        with mock.patch.object(fetch, "send", servers.send), mock.patch.object(fetch, "QgsMessageLog"):
            try:
                return fetch.fetch_anywhere("[out:xml];node(1);out body;", urls, feedback), servers
            except ValueError as failure:
                return failure, servers

    def test_a_server_that_does_not_answer_hands_the_query_to_the_mirror(self):
        unanswered = (
            Answer(status=504, failed=True, error="Gateway Timeout"),
            Answer(status=429, failed=True, error="Too Many Requests"),
            Answer(status=0, failed=True, error="Host not found"),
            Answer(status=200, body=BUSY_REMARK),
            Answer(status=200, body=TIMED_OUT_ANSWER),
            Answer(status=200, body=b"<html>The server is probably too busy to handle your request.</html>"),
        )
        for first in unanswered:
            with self.subTest(first=first):
                text, servers = self._fetch(first, Answer(status=200, body=CAFES))
                self.assertEqual(text, CAFES.decode())
                self.assertEqual(len(servers.asked), 2)
                self.assertEqual(servers.asked[0], servers.asked[1])

    def test_a_query_the_server_could_not_run_is_not_sent_again(self):
        refused = (
            Answer(status=400, failed=True, error="Bad Request", body=PARSE_ERROR),
            Answer(status=200, body=OUT_OF_MEMORY),
            Answer(status=200, body=b"<html>nothing like OSM here</html>"),
        )
        for first in refused:
            with self.subTest(first=first):
                failure, servers = self._fetch(first, Answer(status=200, body=CAFES))
                self.assertIsInstance(failure, ValueError)
                self.assertEqual(len(servers.asked), 1)

    def test_a_refused_query_comes_back_with_what_overpass_said(self):
        failure, _ = self._fetch(Answer(status=400, failed=True, error="Bad Request", body=PARSE_ERROR))
        self.assertIn('line 1: parse error: Unknown type "nod"', str(failure))

    def test_an_empty_answer_is_an_answer(self):
        text, servers = self._fetch(Answer(status=200, body=_Overpass.answer), Answer(status=200, body=CAFES))
        self.assertEqual(text, _Overpass.answer.decode())
        self.assertEqual(len(servers.asked), 1)

    def test_a_stopped_download_does_not_move_to_the_mirror(self):
        stopped = mock.Mock(isCanceled=lambda: True)
        failure, servers = self._fetch(
            Answer(status=0, failed=True, error="Operation canceled", cancelled=True), feedback=stopped
        )
        self.assertIsInstance(failure, ValueError)
        self.assertEqual(len(servers.asked), 1)

    def test_both_servers_failing_names_the_mirror_too(self):
        busy = Answer(status=504, failed=True, error="Gateway Timeout")
        failure, servers = self._fetch(busy, busy)
        self.assertEqual(len(servers.asked), 2)
        self.assertIn("Gateway Timeout", str(failure))
        self.assertIn("mirror.test", str(failure))

    def test_only_the_public_server_has_a_mirror(self):
        with mock.patch.object(overpass, "endpoint", return_value=overpass.DEFAULT_ENDPOINT):
            self.assertEqual(overpass.endpoints(), (overpass.DEFAULT_ENDPOINT, overpass.FALLBACK_ENDPOINT))
        with mock.patch.object(overpass, "endpoint", return_value="https://overpass.example.org/api/interpreter"):
            self.assertEqual(overpass.endpoints(), ("https://overpass.example.org/api/interpreter",))

    def test_every_overpass_host_is_one_the_connector_names(self):
        sources = pathlib.Path(overpass.__file__).parents[1] / "data" / "sources"
        hosts = json.loads((sources / f"{overpass.CONNECTOR}.json").read_text(encoding="utf-8"))["hosts"]
        for url in (overpass.DEFAULT_ENDPOINT, overpass.FALLBACK_ENDPOINT):
            self.assertIn(urlsplit(url).hostname, hosts)


BERLIN_PHOTON = json.dumps(
    {
        "features": [
            {
                "geometry": {"coordinates": [13.3888, 52.517]},
                "properties": {
                    "name": "Berlin",
                    "country": "Germany",
                    "osm_type": "R",
                    "osm_id": 62422,
                    "osm_key": "place",
                    "osm_value": "city",
                    "extent": [13.08, 52.67, 13.76, 52.33],
                },
            }
        ]
    }
)
VILLAGE_NOMINATIM = json.dumps(
    [
        {
            "display_name": "Divnomorskoye, Krasnodar Krai",
            "category": "place",
            "type": "village",
            "osm_type": "node",
            "osm_id": 27505009,
            "lat": "44.5052",
            "lon": "38.1305",
            "boundingbox": ["44.49", "44.52", "38.11", "38.15"],
        }
    ]
)
COUNTRY_NODE = json.dumps(
    [
        {
            "display_name": "Россия",
            "category": "place",
            "type": "country",
            "osm_type": "node",
            "osm_id": 1,
            "lat": "64.6",
            "lon": "97.7",
            "boundingbox": ["41.1", "82.0", "19.6", "180.0"],
        }
    ]
)
PHOTON_SERVICE = territory.Geocoder(GEOCODER_PHOTON, "https://photon.test")
NOMINATIM_SERVICE = territory.Geocoder(GEOCODER_NOMINATIM, "https://geo.test/nominatim")


class GeocodedTerritoryTest(unittest.TestCase):
    def setUp(self):
        self.tool = download_osm.DownloadOsmTool()
        self.requests = []
        self.queries = []
        self.geocoder_answer = Answer(status=200, body=BERLIN_PHOTON.encode())
        for target, replacement in (
            (geocoding, self._geocoder),
            (fetch, self._overpass),
        ):
            patcher = mock.patch.object(target, "send", replacement)
            patcher.start()
            self.addCleanup(patcher.stop)
        for name, value in (("QUrl", str), ("QNetworkRequest", mock.Mock(side_effect=lambda url: _Request(url)))):
            patcher = mock.patch.object(geocoding, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _geocoder(self, request, payload=None, feedback=None):
        self.requests.append(request.url)
        return self.geocoder_answer

    def _overpass(self, request, payload=None, feedback=None, on_progress=None):
        self.queries.append(parse_qs(payload.decode("ascii"))["data"][0])
        return Answer(status=200, body=CAFES)

    def _download(self, service, configured="same", **params):
        arguments = {"key": "amenity", "value": "cafe", "area": "Berlin", **params}
        now = service if configured == "same" else configured
        with (
            mock.patch.object(download_osm, "configured_geocoder", return_value=service),
            mock.patch.object(territory, "configured_geocoder", return_value=now),
            mock.patch.object(download_osm, "endpoints", return_value=(OVERPASS_URL,)),
            mock.patch.object(download_osm, "load_answer", return_value={"layers": [], "total_features": 1}),
        ):
            prepared = self.tool.prepare(arguments)
            return prepared, self.tool.execute(prepared)

    def test_a_relation_the_geocoder_returns_becomes_the_search_area(self):
        prepared, payload = self._download(PHOTON_SERVICE)
        self.assertEqual(self.requests, ["https://photon.test/api?limit=5&q=Berlin"])
        (query,) = self.queries
        self.assertIn("area(id:3600062422)->.searchArea;", query)
        self.assertNotIn('area["name"', query)
        self.assertEqual(payload["territory"], "Berlin, Germany")
        self.assertIn("photon.test", self.tool.summarize_call(prepared))

    def test_a_place_without_a_relation_is_searched_in_its_box(self):
        self.geocoder_answer = Answer(status=200, body=VILLAGE_NOMINATIM.encode())
        _, payload = self._download(NOMINATIM_SERVICE, area="Divnomorskoye")
        self.assertEqual(self.requests, ["https://geo.test/nominatim/search?format=jsonv2&limit=5&q=Divnomorskoye"])
        (query,) = self.queries
        self.assertIn("[bbox:44.490000,38.110000,44.520000,38.150000]", query)
        self.assertNotIn("searchArea", query)
        self.assertEqual(payload["territory"], "Divnomorskoye, Krasnodar Krai")

    def test_without_a_geocoder_the_name_is_matched_as_before(self):
        prepared, payload = self._download(None)
        self.assertEqual(self.requests, [])
        self.assertIn('area["name"="Berlin"];', self.queries[0])
        self.assertNotIn("territory", payload)
        self.assertNotIn(territory.URL_KEY, prepared)
        self.assertNotIn("located", self.tool.summarize_call(prepared))

    def test_a_geocoder_that_fails_or_knows_nothing_falls_back_to_the_name(self):
        for answer in (
            Answer(status=503, failed=True, error="Service Unavailable"),
            Answer(status=200, body=b'{"features": []}'),
            Answer(status=200, body=b"<html>not json</html>"),
            Answer(status=200, body=COUNTRY_NODE.encode()),
        ):
            with self.subTest(answer=answer):
                self.queries.clear()
                self.geocoder_answer = answer
                service = NOMINATIM_SERVICE if answer.body.startswith(b"[") else PHOTON_SERVICE
                _, payload = self._download(service)
                self.assertIn('area["name"="Berlin"];', self.queries[0])
                self.assertNotIn("territory", payload)

    def test_a_rectangle_never_asks_the_geocoder(self):
        prepared, _ = self._download(PHOTON_SERVICE, area="", bbox="13.3,52.4,13.5,52.6")
        self.assertEqual(self.requests, [])
        self.assertNotIn(territory.URL_KEY, prepared)

    def test_a_geocoder_the_plan_did_not_name_is_not_contacted(self):
        for planned, now in ((None, PHOTON_SERVICE), (PHOTON_SERVICE, None), (PHOTON_SERVICE, NOMINATIM_SERVICE)):
            with self.subTest(planned=planned, now=now):
                self.requests.clear()
                self.queries.clear()
                self._download(planned, configured=now)
                self.assertEqual(self.requests, [])
                self.assertIn('area["name"="Berlin"];', self.queries[0])

    def test_the_model_cannot_name_the_geocoder(self):
        smuggled = {territory.PROVIDER_KEY: GEOCODER_PHOTON, territory.URL_KEY: "https://elsewhere.test"}
        prepared, _ = self._download(None, **smuggled)
        self.assertNotIn(territory.URL_KEY, prepared)
        self.assertEqual(self.requests, [])

    def test_the_switched_off_connector_stops_the_geocoder_too(self):
        with (
            mock.patch.object(download_osm, "configured_geocoder", return_value=PHOTON_SERVICE),
            mock.patch.object(territory, "configured_geocoder", return_value=PHOTON_SERVICE),
        ):
            prepared = self.tool.prepare({"key": "amenity", "value": "cafe", "area": "Berlin"})
            with mock.patch.object(overpass, "disabled_connectors", return_value=frozenset({overpass.CONNECTOR})):
                for call in (self.tool.execute, self.tool.start):
                    with self.assertRaisesRegex(ValueError, "connector is turned off"):
                        call(prepared)
        self.assertEqual((self.requests, self.queries), ([], []))

    def test_only_a_geocoder_switched_on_in_settings_counts(self):
        with mock.patch.object(territory, "get_provider", return_value="disabled"):
            self.assertIsNone(territory.configured_geocoder())
        for url in ("https://nominatim.openstreetmap.org", "http://geo.example", ""):
            with (
                self.subTest(url=url),
                mock.patch.object(territory, "get_provider", return_value=GEOCODER_NOMINATIM),
                mock.patch.object(territory, "get_url", return_value=url),
            ):
                self.assertIsNone(territory.configured_geocoder())
        with (
            mock.patch.object(territory, "get_provider", return_value=GEOCODER_PHOTON),
            mock.patch.object(territory, "get_url", return_value="https://photon.komoot.io"),
        ):
            self.assertEqual(territory.configured_geocoder().host, "photon.komoot.io")


class NothingFoundTest(unittest.TestCase):
    def _message(self, where, geocoder=None):
        job = download_osm._Job("amenity", "cafe", (), "all", "x", where.area, where.bbox, (OVERPASS_URL,), geocoder)
        return job._nothing_found(where)

    def test_a_name_that_matched_nothing_says_how_names_are_matched_and_offers_the_geocoder(self):
        message = self._message(territory.Territory(area="Berlin, Germany"))
        self.assertIn("'Berlin, Germany' does not", message)
        self.assertIn("Settings → Geocoding", message)
        self.assertNotIn("Settings → Geocoding", self._message(territory.Territory(area="Berlin"), PHOTON_SERVICE))

    def test_a_geocoded_place_is_named_so_a_wrong_one_shows(self):
        message = self._message(territory.Territory(area_id=3600062422, found="Berlin, Germany"), PHOTON_SERVICE)
        self.assertIn("'Berlin, Germany'", message)
        self.assertIn("add the region or the country", message)

    def test_a_rectangle_is_not_told_about_names(self):
        message = self._message(territory.Territory(bbox=(13.3, 52.4, 13.5, 52.6)))
        self.assertNotIn("name:en", message)
        self.assertIn("widen the bbox", message)


class _Request:
    def __init__(self, url):
        self.url = url

    def setRawHeader(self, name, value):
        pass
