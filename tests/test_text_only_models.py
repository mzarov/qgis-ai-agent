import unittest
from unittest import mock

from ai_agent.core.agent import request, verification
from ai_agent.core.agent.prompts import build_verification_prompt
from ai_agent.core.agent.skills import load_skill, tools_for_skills
from ai_agent.core.agent.transcript import Transcript
from ai_agent.core.llm.transport import ToolCall
from ai_agent.qgis_tools.base import EGRESS_IMAGE
from ai_agent.qgis_tools.registry import ALL_TOOLS

IMAGE_TOOLS = {"render_map", "render_layout"}
OVERRIDES = {"url_override": "https://api.example/v1", "model_override": "text-only", "dialect_override": "openai"}


def _names(schemas: list[dict]) -> set[str]:
    return {schema["function"]["name"] for schema in schemas}


class _Result:
    def __init__(self, name: str) -> None:
        self.call = ToolCall(id="c1", name=name)
        self.ok = True
        self.payload: dict = {}


class ImageToolDeclarationTest(unittest.TestCase):
    def test_the_image_tools_declare_it(self):
        self.assertEqual({tool.name for tool in ALL_TOOLS if tool.returns_image}, IMAGE_TOOLS)

    def test_returning_an_image_and_image_egress_agree(self):
        for tool in ALL_TOOLS:
            with self.subTest(tool=tool.name):
                self.assertEqual(tool.returns_image, tool.egress == EGRESS_IMAGE)


class SchemaFilteringTest(unittest.TestCase):
    def test_image_tools_are_offered_by_default(self):
        names = _names(request.build_tool_schemas_for(["inspect", "layout"]))
        self.assertTrue(names >= IMAGE_TOOLS)

    def test_a_text_only_model_gets_no_image_tools(self):
        names = _names(request.build_tool_schemas_for(["inspect", "layout"], images=False))
        self.assertFalse(IMAGE_TOOLS & names)
        self.assertIn("describe_layout", names)
        self.assertIn("list_layers", names)
        self.assertIn("load_skill", names)

    def test_load_skill_lists_only_the_tools_offered(self):
        call = ToolCall(id="c1", name="load_skill", arguments={"names": ["layout"]})
        result, _ = load_skill(call, [], images=False)
        self.assertNotIn("render_layout", result.payload["tools"])
        self.assertIn("describe_layout", result.payload["tools"])
        result, _ = load_skill(call, [])
        self.assertIn("render_layout", result.payload["tools"])

    def test_tools_for_skills_keeps_image_tools_unless_told(self):
        self.assertIn("render_map", {tool.name for tool in tools_for_skills(["inspect"])})
        self.assertNotIn("render_map", {tool.name for tool in tools_for_skills(["inspect"], images=False)})


class StepRequestTest(unittest.TestCase):
    def _tool_names(self, stored: bool | None) -> set[str]:
        with mock.patch.object(request, "get_supports_images", return_value=stored):
            built = request.build_step_request(Transcript(), ["inspect", "layout"], [], dict(OVERRIDES))
        return _names(built.tool_schemas)

    def test_a_stored_refusal_drops_the_image_tools(self):
        self.assertFalse(IMAGE_TOOLS & self._tool_names(False))

    def test_unknown_support_behaves_as_before(self):
        self.assertTrue(self._tool_names(None) >= IMAGE_TOOLS)

    def test_known_support_keeps_the_image_tools(self):
        self.assertTrue(self._tool_names(True) >= IMAGE_TOOLS)


class VerificationPromptVariantTest(unittest.TestCase):
    def test_a_text_only_check_reads_instead_of_rendering(self):
        prompt = build_verification_prompt([{"tool": "set_symbol", "ok": True}], "make rivers blue", images=False)
        self.assertNotIn("render_map", prompt)
        self.assertNotIn("render_layout", prompt)
        self.assertIn("cannot see images", prompt)
        for tool in ("describe_style", "query_layer", "describe_layout"):
            self.assertIn(tool, prompt)
        self.assertIn("- set_symbol: ok", prompt)
        self.assertIn("If everything is right, queue nothing", prompt)

    def test_the_default_check_still_renders(self):
        prompt = build_verification_prompt([{"tool": "set_symbol", "ok": True}])
        self.assertIn("render_map", prompt)
        self.assertNotIn("cannot see images", prompt)

    def test_both_variants_read_as_one_sentence_flow(self):
        for images in (True, False):
            prompt = build_verification_prompt([], images=images)
            with self.subTest(images=images):
                self.assertNotIn("  ", prompt)
                self.assertIn(" Reply with a short verdict", prompt)


class PlanVerificationTest(unittest.TestCase):
    def _prompt(self, unsupported: bool) -> str:
        with mock.patch.object(verification, "detect_images_unsupported", return_value=unsupported):
            start = verification.plan_verification([_Result("set_symbol")], 0, "make rivers blue", ["style"])
        assert start is not None
        return start.prompt

    def test_a_stored_refusal_picks_the_reading_variant(self):
        self.assertIn("cannot see images", self._prompt(True))

    def test_otherwise_the_check_renders(self):
        self.assertIn("render_map", self._prompt(False))


if __name__ == "__main__":
    unittest.main()
