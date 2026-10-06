import os
import tempfile
import time
import unittest
from unittest import mock

from ai_agent.qgis_tools.data import catalogue, coverage, load_dataset, load_imagery, region, search_imagery, stac
from ai_agent.qgis_tools.registry import get_tool_by_name
from ai_agent.skills.registry import SKILL_REGISTRY


class Layer:
    def __init__(self, source, name, provider):
        self.source, self._name, self.provider = source, name, provider

    def isValid(self):
        return True

    def name(self):
        return self._name

    def id(self):
        return "id-" + self._name

    def featureCount(self):
        return 6

    def bandCount(self):
        return 3

    def dataProvider(self):
        if not hasattr(self, "provider_calls"):
            self.provider_calls = []
        return mock.Mock(setUserNoDataValue=lambda band, ranges: self.provider_calls.append(band))


class CatalogueTest(unittest.TestCase):
    def test_words_rank_the_matching_datasets_first(self):
        self.assertEqual(catalogue.search("elevation")[0].id, "cop-dem-glo-30")
        self.assertIn(catalogue.search("district boundaries")[0].id, ("geoboundaries",))
        self.assertEqual(catalogue.search("satellite image")[0].kind, catalogue.KIND_IMAGERY)
        self.assertEqual(len(catalogue.search("")), len(catalogue.DATASETS))
        self.assertEqual(catalogue.search("zzzz"), [])

    def test_unknown_or_wrong_kind_lists_what_exists(self):
        with self.assertRaisesRegex(ValueError, "sentinel-2-l2a"):
            catalogue.dataset("modis", catalogue.KIND_IMAGERY)
        with self.assertRaisesRegex(ValueError, "Unknown dataset"):
            catalogue.dataset("natural-earth", catalogue.KIND_IMAGERY)

    def test_every_imagery_default_asset_is_offered(self):
        for item in catalogue.DATASETS:
            if item.kind == catalogue.KIND_IMAGERY:
                self.assertIn(item.default_asset, item.assets, item.id)

    def test_the_skill_and_the_tools_agree(self):
        self.assertEqual(
            SKILL_REGISTRY.get("data").tool_names, ["find_open_data", "search_imagery", "load_imagery", "load_dataset"]
        )
        found = get_tool_by_name("find_open_data").execute({"query": "land cover"})
        self.assertIn("esa-worldcover", [entry["id"] for entry in found["datasets"]])


class RegionTest(unittest.TestCase):
    def test_numbers_are_checked(self):
        self.assertEqual(region.region({"bbox": "37.5, 55.6, 37.8, 55.9"}), (37.5, 55.6, 37.8, 55.9))
        with self.assertRaisesRegex(ValueError, "inverted"):
            region.region({"bbox": "38,55,37,56"})
        with self.assertRaisesRegex(ValueError, "wider"):
            region.region({"bbox": "0,0,30,10"})
        with self.assertRaisesRegex(ValueError, "No area"):
            region.region({})
        with self.assertRaisesRegex(ValueError, "not both"):
            region.region({"bbox": "1,1,2,2", "layer_name": "x"})


class SearchImageryTest(unittest.TestCase):
    def test_an_optical_search_filters_clouds_and_sorts_clearest_first(self):
        answer = {
            "features": [
                {
                    "id": "S2C_X",
                    "bbox": [37.0, 55.0, 38.0, 56.0],
                    "properties": {"datetime": "2026-09-10T08:46:01Z", "eo:cloud_cover": 0.4, "s2:mgrs_tile": "37VDC"},
                }
            ]
        }
        with mock.patch.object(stac, "post_json", return_value=answer) as sent:
            result = search_imagery.SearchImageryTool().execute(
                {"collection": "sentinel-2-l2a", "bbox": "37.5,55.6,37.8,55.9", "date_from": "2026-06-01"}
            )
        url, body = sent.call_args.args
        self.assertTrue(url.endswith("/search"))
        self.assertEqual(body["query"], {"eo:cloud_cover": {"lte": 20.0}})
        self.assertEqual(body["sortby"][0], {"field": "properties.eo:cloud_cover", "direction": "asc"})
        self.assertEqual(body["datetime"], "2026-06-01T00:00:00Z/..")
        self.assertEqual(
            result["scenes"][0],
            {
                "id": "S2C_X",
                "date": "2026-09-10",
                "cloud_cover": 0.4,
                "tile": "37VDC",
                "bbox": [37.0, 55.0, 38.0, 56.0],
            },
        )

    def test_timeless_tiles_ignore_clouds_and_report_an_empty_search(self):
        with mock.patch.object(stac, "post_json", return_value={"features": []}) as sent:
            result = search_imagery.SearchImageryTool().execute({"collection": "cop-dem-glo-30", "bbox": "1,1,2,2"})
        self.assertNotIn("query", sent.call_args.args[1])
        self.assertIn("No scene", result["note"])

    def test_bad_dates_and_collections_are_refused_before_the_queue(self):
        tool = search_imagery.SearchImageryTool()
        with self.assertRaisesRegex(ValueError, "not a date"):
            tool.prepare({"collection": "sentinel-2-l2a", "bbox": "1,1,2,2", "date_from": "June"})
        with self.assertRaisesRegex(ValueError, "after"):
            tool.prepare(
                {"collection": "sentinel-2-l2a", "bbox": "1,1,2,2", "date_from": "2026-09-01", "date_to": "2026-06-01"}
            )
        with self.assertRaisesRegex(ValueError, "Unknown dataset"):
            tool.prepare({"collection": "geoboundaries", "bbox": "1,1,2,2"})


class CoverageTest(unittest.TestCase):
    def test_the_share_of_the_area_inside_a_footprint(self):
        square = {"type": "Polygon", "coordinates": [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]]}
        self.assertEqual(coverage.covered_share(square, (0, 0, 1, 1)), 100.0)
        self.assertEqual(coverage.covered_share(square, (1, 1, 3, 3)), 25.0)
        sliver = {"type": "MultiPolygon", "coordinates": [[[[0, 0], [1, 0], [0, 1], [0, 0]]]]}
        self.assertEqual(coverage.covered_share(sliver, (0, 0, 1, 1)), 50.0)
        self.assertIsNone(coverage.covered_share({"type": "Point"}, (0, 0, 1, 1)))

    def test_scenes_that_cover_the_area_come_before_clearer_slivers(self):
        def scene(name, cloud, ring):
            return {
                "id": name,
                "geometry": {"type": "Polygon", "coordinates": [ring]},
                "properties": {"eo:cloud_cover": cloud},
            }

        full = [[0, 0], [3, 0], [3, 3], [0, 3], [0, 0]]
        edge = [[0, 0], [1.2, 0], [1.2, 3], [0, 3], [0, 0]]
        answer = {"features": [scene("edge", 0.1, edge), scene("full", 4.0, full)]}
        with mock.patch.object(stac, "post_json", return_value=answer):
            found = stac.search("sentinel-2-l2a", (1, 1, 2, 2), "", 20.0, 2, False)
        self.assertEqual([item["id"] for item in found], ["full", "edge"])
        self.assertEqual(found[1]["covers_area_percent"], 20.0)


class TokenTest(unittest.TestCase):
    def setUp(self):
        stac._tokens.clear()

    def test_a_token_is_per_container_and_reused_until_close_to_expiry(self):
        future = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 3600))
        with mock.patch.object(stac, "get_json", return_value={"token": "se=1&sig=a", "msft:expiry": future}) as asked:
            link, expiry = stac.signed("https://acct.blob.core.windows.net/box/a.tif")
            stac.signed("https://acct.blob.core.windows.net/box/b.tif")
        self.assertEqual((link, expiry), ("https://acct.blob.core.windows.net/box/a.tif?se=1&sig=a", future))
        self.assertEqual(asked.call_count, 1)
        self.assertTrue(asked.call_args.args[0].endswith("/token/acct/box"))

    def test_no_token_or_foreign_storage_is_an_error_for_the_model(self):
        with mock.patch.object(stac, "get_json", return_value={}), self.assertRaisesRegex(ValueError, "read token"):
            stac.sas_token("https://acct.blob.core.windows.net/box/a.tif")
        with self.assertRaisesRegex(ValueError, "not in Planetary Computer storage"):
            stac.sas_token("https://example.com/a.tif")


SCENE = {
    "id": "S2C_X",
    "properties": {"datetime": "2026-09-10T08:46:01Z"},
    "assets": {"visual": {"href": "https://blob/visual.tif"}, "red": {"href": "https://blob/r.tif"}},
}


class LoadImageryTest(unittest.TestCase):
    def test_prepare_checks_assets_and_counts(self):
        tool = load_imagery.LoadImageryTool()
        prepared = tool.prepare({"collection": "sentinel-2-l2a", "item_ids": "S2C_X"})
        self.assertEqual((prepared["item_ids"], prepared["asset"]), (["S2C_X"], "visual"))
        with self.assertRaisesRegex(ValueError, "no asset"):
            tool.prepare({"collection": "sentinel-2-l2a", "item_ids": ["a"], "asset": "nir"})
        with self.assertRaisesRegex(ValueError, "too many"):
            tool.prepare({"collection": "cop-dem-glo-30", "item_ids": [str(n) for n in range(9)]})
        with self.assertRaisesRegex(ValueError, "empty"):
            tool.prepare({"collection": "cop-dem-glo-30", "item_ids": []})

    def test_a_scene_opens_in_place_through_a_signed_link(self):
        added = []
        project = mock.Mock(addMapLayer=lambda layer, show=True: added.append(layer))
        project.layerTreeRoot.return_value.children.return_value = ["a", "b"]
        with (
            mock.patch.object(load_imagery, "item", return_value=SCENE),
            mock.patch.object(load_imagery, "signed", side_effect=lambda href: (href + "?sig", "2026-10-07T11:00:00Z")),
            mock.patch.object(load_imagery, "QgsRasterLayer", Layer),
            mock.patch.object(load_imagery.QgsProject, "instance", return_value=project),
        ):
            result = load_imagery.LoadImageryTool().execute({"collection": "sentinel-2-l2a", "item_ids": ["S2C_X"]})
        self.assertEqual(added[0].source, "/vsicurl/https://blob/visual.tif?sig")
        self.assertEqual(result["added"][0]["layer"], "Sentinel-2 Level-2A 2026-09-10")
        self.assertEqual(added[0].provider_calls, [1, 2, 3], "the no-data frame must be transparent")
        project.layerTreeRoot.return_value.insertLayer.assert_called_once_with(2, added[0])
        self.assertIn("2026-10-07T11:00:00Z", result["note"])


class LoadDatasetTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.added = []
        self.patches = [
            mock.patch.object(load_dataset, "target_path", side_effect=self.path),
            mock.patch.object(load_dataset, "QgsVectorLayer", Layer),
            mock.patch.object(
                load_dataset.QgsProject, "instance", return_value=mock.Mock(addMapLayer=self.added.append)
            ),
        ]
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)

    def path(self, stem, suffix):
        return os.path.join(self.folder, stem + suffix), True

    def test_natural_earth_picks_the_scale_and_downloads_from_the_mirror(self):
        tool = load_dataset.LoadDatasetTool()
        self.assertEqual(tool.prepare({"dataset": "natural-earth", "layer": "roads"})["scale"], "10m")
        with self.assertRaisesRegex(ValueError, "10m only"):
            tool.prepare({"dataset": "natural-earth", "layer": "ports", "scale": "110m"})
        with mock.patch.object(load_dataset, "get_bytes", return_value=b"{}") as fetched:
            result = tool.execute({"dataset": "natural-earth", "layer": "countries"})
        self.assertTrue(fetched.call_args.args[0].endswith("/geojson/ne_50m_admin_0_countries.geojson"))
        self.assertEqual(result["layer"], "Countries (50m)")
        self.assertIn("storage_note", result)

    def test_geoboundaries_asks_the_api_then_downloads_the_simplified_file(self):
        meta = {
            "boundaryName": "Kenya",
            "boundaryLicense": "CC BY 3.0 IGO",
            "gjDownloadURL": "https://github.com/full.geojson",
            "simplifiedGeometryGeoJSON": "https://github.com/simple.geojson",
        }
        with (
            mock.patch.object(load_dataset, "get_json", return_value=meta) as asked,
            mock.patch.object(load_dataset, "get_bytes", return_value=b"{}") as fetched,
        ):
            result = load_dataset.LoadDatasetTool().execute(
                {"dataset": "geoboundaries", "country": "ken", "level": "ADM1"}
            )
        self.assertTrue(asked.call_args.args[0].endswith("/gbOpen/KEN/ADM1/"))
        self.assertEqual(fetched.call_args.args[0], "https://github.com/simple.geojson")
        self.assertEqual((result["layer"], result["license"]), ("Kenya ADM1", "CC BY 3.0 IGO"))
        with self.assertRaisesRegex(ValueError, "alpha-3"):
            load_dataset.LoadDatasetTool().prepare({"dataset": "geoboundaries", "country": "Kenya"})


if __name__ == "__main__":
    unittest.main()
