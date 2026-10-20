import dataclasses
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from typing import Any
from unittest import mock

from e2e_harness import PluginCase, pump
from qgis.PyQt.QtCore import QEvent, QObject, QPoint, QPointF, Qt, QUrl, QVariantAnimation, pyqtSlot
from qgis.PyQt.QtGui import (
    QColor,
    QDesktopServices,
    QImage,
    QKeyEvent,
    QMouseEvent,
    QTextCursor,
    QTextDocument,
    QWheelEvent,
)
from qgis.PyQt.QtWidgets import QApplication, QLabel, QLineEdit, QScrollBar, QTextBrowser, QToolTip, QWidget

from ai_agent.config import personal
from ai_agent.core.orchestrator.notices import STATUS_DONE, SWITCH_WHILE_RUNNING
from ai_agent.ui import compass, controls, progress, settings_fields, skill_popup, style, transitions
from ai_agent.ui.activity import ActivityGroup, PulseRing
from ai_agent.ui.chart import ChartCard
from ai_agent.ui.composer_parts import LAYER_TOKEN, SKILL_TOKEN
from ai_agent.ui.connection_widgets import STATE_BAD, StatusCard
from ai_agent.ui.conversation import ConversationView
from ai_agent.ui.dropdown import Dropdown
from ai_agent.ui.messages import AssistantMessage, SystemMessage
from ai_agent.ui.plan import RUN_PLAN_QUESTION, PlanOffer
from ai_agent.ui.question import QuestionCard
from ai_agent.ui.settings_dialog import SettingsDialog
from ai_agent.ui.table_card import TableCard
from ai_agent.ui.thinking import ThinkingBlock

SLOW_TEST_S = 4.0
CLOSE_WAIT_S = 20.0
CHILD_TIMEOUT_S = 120
# Each close runs in a child QGIS: a QThread destroyed while it runs aborts the whole process.
CLOSE_CHILD = """
import pathlib, sys, tempfile
from real_qgis_smoke import qgis_application
with tempfile.TemporaryDirectory() as root, qgis_application(pathlib.Path(root)):
    import real_qgis_controls
    code = real_qgis_controls.close_during_a_slow_test(sys.argv[1])
sys.exit(code)
"""
PANEL_WIDTH = 360
LAST_CELL = "the last column holds a long value"
WIDE_TABLE = {
    "type": "table",
    "title": "Every field of districts",
    "columns": [f"field_{index}" for index in range(10)],
    "rows": [[f"value {index}" for index in range(9)] + [LAST_CELL]] * 3,
    "total": 3,
}
PAYLOAD = "<b>bold</b>"
RED = QColor(255, 0, 0)
LONG_FEED = 120
DISTRICT_LIST = "A district list:\n\n" + "\n".join(f"- item {index}" for index in range(8))


def shown(text: str, text_format: Any = Qt.TextFormat.AutoText) -> str:
    # What Qt draws: AutoText, as a tooltip, turns rich at a tag on the first line.
    plain = text_format == Qt.TextFormat.PlainText
    if plain or (text_format == Qt.TextFormat.AutoText and "<" not in text.split("\n", 1)[0]):
        return text
    document = QTextDocument()
    document.setHtml(text)
    return document.toPlainText()


def red_pixels(widget: QWidget) -> int:
    image = widget.grab().toImage()
    return sum(
        1
        for y in range(0, image.height(), 2)
        for x in range(0, image.width(), 2)
        if image.pixelColor(x, y).red() > 200 and image.pixelColor(x, y).green() < 60
    )


def mouse(widget: QWidget, kind: Any, point: QPointF, button: Any, buttons: Any) -> None:
    at = QPointF(widget.mapToGlobal(point.toPoint()))
    QApplication.sendEvent(widget, QMouseEvent(kind, point, at, button, buttons, Qt.KeyboardModifier.NoModifier))


def click_text(browser: QTextBrowser, text: str) -> None:
    found = browser.document().find(text)
    cursor = QTextCursor(found)
    cursor.setPosition(found.selectionStart() + 1)
    point = QPointF(browser.cursorRect(cursor).center())
    left = Qt.MouseButton.LeftButton
    mouse(browser.viewport(), QEvent.Type.MouseButtonPress, point, left, left)
    mouse(browser.viewport(), QEvent.Type.MouseButtonRelease, point, left, Qt.MouseButton.NoButton)


def tip_at(widget: QWidget, point: QPointF) -> str:
    none = Qt.MouseButton.NoButton
    mouse(widget, QEvent.Type.MouseMove, point, none, none)
    return QToolTip.text()


class UrlCatcher(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.urls: list[str] = []

    @pyqtSlot(QUrl)
    def handle(self, url: QUrl) -> None:
        self.urls.append(url.toString())


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
        self.segmented.setCurrentIndex(0)
        self.assertEqual(self.seen, [])

    def test_a_click_slides_the_highlight_to_the_new_choice(self) -> None:
        self.segmented.show()
        pump(0.05)
        target = self.segmented._group.button(2)
        target.click()
        self.assertEqual(self.seen, ["anthropic"])
        pump(0.05)
        moving = self.segmented._pill
        self.assertIsNotNone(moving)
        self.assertLess(moving.x(), target.x())
        pump(controls.SLIDE_MS / 1000 + 0.2)
        self.assertIsNone(self.segmented._pill)
        self.segmented.hide()


class CompassMotionTest(unittest.TestCase):
    def test_search_swings_and_done_settles_north(self) -> None:
        mark = compass.Compass(18, QWidget().palette())
        mark.set_state(compass.SEARCH)
        seen = set()
        for _ in range(6):
            pump(0.1)
            seen.add(round(mark.angle))
        self.assertGreater(len(seen), 3)
        mark.set_state(compass.DONE)
        pump(compass.MOTIONS[compass.DONE].milliseconds / 1000 + 0.3)
        self.assertAlmostEqual(mark.angle, 0.0, places=1)
        mark.deleteLater()


class FoldMotionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.view = ConversationView()
        self.view.resize(560, 260)
        self.view.show()
        self.view.add_user_message("Which layers are in the project?", animate=False)
        thought = "The user asks which layers there are and what they hold. Let me inspect the project first."
        steps = [
            {"kind": "thought", "text": thought, "seconds": 0.4},
            {"kind": "call", "text": "Looking at the whole project", "parts": [], "skill": "inspect", "ok": True},
            {"kind": "call", "text": "Looking at the layers", "parts": [], "skill": "inspect", "ok": True},
        ]
        self.view.add_trace({"steps": steps, "seconds": 0.4})
        self.view.add_assistant_message("\n\n".join(["Two raster basemaps, no attribute data."] * 6))
        pump(0.2)
        self.feed = self.view.widget()
        self.group = self.feed.findChildren(ActivityGroup)[0]
        self.block = self.feed.findChildren(ThinkingBlock)[0]
        self.answer = self.feed.findChildren(AssistantMessage)[0]

    def tearDown(self) -> None:
        self.view.hide()
        self.view.deleteLater()

    def _top(self, widget: QWidget) -> int:
        return widget.mapTo(self.feed, QPoint(0, 0)).y()

    def _assert_laid_out(self) -> None:
        for clip in (self.block._clip, self.group._rows_holder):
            if clip.isVisible():
                self.assertEqual(clip.height(), min(clip.maximumHeight(), clip.natural_height()))
        if self.block._clip.isVisible():
            fitted = self.block.layout().contentsMargins().top() + self.block._line.height() + self.block._clip.height()
            self.assertEqual(self.block.height(), max(fitted, self.block.parentWidget().glyph.height()))
        below = self._top(self.group) + self.group.height() + self.view._column.spacing()
        self.assertEqual(self._top(self.answer), below)
        self.assertGreaterEqual(self.feed.height(), self.feed.heightForWidth(self.feed.width()))

    def _frames(self, fold) -> None:
        for value in (0.15, 0.4, 0.7, 1.0):
            fold._step(value)
            self._assert_laid_out()

    def test_the_reasoning_moves_the_trace_and_the_answer_in_the_same_frame(self) -> None:
        self.group._header.set_expanded(True)
        self.group.finish_folding()
        pump(0.1)
        title = self._top(self.block._line)
        self.block.set_expanded(True)
        self._frames(self.block._clip)
        self.assertEqual(self._top(self.block._line), title, "the title stays put while its box opens")
        self.block.finish_folding()
        self.block.set_expanded(False)
        self._frames(self.block._clip)
        self.block.finish_folding()

    def test_the_trace_moves_the_answer_in_the_same_frame(self) -> None:
        self.group._header.set_expanded(True)
        self._frames(self.group._rows_holder)
        self.group.finish_folding()
        self.group._header.set_expanded(False)
        self._frames(self.group._rows_holder)
        self.group.finish_folding()


class TraceSpacingTest(unittest.TestCase):
    def test_reasoning_alone_sits_as_close_above_the_answer_as_a_folded_trace(self) -> None:
        view = ConversationView()
        view.resize(560, 600)
        view.show()
        view.add_user_message("Which layers?", animate=False)
        step = {"kind": "call", "text": "Looking at the layers", "parts": [], "skill": "inspect", "ok": True}
        view.add_trace({"steps": [step], "seconds": 0.4})
        view.add_assistant_message("Two layers.")
        view.add_user_message("Thanks", animate=False)
        view.add_trace({"steps": [{"kind": "thought", "text": "Nothing to do.", "seconds": 0.3}], "seconds": 0.3})
        view.add_assistant_message("You are welcome.")
        pump(0.2)
        feed = view.widget()
        trace, reasoning = feed.findChildren(ActivityGroup)
        first, second = feed.findChildren(AssistantMessage)

        def gap(line: QWidget, answer: QWidget) -> float:
            return answer.mapTo(feed, QPoint(0, 0)).y() - line.mapTo(feed, QPoint(0, 0)).y() - line.height() / 2

        thought_line = reasoning.findChildren(ThinkingBlock)[0]._line
        self.assertLessEqual(abs(gap(thought_line, second) - gap(trace._header, first)), 3)
        view.hide()
        view.deleteLater()


class ErrorNoteTest(unittest.TestCase):
    def test_an_error_wears_the_danger_colour_and_a_note_does_not(self) -> None:
        view = ConversationView()
        view.add_system_message("Run stopped.")
        view.add_error_message("Error: The API returned 429: overloaded")
        note, error = view.widget().findChildren(SystemMessage)
        danger = style.css_color(style.danger(view.palette()))
        sheets = [message.findChild(QLabel).styleSheet() for message in (note, error)]
        self.assertNotIn(danger, sheets[0])
        self.assertIn(f"color: {danger}", sheets[1])
        view.deleteLater()


class NoteColumnTest(unittest.TestCase):
    def test_a_note_starts_in_the_reply_column(self) -> None:
        view = ConversationView()
        view.resize(560, 400)
        view.show()
        view.add_assistant_message("Two layers.")
        view.add_system_message("Run stopped.")
        pump(0.2)
        feed = view.widget()
        answer = feed.findChildren(AssistantMessage)[0]._browser
        label = feed.findChildren(SystemMessage)[0]._label
        text = label.mapTo(feed, label.contentsRect().topLeft())
        self.assertEqual(text.x(), answer.mapTo(feed, QPoint(0, 0)).x())
        view.hide()
        view.deleteLater()


class WideTableTest(unittest.TestCase):
    def setUp(self) -> None:
        self.view = ConversationView()
        self.view.resize(PANEL_WIDTH, 600)
        self.view.show()
        self.view.add_visual(WIDE_TABLE)
        pump(0.2)
        self.card = self.view.widget().findChildren(TableCard)[0]

    def tearDown(self) -> None:
        self.view.hide()
        self.view.deleteLater()

    def _bar(self) -> QScrollBar:
        bar = self.card.findChild(QScrollBar)
        self.assertIsNotNone(bar, "a table wider than the feed has no way to show its right columns")
        return bar

    def _wheel(self, dx: int, dy: int) -> QWheelEvent:
        at = QPointF(20, 40)
        return QWheelEvent(
            at,
            QPointF(self.card.mapToGlobal(at.toPoint())),
            QPoint(0, 0),
            QPoint(dx, dy),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )

    def test_the_last_column_can_be_brought_into_view(self) -> None:
        card = self.card
        self.assertGreater(sum(card.column_widths(card.width())), card.width() + 1, "the table must overflow")
        bar = self._bar()
        self.assertTrue(bar.isVisible())
        bar.setValue(bar.maximum())
        card.grab()
        boxes = [box for box, text in card._cells if text == LAST_CELL]
        self.assertTrue(boxes, "the last column's long cell was not drawn")
        self.assertGreaterEqual(boxes[0].left(), 0)
        self.assertLessEqual(boxes[0].right(), card.width() + 1, "the last column is still cut off")
        self.assertLessEqual(bar.geometry().bottom(), card.height())

    def test_only_a_sideways_wheel_moves_the_table(self) -> None:
        bar = self._bar()
        upright = self._wheel(0, -120)
        QApplication.sendEvent(self.card, upright)
        self.assertFalse(upright.isAccepted(), "an upright wheel belongs to the feed")
        self.assertEqual(bar.value(), 0)
        QApplication.sendEvent(self.card, self._wheel(-120, 0))
        self.assertGreater(bar.value(), 0, "a sideways wheel did not slide the table")

    def test_a_table_that_fits_shows_no_bar(self) -> None:
        self.view.resize(1400, 600)
        pump(0.2)
        bar = self._bar()
        self.assertFalse(bar.isVisible())
        rows = self.card._title_height() + self.card._row_height() * (len(self.card.rows) + 1)
        self.assertLessEqual(self.card.height(), rows + 2, "the card kept room for a bar it does not show")


class DropdownPlacementTest(unittest.TestCase):
    def test_the_menu_never_covers_its_field(self) -> None:
        box = Dropdown(QWidget().palette())
        for index in range(14):
            box.addItem(f"Item {index}", index)
        box.resize(300, 34)
        area = box.screen().availableGeometry()
        try:
            for y in (area.top() + 40, area.bottom() - 60):
                box.move(100, y)
                box.show()
                pump(0.05)
                top = box.mapToGlobal(QPoint(0, 0)).y()
                menu = box._menu_position(420)
                self.assertTrue(menu.y() >= top + box.height() or menu.y() + 420 <= top, (y, menu.y()))
        finally:
            box.hide()
            box.deleteLater()


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


class UsageNoticeTest(PluginCase):
    api_url = "http://localhost:11434/v1"
    model_name = "qwen3"

    def test_the_first_load_shows_the_notice_once_and_turn_off_says_no(self) -> None:
        from qgis.core import QgsSettings
        from qgis.gui import QgsMessageBar

        from ai_agent.core import usage_stats
        from ai_agent.ui.usage_notice import TURNED_OFF

        settings = QgsSettings()
        settings.remove(usage_stats.CONSENT_KEY)
        # The test profile opts out of usage statistics again afterwards, whatever this test leaves.
        self.addCleanup(settings.remove, usage_stats.NOTICE_KEY)
        self.addCleanup(usage_stats.set_consent, False)
        bar = QgsMessageBar(self.iface.window)
        self.iface.messageBar = lambda: bar
        with mock.patch.object(usage_stats, "COLLECTOR_URL", ""):
            self.plugin._notify_usage_stats()
        self.assertEqual(bar.items(), [], "no collector, no notice")
        self.plugin._notify_usage_stats()
        self.plugin._notify_usage_stats()
        self.assertEqual(len(bar.items()), 1, "the notice comes once")
        self.assertTrue(usage_stats.enabled(), "on by default once the user was told")
        notice = self.plugin._usage_notice
        notice.off.click()
        pump(0.05)
        self.assertEqual(usage_stats.consent(), usage_stats.CONSENT_NO)
        self.assertFalse(usage_stats.enabled())
        self.assertEqual(notice.item.text(), TURNED_OFF)
        self.assertTrue(notice.off.isHidden())


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
        tile = next(tile for tile in self.dialog.provider_tiles.tiles if tile.key == "LM Studio")
        tile.clicked.emit(tile.key)
        self.assertEqual(self.dialog.url_edit.text(), "http://localhost:1234/v1")
        self.assertEqual(self.dialog.preset_combo.currentText(), "LM Studio")
        self.assertTrue(self.dialog.save_btn.isEnabled())

    def test_typing_an_address_selects_its_tile(self) -> None:
        self.dialog.url_edit.setText("https://api.openai.com/v1")
        selected = [tile.key for tile in self.dialog.provider_tiles.tiles if tile.selected]
        self.assertEqual(selected, ["OpenAI"])

    def test_only_the_main_providers_get_a_tile_and_they_carry_logos(self) -> None:
        titles = [tile.key for tile in self.dialog.provider_tiles.tiles]
        self.assertEqual(len(titles), 7)
        self.assertNotIn("DeepSeek", titles)
        from ai_agent.ui import logos

        for title in titles[:-1]:
            self.assertIsNotNone(logos.pixmap(title, QColor(0, 0, 0), 16), title)

    def test_the_probe_result_lands_in_the_status_card(self) -> None:
        self.dialog._probe_started = 0.0
        self.dialog._on_probe_completed(False, "boom")
        self.assertEqual((self.dialog.status_card.state, self.dialog.status_card.detail.text()), ("bad", "boom"))

    def test_a_model_that_does_not_see_pictures_is_remembered_and_said(self) -> None:
        from ai_agent.core.settings import get_supports_images, reset_capabilities
        from ai_agent.ui import settings_probe

        scope = ("http://probe.invalid/v1", "text-only", "openai")
        self.addCleanup(reset_capabilities, *scope)
        self.dialog._probe_scope = scope
        self.dialog._probe_started = 0.0
        self.dialog._on_probe_completed(True, "Model replied: ok")
        self.dialog._on_images_checked(False)
        self.assertIs(get_supports_images(*scope), False)
        self.assertEqual(self.dialog.status_card.state, "ok")
        self.assertIn(settings_probe.TEXT_ONLY, self.dialog.status_card.detail.text())
        self.assertIn("Model replied: ok", self.dialog.status_card.detail.text())
        self.dialog._on_images_checked(True)
        self.assertIs(get_supports_images(*scope), True)

    def test_finding_a_setting_opens_its_page_at_the_row(self) -> None:
        from ai_agent.ui import settings_advanced

        self.dialog.search.field.setText(settings_advanced.TIMEOUT_LABEL)
        pump(0.05)
        results = [row for row in self.dialog.search._results.findChildren(controls.HoverFrame) if row.isVisible()]
        self.assertTrue(results, "the row is found by its title")
        results[0].clicked.emit()
        self.assertEqual(self.dialog.pages.currentIndex(), 4, "Advanced")
        self.dialog.search.field.clear()
        self.assertFalse(self.dialog._nav_buttons[0].isHidden(), "an empty box brings the page list back")

    def test_where_data_goes_follows_the_address(self) -> None:
        from ai_agent.ui import settings_advanced

        self.dialog.url_edit.setText("http://localhost:11434/v1")
        self.assertEqual(self.dialog.privacy_status.title.text(), settings_advanced.LOCAL_TITLE)
        self.dialog.url_edit.setText("https://api.openai.com/v1")
        self.assertEqual(self.dialog.privacy_status.title.text(), settings_advanced.REMOTE_TITLE)

    def test_a_skill_switched_off_marks_the_page_and_is_saved(self) -> None:
        from ai_agent.core.settings import get_disabled_skills, set_disabled_skills

        self.addCleanup(set_disabled_skills, [])
        self.dialog.skills.switches["charts"].setChecked(False)
        self.assertTrue(self.dialog.save_btn.isEnabled())
        self.dialog._save()
        self.assertEqual(get_disabled_skills(), ["charts"])

    def test_a_header_that_would_carry_a_key_is_refused_on_save(self) -> None:
        self.dialog.headers_edit.setPlainText("Authorization: Bearer sentinel")
        self.dialog._save()
        self.assertTrue(self.dialog.isVisible(), "nothing saved, the window stays")
        self.assertIn("1", self.dialog._status.text())

    def test_your_own_geocoder_takes_an_address_the_others_do_not(self) -> None:
        from ai_agent.core.settings import GEOCODER_NOMINATIM, GEOCODER_PHOTON

        geocoder = self.dialog.geocoder
        geocoder._choose(GEOCODER_PHOTON)
        self.assertFalse(geocoder.url_edit.isEnabled())
        geocoder._choose(GEOCODER_NOMINATIM)
        self.assertTrue(geocoder.url_edit.isEnabled())
        self.assertTrue(self.dialog.save_btn.isEnabled())

    def test_the_steppers_stay_in_their_range(self) -> None:
        from ai_agent.config import limits

        stepper = self.dialog.steps_stepper
        stepper.setValue(1000)
        self.assertEqual(stepper.value(), limits.MAX_STEPS)
        self.assertFalse(stepper.plus.isEnabled())
        self.assertTrue(self.dialog.save_btn.isEnabled())

    def test_no_page_shows_a_window_of_its_own(self) -> None:
        for index in range(self.dialog.pages.count()):
            self.dialog.show_page(index)
        self.dialog.search.field.setText("a")
        pump(0.05)
        self.assertEqual(self.window_spy.strays, [])

    def test_a_setting_on_a_page_not_yet_opened_is_found(self) -> None:
        from ai_agent.ui import personalisation_settings, settings_layout

        self.assertIn(settings_layout.PERSONALISATION, self.dialog._unbuilt_pages)
        self.dialog.search.field.setText(personalisation_settings.UNITS)
        pump(0.05)
        results = [row for row in self.dialog.search._results.findChildren(controls.HoverFrame) if row.isVisible()]
        shown = [label.text() for row in results for label in row.findChildren(QLabel)]
        self.assertIn("Personalisation", shown, "the page is built for the search")
        self.assertEqual(self.dialog._unbuilt_pages, {})

    def test_a_chosen_group_sits_under_the_chips(self) -> None:
        from ai_agent.ui import connectors_settings, settings_layout

        self.dialog._nav_buttons[settings_layout.CONNECTORS].click()
        connectors = self.dialog.connectors
        chips = connectors.chips[0][0].parentWidget()
        under_chips = chips.mapTo(connectors.list, QPoint(0, chips.height())).y()
        for _chip, key in connectors.chips[1:]:
            connectors._choose(key)
            pump(0.05)
            title = connectors_settings.CATEGORY_TITLES[key]
            caption = next(label for label in connectors.list.findChildren(QLabel) if label.text() == title)
            self.assertTrue(caption.isVisible(), key)
            top = caption.mapTo(connectors.list, QPoint(0, 0)).y()
            self.assertEqual(top - under_chips, connectors_settings.GROUP_GAP, key)


def close_during_a_slow_test(close: str) -> int:
    from qgis.PyQt.QtWidgets import QMainWindow, QMessageBox

    from ai_agent.core.llm import probe_worker
    from ai_agent.ui import settings_advanced

    def slow_probe(_overrides: dict) -> tuple[bool, str]:
        time.sleep(SLOW_TEST_S)
        return False, "too late"

    window = QMainWindow()
    dialog = SettingsDialog(window)
    dialog.url_edit.setText("http://localhost:11434/v1")
    dialog.model_edit.setText("qwen3")
    dialog.show()
    with mock.patch.object(probe_worker, "probe", slow_probe):
        dialog._test_connection()
        if close == "save":
            dialog.journal_cb.toggle()
            dialog._save()
        else:
            yes = QMessageBox.StandardButton.Yes
            with mock.patch.object(settings_advanced.QMessageBox, "question", return_value=yes):
                settings_advanced.reset_settings(dialog)
        deadline = time.monotonic() + CLOSE_WAIT_S
        while dialog.isVisible() and time.monotonic() < deadline:
            pump(0.05)
    closed = not dialog.isVisible()
    dialog.deleteLater()
    pump(0.1)
    return 0 if closed else 1


class ClosingDuringATestTest(unittest.TestCase):
    def _close_in_a_child(self, close: str) -> subprocess.CompletedProcess[str]:
        import ai_agent

        tests = pathlib.Path(__file__).resolve().parent
        package_parent = pathlib.Path(ai_agent.__file__).resolve().parent.parent
        paths = (os.fspath(tests), os.fspath(package_parent), os.environ.get("PYTHONPATH", ""))
        return subprocess.run(
            [sys.executable, "-c", CLOSE_CHILD, close],
            cwd=tests,
            env={**os.environ, "PYTHONPATH": os.pathsep.join(path for path in paths if path)},
            capture_output=True,
            text=True,
            timeout=CHILD_TIMEOUT_S,
        )

    def test_save_waits_for_the_test_to_stop(self) -> None:
        child = self._close_in_a_child("save")
        self.assertEqual(child.returncode, 0, child.stderr[-2000:])

    def test_reset_waits_for_the_test_to_stop(self) -> None:
        child = self._close_in_a_child("reset")
        self.assertEqual(child.returncode, 0, child.stderr[-2000:])


class ComposerBehaviourTest(PluginCase):
    api_url = "http://localhost:11434/v1"
    model_name = "qwen3"

    def test_a_menu_drops_in_and_settles_where_it_opened(self) -> None:
        toolbar = self.dock.composer.toolbar
        toolbar.mode.click()
        popup = toolbar.modes
        first = popup.pos()
        self.assertLess(popup.windowOpacity(), 0.5, "the menu is shown at once instead of fading in")
        pump(0.4)
        self.assertEqual(popup.windowOpacity(), 1.0)
        self.assertEqual(popup.pos().y() - first.y(), transitions.MENU_DROP, "the menu did not drop into place")
        popup.hide()
        self.assertEqual(popup.windowOpacity(), 1.0)

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

    def test_a_place_picked_on_the_map_lands_in_the_request(self) -> None:
        from qgis.core import QgsCoordinateReferenceSystem, QgsPointXY, QgsRectangle
        from qgis.gui import QgsMapCanvas, QgsMapToolPan

        canvas = QgsMapCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
        pan = QgsMapToolPan(canvas)
        canvas.setMapTool(pan)
        self.iface.mapCanvas = lambda: canvas
        composer = self.dock.composer
        composer._edit.setPlainText("buffer 500 m around")
        composer._edit.moveCursor(composer._edit.textCursor().MoveOperation.End)
        composer.toolbar.place_requested.emit("point")
        tool = canvas.mapTool()
        self.assertIsNot(tool, pan, "the map got no picking tool")
        self.assertFalse(composer.place_hint.isHidden())
        tool.canvasClicked.emit(QgsPointXY(4187799.6, 7509040.5), Qt.MouseButton.LeftButton)
        pump(0.05)
        self.assertRegex(composer._edit.toPlainText(), r"^buffer 500 m around @point\(37\.6\d{4}, 55\.75\d{3}\) $")
        self.assertTrue(composer.place_hint.isHidden())
        self.assertIs(canvas.mapTool(), pan, "the user's tool did not come back")
        composer.toolbar.place_requested.emit("area")
        canvas.mapTool().extentChanged.emit(QgsRectangle(4185000, 7505000, 4190000, 7512000))
        pump(0.05)
        self.assertIn("@area(37.59", composer._edit.toPlainText())
        composer.toolbar.place_requested.emit("point")
        escape = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
        composer._edit.keyPressEvent(escape)
        self.assertIs(canvas.mapTool(), pan, "Esc did not give the map its tool back")
        self.assertTrue(composer.place_hint.isHidden())

    def _type_at(self, text: str, before_end: int) -> None:
        edit = self.dock.composer._edit
        cursor = edit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.MoveAnchor, before_end)
        edit.setTextCursor(cursor)
        edit.insertPlainText(text)
        pump(0.05)

    def test_a_mention_after_astral_characters_replaces_only_itself(self) -> None:
        composer = self.dock.composer
        composer.set_layer_source(lambda: [("roads", "", "")])
        edit = composer._edit
        edit.setPlainText("🌍🌍  tail")
        self._type_at("@ro", len(" tail"))
        self.assertFalse(composer._popup.isHidden(), "the layer list did not open at the mention")
        composer._on_complete()
        self.assertEqual(edit.toPlainText(), "🌍🌍 @roads  tail")
        edit.insertPlainText("by type")
        self.assertEqual(edit.toPlainText(), "🌍🌍 @roads by type tail", "the caret did not land after the mention")
        composer.set_layer_source(lambda: [("𝄞 scores", "", "")])
        edit.setPlainText("𠀋 colour")
        self._type_at(" @𝄞", 0)
        self.assertFalse(composer._popup.isHidden())
        composer._on_complete()
        edit.insertPlainText("red")
        self.assertEqual(edit.toPlainText(), '𠀋 colour @"𝄞 scores" red')

    def test_words_put_at_the_caret_after_astral_characters_keep_their_space(self) -> None:
        composer = self.dock.composer
        edit = composer._edit
        edit.setPlainText("🌍a b")
        self._type_at("", len(" b"))
        composer.insert_place("@point(37.6, 55.7)")
        self.assertEqual(edit.toPlainText(), "🌍a @point(37.6, 55.7)  b")
        edit.setPlainText("𝄞a b")
        self._type_at("", len(" b"))
        composer.mention_layers(["rivers"])
        self.assertEqual(edit.toPlainText(), "𝄞a @rivers  b")
        edit.setPlainText("🌍a b")
        self._type_at("", len(" b"))
        composer._start_mention()
        self.assertEqual(edit.toPlainText(), "🌍a @ b")

    def test_tokens_after_astral_characters_are_lit_where_they_stand(self) -> None:
        edit = self.dock.composer._edit
        edit.setPlainText("/style 🌍 @𝄞roads x")
        pump(0.05)
        lit = {(span.start, span.length) for span in edit.document().firstBlock().layout().formats()}
        self.assertEqual(lit, {(0, 6), (10, 8)})

    def test_the_progress_line_follows_the_run(self) -> None:
        self.assertTrue(self.dock.progress.isHidden())
        self.dock.set_busy(True)
        self.dock.add_tool_message("Reading layer 'districts'")
        self.assertFalse(self.dock.progress.isHidden())
        self.assertEqual(self.dock.progress._step.text(), progress.WORKING)
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
            labels = [action.text().split("\t")[0] for action in toolbar.menu.actions() if action.text()]
            expected = ["Layer…", "File or table…", "Picture…", "Point on the map…", "Area on the map…", "Skill…"]
            self.assertEqual(labels, expected)
            self.assertLess(toolbar.menu.geometry().bottom(), toolbar.attach.mapToGlobal(QPoint(0, 0)).y())
        finally:
            toolbar.menu.hide()

    def test_the_box_starts_at_two_lines_and_grows_to_a_cap(self) -> None:
        edit = self.dock.composer._edit
        two_lines = edit.height()
        edit.setPlainText("first\nsecond\nthird")
        pump(0.05)
        self.assertGreater(edit.height(), two_lines)
        edit.setPlainText("line\n" * 30)
        pump(0.05)
        capped = edit.height()
        edit.setPlainText("line\n" * 60)
        pump(0.05)
        self.assertEqual(edit.height(), capped)
        self.assertEqual(edit.verticalScrollBarPolicy(), Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        edit.clear()
        pump(0.05)
        self.assertEqual(edit.height(), two_lines)

    def test_the_popup_never_grows_wider_than_the_composer(self) -> None:
        composer = self.dock.composer
        composer.set_skill_source(lambda: [("style", "x" * 400, "builtin")])
        composer._edit.setPlainText("/s")
        pump(0.1)
        self.assertEqual(composer._popup.width(), composer._frame.width())

    def test_a_caret_leaving_the_mention_closes_the_layer_list(self) -> None:
        composer = self.dock.composer
        composer.set_layer_source(lambda: [("roads", "", ""), ("rivers", "", "")])
        sent: list[str] = []
        composer.submitted.disconnect()
        composer.submitted.connect(sent.append)
        edit = composer._edit
        edit.setFocus()
        edit.insertPlainText("show me @ro")
        pump(0.05)
        self.assertTrue(edit.popup_open)
        edit.moveCursor(QTextCursor.MoveOperation.Start)
        self.assertFalse(edit.popup_open, "the list stayed open with the caret away from the mention")
        self.assertTrue(composer._popup.isHidden())
        edit.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier))
        self.assertEqual((edit.toPlainText(), sent), ("show me @ro", ["show me @ro"]))
        composer._insert_layer("roads")
        self.assertEqual(edit.toPlainText(), "show me @ro", "a choice away from the mention rewrote the text")

    def test_the_layer_list_says_when_no_layer_matches(self) -> None:
        composer = self.dock.composer
        composer.set_layer_source(lambda: [("roads", "", "")])
        composer._edit.insertPlainText("buffer @zz")
        pump(0.05)
        popup = composer._popup
        shown_texts = [label.text() for label in popup.findChildren(QLabel) if label.isVisibleTo(popup)]
        self.assertIn(skill_popup.NO_LAYER, shown_texts)
        self.assertNotIn(skill_popup.EMPTY, shown_texts)

    def test_a_connector_example_keeps_the_draft_for_undo(self) -> None:
        edit = self.dock.composer._edit
        edit.insertPlainText("my long draft")
        self.dock.put_prompt("Show the population of Paris")
        self.assertEqual(edit.toPlainText(), "Show the population of Paris")
        edit.undo()
        self.assertEqual(edit.toPlainText(), "my long draft")

    def test_typing_a_reply_holds_the_auto_answer(self) -> None:
        load = personal.load
        with mock.patch.object(personal, "load", lambda: dataclasses.replace(load(), auto_answer=1)):
            self.dock.add_question("Which layer should I buffer?", ["roads — the main network", "rivers"])
        card = self.dock.conversation.widget().findChildren(QuestionCard)[-1]
        answers: list[str] = []
        card.answered.connect(answers.append)
        self.dock.prompt_submitted.disconnect()
        self.dock.composer._edit.insertPlainText("neither, use the rail")
        pump(1.5)
        self.assertEqual(answers, [], "the card answered while the user typed a reply")
        self.assertTrue(card.countdown.isHidden())


class AnswerSafetyTest(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.mkdtemp(prefix="ai-agent-answer-")
        self.addCleanup(shutil.rmtree, folder, True)
        self.picture = os.path.join(folder, "red.png")
        image = QImage(40, 40, QImage.Format.Format_RGB32)
        image.fill(RED)
        image.save(self.picture)
        self.secret = os.path.join(folder, "secret.txt")
        pathlib.Path(self.secret).write_text("TOP-SECRET", encoding="utf-8")
        self.view = ConversationView()
        self.view.resize(560, 600)
        self.view.show()

    def tearDown(self) -> None:
        self.view.hide()
        self.view.deleteLater()

    def _answer(self, markdown: str) -> AssistantMessage:
        self.view.add_assistant_message(markdown)
        pump(0.1)
        return self.view.widget().findChildren(AssistantMessage)[-1]

    def test_an_answer_reads_no_file_it_names(self) -> None:
        for markdown in (f"![map]({self.picture})", f"![map](file://{self.picture})"):
            answer = self._answer(f"The map: {markdown}")
            self.assertEqual(red_pixels(answer), 0, f"{markdown} was read from disk")

    def test_a_link_opens_only_on_the_web(self) -> None:
        catcher = UrlCatcher()
        for scheme in ("https", "x-launch"):
            QDesktopServices.setUrlHandler(scheme, catcher, "handle")
            self.addCleanup(QDesktopServices.unsetUrlHandler, scheme)
        links = {
            "relative": "buffers.gpkg",
            "local": f"file://{self.secret}",
            "launcher": "x-launch://run?arg=1",
            "website": "https://example.org/a",
        }
        browser = self._answer(" ".join(f"[{name}]({target})" for name, target in links.items())).findChild(
            QTextBrowser
        )
        before = browser.toPlainText()
        for name in links:
            click_text(browser, name)
            pump(0.05)
            self.assertEqual(browser.toPlainText(), before, f"the {name} link replaced the answer")
        self.assertEqual(catcher.urls, [links["website"]])


class PlainTextTest(PluginCase):
    api_url = "http://localhost:11434/v1"
    model_name = "qwen3"

    def _assert_literal(self, root: QWidget) -> None:
        for widget in [root, *root.findChildren(QWidget)]:
            if isinstance(widget, QLabel) and "bold" in widget.text():
                drawn = shown(widget.text(), widget.textFormat())
                self.assertIn(PAYLOAD, drawn, f"{type(widget.parent()).__name__} draws {drawn!r}")
            if "bold" in widget.toolTip():
                self.assertIn(PAYLOAD, shown(widget.toolTip()), f"{type(widget).__name__} tip {widget.toolTip()!r}")

    def test_text_from_the_model_data_and_user_shows_as_written(self) -> None:
        dock = self.dock
        dock.set_project_line(PAYLOAD)
        self._assert_literal(dock)
        dock.set_conversation_title(PAYLOAD)
        dock.set_active_layer(PAYLOAD, PAYLOAD)
        dock.add_user_message(PAYLOAD)
        dock.add_tool_message(PAYLOAD)
        dock.add_system_message(PAYLOAD)
        dock.add_error_message(PAYLOAD)
        dock.add_plan_message([f"{PAYLOAD} · {PAYLOAD}"], layer=PAYLOAD)
        dock.add_visual({"type": "legend", "title": PAYLOAD, "items": [{"label": PAYLOAD, "color": "#ff0000"}]})
        dock.add_run_failure(PAYLOAD, PAYLOAD, f"{PAYLOAD}\n{PAYLOAD}", "connection", True, True)
        load = personal.load
        with mock.patch.object(personal, "load", lambda: dataclasses.replace(load(), auto_answer=30)):
            dock.add_question(PAYLOAD, [f"{PAYLOAD} — {PAYLOAD}", "second"])
        dock.set_busy(True)
        dock.show_outcome(STATUS_DONE, PAYLOAD)
        dock.composer.set_layer_source(lambda: [(PAYLOAD, PAYLOAD, "")])
        dock.composer._edit.insertPlainText("@")
        pump(0.1)
        self._assert_literal(dock)
        dock.set_session_source(lambda: [("one", PAYLOAD, time.time(), True)])
        dock._show_sessions()
        self._assert_literal(dock._sessions_popup)
        dock._sessions_popup.hide()
        status = StatusCard(dock.palette(), QWidget())
        status.show_state(STATE_BAD, PAYLOAD, PAYLOAD)
        self._assert_literal(status)
        status.deleteLater()

    def test_local_skills_show_as_written(self) -> None:
        from ai_agent.ui import skills_settings

        described = {
            "path": "",
            "skills": [{"name": PAYLOAD, "description": PAYLOAD, "tools": [PAYLOAD], "path": ""}],
            "drafts": [{"name": PAYLOAD, "path": ""}],
            "problems": [PAYLOAD],
        }
        with mock.patch.object(skills_settings, "describe_local_skills", return_value=described):
            page = skills_settings.SkillsSettings(self.dock.palette())
        self._assert_literal(page.widget)
        page.widget.deleteLater()

    def test_table_and_chart_tips_show_as_written(self) -> None:
        long_cell = f"{PAYLOAD} {'x' * 300}"
        self.dock.add_visual({"type": "table", "title": "t", "columns": ["name"], "rows": [[long_cell]], "total": 1})
        self.dock.add_visual(
            {
                "type": "chart",
                "kind": "bar",
                "title": "t",
                "labels": [PAYLOAD],
                "series": [{"name": "s", "values": [3]}],
            }
        )
        pump(0.3)
        feed = self.dock.conversation.widget()
        for card, hits in ((feed.findChildren(TableCard)[0], "_cells"), (feed.findChildren(ChartCard)[0], "_hits")):
            card.grab()
            box, text = getattr(card, hits)[0]
            self.assertIn(PAYLOAD, text)
            tip = tip_at(card, box.center())
            QToolTip.hideText()
            self.assertIn(PAYLOAD, shown(tip), f"{type(card).__name__} tip {tip!r}")


class CompactionStepTest(PluginCase):
    api_url = "http://localhost:11434/v1"
    model_name = "qwen3"

    def setUp(self) -> None:
        super().setUp()
        self.compaction = self.orchestrator.compaction
        self.compaction._compactor = mock.MagicMock()
        self.orchestrator.conversation.add("user", "Colour districts by pop2020")
        self.orchestrator.conversation.add("assistant", "Districts are coloured.")
        self.assertTrue(self.compaction.start())
        self.assertEqual(len(self._breathing()), 1)

    def _breathing(self) -> list[PulseRing]:
        rings = self.dock.conversation.widget().findChildren(PulseRing)
        return [ring for ring in rings if ring._breath.state() == QVariantAnimation.State.Running]

    def test_a_finished_compaction_settles_its_step(self) -> None:
        self.compaction._on_finished("The user coloured districts.", 10, 10)
        self.assertEqual(self._breathing(), [])

    def test_a_failed_compaction_settles_its_step(self) -> None:
        self.compaction._on_failed("HTTP 500")
        self.assertEqual(self._breathing(), [])

    def test_a_stopped_compaction_settles_its_step(self) -> None:
        self.orchestrator.on_stop()
        self.assertEqual(self._breathing(), [])

    def test_a_compaction_for_a_conversation_left_settles_its_step(self) -> None:
        self.orchestrator.conversation.start_new()
        self.compaction._on_finished("The user coloured districts.", 10, 10)
        self.assertEqual(self._breathing(), [])


class RestingTraceTest(unittest.TestCase):
    def test_a_trace_put_to_rest_stops_its_rings(self) -> None:
        view = ConversationView()
        view.add_activity_step("Reading layer 'districts'")
        view.add_system_message("Run stopped.")
        rings = view.widget().findChildren(PulseRing)
        self.assertEqual(len(rings), 1)
        self.assertNotEqual(rings[0]._breath.state(), QVariantAnimation.State.Running)
        view.deleteLater()


class PlanOfferTest(PluginCase):
    api_url = "http://localhost:11434/v1"
    model_name = "qwen3"

    def test_a_refused_run_leaves_the_offer_open(self) -> None:
        self.dock.add_user_message("plan a buffer of the roads")
        self.dock.add_result_message("1. Buffer roads by 50 m")
        self.dock.offer_plan()
        offer = self.dock.conversation.widget().findChildren(PlanOffer)[-1]
        self.orchestrator.compaction._running = True
        offer._rows[0].clicked.emit(offer._rows[0].key)
        self.orchestrator.compaction._running = False
        lines = [message.plain_text() for message in self.dock.conversation.widget().findChildren(SystemMessage)]
        self.assertIn(SWITCH_WHILE_RUNNING, lines)
        self.assertEqual(offer._question.text(), RUN_PLAN_QUESTION)
        self.assertFalse(any(row.isHidden() for row in offer._rows), "a refused offer can no longer be taken")


class PaintCounter(QObject):
    def __init__(self, watched: QWidget) -> None:
        super().__init__()
        self.paints = 0
        watched.installEventFilter(self)

    def eventFilter(self, _watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Paint:
            self.paints += 1
        return False


class LongFeedArrivalTest(unittest.TestCase):
    def test_opening_a_long_conversation_paints_only_what_shows(self) -> None:
        view = ConversationView()
        view.resize(PANEL_WIDTH, 600)
        view.show()
        for index in range(LONG_FEED):
            view.add_user_message(f"question {index}", animate=False)
            view.add_assistant_message(DISTRICT_LIST)
        pump(0.2)
        self.assertGreater(view.widget().height(), 5 * view.height())
        answers = view.widget().findChildren(AssistantMessage)
        far, near = PaintCounter(answers[0]._browser.viewport()), PaintCounter(answers[-1]._browser.viewport())
        view.play_entrance(view.viewport().grab())
        pump(transitions.LEAVE_MS / 1000 + (transitions.ARRIVE_MS + transitions.LAG_MS) / 1000 + 0.3)
        self.assertGreater(near.paints, 0, "the arrival drew nothing")
        self.assertEqual(far.paints, 0, "every frame rendered the whole feed, the first answer far above too")
        view.hide()
        view.deleteLater()
