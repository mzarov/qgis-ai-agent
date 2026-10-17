"""The data check's pure parts: what a scan counts, how the report is shaped and capped, each problem's fix."""

import json
import unittest

from ai_agent.qgis_tools.quality import findings
from ai_agent.qgis_tools.quality.check_layer import CheckLayerTool, crs_facts, partial_note
from ai_agent.qgis_tools.quality.scan import MAX_FEATURES, invalid_reason
from ai_agent.qgis_tools.quality.tally import (
    BLANK,
    MAX_DUPLICATE_GROUPS,
    MAX_GROUP_IDS,
    MAX_INVALID_SAMPLES,
    MAX_SAMPLE_IDS,
    NULL,
    Bounds,
    Tally,
    missing_kind,
)
from ai_agent.qgis_tools.registry import get_tool_by_name


class NullDate:
    """A value type that knows it is empty, as a QDate or a QVariant does."""

    def isNull(self):
        return True


class Point:
    def __init__(self, x, y):
        self._x, self._y = x, y

    def x(self):
        return self._x

    def y(self):
        return self._y


class Error:
    def __init__(self, what, where=None):
        self._what, self._where = what, where

    def what(self):
        return self._what

    def hasWhere(self):
        return self._where is not None

    def where(self):
        return self._where


class Geometry:
    def __init__(self, errors):
        self._errors = errors

    def validateGeometry(self, engine):
        return self._errors


class Crs:
    def __init__(self, valid=True, authid="", description="", geographic=False):
        self._valid, self._authid, self._description, self._geographic = valid, authid, description, geographic

    def isValid(self):
        return self._valid

    def authid(self):
        return self._authid

    def description(self):
        return self._description

    def isGeographic(self):
        return self._geographic


class Layer:
    def __init__(self, crs):
        self._crs = crs

    def crs(self):
        return self._crs


def tally_of(*rows, fields=("name", "pop")):
    tally = Tally(list(fields))
    for values in rows:
        tally.checked += 1
        tally.add_values(values)
    return tally


class MissingValuesTest(unittest.TestCase):
    def test_none_and_null_types_are_null_spaces_are_blank_values_are_values(self):
        self.assertEqual(missing_kind(None), NULL)
        self.assertEqual(missing_kind(NullDate()), NULL)
        self.assertEqual(missing_kind("  "), BLANK)
        self.assertEqual(missing_kind(""), BLANK)
        for value in (0, 0.0, False, "x", [1]):
            with self.subTest(value=value):
                self.assertEqual(missing_kind(value), "")

    def test_a_field_without_a_single_value_is_empty_and_partial_gaps_are_counted(self):
        tally = tally_of([None, 5], ["", None], [" ", 7])
        self.assertEqual(tally.empty_fields(), ["name"])
        self.assertEqual([(name, gaps.null, gaps.blank) for name, gaps in tally.partly_missing()], [("pop", 1, 0)])

    def test_nothing_checked_means_no_field_is_called_empty(self):
        self.assertEqual(Tally(["name"]).empty_fields(), [])

    def test_the_fields_with_most_gaps_come_first(self):
        tally = tally_of([None, None, 1], [1, None, None], [1, None, 1], [1, 1, 1], fields=("a", "b", "c"))
        self.assertEqual([name for name, _ in tally.partly_missing()], ["b", "a", "c"])


class TallyCapsTest(unittest.TestCase):
    def test_invalid_geometries_keep_counting_past_the_sample_cap(self):
        tally = Tally([])
        for feature_id in range(MAX_INVALID_SAMPLES + 5):
            tally.add_invalid(feature_id, "Self-intersection")
        self.assertEqual(tally.invalid, MAX_INVALID_SAMPLES + 5)
        self.assertEqual(len(tally.invalid_samples), MAX_INVALID_SAMPLES)
        self.assertFalse(tally.wants_reason(), "a reason nobody will see is not worth GEOS's time")

    def test_empty_geometries_keep_counting_past_the_id_cap(self):
        tally = Tally([])
        for feature_id in range(MAX_SAMPLE_IDS * 3):
            tally.add_empty(feature_id)
        self.assertEqual((tally.empty, len(tally.empty_ids)), (MAX_SAMPLE_IDS * 3, MAX_SAMPLE_IDS))

    def test_duplicates_count_the_copies_beyond_the_first_and_group_by_shape(self):
        tally = Tally([])
        for feature_id, key in enumerate([b"a", b"b", b"a", b"c", b"a", b"b"], start=1):
            tally.add_geometry(feature_id, key)
        self.assertEqual(tally.duplicates, 3)
        self.assertEqual(tally.duplicate_groups, 2)
        self.assertEqual(list(tally.group_samples.values()), [[1, 3, 5], [2, 6]])

    def test_duplicate_groups_and_their_ids_are_capped(self):
        tally = Tally([])
        for group in range(MAX_DUPLICATE_GROUPS + 3):
            for copy in range(MAX_GROUP_IDS + 4):
                tally.add_geometry(group * 100 + copy, bytes([group]))
        self.assertEqual(tally.duplicate_groups, MAX_DUPLICATE_GROUPS + 3)
        self.assertEqual(tally.duplicates, (MAX_DUPLICATE_GROUPS + 3) * (MAX_GROUP_IDS + 3))
        self.assertEqual(len(tally.group_samples), MAX_DUPLICATE_GROUPS)
        self.assertTrue(all(len(ids) == MAX_GROUP_IDS for ids in tally.group_samples.values()))

    def test_bounds_grow_over_every_geometry(self):
        tally = Tally([])
        tally.add_bounds(Bounds(0, 0, 1, 1))
        tally.add_bounds(Bounds(-5, 2, 3, 9))
        self.assertEqual(tally.bounds, Bounds(-5, 0, 3, 9))


class CoordinatesTest(unittest.TestCase):
    def test_metres_under_a_geographic_crs_look_projected(self):
        bounds = Bounds(4_000_000, 6_000_000, 4_100_000, 6_100_000)
        self.assertEqual(findings.coordinate_kind(True, bounds), findings.COORDINATES_PROJECTED)
        self.assertEqual(findings.coordinate_kind(False, bounds), "")

    def test_degrees_under_a_projected_crs_look_like_degrees(self):
        bounds = Bounds(37.5, 55.6, 37.8, 55.9)
        self.assertEqual(findings.coordinate_kind(False, bounds), findings.COORDINATES_DEGREES)
        self.assertEqual(findings.coordinate_kind(True, bounds), "")

    def test_a_latitude_past_the_pole_is_no_degree(self):
        self.assertEqual(findings.coordinate_kind(True, Bounds(10, 10, 20, 91)), findings.COORDINATES_PROJECTED)
        self.assertEqual(findings.coordinate_kind(True, Bounds(-180, -90, 180, 90)), "")

    def test_no_geometry_means_nothing_to_judge(self):
        self.assertEqual(findings.coordinate_kind(True, None), "")
        self.assertEqual(findings.coordinate_block(True, None), {})

    def test_the_block_names_the_bounds_behind_the_note(self):
        block = findings.coordinate_block(True, Bounds(4_000_000.123456789, 0, 4_000_001, 1))
        self.assertIn("projected", block["coordinates"])
        self.assertEqual(block["data_bounds"]["xmin"], 4_000_000.123457)


class CrsSpreadTest(unittest.TestCase):
    def test_two_crss_are_ordinary_three_get_a_line(self):
        self.assertEqual(findings.crs_spread(["EPSG:4326", "EPSG:32637", "EPSG:4326"]), "")
        line = findings.crs_spread(["EPSG:4326", "EPSG:32637", "EPSG:3857", ""])
        self.assertEqual(line, "The project's data layers use 3 different CRSs: EPSG:4326, EPSG:32637, EPSG:3857.")

    def test_a_long_list_is_cut(self):
        labels = [f"EPSG:{code}" for code in range(32601, 32601 + findings.MAX_LISTED_CRS + 2)]
        line = findings.crs_spread(labels)
        self.assertIn(f"{findings.MAX_LISTED_CRS + 2} different CRSs", line)
        self.assertTrue(line.endswith("and 2 more."))


class ReportTest(unittest.TestCase):
    def broken(self):
        tally = tally_of([None, 1], [None, 2], [None, None])
        tally.add_invalid(7, "Self-intersection at 0.5, 0.5")
        tally.add_empty(9)
        tally.add_geometry(1, b"x")
        tally.add_geometry(2, b"x")
        tally.add_bounds(Bounds(4_000_000, 6_000_000, 4_000_100, 6_000_100))
        return tally

    def test_a_clean_layer_has_no_problems_and_no_samples(self):
        tally = tally_of(["a", 1], ["b", 2])
        tally.add_bounds(Bounds(400_000, 6_000_000, 401_000, 6_001_000))
        report = findings.vector_findings(tally, geographic=False, crs_valid=True)
        self.assertEqual(report, {"problems": {}})
        self.assertEqual(findings.suggestions(report["problems"]), [])

    def test_counts_come_first_in_a_fixed_order_and_samples_follow(self):
        report = findings.vector_findings(self.broken(), geographic=True, crs_valid=True)
        self.assertEqual(next(iter(report)), "problems")
        self.assertEqual(
            report["problems"],
            {
                "suspicious_coordinates": 1,
                "invalid_geometry": 1,
                "empty_geometry": 1,
                "duplicate_geometry": 1,
                "empty_fields": 1,
            },
        )
        self.assertEqual(report["invalid_geometry"], [{"id": 7, "reason": "Self-intersection at 0.5, 0.5"}])
        self.assertEqual(report["empty_geometry_ids"], [9])
        self.assertEqual(report["duplicate_geometry_groups"], [[1, 2]])
        self.assertEqual(report["empty_fields"], ["name"])
        self.assertEqual(report["missing_values"], {"pop": {"null": 1}})
        self.assertIn("data_bounds", report)
        json.dumps(report)

    def test_an_invalid_crs_is_a_problem_and_its_coordinates_are_not_judged(self):
        report = findings.vector_findings(self.broken(), geographic=False, crs_valid=False)
        self.assertEqual(next(iter(report["problems"])), "invalid_crs")
        self.assertNotIn("suspicious_coordinates", report["problems"])
        self.assertNotIn("coordinates", report)

    def test_the_groups_total_is_said_only_when_groups_were_left_out(self):
        tally = Tally([])
        for group in range(MAX_DUPLICATE_GROUPS + 1):
            tally.add_geometry(group * 2, bytes([group]))
            tally.add_geometry(group * 2 + 1, bytes([group]))
        report = findings.vector_findings(tally, geographic=False, crs_valid=True)
        self.assertEqual(len(report["duplicate_geometry_groups"]), MAX_DUPLICATE_GROUPS)
        self.assertEqual(report["duplicate_groups_total"], MAX_DUPLICATE_GROUPS + 1)

    def test_listed_fields_are_capped(self):
        names = [f"f{index}" for index in range(findings.MAX_LISTED_FIELDS + 5)]
        tally = tally_of([None] * len(names), [None] * len(names), fields=names)
        report = findings.vector_findings(tally, geographic=False, crs_valid=True)
        self.assertEqual(report["problems"]["empty_fields"], len(names))
        self.assertEqual(len(report["empty_fields"]), findings.MAX_LISTED_FIELDS)


class SuggestionTest(unittest.TestCase):
    def test_each_problem_names_the_algorithm_that_fixes_it(self):
        expected = {
            "invalid_geometry": "native:fixgeometries",
            "empty_geometry": "native:removenullgeometries",
            "duplicate_geometry": "native:deleteduplicategeometries",
            "invalid_crs": "native:assignprojection",
            "empty_fields": "delete_field",
        }
        for problem, route in expected.items():
            with self.subTest(problem=problem):
                (line,) = findings.suggestions({problem: 1})
                self.assertIn(route, line)

    def test_processing_fixes_say_they_write_a_new_layer(self):
        for problem in ("invalid_geometry", "empty_geometry", "duplicate_geometry"):
            with self.subTest(problem=problem):
                self.assertIn("new layer", findings.suggestions({problem: 1})[0])

    def test_a_wrong_crs_is_assigned_never_reprojected(self):
        for kind in (findings.COORDINATES_PROJECTED, findings.COORDINATES_DEGREES):
            with self.subTest(kind=kind):
                (line,) = findings.suggestions({"suspicious_coordinates": 1}, kind)
                self.assertIn("native:assignprojection", line)
        self.assertIn("EPSG:4326", findings.suggestions({"suspicious_coordinates": 1}, "degrees")[0])

    def test_suggestions_follow_the_problem_order_then_the_project_and_nodata(self):
        lines = findings.suggestions(
            {"duplicate_geometry": 2, "invalid_geometry": 1}, crs_spread_found=True, nodata_missing=True
        )
        self.assertEqual(len(lines), 4)
        self.assertIn("fixgeometries", lines[0])
        self.assertIn("deleteduplicategeometries", lines[1])
        self.assertIn("no_data_values", lines[2])
        self.assertIn("native:reprojectlayer", lines[3])

    def test_unknown_or_zero_problems_suggest_nothing(self):
        self.assertEqual(findings.suggestions({"invalid_geometry": 0, "made_up": 3}), [])


class ScanPartsTest(unittest.TestCase):
    def test_geos_reason_names_the_place(self):
        geometry = Geometry([Error("Self-intersection", Point(0.5, 4_000_000.1234567))])
        self.assertEqual(invalid_reason(geometry), "Self-intersection at 0.5, 4000000.123457")

    def test_a_reason_without_a_place_or_errors_still_reads(self):
        self.assertEqual(invalid_reason(Geometry([Error("Too few points")])), "Too few points")
        self.assertEqual(invalid_reason(Geometry([])), "invalid")

    def test_the_partial_note_names_the_cap_and_the_total_when_known(self):
        self.assertIn(f"first {MAX_FEATURES} features of 120000", partial_note(MAX_FEATURES, 120000))
        self.assertIn("the layer has more", partial_note(MAX_FEATURES, None))

    def test_crs_facts(self):
        self.assertEqual(crs_facts(Layer(Crs(authid="EPSG:4326", geographic=True))), ("EPSG:4326", True, True))
        self.assertEqual(crs_facts(Layer(Crs(description="Local grid"))), ("Local grid", True, False))
        self.assertEqual(crs_facts(Layer(Crs(valid=False))), ("unknown", False, False))


class ToolTest(unittest.TestCase):
    def setUp(self):
        self.tool = get_tool_by_name("check_layer")

    def test_it_is_a_registered_read_of_its_own_skill(self):
        self.assertIsInstance(self.tool, CheckLayerTool)
        self.assertEqual((self.tool.skill, self.tool.safety), ("quality", "read"))
        self.assertFalse(self.tool.has_network_access({}))

    def test_the_call_names_the_layer_and_survives_bad_input(self):
        self.assertIn("roads", self.tool.summarize_call({"layer_name": "roads"}))
        for broken in ({}, {"layer_name": None}, {"layer_name": 5}):
            with self.subTest(params=broken):
                self.assertTrue(self.tool.summarize_call(broken))

    def test_the_result_line_counts_features_and_problems(self):
        payload = {
            "kind": "vector",
            "checked_features": 12,
            "problems": {"invalid_geometry": 1, "duplicate_geometry": 2, "empty_fields": 1},
        }
        self.assertEqual(
            self.tool.summarize_result({}, payload),
            "Checked 12 features: 1 feature with invalid geometry, 2 geometry duplicates, 1 empty field",
        )

    def test_a_clean_partial_and_a_raster_result(self):
        clean = {"kind": "vector", "checked_features": 1, "problems": {}}
        self.assertEqual(self.tool.summarize_result({}, clean), "Checked 1 feature: no problems found")
        partial = {"kind": "vector", "checked_features": MAX_FEATURES, "partial": True, "problems": {}}
        self.assertIn(f"first {MAX_FEATURES} features", self.tool.summarize_result({}, partial))
        raster = {"kind": "raster", "band_count": 3, "problems": {"invalid_crs": 1}}
        self.assertEqual(self.tool.summarize_result({}, raster), "Checked 3 bands: no valid CRS")

    def test_a_payload_without_problems_says_nothing(self):
        self.assertEqual(self.tool.summarize_result({}, {"error": "Layer not found"}), "")


if __name__ == "__main__":
    unittest.main()
