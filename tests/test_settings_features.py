"""The functional additions of Settings: step and time limits, history keeping, skill switches, reset."""

import os
import tempfile
import time
import unittest
from unittest import mock

from ai_agent.config import connectors, geocoder, limits, personal
from ai_agent.core import history, settings
from ai_agent.core.agent import journal
from ai_agent.core.agent.skills import tools_for_skills
from ai_agent.core.local_skills import builtin_skills, register_local_skills, skill_choices
from ai_agent.core.state.session import Session
from ai_agent.core.state.store import DAY_SECONDS, SessionStore
from ai_agent.skills.registry import SKILL_REGISTRY
from ai_agent.ui import settings_dialog, settings_layout
from tests.test_credentials import MemorySettings


class SettingsCase(unittest.TestCase):
    def setUp(self):
        MemorySettings.values = {}
        for module in (personal, settings, limits, connectors, geocoder):
            patcher = mock.patch.object(module, "QgsSettings", MemorySettings)
            patcher.start()
            self.addCleanup(patcher.stop)


class LimitsSettingsTest(SettingsCase):
    def test_the_limits_read_back_clamped_to_their_ranges(self):
        defaults = (limits.DEFAULT_STEPS, limits.DEFAULT_TOOL_SECONDS)
        self.assertEqual((limits.max_steps(), limits.tool_seconds()), defaults)
        limits.set_max_steps(25)
        limits.set_tool_seconds(9000)
        self.assertEqual((limits.max_steps(), limits.tool_seconds()), (25, limits.MAX_TOOL_SECONDS))


class HistoryKeepingTest(SettingsCase):
    """Conversations older than the chosen days go; the open one never does; erasing takes everything."""

    def setUp(self):
        super().setUp()
        self.root = tempfile.mkdtemp()
        self.store = SessionStore(self.root)

    def _session(self, days_old: float) -> Session:
        session = Session.create("project")
        session.add("user", "hello")
        session.updated = time.time() - days_old * DAY_SECONDS
        self.store.save(session)
        return session

    def test_only_the_chosen_days_are_kept_and_never_the_open_conversation(self):
        fresh, stale, open_one = self._session(1), self._session(40), self._session(45)
        self.assertEqual(self.store.prune(30, keep=open_one.identifier), 1)
        kept = {session.identifier for session in self.store._all()}
        self.assertEqual(kept, {fresh.identifier, open_one.identifier})
        self.assertNotIn(stale.identifier, kept)

    def test_keeping_forever_deletes_nothing(self):
        self._session(400)
        self.assertEqual(self.store.prune(0), 0)
        self.assertEqual(self.store.usage()[0], 1)

    def test_only_the_offered_choices_are_stored(self):
        settings.set_history_days(30)
        self.assertEqual(settings.get_history_days(), 30)
        settings.set_history_days(12)
        self.assertEqual(settings.get_history_days(), 0)

    def test_erasing_takes_conversations_and_journals(self):
        self._session(1)
        journals = tempfile.mkdtemp()
        path = journal.write_journal("# Run journal", journals)
        self.assertTrue(os.path.exists(path))
        with (
            mock.patch.object(history, "SessionStore", lambda: SessionStore(self.root)),
            mock.patch.object(journal, "default_root", return_value=journals),
        ):
            count, size = history.usage()
            self.assertEqual(count, 1)
            self.assertGreater(size, 0)
            history.erase()
            self.assertEqual(history.usage(), (0, 0))
        self.assertTrue(os.path.isdir(journals), "the folder stays, only the journals go")


class SkillSwitchTest(SettingsCase):
    """A built-in skill switched off is gone for the agent: no line in the prompt, no loading, no tools."""

    def tearDown(self):
        SKILL_REGISTRY.set_disabled(())

    def test_a_switched_off_skill_is_hidden_but_still_listed_for_the_settings(self):
        settings.set_disabled_skills(["charts", "charts", " "])
        self.assertEqual(settings.get_disabled_skills(), ["charts"])
        register_local_skills(tempfile.mkdtemp())
        self.assertIsNone(SKILL_REGISTRY.get("charts"))
        self.assertNotIn("charts", SKILL_REGISTRY.names())
        self.assertNotIn("charts", [name for name, _description, _origin in skill_choices()])
        listed = {name: enabled for name, _description, enabled in builtin_skills()}
        self.assertFalse(listed["charts"])
        self.assertTrue(listed["inspect"])

    def test_no_tool_of_a_switched_off_domain_is_offered(self):
        SKILL_REGISTRY.set_disabled(["charts"])
        offered = {tool.skill for tool in tools_for_skills(["inspect", "charts"])}
        self.assertNotIn("charts", offered)
        self.assertIn("inspect", offered)

    def test_an_unknown_name_switches_nothing_off(self):
        SKILL_REGISTRY.set_disabled(["no-such-skill"])
        self.assertFalse(SKILL_REGISTRY.is_disabled("no-such-skill"))


class SkillSummaryTest(unittest.TestCase):
    def test_every_built_in_skill_has_a_line_a_person_reads(self):
        from ai_agent.ui.skill_summaries import SUMMARIES

        self.assertEqual(set(SUMMARIES), {skill.name for skill in SKILL_REGISTRY.builtin_skills()})


class DeferredPagesTest(SettingsCase):
    """Pages the Connection page does not edit with it are built on their first visit, and saved only then."""

    def setUp(self):
        super().setUp()
        self.dialog = settings_dialog.SettingsDialog()

    def test_the_window_opens_without_the_pages_nobody_has_visited(self):
        deferred = {
            settings_layout.SKILLS,
            settings_layout.GEOCODING,
            settings_layout.CONNECTORS,
            settings_layout.PERSONALISATION,
        }
        self.assertEqual(set(self.dialog._unbuilt_pages), deferred)
        self.assertEqual(self.dialog._built_pages, {})

    def test_a_page_is_built_on_its_first_visit_and_kept(self):
        self.dialog.show_page(settings_layout.CONNECTORS)
        built = self.dialog.connectors
        self.dialog.show_page(settings_layout.CONNECTION)
        self.dialog.show_page(settings_layout.CONNECTORS)
        self.assertIs(self.dialog.connectors, built)
        self.assertNotIn(settings_layout.CONNECTORS, self.dialog._unbuilt_pages)

    def test_an_edit_on_a_visited_page_is_saved_and_unvisited_pages_are_left_alone(self):
        with (
            mock.patch.object(settings_dialog, "set_disabled_skills") as skills_saved,
            mock.patch.object(settings_dialog, "save_enabled") as connectors_saved,
            mock.patch.object(settings_dialog, "set_geocoder_provider") as geocoder_saved,
        ):
            self.dialog.show_page(settings_layout.SKILLS)
            self.dialog.skills.switches["charts"].setChecked(False)
            self.assertTrue(self.dialog.save_btn.isEnabled())
            self.dialog._save()
        skills_saved.assert_called_once_with(["charts"])
        connectors_saved.assert_not_called()
        geocoder_saved.assert_not_called()


class ResetTest(SettingsCase):
    def test_reset_returns_preferences_and_keeps_the_connection_and_the_users_words(self):
        settings.set_api_url("https://api.example.com/v1")
        settings.set_extra_headers("x-folder-id: b1g8")
        settings.set_token_budget(1000)
        settings.set_disabled_skills(["charts"])
        settings.set_history_days(7)
        limits.set_max_steps(10)
        connectors.set_disabled_connectors(["openstreetmap"])
        personal.save(personal.Profile(name="Masha", about="Hydrologist", units="imperial", show_steps=False))
        settings.reset_preferences()
        self.assertEqual(settings.get_api_url(), "https://api.example.com/v1")
        self.assertEqual(settings.get_extra_headers(), "x-folder-id: b1g8")
        self.assertEqual(settings.get_token_budget(), settings.DEFAULT_TOKEN_BUDGET)
        self.assertEqual((settings.get_disabled_skills(), settings.get_history_days()), ([], 0))
        self.assertEqual(limits.max_steps(), limits.DEFAULT_STEPS)
        self.assertEqual(connectors.disabled_connectors(), frozenset())
        profile = personal.load()
        self.assertEqual((profile.name, profile.about), ("Masha", "Hydrologist"))
        self.assertEqual((profile.units, profile.show_steps), ("metric", True))


if __name__ == "__main__":
    unittest.main()
