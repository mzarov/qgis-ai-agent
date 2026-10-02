import pathlib
import re
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "tests.yml"
PIXELS = REPO_ROOT / "tests" / "data" / "ui" / "pixels"
STRUCTURE = REPO_ROOT / "tests" / "data" / "ui" / "structure"
DIGEST = re.compile(r"qgis/qgis@sha256:[0-9a-f]{64}")


class PixelBaselinePinTest(unittest.TestCase):
    def test_pixel_goldens_come_from_one_pinned_image(self):
        pins = set(DIGEST.findall(WORKFLOW.read_text(encoding="utf-8")))
        self.assertEqual(len(pins), 1, "the ui-pixels job must pin exactly one QGIS image by digest")
        for doc in ("smoke_checklist.md", "smoke_checklist.ru.md"):
            text = (REPO_ROOT / "docs" / doc).read_text(encoding="utf-8")
            self.assertEqual(set(DIGEST.findall(text)), pins, f"{doc} regenerates goldens in another image")

    def test_every_english_screen_has_both_pixel_goldens(self):
        screens = {path.stem for path in STRUCTURE.glob("*.json")}
        pixels = {path.stem for path in PIXELS.glob("*.png")}
        self.assertTrue(screens)
        self.assertEqual(pixels, screens | {f"{name}_ru" for name in screens})


if __name__ == "__main__":
    unittest.main()
