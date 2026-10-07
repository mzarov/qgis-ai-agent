import sys
import unittest
from unittest import mock

from ai_agent.qgis_tools.project.zoom_to_area import DEFAULT_SCALE, MAX_SCALE, ZoomToAreaTool, parse_bbox


class ZoomToAreaTest(unittest.TestCase):
    def setUp(self):
        self.tool = ZoomToAreaTool()

    def test_a_geocode_bbox_is_read_as_west_south_east_north(self):
        self.assertEqual(parse_bbox("4.0,51.8,4.6,52.0"), (4.0, 51.8, 4.6, 52.0))
        for broken in ("4,51,4.6", "east,south,west,north", "10,50,5,53", "4,95,5,96"):
            with self.assertRaises(ValueError):
                parse_bbox(broken)

    def test_prepare_wants_one_kind_of_area(self):
        with self.assertRaisesRegex(ValueError, "bbox"):
            self.tool.prepare({})
        with self.assertRaisesRegex(ValueError, "not both"):
            self.tool.prepare({"bbox": "4,51,5,52", "lon": 4.5, "lat": 51.9})
        with self.assertRaisesRegex(ValueError, "outside"):
            self.tool.prepare({"lon": 200, "lat": 10})
        point = self.tool.prepare({"lon": "4.89", "lat": 52.37})
        self.assertEqual((point["lon"], point["lat"], point["scale"]), (4.89, 52.37, DEFAULT_SCALE))
        self.assertEqual(self.tool.prepare({"lon": 0, "lat": 0, "scale": 1e12})["scale"], MAX_SCALE)

    def test_the_row_names_the_place(self):
        self.assertEqual(
            self.tool.summarize_call({"place": "Rotterdam", "bbox": "4,51,5,52"}), "Moving the map to Rotterdam."
        )
        self.assertIn("52.37", self.tool.summarize_call({"lon": 4.89, "lat": 52.37}))
        self.assertEqual(self.tool.summarize_call({"bbox": "nonsense"}), "Moving the map view.")

    def test_a_bbox_sets_the_extent_and_a_point_centres_at_a_scale(self):
        canvas = mock.Mock()
        canvas.scale.return_value = 50000.4
        with mock.patch.dict(sys.modules, {"qgis.utils": mock.Mock(iface=mock.Mock(mapCanvas=lambda: canvas))}):
            self.tool.execute({"bbox": "4,51,5,52"})
            canvas.setExtent.assert_called_once()
            result = self.tool.execute({"lon": 4.89, "lat": 52.37, "scale": 10000})
        canvas.zoomScale.assert_called_once_with(10000.0)
        self.assertEqual(result["scale"], 50000)

    def test_without_a_map_window_it_says_so(self):
        no_window = mock.patch.dict(sys.modules, {"qgis.utils": mock.Mock(iface=None)})
        with no_window, self.assertRaisesRegex(ValueError, "map is not available"):
            self.tool.execute({"bbox": "4,51,5,52"})


if __name__ == "__main__":
    unittest.main()
