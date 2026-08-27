import pathlib
import unittest

from qgis_ai_agent.core.llm import providers
from qgis_ai_agent.core.llm.dialects import ANTHROPIC, OPENAI, resolve
from qgis_ai_agent.ui import settings_fields as fields
from qgis_ai_agent.core.llm import probe as settings_probe


class PresetTest(unittest.TestCase):
    def test_first_preset_is_the_custom_one(self):
        self.assertTrue(providers.PRESETS[0].is_custom)

    def test_titles_are_unique(self):
        self.assertEqual(len(providers.TITLES), len(set(providers.TITLES)))

    def test_every_preset_has_a_model_hint(self):
        for preset in providers.PRESETS:
            self.assertTrue(preset.model_hint.strip(), preset.title)

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


SOURCE = (
    pathlib.Path(__file__).resolve().parent.parent
    / "qgis_ai_agent"
    / "ui"
    / "settings_fields.py"
).read_text(encoding="utf-8")


class StyleSheetTest(unittest.TestCase):
    def test_card_style_is_scoped_by_object_name(self):
        self.assertIn(f"QFrame#{{CARD_NAME}}", SOURCE)
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
        offenders = [
            line.strip()
            for line in SOURCE.split("\n")
            if "border: none" in line and "drop-down" not in line
        ]
        self.assertEqual(offenders, [])


class PanelLevelTest(unittest.TestCase):
    STYLE = (
        pathlib.Path(__file__).resolve().parent.parent
        / "qgis_ai_agent"
        / "ui"
        / "style.py"
    ).read_text(encoding="utf-8")

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
    def _with_chat(self, fake):
        module = __import__("qgis_ai_agent.core.llm.client", fromlist=["chat"])
        saved = module.chat
        module.chat = fake
        self.addCleanup(lambda: setattr(module, "chat", saved))

    def test_successful_reply_is_reported(self):
        self._with_chat(lambda messages, **kwargs: "ок")
        ok, message = settings_probe.probe({})
        self.assertTrue(ok)
        self.assertIn("ок", message)

    def test_empty_reply_counts_as_failure(self):
        self._with_chat(lambda messages, **kwargs: "   ")
        ok, message = settings_probe.probe({})
        self.assertFalse(ok)
        self.assertIn("пустой", message)

    def test_error_is_reported_not_raised(self):
        def broken(messages, **kwargs):
            raise ValueError("Не задан API-ключ")

        self._with_chat(broken)
        ok, message = settings_probe.probe({})
        self.assertFalse(ok)
        self.assertIn("API-ключ", message)

    def test_silent_exception_still_names_something(self):
        def broken(messages, **kwargs):
            raise TimeoutError()

        self._with_chat(broken)
        ok, message = settings_probe.probe({})
        self.assertFalse(ok)
        self.assertTrue(message.strip())

    def test_long_reply_is_shortened(self):
        self._with_chat(lambda messages, **kwargs: "о" * 500)
        _, message = settings_probe.probe({})
        self.assertLess(len(message), 200)
        self.assertTrue(message.endswith("…"))

    def test_newlines_are_flattened(self):
        self._with_chat(lambda messages, **kwargs: "первая\n\nвторая")
        _, message = settings_probe.probe({})
        self.assertNotIn("\n", message)

    def test_overrides_reach_the_client(self):
        seen = {}

        def spy(messages, **kwargs):
            seen.update(kwargs)
            return "ок"

        self._with_chat(spy)
        settings_probe.probe({"url_override": "http://localhost:11434/v1", "key_override": None})
        self.assertEqual(seen["url_override"], "http://localhost:11434/v1")


if __name__ == "__main__":
    unittest.main()
