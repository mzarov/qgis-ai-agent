"""Behaviour of the redesigned controls in a live QGIS.

The screen checks prove how the settings window and the composer look; these
prove they still work: the custom controls answer like the combo boxes they
replaced, edits are tracked until saved, the composer's states follow the run.

Runs inside `real_qgis_workflows.py` against the extracted plugin ZIP.
"""

import unittest

from e2e_harness import PluginCase, pump
from qgis.PyQt.QtCore import QEvent, QPoint, Qt
from qgis.PyQt.QtGui import QColor, QKeyEvent
from qgis.PyQt.QtWidgets import QLineEdit, QWidget

from ai_agent.ui import controls, settings_fields
from ai_agent.ui.composer_parts import LAYER_TOKEN, SKILL_TOKEN
from ai_agent.ui.settings_dialog import SettingsDialog


class SegmentedTest(unittest.TestCase):
    def setUp(self) -> None:
        self.segmented = controls.Segmented(QWidget().palette())
        self.segmented.addItems(["auto", "openai", "anthropic"])
        self.seen: list[str] = []
        self.segmented.currentTextChanged.connect(self.seen.append)

    def test_it_reads_like_a_combo_box(self) -> None:
        self.assertEqual(self.segmented.currentText(), "auto")
        self.assertEqual(self.segmented.findText("anthropic"), 2)
        self.assertEqual(self.segmented.findText("missing"), -1)
        settings_fields.select(self.segmented, "openai")
        self.assertEqual(self.segmented.currentText(), "openai")
        self.assertEqual(self.seen, ["openai"])

    def test_choosing_the_current_item_again_is_silent(self) -> None:
        self.segmented.setCurrentText("auto")
        self.assertEqual(self.seen, [])


class ChipsTest(unittest.TestCase):
    def test_a_chip_writes_its_value_and_typing_lights_the_match(self) -> None:
        edit = QLineEdit("300000")
        chips = controls.Chips(
            edit.palette(), edit, [("100k", "100000"), ("300k", "300000")], settings_fields.parsed_budget
        )
        buttons = [chip for chip, _value in chips._chips]
        self.assertEqual([button.isChecked() for button in buttons], [False, True])
        buttons[0].click()
        self.assertEqual(edit.text(), "100000")
        self.assertEqual([button.isChecked() for button in buttons], [True, False])
        edit.setText("123k")
        self.assertEqual([button.isChecked() for button in buttons], [False, False])
        edit.setText("100k")
        self.assertTrue(buttons[0].isChecked())


class TokenPatternTest(unittest.TestCase):
    def test_skill_and_layer_tokens(self) -> None:
        self.assertEqual(SKILL_TOKEN.match("/style colour").group(), "/style")
        self.assertIsNone(SKILL_TOKEN.match("colour /style"))
        found = [m.group() for m in LAYER_TOKEN.finditer('colour @districts and @"Main rivers" mail a@b.c')]
        self.assertEqual(found, ["@districts", '@"Main rivers"'])


class SettingsBehaviourTest(PluginCase):
    api_url = "http://localhost:11434/v1"
    model_name = "qwen3"

    def setUp(self) -> None:
        super().setUp()
        self.dialog = SettingsDialog(self.dock)
        self.dialog.show()
        pump(0.1)

    def tearDown(self) -> None:
        self.dialog.reject()
        self.dialog.deleteLater()
        super().tearDown()

    def test_save_waits_for_an_edit_and_the_page_shows_a_dot(self) -> None:
        self.assertFalse(self.dialog.save_btn.isEnabled())
        dot = self.dialog._nav_buttons[1].findChild(QWidget, "pageDirty")
        self.assertTrue(dot.isHidden())
        self.dialog.journal_cb.toggle()
        self.assertTrue(self.dialog.save_btn.isEnabled())
        self.assertFalse(dot.isHidden())

    def test_a_provider_tile_fills_the_endpoint(self) -> None:
        tile = next(tile for tile in self.dialog.provider_tiles._tiles if tile.title == "LM Studio")
        tile.clicked.emit(tile.title)
        self.assertEqual(self.dialog.url_edit.text(), "http://localhost:1234/v1")
        self.assertEqual(self.dialog.preset_combo.currentText(), "LM Studio")
        self.assertTrue(self.dialog.save_btn.isEnabled())

    def test_typing_an_address_selects_its_tile(self) -> None:
        self.dialog.url_edit.setText("https://api.openai.com/v1")
        selected = [tile.title for tile in self.dialog.provider_tiles._tiles if tile.selected]
        self.assertEqual(selected, ["OpenAI"])

    def test_only_the_main_providers_get_a_tile_and_they_carry_logos(self) -> None:
        titles = [tile.title for tile in self.dialog.provider_tiles._tiles]
        self.assertEqual(len(titles), 7)
        self.assertNotIn("DeepSeek", titles)
        from ai_agent.ui import logos

        for title in titles[:-1]:
            self.assertIsNotNone(logos.pixmap(title, QColor(0, 0, 0), 16), title)

    def test_the_probe_result_lands_in_the_status_card(self) -> None:
        self.dialog._probe_started = 0.0
        self.dialog._on_probe_completed(False, "boom")
        self.assertEqual((self.dialog.status_card.state, self.dialog.status_card.detail.text()), ("bad", "boom"))


class ComposerBehaviourTest(PluginCase):
    api_url = "http://localhost:11434/v1"
    model_name = "qwen3"

    def test_escape_stops_a_running_agent_only(self) -> None:
        stops: list[bool] = []
        self.dock.composer.stopped.connect(lambda: stops.append(True))
        escape = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
        self.dock.composer._edit.keyPressEvent(escape)
        self.assertEqual(stops, [])
        self.dock.set_busy(True)
        self.dock.composer._edit.keyPressEvent(escape)
        self.assertEqual(stops, [True])
        self.dock.set_busy(False)

    def test_the_progress_line_follows_the_run(self) -> None:
        self.assertTrue(self.dock.progress.isHidden())
        self.dock.set_busy(True)
        self.dock.add_tool_message("Reading layer 'districts'")
        self.assertFalse(self.dock.progress.isHidden())
        self.assertEqual(self.dock.progress.step_text, "Reading layer 'districts'")
        self.dock.set_busy(False)
        self.assertTrue(self.dock.progress.isHidden())

    def test_the_button_and_toolbar_follow_the_state(self) -> None:
        composer = self.dock.composer
        self.assertEqual(composer._send.toolTip(), "Send")
        self.assertFalse(composer._send.isEnabled(), "nothing to send yet")
        composer._edit.setPlainText("colour the rivers")
        self.assertTrue(composer._send.isEnabled())
        composer._edit.clear()
        self.dock.set_model("moonshotai/kimi-k2.5")
        self.assertEqual(composer.toolbar.model.text(), "kimi-k2.5")
        self.dock.set_busy(True)
        self.assertEqual(composer._send.toolTip(), "Stop")
        self.assertTrue(composer._send.isEnabled(), "stop works with an empty box")
        self.dock.set_busy(False)
        self.dock.set_configured(False)
        self.assertTrue(composer._send.isHidden())
        self.assertTrue(composer._edit.isReadOnly())

    def test_the_attach_menu_opens_above_the_button(self) -> None:
        toolbar = self.dock.composer.toolbar
        toolbar.attach.click()
        pump(0.05)
        try:
            self.assertTrue(toolbar.menu.isVisible())
            self.assertEqual([action.isEnabled() for action in toolbar.menu.actions()], [True, True])
            self.assertLess(toolbar.menu.geometry().bottom(), toolbar.attach.mapToGlobal(QPoint(0, 0)).y())
        finally:
            toolbar.menu.hide()

    def test_the_box_starts_as_one_line_and_grows_to_a_cap(self) -> None:
        edit = self.dock.composer._edit
        one_line = edit.height()
        edit.setPlainText("first\nsecond\nthird")
        pump(0.05)
        self.assertGreater(edit.height(), one_line)
        edit.setPlainText("line\n" * 30)
        pump(0.05)
        capped = edit.height()
        edit.setPlainText("line\n" * 60)
        pump(0.05)
        self.assertEqual(edit.height(), capped)
        self.assertEqual(edit.verticalScrollBarPolicy(), Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        edit.clear()
        pump(0.05)
        self.assertEqual(edit.height(), one_line)

    def test_the_popup_never_grows_wider_than_the_composer(self) -> None:
        composer = self.dock.composer
        composer.set_skill_source(lambda: [("style", "x" * 400, "builtin")])
        composer._edit.setPlainText("/s")
        pump(0.1)
        self.assertEqual(composer._popup.width(), composer._frame.width())
