import unittest
from unittest import mock

from ai_agent.qgis_tools.inspect import project_info
from tests.test_project_info_privacy import _Project


class _UnitProject(_Project):
    def distanceUnits(self):
        return "distance"

    def areaUnits(self):
        return "area"


class _Units:
    """Only stable codes exist here: a call to the translated toString fails the test."""

    @staticmethod
    def encodeUnit(unit):
        return {"distance": "meters", "area": "m2"}[unit]


class ProjectInfoUnitsTest(unittest.TestCase):
    def test_units_are_codes_not_interface_language_names(self):
        singleton = type("ProjectSingleton", (), {"instance": staticmethod(_UnitProject)})
        with (
            mock.patch.object(project_info, "QgsProject", singleton),
            mock.patch.object(project_info, "QgsUnitTypes", _Units),
        ):
            result = project_info.GetProjectInfoTool().execute({})

        self.assertEqual(result["distance_units"], "meters")
        self.assertEqual(result["area_units"], "m2")


if __name__ == "__main__":
    unittest.main()
