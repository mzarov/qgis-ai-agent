import unittest

from qgis_ai_agent.core import privacy
from qgis_ai_agent.core.agent import dispatch as dispatch_module
from qgis_ai_agent.core.agent import request as request_module
from qgis_ai_agent.core.agent.loop import AgentLoop
from qgis_ai_agent.core.agent.transcript import Transcript
from qgis_ai_agent.core.llm.transport import ToolCall
from qgis_ai_agent.qgis_tools.base import EGRESS_FEATURE_VALUES, EGRESS_IMAGE, EGRESS_METADATA
from qgis_ai_agent.qgis_tools.inspect.canvas_extent import GetCanvasExtentTool
from qgis_ai_agent.qgis_tools.inspect.describe_layer import DescribeLayerTool
from qgis_ai_agent.qgis_tools.inspect.field_values import GetFieldValuesTool
from qgis_ai_agent.qgis_tools.inspect.list_layers import ListLayersTool
from qgis_ai_agent.qgis_tools.inspect.render_map import RenderMapTool
from qgis_ai_agent.qgis_tools.inspect.sample_features import SampleFeaturesTool
from qgis_ai_agent.qgis_tools.project.views import SaveBookmarkTool
from qgis_ai_agent.qgis_tools.project.zoom_to_layer import ZoomToLayerTool
from qgis_ai_agent.qgis_tools.python.run_python import RunPythonTool
from qgis_ai_agent.qgis_tools.style.describe_style import DescribeStyleTool


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

    def test_local_endpoint_keeps_sensitive_tools_on_device(self):
        self.assertTrue(privacy.sensitive_data_allowed("http://127.0.0.1:11434/v1"))

    def test_endpoint_label_never_displays_path_query_or_credentials(self):
        label = privacy.endpoint_label("https://user:secret@example.com:8443/v1?token=x")
        self.assertEqual(label, "https://example.com:8443")

    def test_malformed_port_does_not_break_the_consent_prompt(self):
        self.assertEqual(privacy.endpoint_label("https://example.com:not-a-port/v1"), "https://example.com")


class PrivacyEnforcementTest(unittest.TestCase):
    def test_sensitive_tools_are_hidden_from_the_model(self):
        saved = request_module.tool_output_allowed
        request_module.tool_output_allowed = lambda tool, endpoint=None: tool.egress == EGRESS_METADATA
        try:
            names = [item["function"]["name"] for item in request_module.build_tool_schemas_for(["inspect"])]
        finally:
            request_module.tool_output_allowed = saved
        self.assertIn("list_layers", names)
        self.assertNotIn("sample_features", names)
        self.assertNotIn("render_map", names)

    def test_hallucinated_sensitive_call_is_still_blocked(self):
        saved = dispatch_module.tool_output_allowed
        seen = []
        dispatch_module.tool_output_allowed = lambda tool, endpoint=None: seen.append(endpoint) or False
        loop = AgentLoop()
        loop._overrides = {"url_override": "https://frozen.example/v1"}
        try:
            result = loop._dispatch(ToolCall(id="sensitive", name="sample_features", arguments={}))
        finally:
            dispatch_module.tool_output_allowed = saved
        self.assertFalse(result.ok)
        self.assertIn("Privacy mode", result.payload["error"])
        self.assertFalse(loop.has_pending_writes)
        self.assertEqual(seen, ["https://frozen.example/v1"])

    def test_request_builder_refuses_remote_egress_after_consent_is_revoked(self):
        saved = request_module.data_sharing_allowed
        request_module.data_sharing_allowed = lambda endpoint: False
        try:
            with self.assertRaisesRegex(PermissionError, "disabled"):
                request_module.build_step_request(
                    Transcript(),
                    [],
                    [],
                    {"url_override": "https://provider.example/v1"},
                )
        finally:
            request_module.data_sharing_allowed = saved


if __name__ == "__main__":
    unittest.main()
