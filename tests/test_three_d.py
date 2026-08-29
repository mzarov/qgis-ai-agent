import unittest

from ai_agent.qgis_tools.three_d import open_3d_view as module
from ai_agent.qgis_tools.three_d.open_3d_view import Open3dViewTool


class OpenViewTest(unittest.TestCase):
    def tearDown(self):
        module._find_opener = self.saved if hasattr(self, "saved") else module._find_opener

    def _patch(self, opener):
        self.saved = module._find_opener
        module._find_opener = lambda: opener

    def test_a_missing_api_yields_a_clear_refusal(self):
        self._patch(None)
        with self.assertRaises(ValueError) as caught:
            Open3dViewTool().execute({})
        self.assertIn("3D", str(caught.exception))

    def test_the_view_opens_with_the_given_name(self):
        seen = []
        self._patch(seen.append)
        result = Open3dViewTool().execute({"name": "Рельеф"})
        self.assertEqual(seen, ["Рельеф"])
        self.assertEqual(result["view"], "Рельеф")

    def test_an_argumentless_api_is_survived(self):
        calls = []

        def opener():
            calls.append(True)

        self._patch(opener)
        Open3dViewTool().execute({})
        self.assertEqual(calls, [True])

    def test_summary_never_raises(self):
        self.assertTrue(Open3dViewTool().summarize_call({}).strip())


if __name__ == "__main__":
    unittest.main()
