import tempfile
import unittest
from unittest import mock

from qgis.PyQt.QtWidgets import QWidget

from ai_agent.config import personal
from ai_agent.core import settings
from ai_agent.core.agent import prompts
from ai_agent.core.agent.profile_prompt import PROFILE_HEADER, QUIET_AFTER, render_profile
from ai_agent.qgis_tools.project import notes as notes_module
from ai_agent.qgis_tools.project import remember
from ai_agent.ui.activity import ActivityGroup
from ai_agent.ui.personalisation_settings import PersonalisationSettings
from ai_agent.ui.question import QuestionCard
from tests.test_credentials import MemorySettings


class SettingsCase(unittest.TestCase):
    def setUp(self):
        MemorySettings.values = {}
        for module in (personal, settings):
            patcher = mock.patch.object(module, "QgsSettings", MemorySettings)
            patcher.start()
            self.addCleanup(patcher.stop)
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        patcher = mock.patch.object(notes_module, "default_root", return_value=folder.name)
        patcher.start()
        self.addCleanup(patcher.stop)


class ProfileStoreTest(SettingsCase):
    def test_a_saved_profile_reads_back_and_bad_values_fall_back(self):
        personal.save(personal.Profile(name="Masha", units="imperial", auto_answer=60, show_steps=False))
        loaded = personal.load()
        self.assertEqual(
            (loaded.name, loaded.units, loaded.auto_answer, loaded.show_steps), ("Masha", "imperial", 60, False)
        )
        MemorySettings.values[f"{personal.PREFIX}/units"] = "furlongs"
        MemorySettings.values[f"{personal.PREFIX}/auto_answer"] = "7"
        MemorySettings.values[f"{personal.PREFIX}/follow_changes"] = "false"
        MemorySettings.values[f"{personal.PREFIX}/name"] = "x" * 500
        loaded = personal.load()
        self.assertEqual((loaded.units, loaded.auto_answer, loaded.follow_changes), ("metric", 0, False))
        self.assertEqual(len(loaded.name), personal.MAX_NAME)
        self.assertFalse(personal.follows_changes())


class ProfilePromptTest(unittest.TestCase):
    def test_defaults_add_nothing(self):
        self.assertEqual(render_profile(personal.Profile()), "")
        static, _live = prompts.build_system_parts("", [], profile="")
        self.assertNotIn(PROFILE_HEADER, static)

    def test_every_choice_reaches_the_prompt(self):
        profile = personal.Profile(
            name="Masha",
            role="hydrologist",
            about="River basins in Kenya.",
            experience="beginner",
            units="imperial",
            layer_names="technical",
            language="de",
            style="concise",
            questions="rarely",
            explain_after=False,
        )
        text = render_profile(profile)
        for expected in ("Masha", "hydrologist", "River basins in Kenya.", "new to GIS", "imperial", "snake_case"):
            self.assertIn(expected, text)
        self.assertIn("German", text)
        self.assertIn(QUIET_AFTER, text)
        static, live = prompts.build_system_parts("", [], profile=text)
        self.assertIn(text, static)
        self.assertNotIn(text, live)


class UserMemoryTest(SettingsCase):
    def test_the_agent_remembers_about_the_user_only_while_allowed(self):
        tool = remember.RememberTool()
        prepared = tool.prepare({"note": "Works in EPSG:32637", "about": "user"})
        tool.execute(prepared)
        store = notes_module.NoteStore()
        self.assertEqual(store.user_notes(), ["Works in EPSG:32637"])
        self.assertTrue(tool.confirm_applied(prepared, {}))
        self.assertIn("about the user", prompts.render_project_notes([], store.user_notes()))
        personal.save(personal.Profile(own_notes=False))
        with self.assertRaisesRegex(ValueError, "turned off"):
            tool.prepare({"note": "Likes red", "about": "user"})
        forget = remember.ForgetTool()
        forget.execute(forget.prepare({"note": "Works in EPSG:32637"}))
        self.assertEqual(store.user_notes(), [])


class PersonalisationPageTest(SettingsCase):
    def test_the_page_round_trips_the_profile_notes_and_instructions(self):
        personal.save(personal.Profile(name="Masha", style="detailed", follow_changes=False))
        settings.set_custom_instructions("Use metres.")
        page = PersonalisationSettings(QWidget().palette())
        self.assertEqual(page.name.text(), "Masha")
        self.assertFalse(page.follow.isChecked())
        page.memory.editor.setText("Exports to GeoPackage")
        page.memory.add()
        page.memory.editor.setText("Exports to GeoPackage")
        page.memory.add()
        self.assertEqual(page.memory.notes, ["Exports to GeoPackage"])
        page.role.setText("planner")
        page.save()
        self.assertEqual(personal.load().role, "planner")
        self.assertEqual(settings.get_custom_instructions(), "Use metres.")
        self.assertEqual(notes_module.NoteStore().user_notes(), ["Exports to GeoPackage"])
        page.memory.remove("Exports to GeoPackage")
        self.assertEqual(page.memory.notes, [])


class FeedPreferenceTest(SettingsCase):
    def test_an_unanswered_question_takes_the_recommended_answer(self):
        card = QuestionCard("Which classes?", ["5 equal", "7 quantile"], QWidget().palette(), auto_seconds=2)
        answers = []
        card.answered.connect(answers.append)
        self.assertIn("5 equal", card.countdown.text())
        card._tick()
        self.assertEqual(answers, [])
        card._tick()
        self.assertEqual(answers, ["5 equal"])

    def test_typing_an_own_answer_stops_the_countdown(self):
        card = QuestionCard("Which classes?", ["5 equal"], QWidget().palette(), auto_seconds=60)
        card.stop_countdown()
        self.assertTrue(card.countdown.isHidden())
        self.assertFalse(card._timer.isActive())

    def test_with_steps_hidden_calls_stay_folded_under_a_header(self):
        personal.save(personal.Profile(show_steps=False))
        group = ActivityGroup()
        group.add_step("Reading layer roads.")
        self.assertTrue(group._rows_holder.isHidden())
        self.assertTrue(group._header.isVisible())


if __name__ == "__main__":
    unittest.main()


class DropdownTest(unittest.TestCase):
    def test_it_behaves_like_the_combo_box_it_replaces(self):
        from ai_agent.ui.dropdown import Dropdown

        box = Dropdown(QWidget().palette())
        changes = []
        box.currentIndexChanged.connect(changes.append)
        box.addItem("Same as QGIS", "")
        box.addItem("German", "de")
        self.assertEqual((box.currentIndex(), box.currentData(), box.currentText()), (0, "", "Same as QGIS"))
        box.setCurrentIndex(box.findData("de"))
        self.assertEqual((box.currentData(), box.currentText(), box.count()), ("de", "German", 2))
        box.setCurrentIndex(7)
        box.setCurrentIndex(1)
        self.assertEqual(changes, [0, 1])
        self.assertEqual(box.findData("fr"), -1)
        box.chevron.set_angle(90)
        self.assertEqual(box.chevron.angle, 90.0)
