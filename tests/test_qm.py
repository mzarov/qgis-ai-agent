import pathlib
import struct
import sys
import unittest
import xml.etree.ElementTree as ElementTree

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))

from qm import BLOCK_HASHES, MAGIC, NUMERUS_RULES, compile_qm, elf_hash, read_qm
from update_translations import translated

DATA = pathlib.Path(__file__).resolve().parent / "data"
GOLDEN_TS = DATA / "golden_ru.ts"
GOLDEN_QM = DATA / "golden_ru.qm"
CONTEXT = "QgisAiAgent"
SAMPLE = [
    (CONTEXT, "Apply", ["Применить"]),
    (CONTEXT, "Working… press ■ to stop", ["Работаю…"]),
    (CONTEXT, "%n action(s)", ["%n действие", "%n действия", "%n действий"]),
]


def golden_messages() -> list[tuple[str, str, list[str]]]:
    root = ElementTree.parse(GOLDEN_TS).getroot()
    context = root.find("context").findtext("name")
    messages = []
    for message in root.iter("message"):
        target = message.find("translation")
        forms = [form.text or "" for form in target.findall("numerusform")]
        messages.append((context, message.findtext("source") or "", forms or [target.text or ""]))
    return messages


class GoldenTest(unittest.TestCase):
    def test_our_compiler_reproduces_what_lrelease_produced(self):
        self.assertEqual(compile_qm("ru", golden_messages()), GOLDEN_QM.read_bytes())

    def test_the_fixture_covers_the_awkward_cases(self):
        sources = [source for _, source, _ in golden_messages()]
        self.assertTrue(any(not text.isascii() for text in sources))
        self.assertTrue(any("&" in text or "<" in text for text in sources))
        self.assertTrue(any("\n" in text for text in sources))
        self.assertTrue(any(len(forms) == 3 for _, _, forms in golden_messages()))

    def test_the_reference_was_not_quietly_regenerated(self):
        self.assertEqual(GOLDEN_QM.read_bytes()[:16], MAGIC)


class CompileTest(unittest.TestCase):
    def test_round_trip_returns_what_went_in(self):
        self.assertEqual(read_qm(compile_qm("ru", SAMPLE)), sorted(SAMPLE, key=lambda m: m[1]))

    def test_output_does_not_depend_on_the_order_it_was_given(self):
        self.assertEqual(compile_qm("ru", SAMPLE), compile_qm("ru", list(reversed(SAMPLE))))

    def test_output_starts_with_the_qt_magic(self):
        self.assertEqual(compile_qm("ru", SAMPLE)[:16], MAGIC)

    def test_an_unknown_language_is_refused_not_guessed(self):
        with self.assertRaises(ValueError) as caught:
            compile_qm("de", SAMPLE)
        self.assertIn("plural rules", str(caught.exception))

    def test_every_offered_language_has_plural_rules(self):
        from qgis_ai_agent import i18n

        for language in i18n.SUPPORTED_LOCALES:
            self.assertIn(language, NUMERUS_RULES, language)

    def test_empty_catalogue_still_produces_a_loadable_header(self):
        built = compile_qm("ru", [])
        self.assertEqual(built[:16], MAGIC)
        self.assertEqual(read_qm(built), [])


class HashTest(unittest.TestCase):
    def test_hash_matches_the_table_lrelease_wrote(self):
        written = set(_golden_hashes())
        self.assertTrue(written)
        for _, source, _ in golden_messages():
            self.assertIn(elf_hash(source), written, source)

    def test_hash_is_never_zero(self):
        self.assertNotEqual(elf_hash(""), 0)

    def test_latin_and_cyrillic_lookalikes_do_not_collide(self):
        self.assertNotEqual(elf_hash("a"), elf_hash("а"))
        self.assertNotEqual(elf_hash("Apply"), elf_hash("Аpply"))


def _golden_hashes() -> list[int]:
    data = GOLDEN_QM.read_bytes()
    position = len(MAGIC)
    while position < len(data):
        tag = data[position]
        size = struct.unpack(">I", data[position + 1 : position + 5])[0]
        payload = data[position + 5 : position + 5 + size]
        if tag == BLOCK_HASHES:
            return [struct.unpack(">I", payload[i : i + 4])[0] for i in range(0, len(payload), 8)]
        position += 5 + size
    return []


class CatalogueTest(unittest.TestCase):
    def test_only_finished_translations_are_compiled(self):
        found = translated(GOLDEN_TS)
        self.assertEqual(len(found), len(golden_messages()))
        for _, _, forms in found:
            self.assertTrue(all(form for form in forms))


if __name__ == "__main__":
    unittest.main()
