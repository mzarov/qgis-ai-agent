import os
import shutil
import tempfile
import time
import unittest

from ai_agent.core.state.conversation import ConversationState
from ai_agent.core.state.session import MAX_MESSAGES, Session, shorten
from ai_agent.core.state.store import MAX_SESSIONS, SessionStore, current_project_key


class SessionTest(unittest.TestCase):
    def test_new_session_is_empty(self):
        self.assertTrue(Session.create("/p.qgz").is_empty)

    def test_identifiers_differ(self):
        self.assertNotEqual(Session.create("/p").identifier, Session.create("/p").identifier)

    def test_title_comes_from_first_user_message(self):
        session = Session.create("/p")
        session.add("user", "какие у меня слои?")
        session.add("assistant", "вот такие")
        self.assertEqual(session.title, "какие у меня слои?")

    def test_assistant_first_leaves_title_empty(self):
        session = Session.create("/p")
        session.add("assistant", "привет")
        self.assertEqual(session.display_title(), "Untitled")

    def test_long_title_is_shortened(self):
        self.assertTrue(shorten("с" * 200).endswith("…"))
        self.assertLessEqual(len(shorten("с" * 200)), 49)

    def test_blank_message_is_ignored(self):
        session = Session.create("/p")
        session.add("user", "   ")
        self.assertTrue(session.is_empty)

    def test_message_cap(self):
        session = Session.create("/p")
        for index in range(MAX_MESSAGES + 30):
            session.add("user", f"сообщение {index}")
        self.assertEqual(len(session.messages), MAX_MESSAGES)
        self.assertIn(str(MAX_MESSAGES + 29), session.messages[-1]["content"])

    def test_round_trip(self):
        session = Session.create("/p.qgz")
        session.add("user", "вопрос")
        restored = Session.from_dict(session.to_dict())
        self.assertEqual(restored.identifier, session.identifier)
        self.assertEqual(restored.project, "/p.qgz")
        self.assertEqual(restored.messages, session.messages)

    def test_broken_payload_gives_none(self):
        self.assertIsNone(Session.from_dict({"messages": []}))

    def test_unknown_project_falls_back(self):
        self.assertEqual(Session.create("").project, "no project")


class SessionStoreTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.store = SessionStore(self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _saved(self, project="/p.qgz", text="вопрос"):
        session = Session.create(project)
        session.add("user", text)
        self.store.save(session)
        return session

    def test_save_and_load(self):
        session = self._saved()
        loaded = self.store.load(session.identifier)
        self.assertEqual(loaded.messages, session.messages)

    def test_empty_session_is_not_saved(self):
        session = Session.create("/p")
        self.store.save(session)
        self.assertIsNone(self.store.load(session.identifier))

    def test_recent_filters_by_project(self):
        self._saved("/a.qgz", "про а")
        self._saved("/b.qgz", "про б")
        titles = [item.title for item in self.store.recent("/a.qgz")]
        self.assertEqual(titles, ["про а"])

    def test_recent_is_newest_first(self):
        first = self._saved(text="первый")
        time.sleep(0.01)
        second = self._saved(text="второй")
        self.assertEqual(self.store.recent("/p.qgz")[0].identifier, second.identifier)
        self.assertEqual(self.store.recent("/p.qgz")[1].identifier, first.identifier)

    def test_delete(self):
        session = self._saved()
        self.store.delete(session.identifier)
        self.assertIsNone(self.store.load(session.identifier))

    def test_missing_session_gives_none(self):
        self.assertIsNone(self.store.load("нет-такого"))

    def test_broken_file_is_skipped(self):
        with open(os.path.join(self.root, "битый.json"), "w", encoding="utf-8") as handle:
            handle.write("не json")
        self._saved()
        self.assertEqual(len(self.store.recent("/p.qgz")), 1)

    def test_old_sessions_are_trimmed(self):
        for index in range(MAX_SESSIONS + 5):
            self._saved(text=f"вопрос {index}")
        self.assertLessEqual(len(self.store.recent("/p.qgz", limit=999)), MAX_SESSIONS)

    def test_unwritable_root_does_not_raise(self):
        SessionStore("/proc/недоступно/сессии").save(self._saved())


class ConversationStateTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.store = SessionStore(self.root)
        self.state = ConversationState(window_limit=4, store=self.store)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_message_reaches_both_window_and_session(self):
        self.state.add("user", "привет")
        self.assertEqual(self.state.window()[-1]["content"], "привет")
        self.assertEqual(self.state.messages[-1]["content"], "привет")

    def test_message_is_persisted_at_once(self):
        self.state.add("user", "вопрос")
        self.assertEqual(self.store.recent(current_project_key())[0].title, "вопрос")

    def test_window_is_capped_but_session_is_not(self):
        for index in range(10):
            self.state.add("user", f"сообщение {index}")
        self.assertEqual(len(self.state.window()), 4)
        self.assertEqual(len(self.state.messages), 10)

    def test_new_conversation_starts_blank(self):
        self.state.add("user", "старое")
        self.state.start_new()
        self.assertEqual(self.state.messages, [])
        self.assertEqual(self.state.window(), [])

    def test_previous_conversation_survives_switch(self):
        self.state.add("user", "старое")
        self.state.start_new()
        self.assertEqual(self.store.recent(current_project_key())[0].title, "старое")

    def test_restore_brings_messages_back(self):
        self.state.add("user", "первый вопрос")
        identifier = self.store.recent(current_project_key())[0].identifier
        self.state.start_new()
        self.assertTrue(self.state.restore(identifier))
        self.assertEqual(self.state.messages[-1]["content"], "первый вопрос")

    def test_restore_refills_model_window(self):
        self.state.add("user", "вопрос")
        self.state.add("assistant", "ответ")
        identifier = self.store.recent(current_project_key())[0].identifier
        self.state.start_new()
        self.state.restore(identifier)
        self.assertEqual([item["role"] for item in self.state.window()], ["user", "assistant"])

    def test_restore_window_respects_limit(self):
        for index in range(10):
            self.state.add("user", f"сообщение {index}")
        identifier = self.store.recent(current_project_key())[0].identifier
        self.state.start_new()
        self.state.restore(identifier)
        self.assertEqual(len(self.state.window()), 4)

    def test_restore_of_unknown_session_changes_nothing(self):
        self.state.add("user", "текущее")
        self.assertFalse(self.state.restore("нет-такого"))
        self.assertEqual(self.state.messages[-1]["content"], "текущее")

    def test_recent_gives_identifier_and_title(self):
        self.state.add("user", "про слои")
        self.assertEqual([title for _, title in self.state.recent()], ["про слои"])

    def test_empty_conversation_is_not_listed(self):
        self.state.save()
        self.assertEqual(self.state.recent(), [])

    def test_repeated_new_does_not_pile_up_empties(self):
        self.state.start_new()
        self.state.start_new()
        self.assertEqual(self.state.recent(), [])


if __name__ == "__main__":
    unittest.main()
