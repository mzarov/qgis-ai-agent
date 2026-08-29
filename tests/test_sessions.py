import os
import shutil
import tempfile
import time
import unittest

from qgis_ai_agent.core.state import conversation as conversation_module
from qgis_ai_agent.core.state.conversation import ConversationState
from qgis_ai_agent.core.state.session import MAX_MESSAGES, Session, shorten
from qgis_ai_agent.core.state.store import MAX_SESSIONS, SessionStore, current_project_key
from qgis_ai_agent.qgis_tools.common import persistence
from qgis_ai_agent.qgis_tools.common.project_identity import STORAGE_PREFIX, project_identity, restore_project_identity


class Signal:
    def __init__(self):
        self._slots = []

    def connect(self, slot):
        self._slots.append(slot)

    def emit(self):
        for slot in self._slots:
            slot()


class Project:
    def __init__(self, path=""):
        self.path = path
        self.cleared = Signal()

    def fileName(self):
        return self.path


class StorageProject(Project):
    def absoluteFilePath(self):
        return ""

    def projectStorage(self):
        return object()


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
        session.add("assistant", "answer")
        self.store.save(session)
        self.store.delete(session.identifier)
        self.assertIsNone(self.store.load(session.identifier))

    def test_missing_session_gives_none(self):
        self.assertIsNone(self.store.load("нет-такого"))

    def test_broken_file_is_skipped(self):
        with open(os.path.join(self.root, "битый.json"), "w", encoding="utf-8") as handle:
            handle.write("не json")
        self._saved()
        self.assertEqual(len(self.store.recent("/p.qgz")), 1)

    def test_valid_json_with_a_wrong_message_shape_is_safely_loaded(self):
        path = os.path.join(self.root, "badshape.json")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write('{"identifier":"badshape","project":"/p.qgz","messages":42}')
        loaded = self.store.load("badshape")
        self.assertEqual(loaded.messages, [])

    def test_a_corrupt_primary_recovers_the_previous_valid_session(self):
        session = self._saved(text="first")
        session.add("assistant", "second")
        self.store.save(session)
        with open(self.store._path(session.identifier), "w", encoding="utf-8") as handle:
            handle.write("not json")
        restored = self.store.load(session.identifier)
        self.assertEqual([item["content"] for item in restored.messages], ["first"])

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

    def test_current_session_identity_is_read_only_state(self):
        self.assertTrue(self.state.session_identifier)
        self.assertEqual(self.state.project_key, current_project_key())

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

    def test_restore_refuses_a_session_owned_by_another_project(self):
        other = Session.create("/another/project.qgz")
        other.add("user", "private")
        self.store.save(other)
        self.state.add("user", "current")
        self.assertFalse(self.state.restore(other.identifier))
        self.assertEqual(self.state.messages[-1]["content"], "current")

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

    def test_sync_project_adopts_a_fresh_session_only_when_the_project_changes(self):
        saved_key = conversation_module.current_project_key
        keys = iter((self.state.project_key, "/different/project.qgz"))
        conversation_module.current_project_key = lambda: next(keys)
        try:
            identifier = self.state.session_identifier
            self.assertFalse(self.state.sync_project())
            self.assertTrue(self.state.sync_project())
            self.assertNotEqual(self.state.session_identifier, identifier)
            self.assertEqual(self.state.project_key, "/different/project.qgz")
            self.assertEqual(self.state.messages, [])
        finally:
            conversation_module.current_project_key = saved_key

    def test_forced_project_sync_starts_fresh_even_when_the_key_is_unchanged(self):
        self.state.add("user", "stale plan context")
        identifier = self.state.session_identifier
        saved_key = conversation_module.current_project_key
        conversation_module.current_project_key = lambda: self.state.project_key
        try:
            self.assertTrue(self.state.sync_project(force_new=True))
        finally:
            conversation_module.current_project_key = saved_key
        self.assertNotEqual(self.state.session_identifier, identifier)
        self.assertEqual(self.state.messages, [])


class ProjectIdentityTest(unittest.TestCase):
    def test_saved_projects_with_the_same_basename_do_not_collide(self):
        first = project_identity(Project("/clients/acme/map.qgz"))
        second = project_identity(Project("/clients/other/map.qgz"))
        self.assertNotEqual(first, second)

    def test_relative_saved_path_is_canonical(self):
        key = project_identity(Project("projects/../map.qgz"))
        self.assertTrue(os.path.isabs(key))
        self.assertEqual(key, os.path.realpath(os.path.abspath("map.qgz")))

    def test_unsaved_identity_is_stable_until_the_project_is_cleared(self):
        project = Project()
        first = project_identity(project)
        self.assertEqual(project_identity(project), first)
        project.cleared.emit()
        self.assertNotEqual(project_identity(project), first)

    def test_two_unsaved_projects_do_not_share_an_identity(self):
        self.assertNotEqual(project_identity(Project()), project_identity(Project()))

    def test_storage_uri_is_hashed_without_credentials_and_is_order_independent(self):
        first_uri = (
            "postgresql://alice:first@DB.EXAMPLE:5432/projects?password=first&schema=maps&project=city&dbname=gis"
        )
        second_uri = (
            "postgresql://bob:second@db.example:5432/projects?dbname=gis&project=city&schema=maps&password=second"
        )
        first = project_identity(StorageProject(first_uri))
        second = project_identity(StorageProject(second_uri))
        self.assertEqual(first, second)
        self.assertTrue(first.startswith(STORAGE_PREFIX))
        for secret in ("alice", "first", "bob", "second", "db.example"):
            self.assertNotIn(secret, first)

    def test_different_stored_projects_have_different_identities(self):
        first = project_identity(StorageProject("geopackage:/data/projects.gpkg?projectName=first"))
        second = project_identity(StorageProject("geopackage:/data/projects.gpkg?projectName=second"))
        self.assertNotEqual(first, second)

    def test_qgis_project_storage_supports_custom_uri_schemes(self):
        first = project_identity(StorageProject("cloud-store:workspace/map?project=city&authcfg=first"))
        second = project_identity(StorageProject("cloud-store:workspace/map?authcfg=second&project=city"))
        self.assertEqual(first, second)
        self.assertTrue(first.startswith(STORAGE_PREFIX))
        self.assertNotIn("cloud-store", first)

    def test_unsaved_identity_can_be_restored_after_a_snapshot_read(self):
        project = Project()
        original = project_identity(project)
        project.cleared.emit()
        self.assertNotEqual(project_identity(project), original)
        restore_project_identity(project, original)
        self.assertEqual(project_identity(project), original)


class AtomicPersistenceTest(unittest.TestCase):
    def test_failed_replacement_keeps_the_previous_primary_readable(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "state.json")
            persistence.atomic_write_json(path, {"version": 1})
            saved_replace = persistence.os.replace

            def fail_primary(source, target):
                if target == path:
                    raise OSError("simulated interruption")
                return saved_replace(source, target)

            persistence.os.replace = fail_primary
            try:
                with self.assertRaises(OSError):
                    persistence.atomic_write_json(path, {"version": 2})
            finally:
                persistence.os.replace = saved_replace
            self.assertEqual(persistence.read_json(path), {"version": 1})
            self.assertFalse(any(name.endswith(".tmp") for name in os.listdir(root)))


if __name__ == "__main__":
    unittest.main()
