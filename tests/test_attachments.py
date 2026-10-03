import os
import tempfile
import unittest
from unittest import mock

from ai_agent.core import attachments
from ai_agent.core.agent.transcript import USER_IMAGE_OMITTED_NOTE, Transcript
from ai_agent.core.orchestrator import attaching


class FakeTool:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.sources: list[dict] = []

    def prepare(self, params):
        return params

    def execute(self, params):
        if self.fail:
            raise ValueError("QGIS could not open it")
        self.sources.append(params)
        return {}


class AttachTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)

    def file(self, name: str) -> str:
        path = os.path.join(self.folder.name, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("x")
        return path

    def test_pictures_wait_and_data_becomes_layers_under_a_free_name(self):
        tool = FakeTool()
        roads, photo = self.file("roads.geojson"), self.file("sketch.png")
        with (
            mock.patch.object(attachments, "get_tool_by_name", return_value=tool),
            mock.patch.object(attachments, "layer_names", return_value=["roads", "roads (2)"]),
        ):
            outcome = attachments.attach([roads, photo, os.path.join(self.folder.name, "gone.shp")])
        self.assertEqual(outcome.added, ["roads (3)"])
        self.assertEqual(tool.sources, [{"source": roads, "name": "roads (3)"}])
        self.assertEqual(outcome.images, [photo])
        self.assertEqual([reason for _path, reason in outcome.failed], ["not a file"])

    def test_a_csv_goes_through_load_table_and_falls_back_to_add_layer(self):
        loader, plain = FakeTool(), FakeTool()
        tools = {"load_table": loader, "add_layer": plain}
        stats = self.file("stats.csv")
        with (
            mock.patch.object(attachments, "get_tool_by_name", side_effect=tools.get),
            mock.patch.object(attachments, "layer_names", return_value=[]),
        ):
            outcome = attachments.attach([stats])
            self.assertEqual(loader.sources, [{"path": stats, "name": "stats"}])
            self.assertEqual(plain.sources, [])
            tools["load_table"] = FakeTool(fail=True)
            outcome = attachments.attach([stats])
        self.assertEqual(outcome.added, ["stats"])
        self.assertEqual(plain.sources, [{"source": stats, "name": "stats"}])

    def test_a_picture_with_a_world_file_is_data(self):
        scan = self.file("scan.png")
        self.file("scan.pgw")
        self.assertFalse(attachments.is_picture(scan))
        self.assertTrue(attachments.is_picture(self.file("photo.JPG")))
        self.assertFalse(attachments.is_picture(self.file("dem.tif")))

    def test_a_file_qgis_cannot_open_is_reported_not_raised(self):
        with (
            mock.patch.object(attachments, "get_tool_by_name", return_value=FakeTool(fail=True)),
            mock.patch.object(attachments, "layer_names", return_value=[]),
        ):
            outcome = attachments.attach([self.file("broken.gpkg")])
        self.assertEqual(outcome.added, [])
        self.assertIn("could not open", outcome.failed[0][1])


class UserPictureTranscriptTest(unittest.TestCase):
    def test_pictures_ride_with_the_request_or_are_named_as_omitted(self):
        transcript = Transcript()
        transcript.add_user("What is on this map?", ["QUJD"])
        seen = transcript.build_messages("system")[1]["content"]
        self.assertEqual(seen[0], {"type": "text", "text": "What is on this map?"})
        self.assertEqual(seen[1]["image_url"]["url"], "data:image/png;base64,QUJD")
        blind = transcript.build_messages("system", include_images=False)[1]["content"]
        self.assertEqual(blind, f"What is on this map?\n{USER_IMAGE_OMITTED_NOTE}")

    def test_a_plain_request_stays_a_string(self):
        transcript = Transcript()
        transcript.add_user("hello")
        self.assertEqual(transcript.build_messages("system")[1]["content"], "hello")


class Dock:
    def __init__(self, pictures=()):
        self.pictures = list(pictures)
        self.system: list[str] = []
        self.mentioned: list[str] = []
        self.waiting: list[str] = []

    def take_attachments(self):
        taken, self.pictures = self.pictures, []
        return taken

    def add_system_message(self, text):
        self.system.append(text)

    def mention_layers(self, names):
        self.mentioned.extend(names)

    def add_attachment(self, path):
        self.waiting.append(path)


class AttachingTest(unittest.TestCase):
    def test_files_split_into_mentions_waiting_pictures_and_messages(self):
        dock = Dock()
        outcome = attachments.Outcome(added=["roads"], images=["/tmp/a.png"], failed=[("/tmp/x.shp", "broken")])
        with mock.patch.object(attaching, "attach", return_value=outcome):
            attaching.files_attached(dock, ["whatever"])
        self.assertEqual((dock.mentioned, dock.waiting), (["roads"], ["/tmp/a.png"]))
        self.assertIn("x.shp", dock.system[0])

    def test_pictures_are_encoded_and_named_in_the_chat(self):
        dock = Dock(["/tmp/map.png"])
        with (
            mock.patch.object(attaching, "detect_images_unsupported", return_value=False),
            mock.patch.object(attaching, "encode_picture", return_value="QUJD"),
        ):
            pictures = attaching.take_pictures(dock)
        self.assertEqual((pictures.encoded, pictures.names), (["QUJD"], ["map.png"]))
        self.assertTrue(attaching.with_names("Look", pictures).endswith("map.png"))
        self.assertEqual(dock.pictures, [])

    def test_a_blind_model_gets_no_pictures_and_the_user_is_told(self):
        dock = Dock(["/tmp/map.png"])
        with mock.patch.object(attaching, "detect_images_unsupported", return_value=True):
            pictures = attaching.take_pictures(dock)
        self.assertEqual(pictures.encoded, [])
        self.assertIn("map.png", dock.system[0])
        self.assertEqual(attaching.with_names("Look", pictures), "Look")


class ChipsTest(unittest.TestCase):
    def test_chips_collect_once_and_empty_on_take(self):
        from qgis.PyQt.QtWidgets import QWidget

        from ai_agent.ui.attachments import AttachmentChips

        chips = AttachmentChips(QWidget().palette())
        self.assertTrue(chips.isHidden())
        chips.add("/tmp/a.png")
        chips.add("/tmp/a.png")
        chips.add("/tmp/b.png")
        self.assertEqual(chips.paths, ["/tmp/a.png", "/tmp/b.png"])
        chips.remove("/tmp/a.png")
        self.assertEqual(chips.take(), ["/tmp/b.png"])
        self.assertTrue(chips.isHidden())


if __name__ == "__main__":
    unittest.main()
