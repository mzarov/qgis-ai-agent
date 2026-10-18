import pathlib
import re
import unittest
from types import SimpleNamespace
from unittest import mock

from qgis.PyQt.QtGui import QPalette
from qgis.PyQt.QtWidgets import QDialog

from ai_agent.config import geocoder as geocoder_config
from ai_agent.core import settings
from ai_agent.core.llm import (
    anthropic_stream,
    probe_worker,
    providers,
    transport,
)
from ai_agent.core.llm import (
    probe as settings_probe,
)
from ai_agent.core.llm.dialects import ANTHROPIC, OPENAI, resolve
from ai_agent.ui import settings_advanced
from ai_agent.ui.settings_dialog import SettingsDialog
from tests.test_credentials import MemorySettings


class PresetTest(unittest.TestCase):
    def test_first_preset_is_the_custom_one(self):
        self.assertTrue(providers.PRESETS[0].is_custom)

    def test_titles_are_unique(self):
        self.assertEqual(len(providers.TITLES), len(set(providers.TITLES)))

    def test_every_preset_has_a_model_hint(self):
        for preset in providers.PRESETS:
            self.assertTrue(preset.model_hint.strip(), preset.title)

    def test_every_concrete_preset_resets_to_a_usable_model(self):
        for preset in providers.PRESETS:
            if not preset.is_custom and preset.title != "LM Studio":
                self.assertTrue(preset.default_model.strip(), preset.title)

    def test_lm_studio_requires_the_server_model_identifier(self):
        self.assertEqual(providers.by_title("LM Studio").default_model, "")
        self.assertIn("LM Studio", providers.by_title("LM Studio").model_hint)

    def test_lookup_by_title(self):
        self.assertEqual(providers.by_title("Anthropic").dialect, ANTHROPIC)

    def test_unknown_title_falls_back_to_custom(self):
        self.assertTrue(providers.by_title("Мегамозг").is_custom)

    def test_url_is_matched_back_to_its_preset(self):
        self.assertEqual(providers.matching("https://openrouter.ai/api/v1").title, "OpenRouter")

    def test_trailing_slash_still_matches(self):
        self.assertEqual(providers.matching("https://openrouter.ai/api/v1/").title, "OpenRouter")

    def test_unknown_url_is_custom(self):
        self.assertTrue(providers.matching("https://шлюз.внутри/v1").is_custom)

    def test_empty_url_is_custom(self):
        self.assertTrue(providers.matching("").is_custom)

    def test_local_presets_need_no_key(self):
        for title in ("Ollama", "LM Studio"):
            self.assertFalse(providers.by_title(title).needs_key, title)

    def test_remote_presets_need_a_key(self):
        for title in ("OpenAI", "Anthropic", "OpenRouter", "Google Gemini"):
            self.assertTrue(providers.by_title(title).needs_key, title)

    def test_declared_dialect_matches_what_detection_would_pick(self):
        for preset in providers.PRESETS:
            if preset.is_custom:
                continue
            self.assertEqual(resolve(preset.url, preset.dialect), preset.dialect, preset.title)

    def test_anthropic_is_the_only_anthropic_preset(self):
        anthropic_titles = [p.title for p in providers.PRESETS if p.dialect == ANTHROPIC]
        self.assertEqual(anthropic_titles, ["Anthropic"])

    def test_everything_else_is_openai_shaped(self):
        for preset in providers.PRESETS:
            if preset.is_custom or preset.dialect == ANTHROPIC:
                continue
            self.assertEqual(preset.dialect, OPENAI, preset.title)


SOURCE = (pathlib.Path(__file__).resolve().parent.parent / "ai_agent" / "ui" / "settings_fields.py").read_text(
    encoding="utf-8"
)
DIALOG_SOURCE = (pathlib.Path(__file__).resolve().parent.parent / "ai_agent" / "ui" / "settings_dialog.py").read_text(
    encoding="utf-8"
)
PROBE_SOURCE = (pathlib.Path(__file__).resolve().parent.parent / "ai_agent" / "ui" / "settings_probe.py").read_text(
    encoding="utf-8"
)
CONTROLS_SOURCE = (pathlib.Path(__file__).resolve().parent.parent / "ai_agent" / "ui" / "controls.py").read_text(
    encoding="utf-8"
)
GEOCODER_SOURCE = (
    pathlib.Path(__file__).resolve().parent.parent / "ai_agent" / "ui" / "geocoder_settings.py"
).read_text(encoding="utf-8")


class StyleSheetTest(unittest.TestCase):
    def test_no_style_uses_a_bare_frame_selector(self):
        self.assertNotIn('f"QFrame {{', SOURCE)

    def test_inputs_get_their_own_border(self):
        self.assertIn("QLineEdit, QComboBox {", SOURCE)
        self.assertIn("setStyleSheet(input_style(palette))", SOURCE)

    def test_focus_is_visible_on_inputs(self):
        self.assertIn("QLineEdit:focus, QComboBox:focus", SOURCE)

    def test_inputs_sit_on_the_recessed_surface(self):
        self.assertIn("style.field(palette)", SOURCE)

    def test_borders_are_not_blanket_erased_on_containers(self):
        offenders = [line.strip() for line in SOURCE.split("\n") if "border: none" in line and "drop-down" not in line]
        self.assertEqual(offenders, [])


ADVANCED_SOURCE = (
    pathlib.Path(__file__).resolve().parent.parent / "ai_agent" / "ui" / "settings_advanced.py"
).read_text(encoding="utf-8")


LAYOUT_SOURCE = (pathlib.Path(__file__).resolve().parent.parent / "ai_agent" / "ui" / "settings_layout.py").read_text(
    encoding="utf-8"
)


class SidebarSettingsTest(unittest.TestCase):
    def test_the_window_is_a_sidebar_over_a_page_stack(self):
        self.assertIn("fields.sidebar()", LAYOUT_SOURCE)
        self.assertIn("fields.pages()", LAYOUT_SOURCE)
        for title in ('tr("Connection")', 'tr("Privacy")', 'tr("Skills")', 'tr("Geocoding")', 'tr("Advanced")'):
            self.assertIn(title, LAYOUT_SOURCE)

    def test_only_the_chosen_entry_stays_checked(self):
        body = LAYOUT_SOURCE.split("def show_page(")[1].split("\ndef ")[0]
        self.assertIn("setChecked(at == index)", body)

    def test_a_long_page_scrolls_instead_of_growing_the_window(self):
        self.assertIn("setWidgetResizable(True)", LAYOUT_SOURCE)
        self.assertIn("scrollable(page)", LAYOUT_SOURCE)

    def test_consent_controls_live_on_the_privacy_page(self):
        privacy = ADVANCED_SOURCE.split("def build_privacy(")[1].split("\ndef ")[0]
        for control in ("verify_ssl_cb", "journal_cb"):
            self.assertIn(control, privacy, control)
        self.assertNotIn("data_sharing_cb", privacy)

    def test_every_privacy_switch_spells_itself_out(self):
        privacy = ADVANCED_SOURCE.split("def build_privacy(")[1].split("\ndef ")[0]
        self.assertEqual(privacy.count("fields.switch_row("), privacy.count("fields.switch(palette)"))

    def test_long_explanations_wrap_instead_of_crossing_the_screen(self):
        body = SOURCE.split("def rich_tooltip(")[1].split("\ndef ")[0]
        self.assertIn("<qt>", body)

    def test_the_probe_button_lives_on_the_connection_page(self):
        connection = DIALOG_SOURCE.split("def _build_connection(")[1].split("\n    def ")[0]
        self.assertIn("self.test_btn", connection)
        buttons = DIALOG_SOURCE.split("def _build_buttons(")[1].split("\n    def ")[0]
        self.assertNotIn("test_btn", buttons)

    def test_switches_are_drawn_toggles_not_native_checkboxes(self):
        self.assertIn("class Switch(QCheckBox):", SOURCE)
        body = SOURCE.split("class Switch(")[1].split("\ndef ")[0]
        self.assertIn("drawRoundedRect", body)
        self.assertIn("style.accent(palette) if on", body)
        self.assertNotIn("QCheckBox(", ADVANCED_SOURCE)

    def test_the_run_journal_is_off_until_asked_for(self):
        from unittest import mock

        from ai_agent.core import settings

        with mock.patch.object(settings, "QgsSettings") as stored:
            stored.return_value.value.return_value = None
            self.assertFalse(settings.get_write_run_journal())
            stored.return_value.value.return_value = "true"
            self.assertTrue(settings.get_write_run_journal())

    def test_budgets_stay_out_of_the_privacy_page(self):
        privacy = ADVANCED_SOURCE.split("def build_privacy(")[1].split("\ndef ")[0]
        self.assertNotIn("budget_edit", privacy)
        self.assertNotIn("thinking_edit", privacy)

    def test_every_saved_control_is_still_built_somewhere(self):
        built = (DIALOG_SOURCE + ADVANCED_SOURCE + GEOCODER_SOURCE).replace("owner.", "self.")
        saved = (
            "dialect_combo",
            "auth_type_combo",
            "verify_ssl_cb",
            "verify_apply_cb",
            "journal_cb",
            "reasoning_cb",
            "budget_edit",
            "thinking_edit",
            "model_edit",
            "url_edit",
            "key_edit",
        )
        for name in saved:
            self.assertIn(f"self.{name} = ", built, name)

    def test_a_row_puts_the_control_opposite_its_label(self):
        body = SOURCE.split("def row(")[1].split("\ndef ")[0]
        self.assertIn("setFixedWidth(CONTROL_WIDTH)", body)
        grammar = SOURCE.split("def _row(")[1].split("\ndef ")[0]
        self.assertIn("Qt.AlignmentFlag.AlignRight", grammar)

    def test_every_row_shows_its_hint_under_the_title(self):
        grammar = SOURCE.split("def _row(")[1].split("\ndef ")[0]
        self.assertIn("holder.hint = hint(note, palette)", grammar)
        self.assertNotIn("def help_mark(", SOURCE)

    def test_hints_wrap_and_long_detail_stays_a_tooltip(self):
        self.assertIn("controls.small(", SOURCE.split("def hint(")[1])
        self.assertIn("label.setWordWrap(True)", CONTROLS_SOURCE.split("def small(")[1].split("\ndef ")[0])
        grammar = SOURCE.split("def _row(")[1].split("\ndef ")[0]
        self.assertIn("caption.setToolTip(rich_tooltip(tooltip))", grammar)

    def test_pages_are_sections_of_flat_rows_like_claude_code(self):
        for source in (DIALOG_SOURCE, ADVANCED_SOURCE, GEOCODER_SOURCE):
            self.assertIn("fields.section(", source)
        rows = SOURCE.split("def card_rows(")[1].split("\ndef ")[0]
        self.assertNotIn("QFrame", rows)

    def test_the_sidebar_groups_its_entries(self):
        self.assertIn("GROUPS = ", LAYOUT_SOURCE)

    def test_save_waits_for_an_edit(self):
        self.assertIn("self.save_btn.setEnabled(False)", DIALOG_SOURCE)
        dirty = DIALOG_SOURCE.split("def _mark_dirty(")[1].split("\n    def ")[0]
        self.assertIn("self.save_btn.setEnabled(True)", dirty)
        self.assertIn("if self._loading_endpoint:", dirty)

    def test_the_preset_combo_stays_the_source_of_truth_for_the_tiles(self):
        connection = DIALOG_SOURCE.split("def _build_connection(")[1].split("\n    def ")[0]
        self.assertIn("self.provider_tiles.chosen.connect(self.preset_combo.setCurrentText)", connection)
        self.assertIn("self.preset_combo.currentTextChanged.connect(self.provider_tiles.select)", connection)

    def test_separators_go_between_rows_never_after_the_last(self):
        body = SOURCE.split("def add_rows(")[1].split("\ndef ")[0]
        self.assertIn("if index:", body)
        self.assertIn("separator(palette)", body)

    def test_the_sidebar_shows_which_pages_hold_unsaved_edits(self):
        self.assertIn("def mark_page(", LAYOUT_SOURCE)

    def test_sidebar_and_pages_share_one_surface_split_by_a_line(self):
        self.assertIn("fields.vertical_separator(palette)", LAYOUT_SOURCE)
        self.assertNotIn("fields.pane(", LAYOUT_SOURCE)

    def test_the_sidebar_carries_no_heading_of_its_own(self):
        self.assertNotIn("nav_heading", LAYOUT_SOURCE)

    def test_pages_show_through_the_pane_not_their_own_grey(self):
        body = LAYOUT_SOURCE.split("def scrollable(")[1].split("\ndef ")[0]
        self.assertIn("setAutoFillBackground(False)", body)
        self.assertIn("background: transparent", body)


class CredentialUiContractTest(unittest.TestCase):
    def test_switching_provider_resets_the_model(self):
        self.assertIn("self.model_edit.setText(preset.default_model)", DIALOG_SOURCE)

    def test_switching_provider_drops_a_custom_oauth_mode(self):
        self.assertIn("fields.select(self.auth_type_combo, AUTH_TYPE_BEARER)", DIALOG_SOURCE)

    def test_key_lookup_and_save_use_the_edited_endpoint(self):
        self.assertIn("get_api_key(url, dialect)", DIALOG_SOURCE)
        self.assertIn("set_api_key(key, url, dialect)", DIALOG_SOURCE)

    def test_stored_key_has_an_explicit_remove_action(self):
        self.assertIn('tr("Remove key")', DIALOG_SOURCE)
        self.assertIn("delete_api_key(url, dialect)", DIALOG_SOURCE)

    def test_connection_probe_runs_outside_the_ui_thread_and_can_be_cancelled(self):
        self.assertIn("ProbeThread(overrides, self)", PROBE_SOURCE)
        self.assertIn("thread.start()", PROBE_SOURCE)
        self.assertIn("thread.cancel()", PROBE_SOURCE)
        self.assertNotIn("probe(self._overrides())", PROBE_SOURCE + DIALOG_SOURCE)

    def test_geocoder_is_selected_in_settings_not_by_the_model(self):
        self.assertIn('(GEOCODER_PHOTON, "Photon"', GEOCODER_SOURCE)
        self.assertIn("(GEOCODER_NOMINATIM, tr(", GEOCODER_SOURCE)
        self.assertIn("validated_service_url", GEOCODER_SOURCE)
        self.assertIn("self.geocoder.values()", DIALOG_SOURCE)


class ThemeTest(unittest.TestCase):
    STYLE = (pathlib.Path(__file__).resolve().parent.parent / "ai_agent" / "ui" / "style.py").read_text(
        encoding="utf-8"
    )

    def test_only_the_theme_spells_a_colour(self):
        ui = pathlib.Path(__file__).resolve().parent.parent / "ai_agent" / "ui"
        offenders = [
            path.name
            for path in ui.glob("*.py")
            if path.name != "theme.py" and re.search(r"#[0-9a-fA-F]{6}\b|QColor\(\s*\d", path.read_text("utf-8"))
        ]
        self.assertEqual(offenders, [])

    def test_the_palette_only_chooses_light_or_dark(self):
        self.assertIn("theme.tokens(palette)", self.STYLE)


def _constant(source, name):
    for line in source.split("\n"):
        if line.startswith(name + " ="):
            return float(line.split("=")[1])
    raise AssertionError(f"нет константы {name}")


class ProbeTest(unittest.TestCase):
    def _with_call_model(self, fake):
        saved = transport.call_model
        transport.call_model = fake
        self.addCleanup(lambda: setattr(transport, "call_model", saved))

    def test_successful_reply_is_reported(self):
        self._with_call_model(lambda *args, **kwargs: transport.ModelTurn(text="ок"))
        ok, message = settings_probe.probe({})
        self.assertTrue(ok)
        self.assertIn("ок", message)

    def test_empty_reply_counts_as_failure(self):
        self._with_call_model(lambda *args, **kwargs: transport.ModelTurn(text="   "))
        ok, message = settings_probe.probe({})
        self.assertFalse(ok)
        self.assertIn("empty answer", message)

    def test_error_is_reported_not_raised(self):
        def broken(*args, **kwargs):
            raise ValueError("Не задан API-ключ")

        self._with_call_model(broken)
        ok, message = settings_probe.probe({})
        self.assertFalse(ok)
        self.assertIn("API", message)

    def test_silent_exception_still_names_something(self):
        def broken(*args, **kwargs):
            raise TimeoutError()

        self._with_call_model(broken)
        ok, message = settings_probe.probe({})
        self.assertFalse(ok)
        self.assertTrue(message.strip())

    def test_long_reply_is_shortened(self):
        self._with_call_model(lambda *args, **kwargs: transport.ModelTurn(text="о" * 500))
        _, message = settings_probe.probe({})
        self.assertLess(len(message), 200)
        self.assertTrue(message.endswith("…"))

    def test_newlines_are_flattened(self):
        self._with_call_model(lambda *args, **kwargs: transport.ModelTurn(text="первая\n\nвторая"))
        _, message = settings_probe.probe({})
        self.assertNotIn("\n", message)

    def test_overrides_reach_the_client(self):
        seen = {}

        def spy(messages, schemas, overrides=None, timeout=0):
            seen.update(overrides or {})
            seen["schemas"] = schemas
            seen["timeout"] = timeout
            return transport.ModelTurn(text="ок")

        self._with_call_model(spy)
        settings_probe.probe({"url_override": "http://localhost:11434/v1", "key_override": None})
        self.assertEqual(seen["url_override"], "http://localhost:11434/v1")
        self.assertEqual(seen["schemas"], [])
        self.assertEqual(seen["timeout"] * settings_probe.BLOCKING_TIMEOUT_FACTOR, settings_probe.PROBE_SECONDS)

    def test_anthropic_probe_builds_and_parses_anthropic_messages(self):
        seen = {}
        saved = anthropic_stream.post_json

        def fake_post(endpoint, headers, body, timeout, verify_override, feedback):
            seen.update(endpoint=endpoint, headers=headers, body=body, timeout=timeout)
            return {
                "content": [{"type": "text", "text": "ok"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 4, "output_tokens": 1},
            }

        anthropic_stream.post_json = fake_post
        self.addCleanup(lambda: setattr(anthropic_stream, "post_json", saved))
        ok, message = settings_probe.probe(
            {
                "url_override": "https://api.anthropic.com/v1",
                "key_override": "test-key",
                "model_override": "claude-sonnet-5",
                "dialect_override": "anthropic",
                "verify_override": True,
            }
        )

        self.assertTrue(ok, message)
        self.assertIn("ok", message)
        self.assertEqual(seen["endpoint"], "https://api.anthropic.com/v1/messages")
        self.assertEqual(seen["headers"]["x-api-key"], "test-key")
        self.assertEqual(seen["body"]["model"], "claude-sonnet-5")
        self.assertEqual(seen["body"]["messages"], [{"role": "user", "content": settings_probe.PROBE_PROMPT}])
        self.assertIn("max_tokens", seen["body"])
        self.assertEqual(seen["timeout"], 60)


class ImageProbeTest(unittest.TestCase):
    """Whether the model sees a picture: an endpoint can take one and drop it before the model."""

    def _replying(self, text, seen=None):
        def fake(messages, schemas, overrides=None, timeout=0):
            if seen is not None:
                seen.extend(messages)
            return transport.ModelTurn(text=text)

        saved = transport.call_model
        transport.call_model = fake
        self.addCleanup(lambda: setattr(transport, "call_model", saved))

    def test_naming_both_colours_means_it_sees(self):
        seen = []
        self._replying("Green, yellow.", seen)
        self.assertTrue(settings_probe.sees_images({}))
        blocks = seen[0]["content"]
        self.assertEqual([block["type"] for block in blocks], ["text", "image_url"])
        self.assertTrue(blocks[1]["image_url"]["url"].startswith("data:image/png;base64,"))

    def test_a_model_without_the_picture_does_not(self):
        for reply in ("I can't see any image.", "Red and blue", "green"):
            with self.subTest(reply):
                self._replying(reply)
                self.assertFalse(settings_probe.sees_images({}))

    def test_a_failed_request_tells_nothing(self):
        def broken(*args, **kwargs):
            raise TimeoutError()

        saved = transport.call_model
        transport.call_model = broken
        self.addCleanup(lambda: setattr(transport, "call_model", saved))
        self.assertIsNone(settings_probe.sees_images({}))

    def test_the_picture_is_a_real_png_with_its_two_halves(self):
        import struct
        import zlib

        data = settings_probe.two_halves_png((4, 2), (0, 160, 0), (255, 255, 0))
        self.assertTrue(data.startswith(settings_probe.PNG_SIGNATURE))
        width, height = struct.unpack(">II", data[16:24])
        self.assertEqual((width, height), (4, 2))
        start = data.index(b"IDAT") + 4
        length = struct.unpack(">I", data[start - 8 : start - 4])[0]
        rows = zlib.decompress(data[start : start + length])
        self.assertEqual(rows[:13], b"\x00" + bytes((0, 160, 0)) * 2 + bytes((255, 255, 0)) * 2)


class ProbeWorkerTest(unittest.TestCase):
    def setUp(self):
        self.saved_probe = probe_worker.probe
        self.addCleanup(lambda: setattr(probe_worker, "probe", self.saved_probe))
        for name in ("detect", "sees_images"):
            saved = getattr(probe_worker, name)
            self.addCleanup(setattr, probe_worker, name, saved)
        probe_worker.detect = lambda overrides: 0
        probe_worker.sees_images = lambda overrides: None

    def test_feedback_reaches_the_probe_and_the_result_is_emitted(self):
        seen = {}
        probe_worker.probe = lambda overrides: (seen.update(overrides) or True, "ok")
        completed = []
        worker = probe_worker.ProbeThread({"model_override": "model"})
        worker.completed.connect(lambda ok, message: completed.append((ok, message)))
        worker.run()
        self.assertIn("feedback_override", seen)
        self.assertEqual(completed, [(True, "ok")])

    def test_a_connected_model_is_asked_about_a_picture(self):
        probe_worker.probe = lambda overrides: (True, "ok")
        probe_worker.sees_images = lambda overrides: False
        checked = []
        worker = probe_worker.ProbeThread({})
        worker.images_checked.connect(checked.append)
        worker.run()
        self.assertEqual(checked, [False])

    def test_no_answer_about_the_picture_changes_nothing(self):
        probe_worker.probe = lambda overrides: (True, "ok")
        checked = []
        worker = probe_worker.ProbeThread({})
        worker.images_checked.connect(checked.append)
        worker.run()
        self.assertEqual(checked, [], "a failed picture request keeps what was known")

    def test_a_failed_connection_asks_nothing_more(self):
        probe_worker.probe = lambda overrides: (False, "refused")
        probe_worker.sees_images = lambda overrides: self.fail("asked about a picture after a failure")
        worker = probe_worker.ProbeThread({})
        worker.run()

    def test_cancelled_probe_does_not_update_the_dialog(self):
        probe_worker.probe = lambda overrides: (True, "late")
        completed = []
        worker = probe_worker.ProbeThread({})
        worker.completed.connect(lambda ok, message: completed.append((ok, message)))
        worker.cancel()
        worker.run()
        self.assertEqual(completed, [])


class RunningProbe:
    """A connection test still on its way: it runs until the test says it stopped."""

    def __init__(self):
        self.running = True
        self.cancelled = False

    def isRunning(self):
        return self.running

    def cancel(self):
        self.cancelled = True

    def wait(self, _milliseconds):
        return not self.running

    def deleteLater(self):
        pass


class ClosingDialog(SettingsDialog):
    """The settings window, remembering the result it closed with."""

    closed_with = None

    def done(self, result):
        self.closed_with = result


class ClosingDuringAProbeTest(unittest.TestCase):
    """Every way out of the window waits for a running connection test: its thread dies with the window."""

    def setUp(self):
        MemorySettings.values = {}
        for module in (settings, geocoder_config):
            patcher = mock.patch.object(module, "QgsSettings", MemorySettings)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.dialog = ClosingDialog()
        self.probe = RunningProbe()
        self.dialog._probe_thread = self.probe

    def _probe_stops(self):
        self.probe.running = False
        self.dialog._on_probe_finished(self.probe)

    def test_save_stores_at_once_and_closes_once_the_probe_stopped(self):
        self.dialog.model_edit.setText("saved-model")
        self.dialog._save()
        self.assertEqual(settings.get_model(), "saved-model")
        self.assertTrue(self.probe.cancelled)
        self.assertIsNone(self.dialog.closed_with, "the window outlived the probe's thread")
        self._probe_stops()
        self.assertEqual(self.dialog.closed_with, QDialog.DialogCode.Accepted)

    def test_reset_closes_once_the_probe_stopped(self):
        yes = settings_advanced.QMessageBox.StandardButton.Yes
        with (
            mock.patch.object(settings_advanced.QMessageBox, "question", return_value=yes),
            mock.patch.object(settings_advanced, "reset_preferences"),
        ):
            settings_advanced.reset_settings(self.dialog)
        self.assertTrue(self.probe.cancelled)
        self.assertIsNone(self.dialog.closed_with, "the window outlived the probe's thread")
        self._probe_stops()
        self.assertEqual(self.dialog.closed_with, QDialog.DialogCode.Accepted)

    def test_cancel_closes_once_the_probe_stopped(self):
        self.dialog.reject()
        self.assertTrue(self.probe.cancelled)
        self.assertIsNone(self.dialog.closed_with)
        self._probe_stops()
        self.assertEqual(self.dialog.closed_with, QDialog.DialogCode.Rejected)

    def test_a_cancel_while_a_save_waits_still_reports_it_saved(self):
        self.dialog._save()
        self.dialog.reject()
        self._probe_stops()
        self.assertEqual(self.dialog.closed_with, QDialog.DialogCode.Accepted)

    def test_with_no_probe_running_save_closes_at_once(self):
        self.dialog._probe_thread = None
        self.dialog._save()
        self.assertEqual(self.dialog.closed_with, QDialog.DialogCode.Accepted)


class ReasoningSwitchTest(unittest.TestCase):
    """The switch built, toggled and saved through the real dialog, on in-memory settings."""

    def setUp(self):
        MemorySettings.values = {}
        for module in (settings, geocoder_config):
            patcher = mock.patch.object(module, "QgsSettings", MemorySettings)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_reasoning_is_off_until_asked_for(self):
        self.assertFalse(settings.get_reasoning_enabled())
        self.assertFalse(SettingsDialog().reasoning_cb.isChecked())

    def test_the_page_shows_the_stored_choice(self):
        settings.set_reasoning_enabled(True)
        owner = SimpleNamespace(_endpoint_finished=lambda *args: None)
        settings_advanced.build_advanced(owner, QPalette())
        self.assertTrue(owner.reasoning_cb.isChecked())

    def test_toggling_the_switch_and_saving_stores_it(self):
        dialog = SettingsDialog()
        dialog.reasoning_cb.setChecked(True)
        dialog._save()
        self.assertTrue(settings.get_reasoning_enabled())
        dialog = SettingsDialog()
        dialog.reasoning_cb.setChecked(False)
        dialog._save()
        self.assertFalse(settings.get_reasoning_enabled())

    def test_switching_on_forgets_a_remembered_refusal(self):
        url, model = settings.DEFAULT_API_URL, settings.DEFAULT_MODEL
        settings.set_supports_thinking(url, False, model, "openai")
        dialog = SettingsDialog()
        dialog.reasoning_cb.setChecked(True)
        dialog._save()
        self.assertIsNone(settings.get_supports_thinking(url, model, "openai"))

    def test_saving_while_already_on_keeps_the_refusal(self):
        url, model = settings.DEFAULT_API_URL, settings.DEFAULT_MODEL
        settings.set_reasoning_enabled(True)
        settings.set_supports_thinking(url, False, model, "openai")
        settings.set_reasoning_enabled(True, url, model, "openai")
        self.assertIs(settings.get_supports_thinking(url, model, "openai"), False)


if __name__ == "__main__":
    unittest.main()
