import pathlib
import unittest

from qgis_ai_agent.core.llm import (
    anthropic_stream,
    probe_worker,
    providers,
    transport,
)
from qgis_ai_agent.core.llm import (
    probe as settings_probe,
)
from qgis_ai_agent.core.llm.dialects import ANTHROPIC, OPENAI, resolve


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
        self.assertEqual(providers.matching("https://api.deepseek.com/v1/").title, "DeepSeek")

    def test_unknown_url_is_custom(self):
        self.assertTrue(providers.matching("https://шлюз.внутри/v1").is_custom)

    def test_empty_url_is_custom(self):
        self.assertTrue(providers.matching("").is_custom)

    def test_local_presets_need_no_key(self):
        for title in ("Ollama", "LM Studio"):
            self.assertFalse(providers.by_title(title).needs_key, title)

    def test_remote_presets_need_a_key(self):
        for title in ("OpenAI", "Anthropic", "OpenRouter", "DeepSeek"):
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


SOURCE = (pathlib.Path(__file__).resolve().parent.parent / "qgis_ai_agent" / "ui" / "settings_fields.py").read_text(
    encoding="utf-8"
)
DIALOG_SOURCE = (
    pathlib.Path(__file__).resolve().parent.parent / "qgis_ai_agent" / "ui" / "settings_dialog.py"
).read_text(encoding="utf-8")


class StyleSheetTest(unittest.TestCase):
    def test_card_style_is_scoped_by_object_name(self):
        self.assertIn("QFrame#{CARD_NAME}", SOURCE)
        self.assertIn("setObjectName(CARD_NAME)", SOURCE)

    def test_card_never_uses_a_bare_type_selector(self):
        self.assertNotIn('f"QFrame {{', SOURCE)

    def test_inputs_get_their_own_border(self):
        self.assertIn("QLineEdit, QComboBox {", SOURCE)
        self.assertIn("setStyleSheet(input_style(palette))", SOURCE)

    def test_focus_is_visible_on_inputs(self):
        self.assertIn("QLineEdit:focus, QComboBox:focus", SOURCE)

    def test_card_lifts_instead_of_sinking(self):
        body = SOURCE.split("def card(")[1].split("\ndef ")[0]
        self.assertIn("style.panel(palette)", body)
        self.assertNotIn("style.card(palette)", body)

    def test_inputs_sit_on_the_recessed_surface(self):
        self.assertIn("style.surface(palette)", SOURCE)

    def test_borders_are_not_blanket_erased_on_containers(self):
        offenders = [line.strip() for line in SOURCE.split("\n") if "border: none" in line and "drop-down" not in line]
        self.assertEqual(offenders, [])


class CredentialUiContractTest(unittest.TestCase):
    def test_switching_provider_resets_the_model(self):
        self.assertIn("self.model_edit.setText(preset.default_model)", DIALOG_SOURCE)

    def test_switching_provider_drops_a_custom_oauth_mode(self):
        self.assertIn("fields.select(self.auth_type_combo, AUTH_TYPE_BEARER)", DIALOG_SOURCE)

    def test_key_lookup_and_save_use_the_edited_endpoint(self):
        self.assertIn("get_api_key(url, dialect)", DIALOG_SOURCE)
        self.assertIn("set_api_key(key, url, dialect)", DIALOG_SOURCE)

    def test_stored_key_has_an_explicit_remove_action(self):
        self.assertIn('tr("Remove stored key")', DIALOG_SOURCE)
        self.assertIn("delete_api_key(url, dialect)", DIALOG_SOURCE)

    def test_sensitive_data_copy_names_every_sensitive_category(self):
        self.assertIn("Feature attribute values", DIALOG_SOURCE)
        self.assertIn("exact map and layer extents", DIALOG_SOURCE)
        self.assertIn("layer filters and sources", DIALOG_SOURCE)
        self.assertIn("Processing and Python results", DIALOG_SOURCE)
        self.assertIn("rendered map or layout images", DIALOG_SOURCE)

    def test_consent_is_loaded_and_saved_for_the_edited_endpoint(self):
        self.assertIn("get_data_sharing_consent(url)", DIALOG_SOURCE)
        self.assertIn("set_data_sharing_consent(self.data_sharing_cb.isChecked(), url)", DIALOG_SOURCE)

    def test_connection_probe_runs_outside_the_ui_thread_and_can_be_cancelled(self):
        self.assertIn("ProbeThread(self._overrides(), self)", DIALOG_SOURCE)
        self.assertIn("thread.start()", DIALOG_SOURCE)
        self.assertIn("thread.cancel()", DIALOG_SOURCE)
        self.assertNotIn("probe(self._overrides())", DIALOG_SOURCE)

    def test_closing_waits_for_a_running_probe_to_finish(self):
        reject_body = DIALOG_SOURCE.split("def reject(self)")[1].split("\n    def ")[0]
        finished_body = DIALOG_SOURCE.split("def _on_probe_finished")[1].split("\n    def ")[0]
        self.assertIn("self._reject_after_probe = True", reject_body)
        self.assertIn("super().reject()", finished_body)
        self.assertIn("thread.cancel()", DIALOG_SOURCE)

    def test_local_endpoint_controls_match_the_auto_allowed_runtime_policy(self):
        self.assertIn("sharing_allowed = local or get_data_sharing_consent(url)", DIALOG_SOURCE)
        self.assertIn("sensitive_allowed = local or", DIALOG_SOURCE)
        self.assertIn("self.data_sharing_cb.setEnabled(not local)", DIALOG_SOURCE)


class PanelLevelTest(unittest.TestCase):
    STYLE = (pathlib.Path(__file__).resolve().parent.parent / "qgis_ai_agent" / "ui" / "style.py").read_text(
        encoding="utf-8"
    )

    def test_panel_exists_and_lifts_only_in_the_dark(self):
        self.assertIn("def panel(", self.STYLE)
        body = self.STYLE.split("def panel(")[1].split("def ")[0]
        self.assertIn("if not is_dark(palette):", body)
        self.assertIn("return base", body)
        self.assertIn("PANEL_LIFT", body)

    def test_lift_is_meaningful(self):
        self.assertGreater(_constant(self.STYLE, "PANEL_LIFT"), 0.05)


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
        self.assertEqual(seen["timeout"], 60)

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


class ProbeWorkerTest(unittest.TestCase):
    def setUp(self):
        self.saved_probe = probe_worker.probe
        self.addCleanup(lambda: setattr(probe_worker, "probe", self.saved_probe))

    def test_feedback_reaches_the_probe_and_the_result_is_emitted(self):
        seen = {}
        probe_worker.probe = lambda overrides: (seen.update(overrides) or True, "ok")
        completed = []
        worker = probe_worker.ProbeThread({"model_override": "model"})
        worker.completed.connect(lambda ok, message: completed.append((ok, message)))
        worker.run()
        self.assertIn("feedback_override", seen)
        self.assertEqual(completed, [(True, "ok")])

    def test_cancelled_probe_does_not_update_the_dialog(self):
        probe_worker.probe = lambda overrides: (True, "late")
        completed = []
        worker = probe_worker.ProbeThread({})
        worker.completed.connect(lambda ok, message: completed.append((ok, message)))
        worker.cancel()
        worker.run()
        self.assertEqual(completed, [])


if __name__ == "__main__":
    unittest.main()
