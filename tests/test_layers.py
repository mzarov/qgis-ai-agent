import unittest

from qgis_ai_agent.qgis_tools.common.layer_meta import sanitize_source
from qgis_ai_agent.qgis_tools.common.layers import utm_authid


class Extent:
    def __init__(self, x1, y1, x2, y2):
        self._box = (x1, y1, x2, y2)

    def xMinimum(self):
        return self._box[0]

    def yMinimum(self):
        return self._box[1]

    def xMaximum(self):
        return self._box[2]

    def yMaximum(self):
        return self._box[3]


class Layer:
    def __init__(self, *box):
        self._extent = Extent(*box) if box else None

    def extent(self):
        if self._extent is None:
            raise RuntimeError("нет охвата")
        return self._extent


class UtmZoneTest(unittest.TestCase):
    def test_sverdlovsk_region(self):
        self.assertEqual(utm_authid(Layer(57, 56, 64, 62)), "EPSG:32641")

    def test_moscow(self):
        self.assertEqual(utm_authid(Layer(36, 55, 38, 56)), "EPSG:32637")

    def test_southern_hemisphere(self):
        self.assertEqual(utm_authid(Layer(150, -34, 152, -33)), "EPSG:32756")

    def test_projected_coordinates_fall_back(self):
        self.assertEqual(utm_authid(Layer(-755412, 6195260, 1594380, 6898448)), "EPSG:3857")

    def test_broken_layer_falls_back(self):
        self.assertEqual(utm_authid(Layer()), "EPSG:3857")


class SanitizeSourceTest(unittest.TestCase):
    def test_postgis_password_is_hidden(self):
        source = "dbname='gis' host=db user='mzarov' password='S3cr3t!' table=roads"
        cleaned = sanitize_source(source)
        self.assertNotIn("S3cr3t", cleaned)
        self.assertIn("‹скрыто›", cleaned)

    def test_uppercase_key_is_hidden(self):
        self.assertNotIn("Qwerty", sanitize_source("user=admin PASSWORD=Qwerty123"))

    def test_token_in_url_is_hidden(self):
        self.assertNotIn("abc123", sanitize_source('url=https://x/wms?token="abc123"'))

    def test_apikey_is_hidden(self):
        self.assertNotIn("DEADBEEF", sanitize_source("url=https://x&apikey=DEADBEEF"))

    def test_primary_key_column_is_kept(self):
        self.assertIn("key='gid'", sanitize_source("dbname='g' key='gid' password='x'"))

    def test_file_path_untouched(self):
        path = "/Users/mzarov/data/Города.shp|layerid=0"
        self.assertEqual(sanitize_source(path), path)

    def test_long_source_is_truncated(self):
        self.assertLessEqual(len(sanitize_source("x" * 900)), 320)


if __name__ == "__main__":
    unittest.main()
