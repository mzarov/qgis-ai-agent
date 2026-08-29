import ast
import pathlib
import re
import sys
import unittest
import xml.etree.ElementTree as ElementTree

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))

from qgis_ai_agent import i18n
from qgis_ai_agent.core.agent.prompts import DEFAULT_LANGUAGE, LANGUAGE_NAMES, language_policy

PACKAGE = pathlib.Path(__file__).resolve().parent.parent / "qgis_ai_agent"
CYRILLIC = re.compile(r"[а-яА-ЯёЁ]")
TRANSLATED_LAYERS = ("ui", "core", "qgis_tools")
SOURCE = (PACKAGE / "i18n.py").read_text(encoding="utf-8")
CATALOGUE = PACKAGE / i18n.FOLDER / f"{i18n.PREFIX}_ru.ts"
COMPILED = CATALOGUE.with_suffix(i18n.SUFFIX)
PLACEHOLDER = re.compile(r"\{[0-9a-z_]+\}|%n")
QM_MAGIC = bytes([0x3C, 0xB8, 0x64, 0x18])


def catalogue_messages() -> list[tuple[str, list[str], bool]]:
    found = []
    for message in ElementTree.parse(CATALOGUE).getroot().iter("message"):
        target = message.find("translation")
        forms = [form.text or "" for form in target.findall("numerusform")]
        found.append(
            (message.findtext("source") or "", forms or [target.text or ""], target.get("type") == "unfinished")
        )
    return found


def russian_constants(folder: pathlib.Path) -> list[str]:
    found = []
    for path in folder.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and CYRILLIC.search(node.value):
                found.append(f"{path.relative_to(PACKAGE)}:{node.lineno}")
    return found


class SourceLanguageTest(unittest.TestCase):
    def test_translated_layers_hold_no_russian_source(self):
        for layer in TRANSLATED_LAYERS:
            self.assertEqual(russian_constants(PACKAGE / layer), [], layer)

    def test_the_prompt_itself_is_english(self):
        self.assertFalse(CYRILLIC.search((PACKAGE / "core" / "agent" / "prompts.py").read_text()))


class TrTest(unittest.TestCase):
    def test_missing_translation_falls_back_to_the_source(self):
        self.assertEqual(i18n.tr("Apply"), "Apply")

    def test_tr_always_returns_a_string(self):
        for text in ("Apply", "", "Ключ"):
            self.assertIsInstance(i18n.tr(text), str)

    def test_broken_translator_does_not_raise(self):
        saved = i18n.QCoreApplication
        i18n.QCoreApplication = None
        try:
            self.assertEqual(i18n.tr("Apply"), "Apply")
        finally:
            i18n.QCoreApplication = saved

    def test_plural_substitutes_the_count(self):
        self.assertEqual(i18n.tr_n("%n action(s)", 3), "3 actions")

    def test_plural_handles_zero_and_one(self):
        self.assertEqual(i18n.tr_n("%n step(s)", 0), "0 steps")
        self.assertEqual(i18n.tr_n("%n step(s)", 1), "1 step")

    def test_plural_never_raises(self):
        saved = i18n.QCoreApplication
        i18n.QCoreApplication = None
        try:
            self.assertEqual(i18n.tr_n("%n step(s)", 2), "2 steps")
        finally:
            i18n.QCoreApplication = saved


class LocaleTest(unittest.TestCase):
    def test_unreadable_locale_falls_back_to_english(self):
        self.assertEqual(i18n.locale_code(), i18n.FALLBACK_LOCALE)

    def test_install_never_raises(self):
        self.assertFalse(i18n.install("/no/such/folder"))

    def test_install_is_wrapped(self):
        body = SOURCE.split("def install(")[1].split("\ndef ")[0]
        self.assertIn("except Exception:", body)
        self.assertIn("return False", body)


class LanguagePolicyTest(unittest.TestCase):
    def test_known_codes_become_names(self):
        self.assertIn("Russian", language_policy("ru"))
        self.assertIn("English", language_policy("en"))

    def test_only_english_and_russian_are_offered(self):
        self.assertEqual(sorted(LANGUAGE_NAMES), ["en", "ru"])
        self.assertEqual(sorted(i18n.SUPPORTED_LOCALES), ["en", "ru"])

    def test_unsupported_code_falls_back_to_english(self):
        for code in ("kk", "de", ""):
            self.assertIn(DEFAULT_LANGUAGE, language_policy(code), code)

    def test_model_is_told_to_follow_the_user(self):
        policy = language_policy("en").lower()
        self.assertIn("different language", policy)
        self.assertIn("switch", policy)

    def test_every_name_is_written_in_english(self):
        for code, name in LANGUAGE_NAMES.items():
            self.assertTrue(name.isascii(), code)


class CatalogueTest(unittest.TestCase):
    def setUp(self):
        self.messages = catalogue_messages()

    def test_the_catalogue_exists_and_is_compiled(self):
        self.assertTrue(CATALOGUE.is_file())
        self.assertTrue(COMPILED.is_file())
        self.assertEqual(COMPILED.read_bytes()[:4], QM_MAGIC)

    def test_nothing_is_left_untranslated(self):
        pending = [source for source, _, unfinished in self.messages if unfinished]
        self.assertEqual(pending, [])

    def test_every_translation_is_actually_russian(self):
        plain = [source for source, forms, _ in self.messages if not any(CYRILLIC.search(form) for form in forms)]
        self.assertEqual(plain, [])

    def test_placeholders_survive_translation(self):
        for source, forms, _ in self.messages:
            wanted = sorted(PLACEHOLDER.findall(source))
            for form in forms:
                self.assertEqual(sorted(PLACEHOLDER.findall(form)), wanted, source)

    def test_russian_gets_all_three_plural_forms(self):
        for source, forms, _ in self.messages:
            if "%n" in source:
                self.assertEqual(len(forms), 3, source)
                self.assertEqual(len(set(forms)), 3, source)

    def test_the_catalogue_matches_what_the_sources_ask_for(self):
        import update_translations

        wanted = {text for text, _, _, _ in update_translations.sources()}
        self.assertEqual({source for source, _, _ in self.messages}, wanted)


class InstallOrderTest(unittest.TestCase):
    def test_entry_point_installs_before_it_imports_the_plugin(self):
        source = (PACKAGE / "__init__.py").read_text(encoding="utf-8")
        self.assertLess(source.index("i18n.install("), source.index("import QgisAiAgentPlugin"))

    def test_plugin_no_longer_installs_too_late(self):
        self.assertNotIn("i18n.install", (PACKAGE / "plugin.py").read_text(encoding="utf-8"))

    def test_translator_is_built_before_any_other_module_loads(self):
        import qgis.core
        import qgis.PyQt.QtCore as qt

        loaded: list[list[str]] = []
        original_translator = qt.QTranslator
        original_settings = qgis.core.QgsSettings
        qt.QTranslator = _probe(original_translator, loaded)
        qgis.core.QgsSettings = _RussianSettings
        stale = [name for name in sys.modules if name.startswith("qgis_ai_agent")]
        saved = {name: sys.modules.pop(name) for name in stale}
        try:
            __import__("qgis_ai_agent")
            self.assertTrue(loaded, "переводчик так и не создался")
            self.assertEqual(loaded[0], ["qgis_ai_agent.i18n"])
        finally:
            qt.QTranslator = original_translator
            qgis.core.QgsSettings = original_settings
            for name in [n for n in sys.modules if n.startswith("qgis_ai_agent")]:
                del sys.modules[name]
            sys.modules.update(saved)


class _RussianSettings:
    def value(self, key: str, default: str = "", type: type = str) -> str:
        return "ru_RU" if key == "locale/userLocale" else default


def _probe(base: type, loaded: list[list[str]]) -> type:
    class Probe(base):
        def __init__(self, *args, **kwargs):
            loaded.append(sorted(n for n in sys.modules if n.startswith("qgis_ai_agent.")))
            super().__init__(*args, **kwargs)

    return Probe


class ShippingTest(unittest.TestCase):
    def setUp(self):
        import build_plugin

        self.packed = {arc for _, arc in build_plugin.collect()}

    def test_the_compiled_catalogue_ships(self):
        self.assertIn(f"qgis_ai_agent/{i18n.FOLDER}/{COMPILED.name}", self.packed)

    def test_the_source_catalogue_stays_out(self):
        self.assertEqual([name for name in self.packed if name.endswith(".ts")], [])

    def test_the_folder_name_matches_what_install_looks_for(self):
        self.assertTrue((PACKAGE / i18n.FOLDER).is_dir())
        self.assertFalse((PACKAGE / i18n.FOLDER / "__init__.py").exists())


if __name__ == "__main__":
    unittest.main()
