import json
import math
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import token_ceilings
from e2e_harness import ARTIFACTS, PluginCase, process, pump
from e2e_model import USAGE, ScriptedModel, call, calls, fail, say, think
from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsSettings, QgsVectorLayer

from ai_agent.core.agent.run_failure import RUN_FAILURES
from ai_agent.core.llm import failure_kinds, retry
from ai_agent.core.orchestrator.notices import (
    CHECKED_BY_READING,
    PROJECT_CHANGED,
    RUN_CHECK,
    STATUS_DONE,
    STATUS_WAITING,
)
from ai_agent.core.settings import get_auto_apply, set_reasoning_enabled, set_supports_images, set_work_mode
from ai_agent.core.state.session import MAX_MESSAGES
from ai_agent.qgis_tools.osm import overpass
from ai_agent.ui import progress
from ai_agent.ui.activity import ActivityGroup
from ai_agent.ui.chart import ChartCard
from ai_agent.ui.composer_parts import MODES
from ai_agent.ui.durations import format_seconds
from ai_agent.ui.failure_card import FailureCard
from ai_agent.ui.legend import LegendCard
from ai_agent.ui.messages import SystemMessage, UserMessage
from ai_agent.ui.plan import FAILED_MARK, RUNNING_MARK, PlanCard
from ai_agent.ui.question import QuestionCard
from ai_agent.ui.transitions import LeavingFeed

MODEL = "scripted-model"
SIZES_FILE = "request_sizes.json"
SCRIPTED_CEILINGS = token_ceilings.load()[token_ceilings.SCRIPTED_KIND]
CAFES = (
    b'<?xml version="1.0" encoding="UTF-8"?><osm version="0.6" generator="fixture">'
    b'<node id="1" lat="55.75" lon="37.62"><tag k="amenity" v="cafe"/><tag k="name" v="One"/></node>'
    b"</osm>"
)
PEAKS: dict[str, Any] = {"kind": token_ceilings.SCRIPTED_KIND, "where": {}}


def request_sizes(body: dict[str, Any]) -> dict[str, int]:
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
    skill_free_start = True
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
        legends = self.dock.conversation.findChildren(LegendCard)
        self.assertEqual(len(legends), 1, "the restyled layer's legend is not in the feed")
        self.assertTrue(legends[0].as_strip)
        self.assertEqual(len(legends[0].items), 5)
        self.assertNotIn("visual_for_user", self.model.sent_text(4), "the legend reached the model")
        checks = [group for group in self.dock.conversation.findChildren(ActivityGroup) if group.kind == RUN_CHECK]
        self.assertEqual(len(checks), 1, "the check after Apply is not its own trace")
        notes = [message.plain_text() for message in self.dock.conversation.findChildren(SystemMessage)]
        self.assertFalse(any("Checking" in note for note in notes), notes)

        verification = self.model.tool_names(4)
        self.assertIn("describe_style", verification, "verification started without the applying run's skills")
        self.assertIn("Message from the plugin", self.model.sent_text(4))
        self.assertEqual(self.answers()[-1], "Checked: districts is coloured in 5 classes.")
        self.assertTrue(
            self.dock.progress._step.text().endswith(" · Layer “districts” redrawn"),
            f"the status line does not say what the apply changed: {self.dock.progress._step.text()!r}",
        )
        expected = {"prompt_tokens": 2 * USAGE["prompt_tokens"], "completion_tokens": 2 * USAGE["completion_tokens"]}
        self.assertEqual(self.agent.usage, {**expected, "requests": 2})
        self.shot("style_apply_verification")


class ShortCheckScenario(ScenarioCase):
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

    def test_a_check_that_failed_does_not_name_the_next_request(self) -> None:
        self.model.script(
            call("load_skill", names=["style"]),
            call("set_graduated", layer_name="districts", field="pop2020", classes=5),
            say("I suggest colouring districts by pop2020 in 5 classes."),
            fail(400, '{"error": "the upstream gave up"}'),
            call("list_layers"),
            say("Two layers."),
        )
        self.ask("Colour districts by pop2020 in 5 classes")
        self.apply()
        self.ask("How many layers are there?")
        identifier = self.orchestrator.conversation.session_identifier
        self.orchestrator.on_new_session()
        self.orchestrator.on_session_chosen(identifier)
        pump(0.1)
        groups = self.dock.conversation.findChildren(ActivityGroup)
        self.assertNotEqual(groups[-1].kind, RUN_CHECK, "a reopened request is drawn as the failed check")


class TextOnlyScenario(ScenarioCase):
    def test_a_model_known_to_reject_images_verifies_by_reading(self) -> None:
        set_supports_images(self.api_url, False, MODEL, "openai")
        self.model.script(
            call("load_skill", names=["style"]),
            call("set_labels", layer_name="districts", properties={"field": "name", "bold": True}),
            say("I suggest bold labels with the district names."),
            call("describe_style", layer_name="districts"),
            say("Checked: districts is labelled in bold."),
        )
        self.ask("Label districts with their names in bold")
        self.apply()
        self.assertTrue(self.layer("districts").labelsEnabled())

        for index in range(len(self.model.requests)):
            offered = self.model.tool_names(index)
            self.assertNotIn("render_map", offered, "an image tool was offered to a text-only model")
            self.assertNotIn("render_layout", offered, "an image tool was offered to a text-only model")
        verification = self.model.sent_text(3)
        self.assertIn("cannot see images", verification)
        self.assertNotIn("call render_map", verification)
        self.assertEqual(self.answers()[-1], "Checked: districts is labelled in bold.")


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
        step = self.dock.conversation.findChildren(PlanCard)[-1]._steps[0].label.text()
        self.assertIn("INPUT=Main rivers", step)
        self.assertNotIn(self.layer("Main rivers").id(), step)
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
        identifier = self.orchestrator.conversation.session_identifier
        self.orchestrator.on_new_session()
        self.orchestrator.on_session_chosen(identifier)
        pump(0.8)
        reopened = self.dock.conversation.findChildren(ThinkingBlock)
        self.assertEqual([block._text for block in reopened if block.isVisibleTo(self.dock.conversation)], [reasoning])
        window = self.orchestrator.conversation.window()
        self.assertFalse(any(reasoning in str(message["content"]) for message in window))
        self.shot("reasoning_reopened")

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
        card = self.dock.conversation.findChildren(FailureCard)[-1]
        self.assertEqual(card.title.text(), RUN_FAILURES[failure_kinds.AUTH][0])
        self.assertFalse(card.settings.isHidden(), "a refused key is fixed in the Connection settings")
        self.apply()
        self.assertAlmostEqual(self.layer("districts").opacity(), 0.5)
        self.shot("failure_keeps_plan")

    def test_retry_waits_for_the_prepared_steps_and_comes_back_once_they_are_cancelled(self) -> None:
        self.model.script(
            call("load_skill", names=["style"]),
            call("set_opacity", layer_name="districts", opacity=0.5),
            fail(400, '{"error": "the upstream gave up"}'),
        )
        self.ask("Make districts half transparent")
        self.assertTrue(self.agent.has_pending_writes)
        failure = self.dock.conversation.findChildren(FailureCard)[-1]
        self.assertTrue(failure.retry.isHidden(), "Retry would start over without the prepared steps")
        self.dock.conversation.findChildren(PlanCard)[-1].cancelled.emit()
        pump(0.05)
        self.assertFalse(failure.retry.isHidden(), "Retry did not come back once the steps were cancelled")
        self.model.script(say("Districts can be made half transparent with set_opacity."))
        failure.retry.click()
        self.wait_idle()
        self.assertEqual(self.last(), "Districts can be made half transparent with set_opacity.")
        users = [message for message in self.orchestrator.conversation.messages if message["role"] == "user"]
        self.assertEqual(len(users), 1, "the retried request was written twice")
        self.assertEqual(self.model.sent_text(-1).count("Make districts half transparent"), 1)


class StageRefusedScenario(ScenarioCase):
    ANSWER = "Districts is being edited by hand: commit or roll back those edits, then ask me again."

    def test_a_stage_the_snapshot_refuses_reaches_the_model_and_can_be_stopped(self) -> None:
        self.model.script(
            call("load_skill", names=["style"]),
            call("set_opacity", layer_name="districts", opacity=0.5),
            call("apply_now", reason="the transparency has to land before the labels"),
            say(self.ANSWER, 0.05),
        )
        self.ask("Make districts half transparent, then label them")
        districts = self.layer("districts")
        self.assertTrue(districts.startEditing())
        self.orchestrator.on_confirm_plan()
        running, busy = self.agent.is_running, self.dock.composer._busy
        self.wait_idle()
        districts.rollBack()
        self.assertTrue(running, "the run did not go on with the model")
        self.assertTrue(busy, "the run went on with the model but offered no Stop")
        self.assertAlmostEqual(districts.opacity(), 1.0)
        self.assertIn("active edit buffer on: districts", self.model.sent_text(-1))
        self.assertEqual(self.last(), self.ANSWER)
        self.assertFalse(self.dock.composer._busy)
        self.assertEqual(self.dock.conversation.findChildren(PlanCard)[-1]._mark.text(), FAILED_MARK)
        self.shot("stage_refused_by_edit_buffer")


class FailureCardScenario(ScenarioCase):
    def test_a_wrong_address_offers_retry_once_the_settings_are_saved(self) -> None:
        self.model.script(fail(404, '{"detail":"Not Found"}'))
        self.ask("Which layers are there?")
        card = self.dock.conversation.findChildren(FailureCard)[-1]
        self.assertEqual(card.title.text(), RUN_FAILURES[failure_kinds.NOT_FOUND][0])
        self.assertTrue(card.retry.isHidden(), "the same request would hit the same wrong address")
        self.assertFalse(card.settings.isHidden())
        self.assertIn("404", card.technical.text(), "the server's own words are not on the card")
        self.assertTrue(self.dock.progress.isHidden(), "the status line repeats the card under it")
        self.shot("failure_card")
        self.orchestrator.on_settings_saved()
        self.assertFalse(card.retry.isHidden(), "Retry did not come back after the settings were saved")
        self.model.script(say("Two layers."))
        card.retry.click()
        self.wait_idle()
        self.assertEqual(self.last(), "Two layers.")
        self.assertEqual(self.dock.conversation.findChildren(FailureCard), [], "the retried failure stayed")
        self.assertEqual(self.dock.progress.state, STATUS_DONE)
        users = [message for message in self.orchestrator.conversation.messages if message["role"] == "user"]
        self.assertEqual(len(users), 1, "the retried request was written twice")
        self.assertEqual(self.dock.composer._edit.toPlainText(), "", "the box still holds the retried request")


class ReopenedFailureScenario(ScenarioCase):
    def test_a_failure_comes_back_when_the_conversation_reopens(self) -> None:
        self.model.script(fail(404, '{"detail":"Not Found"}'))
        self.ask("Which layers are there?")
        identifier = self.orchestrator.conversation.session_identifier
        self.orchestrator.on_new_session()
        self.orchestrator.on_session_chosen(identifier)
        pump(0.8)
        cards = [card for card in self.dock.conversation.findChildren(FailureCard) if card.isVisibleTo(self.dock)]
        self.assertEqual(len(cards), 1, "the reopened conversation looks as if the model said nothing")
        self.assertEqual(cards[0].title.text(), RUN_FAILURES[failure_kinds.NOT_FOUND][0])
        self.assertTrue(cards[0].retry.isHidden() and cards[0].settings.isHidden(), "a past failure offers actions")
        self.assertEqual([m["role"] for m in self.orchestrator.conversation.window()], ["user"])


class RetryScenario(ScenarioCase):
    def test_an_overloaded_model_is_retried_and_the_status_line_says_so(self) -> None:
        said: list[str] = []
        line = self.dock.progress
        announce = line.show_retry

        def spy(*args: Any) -> None:
            announce(*args)
            said.append(line._step.text())

        line.show_retry = spy
        self.model.script(fail(429, "model deepseek-v4-flash is overloaded"), say("Two layers."))
        self.ask("Which layers are there?")
        countdown = math.ceil(retry.BACKOFF_SECONDS[0])
        busy = progress.RETRY_BUSY.format(format_seconds(countdown, decimals=0), 2, retry.MAX_OVERLOAD_ATTEMPTS)
        self.assertEqual(said, [busy], "the pause before the second attempt was not shown")
        self.assertEqual(self.last(), "Two layers.")
        self.assertEqual(line.state, STATUS_DONE)


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

    def place_of(self, text: str) -> int:
        messages = self.orchestrator.conversation.messages
        return next(index for index, message in enumerate(messages) if message["content"] == text)

    def test_a_message_sent_again_after_a_conversation_rewind_rewinds_to_the_project_before_it(self) -> None:
        self.model.script(
            call("load_skill", names=["project"]),
            call("configure_layer", layer_name="districts", properties={"name": "Districts A"}),
            say("Renamed to Districts A."),
            call("configure_layer", layer_name="Districts A", properties={"name": "Districts B"}),
            say("Renamed to Districts B."),
            call("configure_layer", layer_name="Districts B", properties={"name": "Districts C"}),
            say("Renamed to Districts C."),
        )
        self.ask("Rename districts to Districts A")
        self.apply()
        self.ask("Now rename it to Districts B")
        self.apply()
        second = self.place_of("Now rename it to Districts B")
        self.dock.choose_rewind = lambda project_available: "conversation"
        self.orchestrator.on_rewind(second)
        pump(0.1)
        self.layer("Districts B")
        self.ask("Rename it to Districts C")
        self.apply()
        self.assertEqual(self.place_of("Rename it to Districts C"), second, "the new message must take the same place")
        self.dock.choose_rewind = lambda project_available: "both" if project_available else None
        self.orchestrator.on_rewind(second)
        pump(0.1)
        self.layer("Districts B")


class LongRewindScenario(ScenarioCase):
    def rewind_from_bubble(self, text: str) -> None:
        bubbles = [item for item in self.dock.conversation.findChildren(UserMessage) if item.plain_text() == text]
        self.assertEqual(len(bubbles), 1, f"expected one bubble saying {text!r}")
        place = bubbles[0].message
        conversation = self.orchestrator.conversation
        self.assertIsNotNone(place, "the bubble offers no rewind")
        named = conversation.message_at(place) or {}
        self.assertEqual(named.get("content"), text, "the bubble names another message")
        bubbles[0].rewind.click()
        pump(0.1)
        self.assertEqual(conversation.next_place, place, "the conversation must end right before the message")
        self.assertEqual(self.dock.composer._edit.toPlainText(), text)

    def test_rewinding_from_a_bubble_after_the_cap_trimmed_the_head(self) -> None:
        conversation = self.orchestrator.conversation
        for number in range(MAX_MESSAGES // 2):
            conversation.add("user", f"Earlier question {number}")
            conversation.add("assistant", f"Earlier answer {number}")
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
        self.assertEqual(len(conversation.messages), MAX_MESSAGES, "the scenario must run past the cap")
        self.dock.choose_rewind = lambda project_available: "both" if project_available else None

        self.rewind_from_bubble("Now rename it to Districts B")
        self.layer("Districts A")

        self.dock.clear_prompt()
        identifier = conversation.session_identifier
        self.orchestrator.on_new_session()
        self.orchestrator.on_session_chosen(identifier)
        pump(0.1)
        self.rewind_from_bubble("Rename districts to Districts A")
        self.layer("districts")
        self.assertEqual(conversation.messages[-1]["content"], f"Earlier answer {MAX_MESSAGES // 2 - 1}")
        self.shot("rewound_past_the_cap")


class LayerChipScenario(ScenarioCase):
    def test_the_active_layer_rides_into_a_new_request_until_dropped(self) -> None:
        self.model.script(say("districts holds six squares."), say("Three layers."))
        self.iface.setActiveLayer(self.layer("districts"))
        chip = self.dock.composer.layer_chip
        self.assertFalse(chip.isHidden(), "the active layer did not reach the composer")
        self.assertIn("districts", chip.label.text())
        self.shot("layer_chip")
        self.ask("What is in this layer?")
        self.assertIn("@districts", self.model.sent_text(0))
        self.assertEqual(self.orchestrator.conversation.messages[0]["content"], "What is in this layer? @districts")
        chip.drop()
        self.ask("How many layers are there?")
        self.assertNotIn("@districts", self.orchestrator.conversation.messages[-2]["content"])


class SlashBesideChipScenario(ScenarioCase):
    skill_free_start = False

    def test_a_bare_skill_command_keeps_its_request_beside_the_chip(self) -> None:
        self.model.script(say("districts has one symbol."))
        self.iface.setActiveLayer(self.layer("districts"))
        self.ask("/style")
        sent = self.model.sent_text(0)
        self.assertIn("Apply the 'style' skill to the current project. @districts", sent)
        self.assertEqual(self.orchestrator.conversation.messages[0]["content"], "/style @districts")


class ChromeScenario(ScenarioCase):
    def test_a_new_conversation_keeps_the_old_one_in_the_history(self) -> None:
        self.assertFalse(self.dock.toolbar.new_button.isEnabled(), "nothing to start over from yet")
        self.model.script(say("Three layers."))
        viewport = self.dock.conversation.viewport()
        holder = self.dock.conversation.widget()
        self.orchestrator.on_prompt("Which layers are there?")
        self.assertEqual(len([item for item in viewport.findChildren(LeavingFeed) if item.isVisible()]), 1)
        self.assertIsNotNone(holder.graphicsEffect(), "the chat must wait behind its entrance")
        self.wait_idle()
        pump(0.6)
        self.assertIsNone(holder.graphicsEffect(), "the chat must paint directly once it is in")
        self.assertEqual(self.dock.toolbar.title.label.text(), "Which layers are there?")
        self.assertTrue(self.dock.toolbar.new_button.isEnabled())
        self.dock.toolbar.new_button.click()
        welcome = self.dock.conversation._empty
        self.assertIsNotNone(welcome, "a new conversation opens on the welcome")
        self.assertFalse(welcome.saved.isHidden(), "the welcome must say where the old conversation went")
        self.assertNotEqual(self.dock.toolbar.title.label.text(), "Which layers are there?")
        leaving = [item for item in viewport.findChildren(LeavingFeed) if item.isVisible()]
        self.assertEqual(len(leaving), 1, "the old feed did not leave")
        self.assertIsNotNone(welcome.graphicsEffect(), "the welcome must wait behind its arrival")
        self.shot_now("new_conversation_leaving", 0.1)
        self.shot_now("new_conversation_arriving", 0.25)
        pump(0.6)
        self.assertEqual([item for item in viewport.findChildren(LeavingFeed) if item.isVisible()], [])
        self.assertIsNone(welcome.graphicsEffect(), "the welcome must paint directly once it has arrived")
        self.shot("new_conversation")
        self.dock._show_sessions()
        popup = self.dock._sessions_popup
        try:
            self.assertEqual([row.title for row in popup.rows], ["Which layers are there?"])
            self.assertFalse(popup.rows[0].current)
        finally:
            popup.hide()
        popup.rows[0].chosen.emit(popup.rows[0].identifier)
        self.assertEqual(self.dock.toolbar.title.label.text(), "Which layers are there?")
        self.assertEqual(len([item for item in viewport.findChildren(LeavingFeed) if item.isVisible()]), 1)
        self.assertIsNotNone(holder.graphicsEffect(), "the opened conversation must rise in")
        pump(0.8)
        self.assertIsNone(holder.graphicsEffect())
        self.shot("conversation_reopened")


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


class SaveAsScenario(ScenarioCase):
    def sessions(self) -> list[str]:
        return [identifier for identifier, *_rest in self.orchestrator.conversation.recent()]

    def project_changes(self) -> int:
        notes = [message.plain_text() for message in self.dock.conversation.findChildren(SystemMessage)]
        return notes.count(PROJECT_CHANGED)

    def assert_kept(self, identifier: str, project_changes: int = 0) -> None:
        self.assertEqual(self.orchestrator.conversation.session_identifier, identifier, "the save opened a new chat")
        self.assertIn(identifier, self.sessions(), "the conversation is not in the saved project's history")
        self.assertEqual(self.project_changes(), project_changes, "a save was told as another project")

    def test_the_agents_save_as_keeps_the_conversation_the_steps_after_it_and_undo(self) -> None:
        target = os.path.join(self.folder, "copy.qgz")
        self.model.script(
            call("load_skill", names=["project"]),
            calls(
                ("save_project", {"path": target}),
                ("configure_layer", {"layer_name": "districts", "properties": {"name": "Districts saved"}}),
            ),
            say("I will save the project as a copy and rename districts."),
        )
        self.ask("Save the project as copy.qgz, then rename districts")
        identifier = self.orchestrator.conversation.session_identifier
        self.apply()
        self.layer("Districts saved")
        self.assertEqual(QgsProject.instance().fileName(), target)
        self.assert_kept(identifier)
        card = self.dock.conversation.findChildren(PlanCard)[-1]
        self.assertFalse(card._undo.isHidden(), "the plan saved under a new name offers no Undo")
        card._undo.click()
        pump(0.3)
        self.layer("districts")
        self.assertEqual(QgsProject.instance().fileName(), target, "Undo took the project back to its old file")
        self.assert_kept(identifier)

    def test_the_first_save_of_a_new_project_keeps_its_conversation(self) -> None:
        QgsProject.instance().clear()
        pump(0.3)
        self.model.script(say("The project is empty."))
        self.ask("What is in the project?")
        identifier = self.orchestrator.conversation.session_identifier
        cleared = self.project_changes()
        QgsProject.instance().write(os.path.join(self.folder, "first.qgz"))
        pump(0.3)
        self.assert_kept(identifier, cleared)
        self.assertEqual(len(self.orchestrator.conversation.messages), 2)

    def test_save_as_while_the_answer_streams_keeps_it_in_the_same_conversation(self) -> None:
        self.model.script(say("A map projection flattens the surface of the Earth onto a plane. " * 30, 0.05))
        self.orchestrator.on_prompt("Tell me about projections")
        pump(1.5)
        self.assertTrue(self.agent.is_running)
        identifier = self.orchestrator.conversation.session_identifier
        QgsProject.instance().write(os.path.join(self.folder, "saved_as.qgz"))
        self.wait_idle()
        self.assert_kept(identifier)
        roles = [message["role"] for message in self.orchestrator.conversation.messages]
        self.assertEqual(roles, ["user", "assistant"])
        self.assertTrue(self.last().endswith("onto a plane."), "the answer was cut off by the save")


class PlanRestoreScenario(ScenarioCase):
    def test_a_cancelled_plan_comes_back_and_applies(self) -> None:
        from ai_agent.ui import plan as plan_module

        self.model.script(
            call("load_skill", names=["style"]),
            call("set_opacity", layer_name="districts", opacity=0.5),
            say("I suggest making districts half transparent."),
        )
        self.ask("Make districts half transparent")
        card = self.dock.conversation.findChildren(PlanCard)[-1]
        self.assertEqual(card.layer.text(), plan_module.LAYER.format("districts"))
        card.cancelled.emit()
        pump(0.05)
        self.assertFalse(self.agent.has_pending_writes)
        self.assertFalse(card._restore.isHidden(), "a cancelled plan is not offered back")
        self.shot("plan_cancelled")
        card._restore.click()
        pump(0.05)
        self.assertTrue(self.agent.has_pending_writes, "the restored plan is not queued again")
        self.assertFalse(card._buttons.isHidden(), "the restored card has no Apply")
        self.apply()
        self.assertAlmostEqual(self.layer("districts").opacity(), 0.5)
        self.assertEqual(card._mark.text(), plan_module.APPLIED_MARK)
        self.shot("plan_restored_and_applied")


class BackgroundStepScenario(ScenarioCase):
    STATIONS = 20000
    BUFFER = {"algorithm_id": "native:buffer", "parameters": {"INPUT": "stations", "DISTANCE": 5, "SEGMENTS": 64}}

    def setUp(self) -> None:
        super().setUp()
        stations = QgsVectorLayer("Point?crs=EPSG:3857", "stations", "memory")
        features = []
        for index in range(self.STATIONS):
            feature = QgsFeature(stations.fields())
            feature.setGeometry(QgsGeometry.fromWkt(f"POINT ({index * 20} {index % 200 * 20})"))
            features.append(feature)
        stations.dataProvider().addFeatures(features)
        QgsProject.instance().addMapLayer(stations)

    def test_the_card_shows_the_progress_of_a_long_step(self) -> None:
        self.model.script(
            call("load_skill", names=["processing"]),
            call("run_processing", **self.BUFFER, output_name="Station zones"),
            say("I will buffer the stations by 5 m."),
            say("Checked: every station has its zone."),
        )
        self.ask("Buffer the stations by 5 m")
        card = self.dock.conversation.findChildren(PlanCard)[-1]
        self.orchestrator.on_confirm_plan()
        shown = []
        while self.agent.is_applying:
            process()
            step = card._steps[0]
            if not step.bar.isHidden():
                shown.append(step.mark.text())
                if len(shown) == 1:
                    ARTIFACTS.mkdir(parents=True, exist_ok=True)
                    self.dock.grab().save(str(ARTIFACTS / "background_step_progress.png"))
        self.assertTrue(shown, "the running step never showed its progress")
        self.assertTrue(all(text.endswith("%") for text in shown if text != RUNNING_MARK), shown)
        self.assertTrue(any(text.endswith("%") for text in shown), shown)
        self.wait_idle()
        self.assertEqual(self.layer("Station zones").featureCount(), self.STATIONS)
        self.assertTrue(card._steps[0].bar.isHidden(), "the bar stays after the step ended")

    def test_stop_stops_a_long_step_and_the_steps_after_it(self) -> None:
        centroids = {"algorithm_id": "native:centroids", "parameters": {"INPUT": "districts"}}
        self.model.script(
            call("load_skill", names=["processing"]),
            call("run_processing", **self.BUFFER, output_name="Station zones"),
            call("run_processing", **centroids, output_name="District centres"),
            say("I will buffer the stations, then find the district centres."),
        )
        self.ask("Buffer the stations and find the district centres")
        self.orchestrator.on_confirm_plan()
        self.assertTrue(self.agent.is_applying, "the long step did not go to the background")
        self.orchestrator.on_stop()
        self.wait_idle()
        project = QgsProject.instance()
        self.assertEqual(project.mapLayersByName("Station zones"), [])
        self.assertEqual(project.mapLayersByName("District centres"), [], "a step after the stopped one ran")
        notes = [message.plain_text() for message in self.dock.conversation.findChildren(SystemMessage)]
        self.assertTrue(any("stopped during apply" in note.lower() for note in notes), notes)


class _Overpass(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        self.send_response(200)
        self.send_header("Content-Type", "application/osm3s+xml")
        self.send_header("Content-Length", str(len(CAFES)))
        self.end_headers()
        self.wfile.write(CAFES)

    def log_message(self, format: str, *args: Any) -> None:
        return


class DownloadStopScenario(ScenarioCase):
    WORK_ENDED_S = 1.0

    def setUp(self) -> None:
        super().setUp()
        server = ThreadingHTTPServer(("127.0.0.1", 0), _Overpass)
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        QgsSettings().setValue(overpass.SETTINGS_KEY, f"http://127.0.0.1:{server.server_address[1]}/api/interpreter")
        self.addCleanup(QgsSettings().remove, overpass.SETTINGS_KEY)

    def test_stop_after_the_answer_came_in_adds_no_layer(self) -> None:
        query = "[out:xml];node[amenity=cafe](55.7,37.6,55.8,37.7);out body;"
        cafes = {"query": query, "name": "Cafes", "intent": "cafes in a corner of Moscow", "geometry": "points"}
        self.model.script(
            call("load_skill", names=["osm"]),
            calls(("run_overpass", cafes)),
            say("I will download the cafes."),
        )
        self.ask("Download the cafes in this corner of Moscow")
        self.orchestrator.on_confirm_plan()
        self.assertTrue(self.agent.is_applying, "the download did not go to the background")
        time.sleep(self.WORK_ENDED_S)
        self.orchestrator.on_stop()
        self.wait_idle()
        self.assertEqual(QgsProject.instance().mapLayersByName("Cafes"), [], "a stopped download added its layer")
        notes = [message.plain_text() for message in self.dock.conversation.findChildren(SystemMessage)]
        self.assertTrue(any("stopped during apply" in note.lower() for note in notes), notes)


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

    def test_rewinding_past_the_question_ends_it(self) -> None:
        self.model.script(
            call("ask_user", question="Buffer by which distance?", options=["100 m", "500 m"]),
            say("Main rivers is one line."),
        )
        self.ask("Buffer the roads")
        self.assertTrue(self.agent.is_awaiting_answer)
        self.dock.choose_rewind = lambda project_available: "conversation"
        self.orchestrator.on_rewind(0)
        pump(0.1)
        self.assertFalse(self.agent.is_awaiting_answer, "the question outlived the conversation it was asked in")
        self.dock.clear_prompt()
        self.ask("Describe the rivers layer")
        sent = self.model.sent_text(-1)
        self.assertNotIn("Buffer the roads", sent, "the request rewound away still reached the model")
        self.assertEqual(self.last(), "Main rivers is one line.")


class InterjectionScenario(ScenarioCase):
    def test_a_correction_sent_during_the_final_answer_gets_one_more_step(self) -> None:
        self.model.script(
            say("Done: the roads would be red, as you asked. " * 10, 0.05),
            say("Done: the roads are blue."),
        )
        self.orchestrator.on_prompt("Colour the roads red")
        pump(0.3)
        self.assertTrue(self.agent.is_running, "the answer ended before the correction could be sent")
        self.orchestrator.on_prompt("Blue, not red")
        self.wait_idle()
        self.assertEqual(len(self.model.requests), 2, "the correction never reached the model")
        sent = self.model.requests[-1]["messages"]
        self.assertEqual([message["role"] for message in sent], ["system", "user", "assistant", "user"])
        self.assertIn("Blue, not red", sent[-1]["content"])
        self.assertTrue(self.answers()[0].startswith("Done: the roads would be red"))
        self.assertEqual(self.last(), "Done: the roads are blue.")


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
        )
        self.ask("Make districts half transparent")
        self.assertAlmostEqual(self.layer("districts").opacity(), 0.5)
        notes = [message.plain_text() for message in self.dock.conversation.findChildren(SystemMessage)]
        self.assertIn(CHECKED_BY_READING, notes, "an opacity reads back without asking the model")
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
        composer._edit.clear()
        composer._edit.insertPlainText("🌍 colour @ma")
        pump(0.1)
        self.assertFalse(composer._popup.isHidden())
        composer._on_complete()
        composer._edit.insertPlainText("blue")
        self.assertEqual(composer._edit.toPlainText(), '🌍 colour @"Main rivers" blue')
