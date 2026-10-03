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

from ai_agent.core.settings import get_auto_apply, set_reasoning_enabled, set_supports_images, set_work_mode
from ai_agent.ui.composer_parts import MODES

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


def _record_peaks(scenario: str, requests: list[dict[str, Any]], skill_free_start: bool) -> dict[str, int]:
    sizes = [request_sizes(body) for body in requests]
    if not sizes:
        return {}
    measured = {metric: max(size[metric] for size in sizes) for metric in ("system_chars", "tools_chars")}
    if skill_free_start:
        # The smallest request is the first one of a run that loaded no skill yet.
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
    # False for a scenario whose every request already carries a skill (a slash
    # command, a preload): it has no skill-free request to measure `base_chars` on.
    skill_free_start = True

    def setUp(self) -> None:
        self.model = ScriptedModel().start()
        self.api_url = self.model.url
        super().setUp()

    def tearDown(self) -> None:
        super().tearDown()
        self.model.stop()
        self.assertEqual(self.model.unexpected, [], "the plugin sent requests no scenario turn answered")
        self.assertEqual(list(self.model.turns), [], "scripted turns were left unused")
        measured = _record_peaks(type(self).__name__, self.model.requests, self.skill_free_start)
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


class TextOnlyScenario(ScenarioCase):
    def test_a_model_known_to_reject_images_verifies_by_reading(self) -> None:
        set_supports_images(self.api_url, False, MODEL, "openai")
        self.model.script(
            call("load_skill", names=["style"]),
            call("set_opacity", layer_name="districts", opacity=0.5),
            say("I suggest making districts half transparent."),
            call("describe_style", layer_name="districts"),
            say("Checked: districts is half transparent."),
        )
        self.ask("Make districts half transparent")
        self.apply()
        self.assertAlmostEqual(self.layer("districts").opacity(), 0.5)

        for index in range(len(self.model.requests)):
            offered = self.model.tool_names(index)
            self.assertNotIn("render_map", offered, "an image tool was offered to a text-only model")
            self.assertNotIn("render_layout", offered, "an image tool was offered to a text-only model")
        verification = self.model.sent_text(3)
        self.assertIn("cannot see images", verification)
        self.assertNotIn("call render_map", verification)
        self.assertEqual(self.answers()[-1], "Checked: districts is half transparent.")


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


class DrawScenario(ScenarioCase):
    def test_a_point_and_a_line_land_in_scratch_layers(self) -> None:
        moscow, kazan = [37.62, 55.75], [49.11, 55.79]
        self.model.script(
            call("load_skill", names=["draw"]),
            calls(
                (
                    "draw_features",
                    {
                        "new_layer_name": "Pins",
                        "geometry": "point",
                        "features": [{"coordinates": [moscow], "attributes": {"name": "Kremlin"}}],
                    },
                ),
                (
                    "draw_features",
                    {
                        "new_layer_name": "Route",
                        "geometry": "line",
                        "features": [{"coordinates": [moscow, kazan], "attributes": {"name": "M7"}}],
                    },
                ),
            ),
            say("I suggest a point at the Kremlin and a line from Moscow to Kazan."),
            say("Both layers are on the map."),
        )
        self.ask("Put a point at 55.75, 37.62 and draw a line from there to Kazan")
        self.assertIn("draw_features", self.model.tool_names(1))
        self.apply()

        pins, route = self.layer("Pins"), self.layer("Route")
        self.assertEqual((pins.providerType(), route.providerType()), ("memory", "memory"))
        self.assertEqual(pins.crs().authid(), "EPSG:4326")
        [point] = list(pins.getFeatures())
        self.assertEqual(point["name"], "Kremlin")
        self.assertAlmostEqual(point.geometry().asPoint().x(), 37.62)
        self.assertAlmostEqual(point.geometry().asPoint().y(), 55.75)
        [line] = list(route.getFeatures())
        self.assertEqual(line["name"], "M7")
        self.assertEqual(
            [(round(v.x(), 6), round(v.y(), 6)) for v in line.geometry().asPolyline()], [(37.62, 55.75), (49.11, 55.79)]
        )
        self.shot("draw_point_and_line")


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

    def test_the_reasoning_switch_asks_and_remembers_a_refusal(self) -> None:
        set_reasoning_enabled(True)
        self.addCleanup(set_reasoning_enabled, False)
        self.model.script(
            fail(400, "Unsupported parameter: 'reasoning_effort' is not supported with this model."),
            think("Three layers are loaded.", "There are three layers."),
        )
        self.ask("What layers do I have?")
        self.assertEqual(self.answers()[-1], "There are three layers.")
        self.assertEqual(self.model.requests[0].get("reasoning_effort"), "medium")
        self.assertNotIn("reasoning_effort", self.model.requests[1], "the refused parameter was sent again")
        self.model.script(say("Still three."))
        self.ask("And now?")
        self.assertEqual(len(self.model.requests), 3)
        self.assertNotIn("reasoning_effort", self.model.requests[2], "the refusal was not remembered")


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


class AutoModeScenario(ScenarioCase):
    def tearDown(self) -> None:
        set_work_mode("ask")
        super().tearDown()

    def test_auto_mode_applies_without_the_button_but_never_a_destructive_step(self) -> None:
        toolbar = self.dock.composer.toolbar
        toolbar.mode.click()
        pump(0.05)
        self.assertTrue(toolbar.modes.isVisible(), "the mode button opens its menu")
        self.shot("mode_menu")
        toolbar.modes.choose("auto")
        self.assertTrue(get_auto_apply(), "choosing Auto must store the mode")
        self.assertEqual(toolbar.mode.text(), next(mode.title for mode in MODES if mode.key == "auto"))
        self.model.script(
            call("load_skill", names=["style"]),
            call("set_opacity", layer_name="districts", opacity=0.5),
            say("Made districts half transparent."),
            say("Checked: districts is at 50 %."),
        )
        self.ask("Make districts half transparent")
        self.assertAlmostEqual(self.layer("districts").opacity(), 0.5)
        self.assertFalse(self.agent.has_pending_writes)
        self.assertEqual(self.destructive, [])
        self.shot("auto_mode_applied")

        self.model.script(
            call("load_skill", names=["edit"]),
            call("delete_features", layer_name="districts", filter='"pop2020" > 0'),
            say("I suggest deleting the populated districts."),
        )
        self.ask("Delete the populated districts")
        self.assertTrue(self.agent.has_pending_writes, "a destructive step must wait for the button in auto mode")
        self.orchestrator.on_cancel_plan()


class CompactionScenario(ScenarioCase):
    skill_free_start = False

    def test_a_full_window_is_compacted_before_the_request_and_by_hand(self) -> None:
        conversation = self.orchestrator.conversation
        conversation.add("user", "Colour districts by pop2020")
        conversation.add("assistant", "Districts are coloured by pop2020 in 5 classes.")
        conversation.set_context(10**9)
        self.model.script(
            say("The user coloured districts by pop2020 in 5 classes."), say("We coloured the districts.")
        )
        self.ask("What did we do so far?")

        compaction_request = self.model.requests[0]
        self.assertFalse(compaction_request.get("tools"), "compaction asks for a summary, not for tools")
        self.assertIn("handoff summary", self.model.sent_text(0))
        self.assertIn("Summary of our conversation so far", self.model.sent_text(1))
        self.assertIn("coloured districts by pop2020", self.model.sent_text(1))
        self.assertEqual(self.answers()[-1], "We coloured the districts.")
        self.assertEqual(
            conversation.context_tokens, USAGE["prompt_tokens"], "the run's first request measures the context afresh"
        )
        self.shot("compacted")

        self.model.script(say("Still about the districts."))
        self.dock.compact_requested.emit()
        self.wait_idle()
        self.assertEqual(len(self.model.requests), 3)
        self.assertIn("Still about the districts.", conversation.window()[0]["content"])


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
