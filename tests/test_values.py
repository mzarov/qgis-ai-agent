import unittest

from qgis_ai_agent.qgis_tools.common.values import (
    clamp_limit,
    plain_value,
    suggest_fields,
)


class Null:
    def isNull(self):
        return True


class ClampLimitTest(unittest.TestCase):
    def test_none_gives_default(self):
        self.assertEqual(clamp_limit(None, 25, 100), 25)

    def test_garbage_gives_default(self):
        self.assertEqual(clamp_limit("abc", 25, 100), 25)

    def test_above_maximum_is_capped(self):
        self.assertEqual(clamp_limit(500, 25, 100), 100)

    def test_zero_becomes_one(self):
        self.assertEqual(clamp_limit(0, 25, 100), 1)

    def test_negative_becomes_one(self):
        self.assertEqual(clamp_limit(-8, 25, 100), 1)


class PlainValueTest(unittest.TestCase):
    def test_scalars_pass_through(self):
        for value in ("текст", 12, 3.5, True):
            self.assertEqual(plain_value(value), value)

    def test_none_stays_none(self):
        self.assertIsNone(plain_value(None))

    def test_qvariant_null_becomes_none(self):
        self.assertIsNone(plain_value(Null()))

    def test_other_objects_become_strings(self):
        self.assertEqual(plain_value(object.__str__), str(object.__str__))


class SuggestFieldsTest(unittest.TestCase):
    def test_close_match_is_offered(self):
        hint = suggest_fields(["hwy"], ["highway", "name", "surface"])
        self.assertIn("highway", hint)
        self.assertIn("Похожие поля", hint)

    def test_several_typos_all_offered(self):
        hint = suggest_fields(["hwy", "nam"], ["highway", "name"])
        self.assertIn("highway", hint)
        self.assertIn("name", hint)

    def test_long_list_is_truncated(self):
        available = [f"field_{index}" for index in range(80)]
        hint = suggest_fields(["совсем_другое"], available)
        self.assertIn("Всего полей 80", hint)
        self.assertLess(len(hint), 400)

    def test_short_list_is_shown_whole(self):
        hint = suggest_fields(["нет"], ["a", "b"])
        self.assertIn("Доступные поля", hint)


if __name__ == "__main__":
    unittest.main()
