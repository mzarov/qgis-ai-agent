import pathlib
import re
import unittest

DOCS = pathlib.Path(__file__).resolve().parent.parent / "docs"
RU_SUFFIX = ".ru.md"
HEADING = re.compile(r"^#{1,3} ", re.MULTILINE)


def english_pages() -> list[pathlib.Path]:
    return sorted(path for path in DOCS.glob("*.md") if not path.name.endswith(RU_SUFFIX))


def russian_pages() -> list[pathlib.Path]:
    return sorted(DOCS.glob(f"*{RU_SUFFIX}"))


class MirrorTest(unittest.TestCase):
    def test_every_english_page_has_a_russian_twin(self):
        orphans = [
            page.name for page in english_pages() if not page.with_name(page.name[: -len(".md")] + RU_SUFFIX).is_file()
        ]
        self.assertEqual(orphans, [])

    def test_every_russian_page_has_an_english_original(self):
        orphans = [
            page.name for page in russian_pages() if not page.with_name(page.name[: -len(RU_SUFFIX)] + ".md").is_file()
        ]
        self.assertEqual(orphans, [])

    def test_there_are_pages_at_all(self):
        self.assertGreaterEqual(len(english_pages()), 5)

    def test_twins_do_not_drift_apart_in_structure(self):
        for page in english_pages():
            twin = page.with_name(page.name[: -len(".md")] + RU_SUFFIX)
            original = len(HEADING.findall(page.read_text(encoding="utf-8")))
            mirrored = len(HEADING.findall(twin.read_text(encoding="utf-8")))
            self.assertEqual(mirrored, original, page.name)


class NavTest(unittest.TestCase):
    def test_the_nav_lists_only_existing_english_pages(self):
        config = (DOCS.parent / "mkdocs.yml").read_text(encoding="utf-8")
        listed = re.findall(r":\s*([\w.]+\.md)\s*$", config, re.MULTILINE)
        self.assertTrue(listed)
        for name in listed:
            self.assertTrue((DOCS / name).is_file(), name)

    def test_every_english_page_is_in_the_nav(self):
        config = (DOCS.parent / "mkdocs.yml").read_text(encoding="utf-8")
        missing = [page.name for page in english_pages() if page.name not in config]
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
