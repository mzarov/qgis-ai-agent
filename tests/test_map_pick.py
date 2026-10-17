import unittest

from ai_agent.core.orchestrator import map_pick


class PlaceTextTest(unittest.TestCase):
    """The words a picked place adds to the request: lon before lat, as the prompt explains."""

    def test_a_point_is_longitude_then_latitude(self):
        self.assertEqual(map_pick.point_text(37.620801, 55.753912), "@point(37.62080, 55.75391)")

    def test_an_area_is_west_south_east_north(self):
        self.assertEqual(map_pick.area_text(37.6, 55.74, 37.65, 55.77), "@area(37.60000, 55.74000, 37.65000, 55.77000)")

    def test_a_picker_without_a_map_ends_at_once(self):
        class NoCanvas:
            def mapCanvas(self):
                return None

        picker = map_pick.MapPicker(NoCanvas())
        ended = []
        picker.ended.connect(lambda: ended.append(True))
        picker.start(map_pick.POINT)
        self.assertEqual(ended, [True])
        self.assertFalse(picker.active)


if __name__ == "__main__":
    unittest.main()
