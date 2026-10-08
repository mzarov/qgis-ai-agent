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
from qgis.core import QgsProject

from ai_agent.core.orchestrator.notices import CHECKED_BY_READING, STATUS_DONE, STATUS_WAITING
from ai_agent.core.settings import get_auto_apply, set_reasoning_enabled, set_supports_images, set_work_mode
from ai_agent.ui.chart import ChartCard
from ai_agent.ui.composer_parts import MODES
from ai_agent.ui.messages import SystemMessage
from ai_agent.ui.plan import PlanCard
from ai_agent.ui.question import QuestionCard

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
    # Naming a conversation after its first answer is one more request; only the scenario about it scripts it.
    names_conversations = False

    def setUp(self) -> None:
        self.model = ScriptedModel().start()
        self.api_url = self.model.url
        super().setUp()
        if not self.names_conversations:
            self.orchestrator.naming.after_answer = lambda: None

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


class ShortCheckScenario(ScenarioCase):
    """A step that reads back as done is checked by the plugin; anything visual still goes to the model."""

    def system_lines(self) -> list[str]:
        return [message.plain_text() for message in self.dock.conversation.findChildren(SystemMessage)]

    def test_a_rename_is_checked_without_asking_the_model(self) -> None:
        self.model.script(
            call("load_skill", names=["project"]),
            call("configure_layer", layer_name="districts", properties={"name": "Districts 2020", "visible": False}),
            say("I suggest renaming districts and hiding it."),
        )
        self.ask("Rename districts to 'Districts 2020' and hide it")
        sent = len(self.model.requests)
        self.apply()
        layer = self.layer("Districts 2020")
        self.assertFalse(QgsProject.instance().layerTreeRoot().findLayer(layer.id()).itemVisibilityChecked())
        self.assertEqual(len(self.model.requests), sent, "a step that reads back as done still started a model check")
        self.assertIn(CHECKED_BY_READING, self.system_lines())
        self.shot("short_check")

    def test_a_step_judged_by_its_values_still_goes_to_the_model(self) -> None:
        self.model.script(
            call("load_skill", names=["fields"]),
            calls(
                ("add_field", {"layer_name": "districts", "name": "code", "type": "text"}),
                ("add_field", {"layer_name": "districts", "name": "people_k", "expression": '"pop2020" / 1000'}),
            ),
            say("I suggest adding a code field and a virtual population field in thousands."),
            call("list_layers"),
            say("Checked: both fields are on districts."),
        )
        self.ask("Add a text field 'code' and a virtual field with population in thousands to districts")
        self.apply()
        self.assertIn("people_k", self.layer("districts").fields().names())
        self.assertNotIn(CHECKED_BY_READING, self.system_lines())
        self.assertEqual(self.last(), "Checked: both fields are on districts.")


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


class TablesScenario(ScenarioCase):
    def write_csv(self, name: str, text: str) -> str:
        import os

        path = os.path.join(self.folder, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path

    def test_a_csv_joins_to_districts_and_another_becomes_points(self) -> None:
        rows = "".join(f"District {index};{100 * index};{index:03d}\n" for index in range(1, 7))
        stats = self.write_csv("district_stats.csv", "district;households;okato\n" + rows)
        self.model.script(
            call("load_skill", names=["tables"]),
            call("preview_table", path=stats),
            call(
                "join_table",
                layer_name="districts",
                layer_field="name",
                table=stats,
                table_field="district",
                fields=["households", "okato"],
                prefix="",
            ),
            say("I suggest attaching households and okato to districts by name."),
            call("list_joins", layer_name="districts"),
            say("Checked: all six districts found their row."),
        )
        self.ask("Attach district_stats.csv to the districts by name")
        preview = self.model.sent_text(2).replace('\\"', '"')
        self.assertIn('"delimiter": ";"', preview)
        self.assertIn('{"name": "okato", "type": "text"}', preview)

        self.apply()
        districts = self.layer("districts")
        joined = {feature["name"]: (feature["households"], feature["okato"]) for feature in districts.getFeatures()}
        self.assertEqual(joined["District 1"], (100, "001"), "codes with leading zeros must stay text")
        self.assertTrue(all(households for households, _ in joined.values()), joined)
        self.assertEqual(self.layer("district_stats").providerType(), "delimitedtext")
        self.assertIn('"matched_keys": 6', self.model.sent_text(5).replace('\\"', '"'))
        self.shot("tables_join")

        cafes = self.write_csv("cafes.csv", "name,lon,lat\nA,37.61,55.75\nB,37.62,55.76\nC,37.63,55.77\n")
        self.model.script(
            call("load_skill", names=["tables"]),
            call("load_table", path=cafes),
            say("I suggest loading cafes as points."),
            say("Checked: three cafes."),
        )
        self.ask("Make points from cafes.csv")
        self.apply()
        points = self.layer("cafes")
        self.assertEqual(points.featureCount(), 3)
        self.assertEqual(points.crs().authid(), "EPSG:4326")
        self.assertEqual(points.geometryType().name, "Point")

    def test_an_attached_csv_with_lon_lat_becomes_points(self) -> None:
        stops = self.write_csv("stops.csv", "stop;lat;lon\nKremlin;55,752;37,617\n")
        self.dock.files_attached.emit([stops])
        pump(0.1)
        layer = self.layer("stops")
        self.assertEqual(layer.geometryType().name, "Point")
        self.assertAlmostEqual(next(layer.getFeatures()).geometry().asPoint().x(), 37.617)
        self.assertIn("@stops", self.dock.composer._edit.toPlainText())


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


class ChartScenario(ScenarioCase):
    def test_a_chart_reaches_the_feed_not_the_model_and_comes_back_with_the_conversation(self) -> None:
        self.model.script(
            call("load_skill", names=["charts"]),
            call("chart_layer", layer_name="districts", value="pop2020", group_by="name"),
            say("District 6 is the most populous."),
        )
        self.ask("Chart the population by district")
        cards = self.dock.conversation.findChildren(ChartCard)
        self.assertEqual(len(cards), 1, "the chart never reached the feed")
        self.assertEqual(len(cards[0].labels), 6)
        after_chart = self.model.sent_text(2)
        self.assertIn('"shown": "chart"', after_chart.replace('\\"', '"'))
        self.assertNotIn("visual_for_user", after_chart)
        self.shot("chart_in_feed")
        identifier = self.orchestrator.conversation.session_identifier
        self.orchestrator.on_new_session()
        self.orchestrator.on_session_chosen(identifier)
        pump(0.1)
        self.assertEqual(len(self.dock.conversation.findChildren(ChartCard)), 1, "the chart did not come back")
        self.assertNotIn("visual", json.dumps([m["role"] for m in self.orchestrator.conversation.window()]))


class RewindScenario(ScenarioCase):
    def test_rewinding_restores_the_project_and_the_conversation_to_before_a_message(self) -> None:
        self.model.script(
            call("load_skill", names=["project"]),
            call("configure_layer", layer_name="districts", properties={"name": "Districts A"}),
            say("Renamed to Districts A."),
            call("configure_layer", layer_name="Districts A", properties={"name": "Districts B"}),
            say("Renamed to Districts B."),
        )
        self.ask("Rename districts to Districts A")
        self.apply()
        self.ask("Now rename it to Districts B")
        self.apply()
        self.layer("Districts B")
        second = next(
            index
            for index, message in enumerate(self.orchestrator.conversation.messages)
            if message["content"] == "Now rename it to Districts B"
        )
        self.dock.choose_rewind = lambda project_available: "both" if project_available else None
        self.orchestrator.on_rewind(second)
        pump(0.1)
        self.layer("Districts A")
        self.assertEqual(len(self.orchestrator.conversation.messages), second)
        self.assertEqual(self.dock.composer._edit.toPlainText(), "Now rename it to Districts B")
        notes = [message.plain_text() for message in self.dock.conversation.findChildren(SystemMessage)]
        self.assertTrue(any("project is back" in note for note in notes), notes)
        self.shot("rewound")


class PlanUndoScenario(ScenarioCase):
    def test_the_plan_card_undoes_its_own_apply(self) -> None:
        self.model.script(
            call("load_skill", names=["project"]),
            call("configure_layer", layer_name="districts", properties={"name": "Districts A"}),
            say("Renamed to Districts A."),
        )
        self.ask("Rename districts to Districts A")
        self.apply()
        self.layer("Districts A")
        self.assertEqual(self.dock.progress.state, STATUS_DONE, "the status line did not say the run is done")
        card = self.dock.conversation.findChildren(PlanCard)[-1]
        self.assertFalse(card._undo.isHidden(), "an applied plan offers no Undo")
        card._undo.click()
        pump(0.1)
        self.layer("districts")
        self.assertTrue(card._undo.isHidden(), "an undone plan still offers Undo")
        notes = [message.plain_text() for message in self.dock.conversation.findChildren(SystemMessage)]
        self.assertTrue(any("plan is undone" in note for note in notes), notes)
        self.assertIn("The plan is undone", self.orchestrator.conversation.messages[-1]["content"])
        self.shot("plan_undone")


class QuestionScenario(ScenarioCase):
    def test_a_picked_answer_resumes_the_same_run(self) -> None:
        self.model.script(
            call("ask_user", question="Colour by which field?", options=["pop2020", "name"]),
            say("I will colour by pop2020."),
        )
        self.ask("Colour the districts")
        cards = self.dock.conversation.findChildren(QuestionCard)
        self.assertEqual(len(cards), 1, "the question card never appeared")
        self.assertEqual([row.text for row in cards[0].rows], ["pop2020", "name"])
        self.assertEqual(self.dock.progress.state, STATUS_WAITING, "the status line did not wait for the answer")
        self.shot("question_card")
        cards[0].rows[0].clicked.emit("pop2020")
        self.wait_idle()
        self.assertFalse(cards[0].is_open, "an answered card still offers its choices")
        self.assertIn("pop2020", self.model.sent_text(-1))
        self.assertEqual(self.last(), "I will colour by pop2020.")


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


class PlanModeScenario(ScenarioCase):
    def tearDown(self) -> None:
        set_work_mode("ask")
        super().tearDown()

    def test_plan_mode_reads_proposes_and_then_runs_the_plan(self) -> None:
        from ai_agent.ui.plan import PlanOffer

        self.dock.composer.toolbar.modes.choose("plan")
        self.model.script(
            call("load_skill", names=["style"]),
            say("1. Graduate districts by pop2020 in 5 classes."),
        )
        self.ask("Colour districts by population")
        self.assertNotIn("set_graduated", self.model.tool_names(1), "plan mode offers no tool that changes things")
        self.assertIn("Plan mode is on", self.model.sent_text(0))
        self.assertFalse(self.agent.has_pending_writes)
        offers = self.dock.conversation.findChildren(PlanOffer)
        self.assertEqual(len(offers), 1, "a plan ends on an offer to run it")
        self.shot("plan_offer")

        self.model.script(
            call("load_skill", names=["style"]),
            call("set_graduated", layer_name="districts", field="pop2020", classes=5),
            say("Districts are graduated by pop2020."),
            say("Checked: 5 classes on pop2020."),
        )
        offers[0]._rows[0].clicked.emit(offers[0]._rows[0].key)
        self.wait_idle()
        self.assertEqual(self.layer("districts").renderer().type(), "graduatedSymbol")
        self.assertEqual(self.dock.composer.mode, "auto")
        self.assertIn("set_graduated", self.model.tool_names(3))


class ConversationsScenario(ScenarioCase):
    names_conversations = True

    def test_the_model_names_a_conversation_and_the_user_renames_and_deletes_it(self) -> None:
        self.model.script(say("There are three layers."), say("Project layers"))
        self.ask("What layers do I have?")
        self.wait_idle()
        conversation = self.orchestrator.conversation
        naming = self.model.requests[1]
        self.assertFalse(naming.get("tools"), "naming asks for a title, not for tools")
        self.assertIn("two to five words", self.model.sent_text(1))
        self.assertEqual(conversation.messages and self.dock._sessions_provider()[0][1], "Project layers")

        identifier = conversation.session_identifier
        self.dock.session_renamed.emit(identifier, "Layers of the town")
        self.assertEqual(self.dock._sessions_provider()[0][1], "Layers of the town")
        self.dock._show_sessions()
        pump(0.1)
        self.assertEqual([row.title for row in self.dock._sessions_popup.rows][:1], ["Layers of the town"])
        self.shot("conversations_menu")
        self.dock._sessions_popup.hide()

        self.dock.session_deleted.emit(identifier)
        self.assertNotEqual(conversation.session_identifier, identifier, "deleting the open one starts afresh")
        self.assertEqual(self.dock._sessions_provider(), [])


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
