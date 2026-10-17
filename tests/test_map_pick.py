import unittest

from ai_agent.core.orchestrator import map_pick
from ai_agent.ui.composer_parts import LAYER_TOKEN


class PlaceTextTest(unittest.TestCase):
    """The words a picked place adds to the request: lon before lat, as the prompt explains."""

    def test_a_point_is_longitude_then_latitude(self):
        self.assertEqual(map_pick.point_text(37.620801, 55.753912), "@point(37.62080, 55.75391)")

    def test_an_area_is_west_south_east_north(self):
        self.assertEqual(map_pick.area_text(37.6, 55.74, 37.65, 55.77), "@area(37.60000, 55.74000, 37.65000, 55.77000)")

    def test_the_box_paints_a_place_as_one_token_with_its_spaces(self):
        # Painted up to the first space, "@area(61.82729," stood out and the rest of it did not.
        text = "cafes in @area(61.82729, 57.65688, 62.29008, 57.87134) near @roads and @point(37.6, 55.7)"
        self.assertEqual(
            [match.group() for match in LAYER_TOKEN.finditer(text)],
            ["@area(61.82729, 57.65688, 62.29008, 57.87134)", "@roads", "@point(37.6, 55.7)"],
        )
        self.assertEqual([match.group() for match in LAYER_TOKEN.finditer("@pointless layer")], ["@pointless"])

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
