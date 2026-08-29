import base64
import unittest

from qgis_ai_agent.core.agent.executor import ToolExecutor
from qgis_ai_agent.core.agent.prompts import build_verification_prompt
from qgis_ai_agent.core.agent.transcript import (
    IMAGE_OMITTED_NOTE,
    ToolResult,
    Transcript,
)
from qgis_ai_agent.core.llm import anthropic, transport
from qgis_ai_agent.core.llm.client import ApiResponseError
from qgis_ai_agent.core.llm.transport import ModelTurn, ToolCall
from qgis_ai_agent.qgis_tools.base import RESULT_IMAGE_KEY
from qgis_ai_agent.qgis_tools.inspect.render_map import (
    DEFAULT_WIDTH,
    MAX_WIDTH,
    MIN_WIDTH,
    RenderMapTool,
    _clamped_width,
)

PIXEL = base64.b64encode(b"fake-png-bytes").decode("ascii")


def _image_turn() -> Transcript:
    transcript = Transcript()
    transcript.add_user("how does it look?")
    transcript.add_turn(ModelTurn(tool_calls=[ToolCall(id="c1", name="render_map")]))
    result = ToolResult(call=ToolCall(id="c1", name="render_map"), payload={"width": 2}, image=PIXEL)
    transcript.add_results([result], "native")
    return transcript


class TranscriptImageTest(unittest.TestCase):
    def test_image_travels_as_a_user_message_after_the_tool_result(self):
        messages = _image_turn().build_messages("sys")
        self.assertEqual(messages[-2]["role"], "tool")
        attachment = messages[-1]
        self.assertEqual(attachment["role"], "user")
        kinds = [block["type"] for block in attachment["content"]]
        self.assertEqual(kinds, ["text", "image_url"])
        self.assertIn(PIXEL, attachment["content"][1]["image_url"]["url"])

    def test_blind_endpoint_gets_a_text_note_instead(self):
        messages = _image_turn().build_messages("sys", include_images=False)
        self.assertIsInstance(messages[-1]["content"], str)
        self.assertIn(IMAGE_OMITTED_NOTE, messages[-1]["content"])

    def test_result_without_image_adds_no_extra_message(self):
        transcript = Transcript()
        transcript.add_turn(ModelTurn(tool_calls=[ToolCall(id="c1", name="list_layers")]))
        transcript.add_results([ToolResult(call=ToolCall(id="c1", name="list_layers"), payload={})], "native")
        messages = transcript.build_messages("sys")
        self.assertEqual(messages[-1]["role"], "tool")

    def test_json_protocol_also_carries_the_image(self):
        transcript = Transcript()
        result = ToolResult(call=ToolCall(id="c1", name="render_map"), payload={}, image=PIXEL)
        transcript.add_results([result], "json")
        messages = transcript.build_messages("sys")
        self.assertIsInstance(messages[-1]["content"], list)


class AnthropicImageTest(unittest.TestCase):
    def test_image_url_becomes_a_base64_source_block(self):
        message = {
            "role": "user",
            "content": [
                {"type": "text", "text": "look"},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{PIXEL}"}},
            ],
        }
        translated = anthropic.translate_message(message)
        image = translated["content"][1]
        self.assertEqual(image["type"], "image")
        self.assertEqual(image["source"]["media_type"], "image/png")
        self.assertEqual(image["source"]["data"], PIXEL)

    def test_a_non_data_url_is_dropped_not_sent(self):
        message = {
            "role": "user",
            "content": [{"type": "image_url", "image_url": {"url": "https://evil.example/x.png"}}],
        }
        self.assertIsNone(anthropic.translate_message(message))


class StripRetryTest(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.saved_dispatch = transport._dispatch
        self.saved_set = transport.set_supports_images
        self.flags = []
        transport.set_supports_images = lambda url, value: self.flags.append(value)

    def tearDown(self):
        transport._dispatch = self.saved_dispatch
        transport.set_supports_images = self.saved_set

    def _messages(self):
        return [
            {"role": "system", "content": "s"},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "look"},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{PIXEL}"}},
                ],
            },
        ]

    def test_rejected_images_are_stripped_and_retried_once(self):
        def fake(messages, tool_schemas, overrides, timeout, url, on_chunk=None, on_thinking=None):
            self.calls.append(messages)
            if len(self.calls) == 1:
                raise ApiResponseError(400, "invalid content")
            return ModelTurn(text="ok")

        transport._dispatch = fake
        turn = transport.call_model(self._messages(), [], {"url_override": "https://api.example/v1"})
        self.assertEqual(turn.text, "ok")
        self.assertEqual(len(self.calls), 2)
        retried = self.calls[1][1]["content"]
        self.assertIsInstance(retried, str)
        self.assertNotIn(PIXEL, retried)
        self.assertEqual(self.flags, [False])

    def test_flag_is_not_written_when_the_retry_fails_too(self):
        def fake(messages, tool_schemas, overrides, timeout, url, on_chunk=None, on_thinking=None):
            raise ApiResponseError(400, "still broken")

        transport._dispatch = fake
        with self.assertRaises(ApiResponseError):
            transport.call_model(self._messages(), [], {"url_override": "https://api.example/v1"})
        self.assertEqual(self.flags, [])

    def test_errors_without_images_pass_straight_through(self):
        def fake(messages, tool_schemas, overrides, timeout, url, on_chunk=None, on_thinking=None):
            self.calls.append(messages)
            raise ApiResponseError(400, "bad request")

        transport._dispatch = fake
        with self.assertRaises(ApiResponseError):
            transport.call_model([{"role": "user", "content": "hi"}], [], {"url_override": "https://api.example/v1"})
        self.assertEqual(len(self.calls), 1)


class ExecutorImageTest(unittest.TestCase):
    def test_the_image_key_is_lifted_out_of_the_payload(self):
        executor = ToolExecutor()
        from qgis_ai_agent.core.agent import executor as module

        saved = module.execute_tool
        module.execute_tool = lambda name, params: {"width": 2, RESULT_IMAGE_KEY: PIXEL}
        try:
            result = executor.run(ToolCall(id="c1", name="render_map"))
        finally:
            module.execute_tool = saved
        self.assertEqual(result.image, PIXEL)
        self.assertNotIn(RESULT_IMAGE_KEY, result.payload)
        self.assertTrue(result.payload["image_attached"])


class RenderMapTest(unittest.TestCase):
    def setUp(self):
        self.tool = RenderMapTool()

    def test_width_is_clamped_to_sane_bounds(self):
        self.assertEqual(_clamped_width(None), DEFAULT_WIDTH)
        self.assertEqual(_clamped_width("junk"), DEFAULT_WIDTH)
        self.assertEqual(_clamped_width(10), MIN_WIDTH)
        self.assertEqual(_clamped_width(99999), MAX_WIDTH)

    def test_headless_run_reports_the_missing_window(self):
        import sys as _sys

        utils = _sys.modules["qgis.utils"]
        saved = utils.iface
        utils.iface = None
        try:
            with self.assertRaises(ValueError) as caught:
                self.tool.execute({})
        finally:
            utils.iface = saved
        self.assertIn("without a QGIS window", str(caught.exception))

    def test_summary_never_raises(self):
        self.assertTrue(self.tool.summarize_call({}).strip())
        self.assertTrue(self.tool.summarize_call({"layer_name": "Дороги"}).strip())


class VerificationPromptTest(unittest.TestCase):
    def test_outcomes_are_listed_per_step(self):
        prompt = build_verification_prompt(
            [
                {"tool": "set_symbol", "ok": True},
                {"tool": "run_processing", "ok": False, "error": "boom"},
            ]
        )
        self.assertIn("- set_symbol: ok", prompt)
        self.assertIn("- run_processing: FAILED — boom", prompt)
        self.assertIn("render_map", prompt)

    def test_an_empty_apply_still_produces_a_prompt(self):
        self.assertIn("Verify", build_verification_prompt([]))


if __name__ == "__main__":
    unittest.main()
