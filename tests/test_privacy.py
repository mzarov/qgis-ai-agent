import pathlib
import unittest

from ai_agent.core import privacy
from ai_agent.core.agent import request as request_module
from ai_agent.qgis_tools.base import EGRESS_FEATURE_VALUES, EGRESS_IMAGE, EGRESS_METADATA
from ai_agent.qgis_tools.inspect.canvas_extent import GetCanvasExtentTool
from ai_agent.qgis_tools.inspect.describe_layer import DescribeLayerTool
from ai_agent.qgis_tools.inspect.field_values import GetFieldValuesTool
from ai_agent.qgis_tools.inspect.list_layers import ListLayersTool
from ai_agent.qgis_tools.inspect.render_map import RenderMapTool
from ai_agent.qgis_tools.inspect.sample_features import SampleFeaturesTool
from ai_agent.qgis_tools.project.views import SaveBookmarkTool
from ai_agent.qgis_tools.project.zoom_to_layer import ZoomToLayerTool
from ai_agent.qgis_tools.python.run_python import RunPythonTool
from ai_agent.qgis_tools.style.describe_style import DescribeStyleTool
from ai_agent.ui import dock_widget


class MessageBoxProbe:
    latest = None

    class Icon:
        Question = 1

    class StandardButton:
        Yes = 1
        No = 2

    def __init__(self, *_args):
        self.default_button = None
        MessageBoxProbe.latest = self

    def setIcon(self, _icon):
        pass

    def setWindowTitle(self, _title):
        pass

    def setTextFormat(self, _text_format):
        pass

    def setText(self, _text):
        pass

    def setStandardButtons(self, _buttons):
        pass

    def setDefaultButton(self, button):
        self.default_button = button

    def exec(self):
        return self.StandardButton.No


class PrivacyClassificationTest(unittest.TestCase):
    def test_metadata_tools_remain_available_in_privacy_mode(self):
        self.assertEqual(ListLayersTool().egress, EGRESS_METADATA)

    def test_feature_samples_and_values_are_sensitive(self):
        self.assertEqual(SampleFeaturesTool().egress, EGRESS_FEATURE_VALUES)
        self.assertEqual(GetFieldValuesTool().egress, EGRESS_FEATURE_VALUES)

    def test_rendered_maps_are_sensitive(self):
        self.assertEqual(RenderMapTool().egress, EGRESS_IMAGE)

    def test_style_categories_and_ranges_are_sensitive_values(self):
        self.assertEqual(DescribeStyleTool().egress, EGRESS_FEATURE_VALUES)

    def test_layer_sources_filters_and_arbitrary_python_are_sensitive(self):
        self.assertEqual(DescribeLayerTool().egress, EGRESS_FEATURE_VALUES)
        self.assertEqual(RunPythonTool().egress, EGRESS_FEATURE_VALUES)

    def test_exact_spatial_extents_are_sensitive(self):
        self.assertEqual(GetCanvasExtentTool().egress, EGRESS_FEATURE_VALUES)
        self.assertEqual(ZoomToLayerTool().egress, EGRESS_FEATURE_VALUES)
        self.assertEqual(SaveBookmarkTool().egress, EGRESS_FEATURE_VALUES)

    def test_endpoint_label_never_displays_path_query_or_credentials(self):
        label = privacy.endpoint_label("https://user:secret@example.com:8443/v1?token=x")
        self.assertEqual(label, "https://example.com:8443")

    def test_malformed_port_does_not_break_the_consent_prompt(self):
        self.assertEqual(privacy.endpoint_label("https://example.com:not-a-port/v1"), "https://example.com")

    def test_the_request_builder_itself_has_no_consent_gate(self):
        self.assertNotIn("data_sharing", pathlib.Path(request_module.__file__).read_text(encoding="utf-8"))

    def test_first_send_dialog_defaults_to_yes_so_enter_sends(self):
        saved = dock_widget.QMessageBox
        dock_widget.QMessageBox = MessageBoxProbe
        try:
            dock_widget.AgentDockWidget.confirm_data_sharing(None, "https://provider.example")
        finally:
            dock_widget.QMessageBox = saved
        self.assertEqual(MessageBoxProbe.latest.default_button, MessageBoxProbe.StandardButton.Yes)


class NoPrivacyModeTest(unittest.TestCase):
    def test_every_tool_of_a_loaded_skill_is_offered_to_a_cloud_model(self):
        from ai_agent.core.agent.request import build_tool_schemas_for

        names = {
            schema["function"]["name"]
            for schema in build_tool_schemas_for(["inspect", "processing", "style"], "https://api.example.com/v1")
        }
        for tool in ("describe_layer", "query_layer", "render_map", "run_processing", "describe_style"):
            self.assertIn(tool, names)


if __name__ == "__main__":
    unittest.main()
