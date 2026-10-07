import unittest

from qgis.PyQt.QtWidgets import QWidget

from ai_agent.ui import compass


class TimingTest(unittest.TestCase):
    def test_css_easings_start_and_end_where_they_should(self):
        for easing in (compass.EASE_IN_OUT, compass.SETTLE, compass.LINEAR):
            self.assertAlmostEqual(compass.cubic_bezier(easing, 0.0), 0.0, places=3)
            self.assertAlmostEqual(compass.cubic_bezier(easing, 1.0), 1.0, places=3)
        self.assertAlmostEqual(compass.cubic_bezier(compass.LINEAR, 0.3), 0.3, places=3)
        self.assertAlmostEqual(compass.cubic_bezier(compass.EASE_IN_OUT, 0.5), 0.5, places=2)
        self.assertGreater(compass.cubic_bezier(compass.SETTLE, 0.3), 0.5)

    def test_every_motion_passes_through_its_keyframes(self):
        for state, motion in compass.MOTIONS.items():
            for fraction, degrees in motion.keys:
                self.assertAlmostEqual(compass.angle_at(state, fraction), degrees, places=1, msg=(state, fraction))

    def test_the_states_rest_where_the_handoff_says(self):
        self.assertEqual(compass.angle_at(compass.REST, 0.7), 45.0)
        self.assertEqual(compass.angle_at(compass.NORTH_STATE, 0.2), 0.0)
        self.assertEqual(compass.end_angle(compass.DONE), 0.0)
        self.assertEqual(compass.end_angle(compass.ARRIVE), 45.0)
        self.assertEqual(compass.end_angle(compass.ERROR), 45.0)
        self.assertEqual(compass.angle_at("unknown", 0.5), 45.0)
        self.assertTrue(compass.MOTIONS[compass.SEARCH].loops)
        self.assertFalse(compass.MOTIONS[compass.DONE].loops)

    def test_the_search_swing_stays_in_its_arc(self):
        angles = [compass.angle_at(compass.SEARCH, step / 100) for step in range(101)]
        self.assertGreaterEqual(min(angles), 18 - 0.01)
        self.assertLessEqual(max(angles), 82 + 0.01)

    def test_lines_get_lighter_as_the_mark_grows(self):
        self.assertEqual(compass.weights(14), (2.6, 1.7))
        self.assertEqual(compass.weights(24), (2.2, 1.5))
        self.assertEqual(compass.weights(56), (1.9, 1.3))


class WidgetTest(unittest.TestCase):
    def test_a_state_sets_the_needle_and_stop_settles_it(self):
        mark = compass.Compass(18, QWidget().palette())
        self.assertEqual(mark.angle, 45.0)
        mark.set_state(compass.ARRIVE)
        self.assertEqual(mark.state, compass.ARRIVE)
        self.assertAlmostEqual(mark.angle, -140.0, places=3)
        mark.stop()
        self.assertEqual(mark.angle, 45.0)
        mark.set_state(compass.SEARCH)
        mark.stop()
        self.assertEqual(mark.angle, 45.0)
        mark.set_state(compass.DONE)
        mark.stop()
        self.assertEqual(mark.angle, 0.0)
        mark.set_state(compass.NORTH_STATE)
        self.assertEqual(mark.angle, 0.0)


if __name__ == "__main__":
    unittest.main()
