import json
import unittest

from ai_agent.core.agent import prompts, request
from ai_agent.core.agent.transcript import Transcript
from ai_agent.core.llm import anthropic

SYSTEM = {"role": "system", "content": "STATIC RULES\n\nLIVE CONTEXT"}
USER = {"role": "user", "content": "hi"}


class SystemPartsTest(unittest.TestCase):
    def test_static_and_live_halves_are_separated(self):
        static, live = prompts.build_system_parts("Layers: a.", ["inspect"], task_plan="Plan: [ ] step")
        self.assertIn(prompts.CORE_PROMPT[:40], static)
        self.assertIn("# Skill: inspect", static)
        self.assertNotIn(prompts.PROJECT_CONTEXT_HEADER, static)
        self.assertIn("Layers: a.", live)
        self.assertIn("Plan: [ ] step", live)

    def test_the_joined_prompt_is_static_then_live(self):
        static, live = prompts.build_system_parts("Layers: a.", ["inspect"])
        self.assertEqual(prompts.build_system_prompt("Layers: a.", ["inspect"]), static + "\n\n" + live)


class AnthropicCacheTest(unittest.TestCase):
    def test_without_a_prefix_the_body_is_untouched(self):
        body = anthropic.build_body([SYSTEM, USER], [], "claude-x")
        self.assertIsInstance(body["system"], str)
        self.assertNotIn("cache_control", json.dumps(body))

    def test_the_prefix_becomes_a_cached_block_and_the_rest_stays_live(self):
        body = anthropic.build_body([SYSTEM, USER], [], "claude-x", cache_prefix_chars=len("STATIC RULES"))
        self.assertEqual(
            body["system"],
            [
                {"type": "text", "text": "STATIC RULES", "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": "LIVE CONTEXT"},
            ],
        )

    def test_the_last_message_carries_a_breakpoint(self):
        messages = [SYSTEM, USER, {"role": "assistant", "content": "sure"}, {"role": "user", "content": "next"}]
        body = anthropic.build_body(messages, [], "claude-x", cache_prefix_chars=12)
        self.assertEqual(body["messages"][-1]["content"][-1]["cache_control"], {"type": "ephemeral"})
        self.assertNotIn("cache_control", json.dumps(body["messages"][:-1]))

    def test_a_tool_result_can_carry_the_breakpoint(self):
        messages = [SYSTEM, USER, {"role": "tool", "tool_call_id": "c1", "content": "{}"}]
        body = anthropic.build_body(messages, [], "claude-x", cache_prefix_chars=12)
        last = body["messages"][-1]["content"][-1]
        self.assertEqual(last["type"], "tool_result")
        self.assertIn("cache_control", last)

    def test_a_prefix_longer_than_the_system_caches_it_whole(self):
        body = anthropic.build_body([SYSTEM, USER], [], "claude-x", cache_prefix_chars=10_000)
        self.assertEqual(len(body["system"]), 1)
        self.assertIn("cache_control", body["system"][0])


class RequestPrefixTest(unittest.TestCase):
    def test_the_request_hands_the_static_length_to_the_transport(self):
        built = request.build_step_request(Transcript(), ["inspect"], [], {"url_override": "https://api.example/v1"})
        system = built.messages[0]
        self.assertEqual(system["role"], "system")
        prefix = built.overrides[anthropic.CACHE_PREFIX_KEY]
        self.assertGreater(prefix, 0)
        self.assertIn(prompts.CORE_PROMPT[:40], system["content"][:prefix])
        tail = system["content"][prefix:]
        self.assertTrue(tail == "" or tail.startswith("\n\n"))


if __name__ == "__main__":
    unittest.main()
