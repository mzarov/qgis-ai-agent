import shutil
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from ai_agent.core.agent.titling import Titler, clean_title
from ai_agent.core.orchestrator.naming import SessionNaming
from ai_agent.core.state.conversation import ConversationState
from ai_agent.core.state.session import Session
from ai_agent.core.state.store import SessionStore


class StateTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.store = SessionStore(self.root)
        self.state = ConversationState(store=self.store)
        self.state.add("user", "Какие у меня слои и что в них?")

    def test_renaming_marks_the_title_as_chosen_and_persists(self):
        self.assertTrue(self.state.rename(self.state.session_identifier, "Слои города"))
        self.assertTrue(self.state.named)
        self.assertEqual(self.store.load(self.state.session_identifier).title, "Слои города")
        self.assertFalse(self.state.rename(self.state.session_identifier, "   "))

    def test_a_past_conversation_can_be_renamed_and_another_projects_cannot(self):
        past = self.state.session_identifier
        self.state.start_new()
        self.assertTrue(self.state.rename(past, "Старое"))
        self.assertEqual(self.store.load(past).title, "Старое")
        other = Session.create("/another/project.qgz")
        other.add("user", "чужое")
        self.store.save(other)
        self.assertFalse(self.state.rename(other.identifier, "x"))
        self.state.delete(other.identifier)
        self.assertIsNotNone(self.store.load(other.identifier), "another project's conversation is not ours to delete")

    def test_deleting_the_open_conversation_starts_a_fresh_one(self):
        open_one = self.state.session_identifier
        self.assertTrue(self.state.delete(open_one))
        self.assertIsNone(self.store.load(open_one))
        self.assertNotEqual(self.state.session_identifier, open_one)
        self.assertEqual(self.state.messages, [])

    def test_deleting_a_past_one_leaves_the_open_one_alone(self):
        past = self.state.session_identifier
        self.state.start_new()
        self.state.add("user", "новое")
        self.assertFalse(self.state.delete(past))
        self.assertIsNone(self.store.load(past))
        self.assertEqual(self.state.messages[-1]["content"], "новое")


class TitleTest(unittest.TestCase):
    def test_a_title_loses_quotes_full_stops_and_extra_lines(self):
        self.assertEqual(clean_title("«Слои Нижнего Тагила».\nпояснение"), "Слои Нижнего Тагила")
        self.assertEqual(clean_title("\n\n  Cafés in Paris  "), "Cafés in Paris")
        self.assertEqual(clean_title("   "), "")
        self.assertLessEqual(len(clean_title("x" * 200)), 48)

    def test_the_request_holds_the_first_exchange_and_no_tools(self):
        titler = Titler()
        started = {}
        titler._turn = SimpleNamespace(
            is_running=False,
            start=lambda messages, tools, overrides, on_turn, on_error: started.update(messages=messages, tools=tools),
        )
        self.assertTrue(titler.start("раскрась районы", "готово", {"url_override": "u"}))
        self.assertEqual(started["tools"], [])
        self.assertIn("раскрась районы", started["messages"][1]["content"])


class NamingTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.state = ConversationState(store=SessionStore(self.root))
        self.naming = SessionNaming(lambda: self.state)
        self.naming._titler = mock.MagicMock(is_running=False)

    def test_named_once_after_the_first_answer_and_never_over_a_users_title(self):
        self.naming.after_answer()
        self.naming._titler.start.assert_not_called()
        self.state.add("user", "Какие у меня слои?")
        self.state.add("assistant", "Три слоя.")
        self.naming.after_answer()
        self.naming.after_answer()
        self.assertEqual(self.naming._titler.start.call_count, 1)
        self.naming._on_named("Слои проекта", 50, 5)
        self.assertEqual(self.state.recent()[0][1], "Слои проекта")
        self.state.rename(self.state.session_identifier, "Мои слои")
        self.naming._on_named("Другое", 50, 5)
        self.assertEqual(self.state.recent()[0][1], "Мои слои")

    def test_a_name_for_a_conversation_the_user_left_is_dropped(self):
        self.state.add("user", "вопрос")
        self.state.add("assistant", "ответ")
        self.naming.after_answer()
        self.state.start_new()
        self.naming._on_named("Чужое", 50, 5)
        self.assertFalse(self.state.named)


class RowTest(unittest.TestCase):
    def test_a_row_renames_in_place_and_asks_before_deleting(self):
        from qgis.PyQt.QtWidgets import QWidget

        from ai_agent.ui.sessions_popup import Entry, SessionRow

        row = SessionRow(Entry("id1", "Старое"), "12:30", QWidget().palette())
        renamed: list[tuple[str, str]] = []
        deletions: list[tuple[str, str]] = []
        row.renamed.connect(lambda identifier, title: renamed.append((identifier, title)))
        row.delete_requested.connect(lambda identifier, title: deletions.append((identifier, title)))
        row.start_rename()
        row.editor.setText("Новое")
        row._keep_name()
        self.assertEqual(renamed, [("id1", "Новое")])
        row._ask_delete()
        self.assertEqual(deletions, [("id1", "Новое")])


class DayGroupsTest(unittest.TestCase):
    """The history menu groups conversations by day, newest first, a time today and yesterday, a date before."""

    def test_today_yesterday_and_earlier(self):
        from datetime import datetime

        from ai_agent.ui import sessions_popup
        from ai_agent.ui.sessions_popup import Entry, day_groups

        now = datetime(2026, 10, 8, 15, 0).timestamp()
        entries = [
            Entry("old", "Old", datetime(2026, 9, 1, 9, 5).timestamp()),
            Entry("today", "Today", datetime(2026, 10, 8, 14, 32).timestamp(), True),
            Entry("last-year", "Last year", datetime(2025, 12, 31, 23, 0).timestamp()),
            Entry("yesterday", "Yesterday", datetime(2026, 10, 7, 9, 10).timestamp()),
        ]
        groups = day_groups(entries, now)
        self.assertEqual(
            [(label, [(entry.identifier, meta) for entry, meta in items]) for label, items in groups],
            [
                (sessions_popup.TODAY, [("today", "14:32")]),
                (sessions_popup.YESTERDAY, [("yesterday", "09:10")]),
                (sessions_popup.EARLIER, [("old", "01.09"), ("last-year", "31.12.2025")]),
            ],
        )

    def test_a_clock_that_ran_ahead_still_reads_as_today(self):
        from datetime import datetime

        from ai_agent.ui import sessions_popup
        from ai_agent.ui.sessions_popup import Entry, day_groups

        now = datetime(2026, 10, 8, 15, 0).timestamp()
        ahead = Entry("ahead", "Ahead", datetime(2026, 10, 9, 1, 0).timestamp())
        self.assertEqual(day_groups([ahead], now)[0][0], sessions_popup.TODAY)

    def test_the_open_conversation_is_marked_by_the_state(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        state = ConversationState(store=SessionStore(root))
        state.add("user", "первый")
        past = state.session_identifier
        state.start_new()
        state.add("user", "второй")
        listed = {entry[0]: entry[3] for entry in state.recent()}
        self.assertEqual(listed, {past: False, state.session_identifier: True})
        self.assertEqual(state.title, "второй")


if __name__ == "__main__":
    unittest.main()
