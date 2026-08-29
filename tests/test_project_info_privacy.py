import unittest

from ai_agent.qgis_tools.inspect import project_info


class _EmptyTree:
    def children(self):
        return []


class _Themes:
    def mapThemes(self):
        return []


class _Crs:
    def authid(self):
        return "EPSG:4326"

    def description(self):
        return "WGS 84"

    def isGeographic(self):
        return True


class _Project:
    def title(self):
        return ""

    def fileName(self):
        return "/Users/alice/confidential/client-map.qgz"

    def isDirty(self):
        return False

    def crs(self):
        return _Crs()

    def distanceUnits(self):
        return 0

    def areaUnits(self):
        return 0

    def ellipsoid(self):
        return "WGS84"

    def layerTreeRoot(self):
        return _EmptyTree()

    def mapThemeCollection(self):
        return _Themes()


class ProjectInfoPrivacyTest(unittest.TestCase):
    def test_project_info_exposes_only_the_file_basename(self):
        saved = project_info.QgsProject
        project_info.QgsProject = type("ProjectSingleton", (), {"instance": staticmethod(_Project)})
        try:
            result = project_info.GetProjectInfoTool().execute({})
        finally:
            project_info.QgsProject = saved

        self.assertEqual(result["file_name"], "client-map.qgz")
        self.assertNotIn("file_path", result)
        self.assertNotIn("/Users/alice/confidential", repr(result))


if __name__ == "__main__":
    unittest.main()
