import os
import shutil
import tempfile
import unittest

from qgis_ai_agent.core.agent.loop import AgentLoop
from qgis_ai_agent.core.agent.notices import INTERJECTION_HEADER
from qgis_ai_agent.core.agent.prompts import build_system_prompt, render_project_notes
from qgis_ai_agent.qgis_tools.project import notes as notes_module
from qgis_ai_agent.qgis_tools.project import remember as remember_module
from qgis_ai_agent.qgis_tools.project.notes import MAX_NOTE_CHARS, MAX_NOTES, NoteStore
from qgis_ai_agent.qgis_tools.project.remember import ForgetTool, ListNotesTool, RememberTool

PROJECT = "city.qgz"


class NoteStoreTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.store = NoteStore(self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_a_note_survives_a_reread(self):
        self.store.remember("POP2020 is the 2020 census", PROJECT)
        self.assertEqual(NoteStore(self.root).notes(PROJECT), ["POP2020 is the 2020 census"])

    def test_notes_are_scoped_to_their_project(self):
        self.store.remember("for the city", PROJECT)
        self.store.remember("for the region", "region.qgz")
        self.assertEqual(self.store.notes(PROJECT), ["for the city"])
        self.assertEqual(self.store.notes("region.qgz"), ["for the region"])

    def test_repeating_a_note_does_not_duplicate_it(self):
        self.store.remember("same", PROJECT)
        self.store.remember("same", PROJECT)
        self.assertEqual(self.store.notes(PROJECT), ["same"])

    def test_an_empty_note_is_refused(self):
        with self.assertRaises(ValueError):
            self.store.remember("   ", PROJECT)

    def test_an_overlong_note_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            self.store.remember("x" * (MAX_NOTE_CHARS + 1), PROJECT)
        self.assertIn(str(MAX_NOTE_CHARS), str(caught.exception))

    def test_old_notes_are_trimmed(self):
        for index in range(MAX_NOTES + 5):
            self.store.remember(f"note {index}", PROJECT)
        kept = self.store.notes(PROJECT)
        self.assertEqual(len(kept), MAX_NOTES)
        self.assertEqual(kept[-1], f"note {MAX_NOTES + 4}")

    def test_forgetting_removes_exactly_one(self):
        self.store.remember("first", PROJECT)
        self.store.remember("second", PROJECT)
        self.assertTrue(self.store.forget("first", PROJECT))
        self.assertEqual(self.store.notes(PROJECT), ["second"])

    def test_forgetting_something_absent_says_so(self):
        self.assertFalse(self.store.forget("never stored", PROJECT))

    def test_a_missing_file_reads_as_empty(self):
        self.assertEqual(NoteStore(os.path.join(self.root, "nowhere")).notes(PROJECT), [])

    def test_a_corrupt_file_reads_as_empty_instead_of_crashing(self):
        with open(self.store.path(), "w", encoding="utf-8") as handle:
            handle.write("{ not json")
        self.assertEqual(self.store.notes(PROJECT), [])

    def test_a_corrupt_primary_recovers_the_previous_valid_notes(self):
        self.store.remember("first", PROJECT)
        self.store.remember("second", PROJECT)
        with open(self.store.path(), "w", encoding="utf-8") as handle:
            handle.write("{ not json")
        self.assertEqual(self.store.notes(PROJECT), ["first"])

    def test_valid_json_with_a_wrong_note_shape_is_treated_as_empty(self):
        os.makedirs(self.root, exist_ok=True)
        with open(self.store.path(), "w", encoding="utf-8") as handle:
            handle.write('{"city.qgz": 42}')
        self.assertEqual(self.store.notes(PROJECT), [])
        self.assertEqual(self.store.remember("safe", PROJECT), ["safe"])


class RememberToolTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.saved = remember_module.NoteStore
        remember_module.NoteStore = lambda: NoteStore(self.root)
        self.saved_key = notes_module.current_project_key
        notes_module.current_project_key = lambda: PROJECT

    def tearDown(self):
        remember_module.NoteStore = self.saved
        notes_module.current_project_key = self.saved_key
        shutil.rmtree(self.root, ignore_errors=True)

    def test_remembering_then_listing_round_trips(self):
        RememberTool().execute({"note": "POP2020 is the 2020 census"})
        listed = ListNotesTool().execute({})
        self.assertEqual(listed["notes"], ["POP2020 is the 2020 census"])
        self.assertEqual(listed["count"], 1)

    def test_an_empty_note_is_refused_at_queue_time(self):
        with self.assertRaises(ValueError):
            RememberTool().prepare({"note": "  "})

    def test_forgetting_an_unknown_note_is_refused_at_queue_time(self):
        with self.assertRaises(ValueError) as caught:
            ForgetTool().prepare({"note": "never stored"})
        self.assertIn("list_notes", str(caught.exception))

    def test_forgetting_a_stored_note_works(self):
        RememberTool().execute({"note": "drop me"})
        ForgetTool().prepare({"note": "drop me"})
        result = ForgetTool().execute({"note": "drop me"})
        self.assertEqual(result["notes_kept"], 0)

    def test_the_scope_is_stated_to_the_model(self):
        result = RememberTool().execute({"note": "scoped"})
        self.assertIn("this project only", result["note"])

    def test_listing_is_a_read_tool(self):
        self.assertTrue(ListNotesTool().is_read_only)

    def test_summaries_never_raise(self):
        for tool in (RememberTool(), ListNotesTool(), ForgetTool()):
            self.assertTrue(tool.summarize_call({}).strip())


class NotesInPromptTest(unittest.TestCase):
    def test_notes_render_as_a_list(self):
        rendered = render_project_notes(["first fact", "second fact"])
        self.assertIn("- first fact", rendered)
        self.assertIn("- second fact", rendered)

    def test_no_notes_render_to_nothing(self):
        self.assertEqual(render_project_notes([]), "")

    def test_notes_are_pinned_into_the_system_prompt(self):
        prompt = build_system_prompt("", [], project_notes=render_project_notes(["POP2020 is population"]))
        self.assertIn("POP2020 is population", prompt)


class RunningThread:
    is_running = True


class InterjectionTest(unittest.TestCase):
    def setUp(self):
        self.loop = AgentLoop()

    def _make_busy(self):
        self.loop._turn = RunningThread()

    def test_nothing_is_taken_when_the_agent_is_idle(self):
        self.assertFalse(self.loop.interject("blue, not red"))

    def test_an_empty_interjection_is_ignored(self):
        self.assertFalse(self.loop.interject("   "))

    def test_a_running_agent_takes_the_correction(self):
        self._make_busy()
        self.assertTrue(self.loop.interject("blue, not red"))
        entries = [entry for entry in self.loop._transcript.entries if entry["kind"] == "user"]
        self.assertEqual(len(entries), 1)
        self.assertIn("blue, not red", entries[0]["text"])

    def test_the_correction_is_framed_as_a_correction(self):
        self._make_busy()
        self.loop.interject("blue, not red")
        text = self.loop._transcript.entries[0]["text"]
        self.assertTrue(text.startswith(INTERJECTION_HEADER))
        self.assertIn("not as a new request", text)


if __name__ == "__main__":
    unittest.main()
