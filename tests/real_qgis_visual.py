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

import ui_snapshot
from e2e_harness import ARTIFACTS, WINDOW_HEIGHT, WINDOW_WIDTH, PluginCase, pump
from qgis.core import QgsApplication
from qgis.PyQt.QtWidgets import QApplication, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

import ai_agent
from ai_agent import i18n
from ai_agent.ui import settings_layout
from ai_agent.ui.settings_dialog import SettingsDialog

LOCAL_URL = "http://localhost:11434/v1"
LOCAL_MODEL = "qwen3"
NARROW_WIDTH = 380
SETTINGS_WIDTH = 900
SETTINGS_HEIGHT = 640
SETTINGS_PAGES = ("connection", "privacy", "skills", "geocoding", "advanced")
PROFILE_MARKER = "ai-agent-integration-"
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
STEP = "Reading layer 'districts'"
TOKENS = "/style colour @districts by pop2020 in 5 classes"
DONE = "Done: %n step(s) applied.{0}"


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

    def check(self, name: str, widget: QWidget) -> None:
        name += LOCALE_SUFFIX
        pump(0.3)
        ui_snapshot.normalize_texts(widget, {_profile_root(): "<profile>"})
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
    def test_working(self) -> None:
        self.dock.add_user_message(REQUEST)
        self.dock.set_busy(True)
        self.dock.add_tool_message(STEP)
        self.dock.progress._timer.stop()
        try:
            self.check("dock_working", self.dock)
        finally:
            self.dock.set_busy(False)

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
