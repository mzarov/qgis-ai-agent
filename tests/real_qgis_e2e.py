"""End-to-end scenarios: the installed plugin, live QGIS, a scripted model.

Each test drives the plugin the way a person does — a request in the chat,
Apply, Stop, undo — while `e2e_model.ScriptedModel` plays the language model
over real HTTP and streaming. Assertions are on what matters to the user: the
project state, what reached the model, and what the chat shows. Screenshots of
the panel land in `E2E_ARTIFACTS` (default `build/e2e`) for a look by eye.

Every request any scenario sends is also measured: the system prompt and the
tool schemas, in characters, are what each step of a run pays again. The
largest of each, and the smallest request (no skill loaded yet — what every
run pays at least), must stay under the `scripted` ceilings in `tests/data/token_ceilings.json`
and land in `request_sizes.json` next to the screenshots — a free, every-push
guard against the permanent prompt growing back (issue #74).

Runs inside `real_qgis_workflows.py` against the extracted plugin ZIP.
"""

import json
from typing import Any

import token_ceilings
from e2e_harness import ARTIFACTS, PluginCase, pump
from e2e_model import USAGE, ScriptedModel, call, calls, fail, say, think

MODEL = "scripted-model"
SIZES_FILE = "request_sizes.json"
SCRIPTED_CEILINGS = token_ceilings.load()[token_ceilings.SCRIPTED_KIND]
# The largest request part of each metric across all scenarios so far, and where it came from.
PEAKS: dict[str, Any] = {"kind": token_ceilings.SCRIPTED_KIND, "where": {}}


def request_sizes(body: dict[str, Any]) -> dict[str, int]:
    """Characters of the parts every request repeats: the system prompt and the tool schemas."""
    system = [message.get("content") for message in body.get("messages", []) if message.get("role") == "system"]
    return {
        "system_chars": len(json.dumps(system, ensure_ascii=False)),
        "tools_chars": len(json.dumps(body.get("tools") or [], ensure_ascii=False)),
    }


def _record_peaks(scenario: str, requests: list[dict[str, Any]]) -> dict[str, int]:
    sizes = [request_sizes(body) for body in requests]
    if not sizes:
        return {}
    measured = {metric: max(size[metric] for size in sizes) for metric in ("system_chars", "tools_chars")}
    measured["base_chars"] = min(size["system_chars"] + size["tools_chars"] for size in sizes)
    for metric, value in measured.items():
        if value > PEAKS.get(metric, 0):
            PEAKS[metric] = value
            PEAKS["where"][metric] = scenario
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS / SIZES_FILE).write_text(json.dumps(PEAKS, indent=2), encoding="utf-8")
    return measured


class ScenarioCase(PluginCase):
    model_name = MODEL

    def setUp(self) -> None:
        self.model = ScriptedModel().start()
        self.api_url = self.model.url
        super().setUp()

    def tearDown(self) -> None:
        super().tearDown()
        self.model.stop()
        self.assertEqual(self.model.unexpected, [], "the plugin sent requests no scenario turn answered")
        self.assertEqual(list(self.model.turns), [], "scripted turns were left unused")
        measured = _record_peaks(type(self).__name__, self.model.requests)
        over = token_ceilings.exceeded(measured, SCRIPTED_CEILINGS)
        self.assertEqual(over, [], "the per-request prompt grew past its ceiling; see docs/smoke_checklist.md")


class StyleScenario(ScenarioCase):
    def test_style_apply_and_verification(self) -> None:
        self.model.script(
            call("list_layers"),
            call("load_skill", names=["style"]),
            call("set_graduated", layer_name="districts", field="pop2020", classes=5),
            say("I suggest colouring districts by pop2020 in 5 classes."),
            call("describe_style", layer_name="districts"),
            say("Checked: districts is coloured in 5 classes."),
        )
        self.ask("Colour districts by pop2020 in 5 classes")

        first = self.model.tool_names(0)
        for tool in ("list_layers", "describe_layer", "query_layer", "get_field_values", "load_skill"):
            self.assertIn(tool, first, "a tool the model needs was hidden from it")
        listed = self.model.sent_text(1)
        self.assertIn('"geometry": "polygon"', listed.replace('\\"', '"'))
        self.assertIn('"geometry": "line"', listed.replace('\\"', '"'))
        self.assertIn("set_graduated", self.model.tool_names(2))

        self.apply()
        renderer = self.layer("districts").renderer()
        self.assertEqual(renderer.type(), "graduatedSymbol")
        self.assertEqual(renderer.classAttribute(), "pop2020")
        self.assertEqual(len(renderer.ranges()), 5)

        verification = self.model.tool_names(4)
        self.assertIn("describe_style", verification, "verification started without the applying run's skills")
        self.assertIn("Message from the plugin", self.model.sent_text(4))
        self.assertEqual(self.answers()[-1], "Checked: districts is coloured in 5 classes.")
        # The live-model token report reads these counters: the verification run's two requests.
        expected = {"prompt_tokens": 2 * USAGE["prompt_tokens"], "completion_tokens": 2 * USAGE["completion_tokens"]}
        self.assertEqual(self.agent.usage, {**expected, "requests": 2})
        self.shot("style_apply_verification")


class StopScenario(ScenarioCase):
    def test_stop_keeps_the_partial_answer_and_clears_the_box(self) -> None:
        self.model.script(say("A map projection flattens the surface of the Earth onto a plane. " * 20, 0.05))
        self.orchestrator.on_prompt("Tell me about projections")
        pump(1.5)
        self.assertTrue(self.agent.is_running)
        self.orchestrator.on_stop()
        self.wait_idle()

        kept = self.answers()
        self.assertEqual(len(kept), 1)
        self.assertTrue(kept[0].startswith("A map projection"))
        self.assertEqual(self.dock.composer._edit.toPlainText(), "", "a stop must not put the request back")
        self.shot("stop_keeps_partial")


class UndoScenario(ScenarioCase):
    def test_buffer_recolour_and_undo_keep_scratch_features(self) -> None:
        self.model.script(
            call("load_skill", names=["processing"]),
            calls(
                (
                    "run_processing",
                    {
                        "algorithm_id": "native:reprojectlayer",
                        "parameters": {"INPUT": "Main rivers", "TARGET_CRS": "EPSG:32637"},
                        "output_name": "rivers utm",
                    },
                ),
                (
                    "run_processing",
                    {
                        "algorithm_id": "native:buffer",
                        "parameters": {"INPUT": "rivers utm", "DISTANCE": 500},
                        "output_name": "river buffer",
                    },
                ),
            ),
            say("I suggest reprojecting the river and buffering it by 500 m."),
            say("The buffer is built."),
        )
        self.ask("Buffer Main rivers by 500 m")
        self.apply()
        buffer = self.layer("river buffer")
        self.assertEqual(buffer.featureCount(), 1)
        self.assertEqual(buffer.providerType(), "memory")

        self.model.script(
            call("load_skill", names=["style"]),
            call("set_symbol", layer_name="river buffer", properties={"color": "#0000ff"}),
            say("I suggest recolouring the buffer blue."),
            say("The buffer is blue."),
        )
        before = self.layer("river buffer").renderer().symbol().color().name()
        self.ask("Recolour the buffer blue")
        self.apply()
        self.assertEqual(self.layer("river buffer").renderer().symbol().color().name(), "#0000ff")

        self.model.script(
            call("load_skill", names=["project"]),
            call("undo_last_apply"),
            say("I suggest undoing the last change."),
            say("Undone."),
        )
        self.ask("Undo the last change")
        self.apply()
        self.assertEqual(len(self.destructive), 1, "undo must ask for the destructive confirmation")
        restored = self.layer("river buffer")
        self.assertEqual(restored.featureCount(), 1, "undo emptied a scratch layer")
        self.assertEqual(restored.renderer().symbol().color().name(), before)
        self.shot("buffer_recolour_undo")


class ReasoningScenario(ScenarioCase):
    def test_streamed_reasoning_folds_into_the_turn(self) -> None:
        from ai_agent.ui.thinking import ThinkingBlock

        reasoning = "The project has three layers, so a listing answers the question."
        self.model.script(think(reasoning, "There are three layers."))
        self.ask("What layers do I have?")
        blocks = self.dock.conversation.findChildren(ThinkingBlock)
        self.assertEqual(len(blocks), 1, "the reasoning never reached the feed")
        self.assertEqual(blocks[0]._text, reasoning)
        self.assertTrue(blocks[0].isVisibleTo(self.dock.conversation), "a reasoning-only turn must stay in the feed")
        self.assertEqual(self.answers()[-1], "There are three layers.")
        self.shot("reasoning_folded")


class AttachScenario(ScenarioCase):
    def test_data_becomes_a_mentioned_layer_and_a_picture_reaches_the_model(self) -> None:
        import json
        import os
        import tempfile

        from qgis.PyQt.QtGui import QColor, QImage

        folder = tempfile.mkdtemp()
        data = os.path.join(folder, "cafes.geojson")
        with open(data, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "properties": {"name": "Le Dôme"},
                            "geometry": {"type": "Point", "coordinates": [2.33, 48.84]},
                        }
                    ],
                },
                handle,
            )
        picture = os.path.join(folder, "sketch.png")
        image = QImage(64, 48, QImage.Format.Format_RGB32)
        image.fill(QColor("orange"))
        self.assertTrue(image.save(picture))

        self.dock.files_attached.emit([data, picture])
        pump(0.1)
        self.assertEqual(self.layer("cafes").featureCount(), 1)
        self.assertIn("@cafes", self.dock.composer._edit.toPlainText())
        self.assertEqual(self.dock.composer.attachments.paths, [picture])
        self.shot("attachments_waiting")

        self.model.script(say("An orange rectangle."))
        self.ask("What is on the picture?")
        request = [m for m in self.model.requests[0]["messages"] if m.get("role") == "user"][-1]["content"]
        self.assertEqual(request[0]["text"], "What is on the picture?")
        self.assertTrue(request[1]["image_url"]["url"].startswith("data:image/png;base64,"))
        self.assertEqual(self.dock.composer.attachments.paths, [], "a sent picture must leave the composer")
        self.assertIn("sketch.png", self.orchestrator.conversation.messages[-2]["content"])


class FailureScenario(ScenarioCase):
    def test_a_failed_run_still_offers_the_prepared_steps(self) -> None:
        self.model.script(
            call("load_skill", names=["style"]),
            call("set_opacity", layer_name="districts", opacity=0.5),
            fail(401, "invalid api key"),
        )
        self.ask("Make districts half transparent")
        self.assertTrue(self.agent.has_pending_writes, "the prepared step was thrown away by the error")
        self.assertEqual(self.dock.composer._edit.toPlainText(), "Make districts half transparent")
        self.model.script(say("Opacity applied."))
        self.apply()
        self.assertAlmostEqual(self.layer("districts").opacity(), 0.5)
        self.shot("failure_keeps_plan")


class ComposerScenario(ScenarioCase):
    def test_slash_and_at_popups_insert_what_was_chosen(self) -> None:
        composer = self.dock.composer
        composer._edit.clear()
        composer._edit.insertPlainText("/o")
        pump(0.1)
        self.assertFalse(composer._popup.isHidden())
        composer._on_complete()
        self.assertEqual(composer._edit.toPlainText(), "/osm ")
        composer._edit.clear()
        composer._edit.insertPlainText("colour @ma")
        pump(0.1)
        self.assertFalse(composer._popup.isHidden())
        self.shot("mention_popup")
        composer._popup._rows[0].mousePressEvent(None)
        self.assertEqual(composer._edit.toPlainText(), 'colour @"Main rivers" ')
