import unittest

from qgis_ai_agent.core.agent import batch_apply as batch_apply_module
from qgis_ai_agent.core.agent import loop as loop_module
from qgis_ai_agent.core.agent import prompts
from qgis_ai_agent.core.agent.loop import MAX_ITERATIONS, AgentLoop
from qgis_ai_agent.core.agent.notices import APPLY_DECLINED_MESSAGE, BUDGET_REACHED_MESSAGE
from qgis_ai_agent.core.agent.prompts import (
    APPLY_NOW_TOOL,
    UPDATE_PLAN_TOOL,
    build_system_prompt,
    render_task_plan,
)
from qgis_ai_agent.core.agent.request import build_tool_schemas_for
from qgis_ai_agent.core.agent.transcript import (
    COMPACT_RESULT_CHARS,
    KEEP_FULL_RESULTS,
    ToolResult,
    Transcript,
)
from qgis_ai_agent.core.llm.transport import ModelTurn, ToolCall, parse_usage


def _call(tool, **arguments):
    return ToolCall(id="c", name=tool, arguments=arguments)


def _result(name="list_layers", payload=None, image=""):
    return ToolResult(call=_call(name), payload=payload or {}, image=image)


class _FakeRequest:
    messages: list = []
    tool_schemas: list = []
    overrides: dict = {}
    protocol = "native"


class UsageParsingTest(unittest.TestCase):
    def test_openai_shape_is_read(self):
        self.assertEqual(parse_usage({"usage": {"prompt_tokens": 10, "completion_tokens": 4}}), (10, 4))

    def test_anthropic_shape_is_read(self):
        self.assertEqual(parse_usage({"usage": {"input_tokens": 7, "output_tokens": 3}}), (7, 3))

    def test_a_missing_or_broken_usage_block_is_zero(self):
        self.assertEqual(parse_usage({}), (0, 0))
        self.assertEqual(parse_usage({"usage": "nonsense"}), (0, 0))
        self.assertEqual(parse_usage({"usage": {"prompt_tokens": "many"}}), (0, 0))


class CompactionTest(unittest.TestCase):
    def _long_transcript(self, rounds):
        transcript = Transcript()
        transcript.add_user("task")
        for index in range(rounds):
            transcript.add_turn(ModelTurn(tool_calls=[_call("list_layers")]))
            transcript.add_results([_result(payload={"data": "x" * 3000, "round": index})], "native")
        return transcript

    def test_recent_results_stay_full(self):
        messages = self._long_transcript(KEEP_FULL_RESULTS + 4).build_messages("sys")
        tool_messages = [message for message in messages if message["role"] == "tool"]
        self.assertGreater(len(tool_messages[-1]["content"]), COMPACT_RESULT_CHARS)

    def test_older_results_are_compacted(self):
        messages = self._long_transcript(KEEP_FULL_RESULTS + 4).build_messages("sys")
        tool_messages = [message for message in messages if message["role"] == "tool"]
        self.assertLessEqual(len(tool_messages[0]["content"]), COMPACT_RESULT_CHARS + 100)
        self.assertIn("compacted", tool_messages[0]["content"])

    def test_a_short_run_is_not_compacted_at_all(self):
        messages = self._long_transcript(2).build_messages("sys")
        for message in (item for item in messages if item["role"] == "tool"):
            self.assertNotIn("compacted", message["content"])

    def test_only_the_newest_image_is_carried(self):
        transcript = Transcript()
        for index in range(3):
            transcript.add_results([_result("render_map", image=f"image{index}")], "native")
        messages = transcript.build_messages("sys")
        attachments = [message for message in messages if isinstance(message["content"], list)]
        self.assertEqual(len(attachments), 1)
        self.assertIn("image2", attachments[0]["content"][1]["image_url"]["url"])

    def test_dropped_images_leave_a_note_that_says_why(self):
        transcript = Transcript()
        for index in range(2):
            transcript.add_results([_result("render_map", image=f"image{index}")], "native")
        messages = transcript.build_messages("sys")
        notes = [m["content"] for m in messages if isinstance(m["content"], str) and "earlier image" in m["content"]]
        self.assertEqual(len(notes), 1)

    def test_a_blind_endpoint_still_gets_its_own_note(self):
        transcript = Transcript()
        transcript.add_results([_result("render_map", image="i")], "native")
        messages = transcript.build_messages("sys", include_images=False)
        self.assertIn("does not accept image", messages[-1]["content"])


class TaskPlanTest(unittest.TestCase):
    def test_the_plan_renders_progress(self):
        rendered = render_task_plan(["download", "style", "export"], 1)
        self.assertIn("[x] download", rendered)
        self.assertIn("[ ] style", rendered)

    def test_an_empty_plan_renders_nothing(self):
        self.assertEqual(render_task_plan([], 0), "")

    def test_the_plan_is_pinned_into_the_system_prompt(self):
        prompt = build_system_prompt("", [], task_plan=render_task_plan(["a", "b"], 1))
        self.assertIn("[x] a", prompt)

    def test_the_meta_tools_are_always_offered(self):
        names = [schema["function"]["name"] for schema in build_tool_schemas_for(["inspect"])]
        self.assertIn(UPDATE_PLAN_TOOL, names)
        self.assertIn(APPLY_NOW_TOOL, names)


class FakeExecutor:
    def run(self, call):
        return ToolResult(call=call, payload={"ok": True})

    @staticmethod
    def queued(call):
        return ToolResult(call=call, payload={"status": "queued"})


class LoopPlanTest(unittest.TestCase):
    def setUp(self):
        self.loop = AgentLoop()
        self.loop._executor = FakeExecutor()

    def test_a_plan_is_recorded_and_reported(self):
        seen = []
        self.loop.plan_changed.connect(lambda steps, done: seen.append((list(steps), done)))
        result = self.loop._dispatch(_call(UPDATE_PLAN_TOOL, steps=["one", "two"], done=1))
        self.assertTrue(result.ok)
        self.assertEqual(seen, [(["one", "two"], 1)])

    def test_an_empty_plan_is_refused(self):
        self.assertFalse(self.loop._dispatch(_call(UPDATE_PLAN_TOOL, steps=[])).ok)

    def test_done_is_clamped_to_the_step_count(self):
        self.loop._dispatch(_call(UPDATE_PLAN_TOOL, steps=["one"], done=99))
        self.assertEqual(self.loop._plan_done, 1)

    def test_a_broken_done_value_falls_back_to_zero(self):
        self.loop._dispatch(_call(UPDATE_PLAN_TOOL, steps=["one"], done="soon"))
        self.assertEqual(self.loop._plan_done, 0)


class StagedRunTest(unittest.TestCase):
    def setUp(self):
        self.loop = AgentLoop()
        self.loop._executor = FakeExecutor()
        self.loop._batch._executor = FakeExecutor()
        self.saved_snapshot = batch_apply_module.take_snapshot
        batch_apply_module.take_snapshot = lambda: "/tmp/snapshot.qgz"

    def tearDown(self):
        batch_apply_module.take_snapshot = self.saved_snapshot

    def test_apply_now_without_queued_writes_is_an_error(self):
        result = self.loop._dispatch(_call(APPLY_NOW_TOOL, reason="need it"))
        self.assertFalse(result.ok)
        self.assertIn("nothing queued", result.payload["error"])

    def test_apply_now_marks_the_run_as_staged(self):
        self.loop._batch._calls = [_call("set_opacity")]
        result = self.loop._dispatch(_call(APPLY_NOW_TOOL, reason="need it"))
        self.assertTrue(result.ok)
        self.assertTrue(self.loop._staged)

    def test_confirming_a_stage_continues_the_same_run(self):
        resumed = []
        self.loop._request_step = lambda: resumed.append(True)
        self.loop._batch._calls = [_call("set_opacity")]
        self.loop._staged = True
        self.loop.confirm_pending()
        self.assertEqual(resumed, [True])
        self.assertFalse(self.loop._staged)

    def test_a_staged_apply_does_not_emit_the_terminal_signal(self):
        finished = []
        self.loop.applied.connect(lambda results: finished.append(results))
        self.loop._request_step = lambda: None
        self.loop._batch._calls = [_call("set_opacity")]
        self.loop._staged = True
        self.loop.confirm_pending()
        self.assertEqual(finished, [])

    def test_an_ordinary_apply_still_ends_the_run(self):
        finished = []
        self.loop.applied.connect(lambda results: finished.append(results))
        self.loop._batch._calls = [_call("set_opacity")]
        self.loop.confirm_pending()
        self.assertEqual(len(finished), 1)

    def test_snapshot_failure_is_fail_closed(self):
        finished = []
        applied = []
        self.loop.applied.connect(finished.append)
        self.loop._batch._calls = [_call("set_opacity")]
        self.loop._batch.apply = lambda *args: applied.append(True) or []
        batch_apply_module.take_snapshot = lambda: ""
        self.loop.confirm_pending()
        self.assertEqual(applied, [])
        self.assertEqual(len(finished), 1)
        self.assertFalse(finished[0][0].ok)
        self.assertIn("No planned changes", finished[0][0].payload["error"])

    def test_stage_results_reach_the_transcript(self):
        self.loop._request_step = lambda: None
        self.loop._batch._calls = [_call("set_opacity")]
        self.loop._staged = True
        self.loop.confirm_pending()
        kinds = [entry["kind"] for entry in self.loop._transcript.entries]
        self.assertIn("results", kinds)

    def test_declining_a_stage_ends_the_run_with_a_reason(self):
        completed = []
        self.loop.finished.connect(lambda text: completed.append(text))
        self.loop._batch._calls = [_call("set_opacity")]
        self.loop._staged = True
        self.loop.cancel_pending()
        self.assertEqual(completed, [APPLY_DECLINED_MESSAGE])

    def test_declining_an_ordinary_plan_stays_silent(self):
        completed = []
        self.loop.finished.connect(lambda text: completed.append(text))
        self.loop._batch._calls = [_call("set_opacity")]
        self.loop.cancel_pending()
        self.assertEqual(completed, [])


class BudgetTest(unittest.TestCase):
    def setUp(self):
        self.loop = AgentLoop()

    def test_usage_accumulates_and_is_reported(self):
        seen = []
        self.loop.usage_changed.connect(lambda spent: seen.append(spent))
        self.loop._track_usage(ModelTurn(input_tokens=100, output_tokens=20))
        self.loop._track_usage(ModelTurn(input_tokens=30, output_tokens=0))
        self.assertEqual(seen, [120, 150])
        self.assertEqual(self.loop.tokens_spent, 150)

    def test_a_turn_without_usage_does_not_report(self):
        seen = []
        self.loop.usage_changed.connect(lambda spent: seen.append(spent))
        self.loop._track_usage(ModelTurn())
        self.assertEqual(seen, [])

    def test_the_budget_stops_the_run_politely(self):
        completed = []
        self.loop.finished.connect(lambda text: completed.append(text))
        self.loop._token_budget = 100
        self.loop._tokens_spent = 150
        self.loop._request_step()
        self.assertEqual(completed, [BUDGET_REACHED_MESSAGE])

    def test_a_zero_budget_means_no_limit(self):
        started = []
        saved = loop_module.build_step_request
        loop_module.build_step_request = lambda *args: _FakeRequest()
        self.loop._turn.start = lambda *args: started.append(True)
        self.loop._token_budget = 0
        self.loop._tokens_spent = 10**9
        try:
            self.loop._request_step()
        finally:
            loop_module.build_step_request = saved
        self.assertEqual(started, [True])

    def test_the_turn_ceiling_allows_real_autonomy(self):
        self.assertGreaterEqual(MAX_ITERATIONS, 40)


if __name__ == "__main__":
    unittest.main()


class QueuedStepsInPromptTest(unittest.TestCase):
    def test_nothing_queued_renders_to_nothing(self):
        self.assertEqual(prompts.render_queued_steps([]), "")

    def test_queued_steps_are_listed_under_a_warning(self):
        rendered = prompts.render_queued_steps(["Скачиваю кафе", "Крашу слой"])
        self.assertIn(prompts.QUEUED_HEADER, rendered)
        self.assertIn("- Скачиваю кафе", rendered)
        self.assertIn("- Крашу слой", rendered)

    def test_they_are_pinned_into_the_system_prompt(self):
        prompt = prompts.build_system_prompt("", [], queued_steps=prompts.render_queued_steps(["Скачиваю кафе"]))
        self.assertIn("Скачиваю кафе", prompt)

    def test_the_prompt_warns_that_context_lags_behind_the_queue(self):
        self.assertIn("not run yet", prompts.CORE_PROMPT)

    def test_the_loop_reports_what_it_has_queued(self):
        loop = AgentLoop()
        loop._batch._calls.append(ToolCall(id="c1", name="add_basemap", arguments={"provider": "osm"}))
        self.assertIn(prompts.QUEUED_HEADER, loop._queued_summaries())

    def test_an_empty_batch_reports_nothing(self):
        self.assertEqual(AgentLoop()._queued_summaries(), "")


class AskUserTest(unittest.TestCase):
    def setUp(self):
        self.loop = AgentLoop()
        self.questions = []
        self.busy = []
        self.steps = 0
        self.loop.question_asked.connect(self.questions.append)
        self.loop.busy_changed.connect(self.busy.append)
        self.loop._request_step = lambda: setattr(self, "steps", self.steps + 1)

    def _turn_with_question(self, question="Какой слой брать?"):
        return ModelTurn(tool_calls=[ToolCall(id="q1", name=prompts.ASK_USER_TOOL, arguments={"question": question})])

    def test_the_schema_is_offered_to_the_model(self):
        schemas = build_tool_schemas_for([])
        names = [s["function"]["name"] for s in schemas]
        self.assertIn(prompts.ASK_USER_TOOL, names)

    def test_a_question_pauses_the_run_instead_of_ending_it(self):
        self.loop._on_turn(self._turn_with_question())
        self.assertEqual(self.questions, ["Какой слой брать?"])
        self.assertEqual(self.busy[-1], False)
        self.assertEqual(self.steps, 0)
        self.assertTrue(self.loop.is_awaiting_answer)

    def test_the_answer_resumes_the_same_run(self):
        self.loop._on_turn(self._turn_with_question())
        self.assertTrue(self.loop.answer("бери первый"))
        self.assertEqual(self.steps, 1)
        self.assertFalse(self.loop.is_awaiting_answer)
        texts = [entry["text"] for entry in self.loop._transcript.entries if entry["kind"] == "user"]
        self.assertIn("бери первый", texts)

    def test_an_empty_question_is_rejected_and_the_run_goes_on(self):
        self.loop._on_turn(self._turn_with_question(""))
        self.assertEqual(self.questions, [])
        self.assertEqual(self.steps, 1)

    def test_an_answer_out_of_the_blue_is_refused(self):
        self.assertFalse(self.loop.answer("что?"))
        self.assertEqual(self.steps, 0)

    def test_abort_clears_the_pending_question(self):
        self.loop._on_turn(self._turn_with_question())
        self.loop.abort()
        self.assertFalse(self.loop.is_awaiting_answer)
        self.assertFalse(self.loop.answer("поздно"))

    def test_the_model_sees_a_waiting_status_not_an_error(self):
        self.loop._on_turn(self._turn_with_question())
        results = self.loop._transcript.entries[-1]["results"]
        self.assertTrue(results[0].ok)
        self.assertEqual(results[0].payload["status"], "waiting_for_user")


class PreambleTest(unittest.TestCase):
    def setUp(self):
        self.loop = AgentLoop()
        self.preambles = []
        self.confirms = []
        self.loop.preamble.connect(self.preambles.append)
        self.loop.confirm_needed.connect(lambda calls, text: self.confirms.append(text))
        self.loop._request_step = lambda: None

    def _turn(self, text, tool="get_project_info"):
        return ModelTurn(text=text, tool_calls=[ToolCall(id="c1", name=tool, arguments={})])

    def test_text_before_tool_calls_is_announced_not_lost(self):
        self.loop._on_turn(self._turn("Сейчас посмотрю проект."))
        self.assertEqual(self.preambles, ["Сейчас посмотрю проект."])

    def test_a_final_answer_is_not_a_preamble(self):
        self.loop._on_turn(ModelTurn(text="Готово."))
        self.assertEqual(self.preambles, [])

    def test_blank_text_is_not_announced(self):
        self.loop._on_turn(self._turn("   "))
        self.assertEqual(self.preambles, [])

    def test_a_staged_pause_does_not_show_the_text_twice(self):
        self.loop._batch._calls.append(ToolCall(id="w1", name="add_basemap", arguments={}))
        self.loop._on_turn(self._turn("Применяю первую часть.", tool=prompts.APPLY_NOW_TOOL))
        self.assertEqual(self.preambles, ["Применяю первую часть."])
        self.assertEqual(self.confirms, [""])


class StageAppliedSignalTest(unittest.TestCase):
    def test_a_staged_apply_announces_itself(self):
        loop = AgentLoop()
        loop._staged = True
        call = ToolCall(id="w", name="add_basemap", arguments={})
        result = ToolResult(call=call, payload={"status": "done"})
        loop._batch._calls.append(call)
        loop._batch.apply = lambda on_start, on_finish, expected_project_identity=None: [result]
        loop._request_step = lambda: None
        saved = batch_apply_module.take_snapshot
        batch_apply_module.take_snapshot = lambda: "/tmp/snapshot.qgz"
        seen = []
        applied = []
        loop.stage_applied.connect(seen.append)
        loop.applied.connect(applied.append)
        try:
            loop.confirm_pending()
        finally:
            batch_apply_module.take_snapshot = saved
        self.assertEqual(seen, [[result]])
        self.assertEqual(applied, [])

    def test_stage_resume_marks_apply_control_result_as_applied(self):
        loop = AgentLoop()
        write = ToolCall(id="write", name="add_basemap", arguments={})
        apply = ToolCall(id="apply", name=prompts.APPLY_NOW_TOOL, arguments={})
        loop._transcript.add_results(
            [
                ToolResult(call=write, payload={"status": "queued"}),
                ToolResult(call=apply, payload={"status": "awaiting_user"}),
            ],
            "native",
        )
        loop._stage_call = apply
        loop._request_step = lambda: None

        loop._resume_after_stage([ToolResult(call=write, payload={"status": "done"})])

        rendered = loop._transcript.build_messages("S")
        self.assertEqual([message["tool_call_id"] for message in rendered[1:]], ["write", "apply"])
        self.assertIn("done", rendered[1]["content"])
        self.assertIn("applied", rendered[2]["content"])
        self.assertNotIn("awaiting_user", rendered[2]["content"])

    def test_a_second_apply_control_call_is_rejected(self):
        loop = AgentLoop()
        loop._batch._calls.append(ToolCall(id="write", name="add_basemap", arguments={}))
        first = loop._request_stage(ToolCall(id="apply-1", name=prompts.APPLY_NOW_TOOL, arguments={}))
        second = loop._request_stage(ToolCall(id="apply-2", name=prompts.APPLY_NOW_TOOL, arguments={}))
        self.assertTrue(first.ok)
        self.assertFalse(second.ok)
        self.assertEqual(loop._stage_call.id, "apply-1")
