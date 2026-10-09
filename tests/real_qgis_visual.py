"""Screen checks of the plugin in a live QGIS: structure, layout faults, pixels.

Each test builds one screen without a model — the dock in a known state, a
composer popup, a settings page — then checks it with `ui_snapshot`:

- the widget structure must match its JSON golden in `tests/data/ui/structure`;
- no text may be clipped and no content may overflow its scroll area;
- with `UI_PIXEL_BASELINE=1` (one pinned CI job) the screenshot must match its
  PNG golden in `tests/data/ui/pixels`.

Screenshots and a gallery page land in `E2E_ARTIFACTS`. After an intended
change, regenerate goldens with `UI_UPDATE_GOLDENS=1`; pixel goldens only from
the `ui-goldens` artifact of the pinned CI job.

Runs inside `real_qgis_workflows.py` against the extracted plugin ZIP.
"""

import os
import pathlib
import unittest
from typing import Any

import ui_snapshot
from e2e_harness import ARTIFACTS, WINDOW_HEIGHT, WINDOW_WIDTH, PluginCase, pump
from qgis.core import QgsApplication
from qgis.PyQt.QtWidgets import QApplication, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

import ai_agent
from ai_agent import i18n
from ai_agent.core.agent import failures
from ai_agent.core.orchestrator import notices
from ai_agent.qgis_tools.registry import summarize_tool_call, summarize_tool_result
from ai_agent.ui import activity, compass, settings_layout, theme, transitions
from ai_agent.ui.dock_widget import AgentDockWidget
from ai_agent.ui.settings_dialog import SettingsDialog
from ai_agent.ui.thinking import ThinkingBlock

LOCAL_URL = "http://localhost:11434/v1"
LOCAL_MODEL = "qwen3"
NARROW_WIDTH = 380
SETTINGS_WIDTH = 900
SETTINGS_HEIGHT = 640
SETTINGS_PAGES = ("connection", "privacy", "skills", "geocoding", "advanced", "connectors", "personalisation")
PROFILE_MARKER = "ai-agent-integration-"
# A real profile path is long; a short stand-in once hid a skills page that overflowed on a real Mac.
LONG_PROFILE = "/Users/someone-with-a-long-name/Library/Application Support/QGIS/QGIS4/profiles/default"
LOCALE = os.environ.get("UI_LOCALE", "").strip()
LOCALE_SUFFIX = f"_{LOCALE}" if LOCALE else ""
REQUEST = "Colour districts by pop2020 in 5 classes"
ANSWER = (
    "**districts** has a numeric `pop2020` field from 20 000 to 95 000. "
    "I prepared a graduated renderer with 5 classes, equal intervals, light to dark."
)
PLAN = [
    "Graduating 'districts' by 'pop2020', classes: 5.",
    "Labeling 'districts' with 'name'.",
]
CHECKING = "Checking the applied changes…"
FAILED_STEPS = "%n step(s) did not run — the reasons are in the plan above."
STEP = ("query_layer", {"layer_name": "districts", "aggregate": "max", "expression": "pop2020"})
# The calls before the answer, with what each found: the open activity list as a person sees it.
READS = (
    ("describe_layer", {"layer_name": "districts"}, {"feature_count": 12}),
    ("get_field_values", {"layer_name": "districts", "field_name": "pop2020"}, {"unique_values": list(range(12))}),
)
TOKENS = "/style colour @districts by pop2020 in 5 classes"
DONE = "Done: %n step(s) applied.{0}"
BAR_CHART = {
    "type": "chart",
    "kind": "bar",
    "title": "Population 2020 by district, people",
    "labels": ["D1", "D2", "D3", "D4", "D5", "D6"],
    "series": [{"name": "pop2020", "values": [20000, 35000, 50000, 65000, 80000, 95000]}],
    "x_label": "",
    "y_label": "",
    "unit": "people",
}
PIE_CHART = {
    "type": "chart",
    "kind": "pie",
    "title": "Land cover by area",
    "labels": ["Forest", "Cropland", "Built-up", "Water"],
    "series": [{"name": "area", "values": [52.0, 31.0, 11.0, 6.0]}],
    "x_label": "",
    "y_label": "",
    "unit": "km²",
}
TABLE = {
    "type": "table",
    "title": "Largest districts",
    "columns": ["name", "pop2020", "area_km2"],
    "rows": [["District 6", "95,000", "112.4"], ["District 5", "80,000", "98.1"], ["District 4", "65,000", "87"]],
    "total": 6,
}


def _profile_root() -> str:
    path = QgsApplication.qgisSettingsDirPath()
    at = path.find(PROFILE_MARKER)
    if at < 0:
        return ""
    end = path.find("/", at)
    return path if end < 0 else path[:end]


class ScreenCase(PluginCase):
    api_url = LOCAL_URL
    model_name = LOCAL_MODEL

    def setUp(self) -> None:
        if LOCALE:
            # The previous test's unload removed the translator; strings built at runtime need it back.
            i18n.install(os.path.dirname(os.path.abspath(ai_agent.__file__)))
        ui_snapshot.EXTRA_VOLATILE[:] = ui_snapshot.duration_patterns(
            [i18n.tr("{0} min {1} s"), i18n.tr("{0} ms"), i18n.tr("{0} s")]
        )
        super().setUp()
        QApplication.setCursorFlashTime(0)
        self.faults: list[str] = []

    def reads(self) -> None:
        self.reads_into(self.dock)

    @staticmethod
    def reads_into(dock: Any) -> None:
        for name, arguments, payload in READS:
            entry = dock.add_tool_message(summarize_tool_call(name, arguments))
            dock.mark_tool_done(entry, True, summarize_tool_result(name, arguments, payload))

    def check(self, name: str, widget: QWidget) -> None:
        name += LOCALE_SUFFIX
        # Focus paints the composer's frame; which widget holds it depends on the tests run before.
        focused = QApplication.focusWidget()
        if focused is not None:
            focused.clearFocus()
        # A swinging needle or a breathing ring would make every pixel golden depend on the moment of the grab.
        for mark in widget.findChildren(compass.Compass):
            mark.stop()
        for ring in widget.findChildren(activity.PulseRing):
            ring.stop()
        # A transition caught halfway would too: what leaves goes, what arrives is in place.
        for overlay in widget.findChildren(transitions.LeavingFeed):
            overlay.finish()
        for arrival in widget.findChildren(transitions.Arrival):
            arrival.finish()
        # And a list or a reasoning box still opening: open it fully.
        for group in widget.findChildren(activity.ActivityGroup):
            group.finish_folding()
        for block in widget.findChildren(ThinkingBlock):
            block.finish_folding()
        pump(0.3)
        ui_snapshot.normalize_texts(widget, {_profile_root(): LONG_PROFILE})
        pump(0.1)
        image = widget.grab().toImage()
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        image.save(str(ARTIFACTS / f"ui_{name}.png"))
        problems = []
        # Translated text is the catalogue's business (tests/test_i18n.py); the
        # Russian run looks for clipping, so its structure is not pinned.
        structure = None if LOCALE else ui_snapshot.compare_structure(name, ui_snapshot.structure(widget))
        if structure:
            problems.append(structure)
        problems.extend(ui_snapshot.layout_faults(widget))
        if ui_snapshot.PIXEL_BASELINE:
            pixels = ui_snapshot.compare_pixels(name, image, ARTIFACTS)
            if pixels:
                problems.append(pixels)
        self.assertEqual(problems, [], f"screen {name!r}")

    def conversation(self) -> None:
        self.dock.add_user_message(REQUEST)
        self.reads()
        self.dock.conversation.add_assistant_message(ANSWER)
        self.dock.add_plan_message(PLAN)
        self.dock.add_system_message(i18n.tr(CHECKING))
        self.dock.add_result_message(i18n.tr_n(DONE, len(PLAN)).format(""))


class DockScreens(ScreenCase):
    def test_welcome(self) -> None:
        self.check("dock_welcome", self.dock)

    def test_welcome_in_a_narrow_dock(self) -> None:
        self.iface.window.resize(NARROW_WIDTH, WINDOW_HEIGHT)
        self.check("dock_welcome_narrow", self.dock)
        self.iface.window.resize(WINDOW_WIDTH, WINDOW_HEIGHT)

    def test_conversation(self) -> None:
        self.conversation()
        self.check("dock_conversation", self.dock)

    def test_conversation_in_a_narrow_dock(self) -> None:
        self.iface.window.resize(NARROW_WIDTH, WINDOW_HEIGHT)
        self.conversation()
        self.check("dock_narrow", self.dock)
        self.iface.window.resize(WINDOW_WIDTH, WINDOW_HEIGHT)


class StateScreens(ScreenCase):
    def test_a_dark_panel_in_a_light_qgis(self) -> None:
        """The panel theme overrides QGIS: every part of the rebuilt panel follows the dark tokens."""
        theme.set_override(theme.THEME_DARK)
        panel = AgentDockWidget()
        try:
            panel.resize(self.dock.width(), self.dock.height())
            panel.set_configured(True)
            panel.show()
            panel.add_user_message(REQUEST)
            self.reads_into(panel)
            panel.conversation.add_assistant_message(ANSWER)
            panel.add_plan_message(PLAN)
            self.check("dock_forced_dark", panel)
        finally:
            theme.set_override(theme.THEME_AUTO)
            panel.hide()
            panel.deleteLater()

    def test_working(self) -> None:
        self.dock.add_user_message(REQUEST)
        self.dock.set_busy(True)
        self.dock.conversation.append_thinking("The renderer needs the value range first.")
        self.reads()
        self.dock.add_tool_message(summarize_tool_call(*STEP))
        self.dock.progress._timer.stop()
        try:
            self.check("dock_working", self.dock)
        finally:
            self.dock.set_busy(False)

    def test_failed_apply(self) -> None:
        self.dock.add_user_message(REQUEST)
        plan = self.dock.add_plan_message(PLAN)
        self.dock.mark_plan_step(
            plan, 0, notices.STEP_FAILED, failures.explain_failure("server replied: Gateway Timeout")
        )
        self.dock.mark_plan_step(plan, 1, notices.STEP_SKIPPED)
        self.dock.mark_plan_failed(plan)
        self.dock.add_system_message(i18n.tr_n(FAILED_STEPS, 1))
        self.check("dock_failed_apply", self.dock)

    def test_plan_offer(self) -> None:
        self.dock.set_work_mode("plan")
        self.dock.add_user_message(REQUEST)
        self.dock.conversation.add_assistant_message(ANSWER)
        self.dock.offer_plan()
        self.check("dock_plan", self.dock)

    def test_plan_offer_in_a_narrow_dock(self) -> None:
        self.iface.window.resize(NARROW_WIDTH, WINDOW_HEIGHT)
        self.dock.set_work_mode("plan")
        self.dock.add_user_message(REQUEST)
        self.dock.conversation.add_assistant_message(ANSWER)
        self.dock.offer_plan()
        self.check("dock_plan_narrow", self.dock)
        self.iface.window.resize(WINDOW_WIDTH, WINDOW_HEIGHT)

    def test_charts_and_a_table(self) -> None:
        self.dock.add_user_message("Chart the population by district and show the largest ones")
        self.dock.add_visual(BAR_CHART)
        self.dock.add_visual(PIE_CHART)
        self.dock.add_visual(TABLE)
        self.check("dock_charts", self.dock)

    def test_question_card(self) -> None:
        self.dock.add_user_message("Colour the roads")
        self.dock.add_question(
            "There are two road layers. Which one should I colour?",
            ["roads_2024 (12 480 features)", "roads_old (9 102 features)", "Both"],
        )
        self.check("dock_question", self.dock)

    def test_question_card_in_a_narrow_dock(self) -> None:
        self.iface.window.resize(NARROW_WIDTH, WINDOW_HEIGHT)
        self.dock.add_user_message("Colour the roads")
        self.dock.add_question(
            "There are two road layers. Which one should I colour?",
            ["roads_2024 (12 480 features)", "roads_old (9 102 features)", "Both"],
        )
        self.check("dock_question_narrow", self.dock)
        self.iface.window.resize(WINDOW_WIDTH, WINDOW_HEIGHT)

    def test_auto_mode(self) -> None:
        self.dock.set_work_mode("auto")
        self.dock.add_user_message(REQUEST)
        self.dock.add_plan_message(PLAN, True)
        self.check("dock_auto", self.dock)

    def test_no_model_connected(self) -> None:
        self.dock.set_configured(False)
        self.check("dock_offline", self.dock)

    def test_tokens_are_highlighted(self) -> None:
        self.dock.composer._edit.setPlainText(TOKENS)
        self.check("composer_tokens", self.dock)


class ComposerScreens(ScreenCase):
    def test_skill_popup(self) -> None:
        self.dock.composer._edit.insertPlainText("/s")
        self.check("composer_skills", self.dock)

    def test_layer_popup(self) -> None:
        self.dock.composer._edit.insertPlainText("colour @")
        self.check("composer_layers", self.dock)

    def test_context_popup(self) -> None:
        meter = self.dock.composer.toolbar.meter
        meter.set_numbers(41_300, 128_000, 212_400, 16)
        meter.popup.open_above(meter.ring)
        try:
            self.check("context_popup", meter.popup)
        finally:
            meter.popup.hide()

    def test_conversations_menu(self) -> None:
        from datetime import datetime

        from ai_agent.ui.sessions_popup import Entry

        # A fixed "now", so the day groups and the dates are the same on every run.
        now = datetime(2026, 10, 8, 15, 0).timestamp()
        entries = [
            Entry("a", "Town layers and what is in them", datetime(2026, 10, 8, 14, 32).timestamp(), True),
            Entry("b", "Roads coloured by type, cafés labelled", datetime(2026, 10, 7, 9, 10).timestamp()),
            Entry(
                "c",
                "A very long conversation title that has to be cut short in the menu",
                datetime(2026, 9, 1).timestamp(),
            ),
        ]
        popup = self.dock._sessions_popup
        popup.show_sessions(entries, self.dock.toolbar.title, now)
        try:
            self.check("conversations_menu", popup)
        finally:
            popup.hide()

    def test_mode_menu(self) -> None:
        toolbar = self.dock.composer.toolbar
        frame = self.dock.composer._frame
        toolbar.modes.open_above(frame, "ask", frame.width())
        try:
            self.check("mode_menu", toolbar.modes)
        finally:
            toolbar.modes.hide()

    def test_attached_pictures(self) -> None:
        import tempfile

        from qgis.PyQt.QtGui import QColor, QImage

        folder = tempfile.mkdtemp()
        for name, colour in (("sketch.png", "orange"), ("a photo of the paper map from the archive.jpg", "teal")):
            image = QImage(48, 32, QImage.Format.Format_RGB32)
            image.fill(QColor(colour))
            image.save(os.path.join(folder, name))
            self.dock.add_attachment(os.path.join(folder, name))
        self.dock.composer._edit.setPlainText("What is on these pictures?")
        self.check("composer_attachments", self.dock)


class SettingsScreens(ScreenCase):
    def test_every_settings_page(self) -> None:
        dialog = SettingsDialog(self.dock)
        dialog.resize(SETTINGS_WIDTH, SETTINGS_HEIGHT)
        dialog.show()
        try:
            for index, page in enumerate(SETTINGS_PAGES):
                with self.subTest(page=page):
                    settings_layout.show_page(dialog, index)
                    self.check(f"settings_{page}", dialog)
            with self.subTest(page="connector_detail"):
                settings_layout.show_page(dialog, SETTINGS_PAGES.index("connectors"))
                dialog.connectors.open("pdok")
                self.check("settings_connector_detail", dialog)
                dialog.connectors.close_detail()
        finally:
            dialog.reject()
            dialog.deleteLater()


class FaultDetector(unittest.TestCase):
    """The layout check must see a fault, or its empty result proves nothing."""

    def setUp(self) -> None:
        self.window = QWidget()
        self.window.resize(300, 200)
        self.column = QVBoxLayout(self.window)

    def tearDown(self) -> None:
        self.window.close()
        self.window.deleteLater()
        pump(0.05)

    def faults(self) -> list[str]:
        self.window.show()
        pump(0.1)
        return ui_snapshot.layout_faults(self.window)

    def test_clipped_label_is_reported(self) -> None:
        label = QLabel("A label far too long for the forty pixels it was given")
        label.setFixedWidth(40)
        self.column.addWidget(label)
        self.assertTrue(any("text does not fit" in fault for fault in self.faults()))

    def test_clipped_button_is_reported(self) -> None:
        button = QPushButton("A button far too long for its width")
        button.setFixedWidth(40)
        self.column.addWidget(button)
        self.assertTrue(any("button text does not fit" in fault for fault in self.faults()))

    def test_horizontal_overflow_is_reported(self) -> None:
        area = QScrollArea()
        content = QWidget()
        content.setFixedWidth(900)
        area.setWidget(content)
        self.column.addWidget(area)
        self.assertTrue(any("wider than its scroll area" in fault for fault in self.faults()))

    def test_a_fitting_layout_is_clean(self) -> None:
        self.column.addWidget(QLabel("Short"))
        self.column.addWidget(QPushButton("OK"))
        self.assertEqual(self.faults(), [])


def tearDownModule() -> None:
    if pathlib.Path(ARTIFACTS).is_dir():
        ui_snapshot.write_gallery(ARTIFACTS)
