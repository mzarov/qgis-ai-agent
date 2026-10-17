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
from qgis.PyQt.QtWidgets import QLabel, QLineEdit, QWidget

from ai_agent.ui import compass, controls, progress, settings_fields, style
from ai_agent.ui.activity import ActivityGroup
from ai_agent.ui.composer_parts import LAYER_TOKEN, SKILL_TOKEN
from ai_agent.ui.conversation import ConversationView
from ai_agent.ui.dropdown import Dropdown
from ai_agent.ui.messages import AssistantMessage, SystemMessage
from ai_agent.ui.settings_dialog import SettingsDialog
from ai_agent.ui.thinking import ThinkingBlock


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
    """The live mark really turns: a looping state keeps moving, a one-shot state settles."""

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
    """Every frame of a fold leaves the whole feed laid out. Qt passes a size change up one parent per
    round of posted events; a frame painted between rounds showed the reasoning grown inside a trace
    that had not, and the motion stalled, then jumped."""

    def setUp(self) -> None:
        self.view = ConversationView()
        # Shorter than the feed: the scroll area has to follow each frame as well.
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
            # No slack under the box: the block shrank or grew with it, and so did every row below.
            fitted = self.block.layout().contentsMargins().top() + self.block._line.height() + self.block._clip.height()
            self.assertEqual(self.block.height(), max(fitted, self.block.parentWidget().glyph.height()))
        below = self._top(self.group) + self.group.height() + self.view._column.spacing()
        self.assertEqual(self._top(self.answer), below)
        self.assertGreaterEqual(self.feed.height(), self.feed.heightForWidth(self.feed.width()))

    def _frames(self, fold) -> None:
        # One frame at a time and no event processing in between: what a paint at that moment shows.
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
            # From the middle of the line the eye reads to the answer: the two lines differ in height.
            return answer.mapTo(feed, QPoint(0, 0)).y() - line.mapTo(feed, QPoint(0, 0)).y() - line.height() / 2

        # The reasoning title sits at the top of its glyph's box like every step's text, the header's is
        # centred in it: a pixel or two apart, never a row gap.
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
        # A style sheet's lone border-left once reserved its width and padding but never painted (Qt takes
        # the whole border's style from the top edge), so the note sat 11 px in beside nothing.
        text = label.mapTo(feed, label.contentsRect().topLeft())
        self.assertEqual(text.x(), answer.mapTo(feed, QPoint(0, 0)).x())
        view.hide()
        view.deleteLater()


class DropdownPlacementTest(unittest.TestCase):
    """Near the bottom of the screen the menu opens above the field instead of sliding over it."""

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


class UsageStatsOfferTest(PluginCase):
    """The one-time card after an answer: only with a collector, once a session; the choice is stored."""

    api_url = "http://localhost:11434/v1"
    model_name = "qwen3"

    def test_the_card_asks_once_and_stores_the_choice(self) -> None:
        from unittest import mock

        from qgis.core import QgsSettings

        from ai_agent.core import usage_stats
        from ai_agent.ui.usage_card import UsageCard

        QgsSettings().remove(usage_stats.CONSENT_KEY)
        self.addCleanup(QgsSettings().remove, usage_stats.CONSENT_KEY)
        self.orchestrator._offer_usage_stats()
        self.assertEqual(self.dock.conversation.findChildren(UsageCard), [], "no collector, no question")
        with mock.patch.object(usage_stats, "COLLECTOR_URL", "https://stats.example"):
            self.orchestrator._offer_usage_stats()
            self.orchestrator._offer_usage_stats()
            cards = self.dock.conversation.findChildren(UsageCard)
            self.assertEqual(len(cards), 1, "asked twice in one session")
            cards[0].share.click()
            pump(0.05)
            self.assertEqual(usage_stats.consent(), usage_stats.CONSENT_YES)
            self.assertTrue(cards[0]._actions.isHidden())


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
        # Thirty hint labels were once shown before their rows took them: each became a window,
        # and making those windows was most of the second the settings took to open.
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

        # The groups above a chosen one once left their air behind: a band of empty page under the chips.
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


class ComposerBehaviourTest(PluginCase):
    api_url = "http://localhost:11434/v1"
    model_name = "qwen3"

    def test_a_menu_drops_in_and_settles_where_it_opened(self) -> None:
        from ai_agent.ui import transitions

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
        """+ → Point on the map: the canvas takes a one-pick tool, the click becomes @point(lon, lat) in the box."""
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
        # Red Square in Web Mercator.
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

    def test_the_progress_line_follows_the_run(self) -> None:
        self.assertTrue(self.dock.progress.isHidden())
        self.dock.set_busy(True)
        self.dock.add_tool_message("Reading layer 'districts'")
        self.assertFalse(self.dock.progress.isHidden())
        # The open list names the call; the line below only says the agent is still at work.
        self.assertEqual(self.dock.progress.step_text, progress.WORKING)
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
            # A caption, then Layer…, File or table…, Picture…, the two places on the map, a separator and Skill….
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
