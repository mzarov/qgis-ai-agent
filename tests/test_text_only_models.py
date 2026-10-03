import unittest
from unittest import mock

from ai_agent.core.agent import request, verification
from ai_agent.core.agent.loop import AgentLoop
from ai_agent.core.agent.prompts import TOOLS_BLOCK_HEADER, build_verification_prompt
from ai_agent.core.agent.skills import load_skill, tools_for_skills
from ai_agent.core.agent.transcript import Transcript
from ai_agent.core.llm.turns import ToolCall
from ai_agent.qgis_tools.registry import ALL_TOOLS, get_tool_by_name

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

    def test_the_json_tools_block_omits_image_tools(self):
        with (
            mock.patch.object(request, "get_supports_images", return_value=False),
            mock.patch.object(request, "get_supports_tools", return_value=False),
        ):
            built = request.build_step_request(Transcript(), ["inspect", "layout"], [], dict(OVERRIDES))
        block = built.messages[0]["content"].split(TOOLS_BLOCK_HEADER, 1)[1]
        self.assertIn("- describe_layout:", block)
        for name in IMAGE_TOOLS:
            self.assertNotIn(f"- {name}:", block)

    def test_a_refusal_stored_mid_run_reaches_the_next_request(self):
        stored: dict[str, bool] = {}
        with mock.patch.object(
            request, "get_supports_images", side_effect=lambda url, model=None, dialect=None: stored.get(model)
        ):
            before = request.build_step_request(Transcript(), ["inspect"], [], dict(OVERRIDES))
            stored[OVERRIDES["model_override"]] = False
            after = request.build_step_request(Transcript(), ["inspect"], [], dict(OVERRIDES))
        self.assertIn("render_map", _names(before.tool_schemas))
        self.assertNotIn("render_map", _names(after.tool_schemas))


class LoopTest(unittest.TestCase):
    """The loop judges image support by the overrides its run started with."""

    def _loop(self) -> AgentLoop:
        loop = AgentLoop()
        loop._overrides = dict(OVERRIDES)
        return loop

    @staticmethod
    def _blind_for_this_model():
        return mock.patch.object(
            request,
            "get_supports_images",
            side_effect=lambda url, model=None, dialect=None: False if model == OVERRIDES["model_override"] else None,
        )

    def test_load_skill_reports_the_tools_this_model_is_offered(self):
        loop = self._loop()
        with self._blind_for_this_model():
            result = loop._load_skill(ToolCall(id="c1", name="load_skill", arguments={"names": ["layout"]}))
        self.assertNotIn("render_layout", result.payload["tools"])
        self.assertIn("describe_layout", result.payload["tools"])

    def test_an_image_tool_is_refused_without_rendering(self):
        loop = self._loop()
        tool = get_tool_by_name("render_map")
        with self._blind_for_this_model(), mock.patch.object(tool, "execute") as execute:
            result = loop._dispatch(ToolCall(id="c1", name="render_map", arguments={}))
        execute.assert_not_called()
        self.assertFalse(result.ok)
        self.assertIn("does not accept image input", result.payload["error"])
        self.assertTrue(result.payload["error"].startswith("render_map"))

    def test_with_unknown_support_the_image_tool_runs(self):
        loop = self._loop()
        tool = get_tool_by_name("render_map")
        with (
            mock.patch.object(request, "get_supports_images", return_value=None),
            mock.patch.object(tool, "execute", return_value={"width": 2}) as execute,
        ):
            result = loop._dispatch(ToolCall(id="c1", name="render_map", arguments={}))
        execute.assert_called_once()
        self.assertTrue(result.ok)


class VerificationPromptVariantTest(unittest.TestCase):
    def test_a_text_only_check_reads_instead_of_rendering(self):
        prompt = build_verification_prompt([{"tool": "set_symbol", "ok": True}], "make rivers blue", images=False)
        self.assertNotIn("render_map", prompt)
        self.assertNotIn("render_layout", prompt)
        self.assertNotIn("describe_layout", prompt)
        self.assertIn("cannot see images", prompt)
        self.assertIn("read tools of the skills you used", prompt)
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
        with mock.patch.object(verification, "detect_images_unsupported", return_value=unsupported) as detect:
            start = verification.plan_verification(
                [_Result("set_symbol")], 0, "make rivers blue", ["style"], dict(OVERRIDES)
            )
        detect.assert_called_once_with(OVERRIDES)
        assert start is not None
        return start.prompt

    def test_a_stored_refusal_picks_the_reading_variant(self):
        self.assertIn("cannot see images", self._prompt(True))

    def test_otherwise_the_check_renders(self):
        self.assertIn("render_map", self._prompt(False))


if __name__ == "__main__":
    unittest.main()
