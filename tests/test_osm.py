import unittest

from qgis_ai_agent.qgis_tools.osm import download_osm, extent, load, overpass


class BuildQueryTest(unittest.TestCase):
    def test_area_query_names_the_place(self):
        query = overpass.build_query("amenity", "cafe", area="Москва")
        self.assertIn('area["name"="Москва"]', query)
        self.assertIn('node["amenity"="cafe"](area.searchArea);', query)

    def test_bbox_query_uses_overpass_order(self):
        query = overpass.build_query("highway", "primary", bbox=(37.0, 55.0, 38.0, 56.0))
        self.assertIn("[bbox:55.000000,37.000000,56.000000,38.000000]", query)

    def test_value_may_be_omitted(self):
        query = overpass.build_query("building", area="Тверь")
        self.assertIn('way["building"](area.searchArea);', query)
        self.assertNotIn("=\"\"", query)

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


class BboxTest(unittest.TestCase):
    def test_four_numbers_parse(self):
        self.assertEqual(extent.parse_bbox("37.0, 55.0, 37.5, 55.5"), (37.0, 55.0, 37.5, 55.5))

    def test_semicolons_are_tolerated(self):
        self.assertEqual(extent.parse_bbox("37;55;37.5;55.5"), (37.0, 55.0, 37.5, 55.5))

    def test_wrong_count_is_rejected(self):
        with self.assertRaises(ValueError) as caught:
            extent.parse_bbox("37,55,37.5")
        self.assertIn("четырьмя", str(caught.exception))

    def test_non_numbers_are_rejected(self):
        with self.assertRaises(ValueError):
            extent.parse_bbox("запад,55,37.5,55.5")

    def test_inverted_corners_are_rejected(self):
        with self.assertRaises(ValueError) as caught:
            extent.parse_bbox("38,55,37,56")
        self.assertIn("меньше востока", str(caught.exception))

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

    def test_territory_is_required(self):
        with self.assertRaises(ValueError) as caught:
            self.tool.prepare({"key": "amenity", "value": "cafe"})
        self.assertIn("canvas", str(caught.exception))

    def test_area_and_bbox_together_are_rejected(self):
        with self.assertRaises(ValueError) as caught:
            self.tool.prepare({"key": "amenity", "area": "Тверь", "bbox": "37,55,37.5,55.5"})
        self.assertIn("что-то одно", str(caught.exception))

    def test_key_is_required(self):
        with self.assertRaises(ValueError):
            self.tool.prepare({"area": "Тверь"})

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
        self.assertFalse(self.tool.is_read_only)


class CountTest(unittest.TestCase):
    def test_known_count_is_used(self):
        self.assertEqual(load._count(_Counting(known=44, features=0)), 44)

    def test_unknown_count_falls_back_to_walking(self):
        self.assertEqual(load._count(_Counting(known=-1, features=44)), 44)

    def test_empty_sublayer_is_recognised_despite_unknown_count(self):
        self.assertEqual(load._count(_Counting(known=-1, features=0)), 0)

    def test_broken_layer_counts_as_empty(self):
        self.assertEqual(load._count(_Broken()), 0)


class SublayerTest(unittest.TestCase):
    def test_every_geometry_maps_to_sublayers(self):
        for name in ("points", "lines", "polygons", "all"):
            self.assertTrue(load.SUBLAYERS[name], name)

    def test_lines_cover_both_ogr_line_layers(self):
        self.assertEqual(load.SUBLAYERS["lines"], ("lines", "multilinestrings"))

    def test_single_sublayer_keeps_the_plain_name(self):
        self.assertEqual(load._title("Кафе", "points", "points"), "Кафе")

    def test_several_sublayers_get_a_suffix(self):
        self.assertEqual(load._title("Дороги", "points", "all"), "Дороги — точки")

    def test_file_name_is_safe_for_disk(self):
        self.assertNotIn("/", load._slug("amenity=cafe/../etc"))

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
