import ast
import json
import pathlib
import unittest
from unittest import mock

from ai_agent.core import settings, usage_stats


class MemorySettings:
    values: dict = {}

    def value(self, key, default=None, type=None):
        return MemorySettings.values.get(key, default)

    def setValue(self, key, value):
        MemorySettings.values[key] = value

    def remove(self, key):
        MemorySettings.values.pop(key, None)


class Reply:
    def __init__(self, status=204, error=0):
        self.status, self.code = status, error
        self.finished = mock.Mock()
        self.finished.connect = lambda slot: setattr(self, "slot", slot)

    def attribute(self, _attribute):
        return self.status

    def error(self):
        return usage_stats.QNetworkReply.NetworkError.NoError if self.code == 0 else self.code

    def errorString(self):
        return "offline"

    def deleteLater(self):
        pass


class UsageStatsTest(unittest.TestCase):
    def setUp(self):
        MemorySettings.values = {}
        for target, value in (
            ("QgsSettings", MemorySettings),
            ("COLLECTOR_URL", "https://stats.example/"),
            ("get_api_url", lambda: "http://localhost:11434/v1"),
            ("get_dialect", lambda: "openai"),
            ("has_saved_model", lambda: True),
            ("plugin_version", lambda: "0.4.0"),
            ("locale_code", lambda: "ru"),
        ):
            patcher = mock.patch.object(usage_stats, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.today = "2026-10-17"
        self.stats = usage_stats.UsageStats(lambda: self.today)

    def counts(self):
        return json.loads(MemorySettings.values.get(usage_stats.COUNTS_KEY, "{}"))

    def test_nothing_is_counted_before_the_notice_and_counting_is_on_after_it(self):
        self.stats.note("runs")
        self.assertEqual(MemorySettings.values, {})
        self.assertTrue(usage_stats.should_notify())
        self.assertFalse(usage_stats.enabled())
        usage_stats.mark_noticed()
        self.assertFalse(usage_stats.should_notify(), "the notice comes once")
        self.assertTrue(usage_stats.enabled(), "on by default once the user was told")
        self.stats.note("runs")
        self.assertEqual(self.counts()["runs"], 1)

    def test_a_no_in_the_notice_stops_counting_and_takes_back_the_counts(self):
        usage_stats.mark_noticed()
        self.stats.note("runs")
        usage_stats.set_consent(False)
        self.assertNotIn(usage_stats.COUNTS_KEY, MemorySettings.values)
        self.stats.note("runs")
        self.assertNotIn(usage_stats.COUNTS_KEY, MemorySettings.values)
        self.assertFalse(usage_stats.enabled())
        usage_stats.set_consent(True)
        self.assertTrue(usage_stats.enabled(), "Settings turns it back on")

    def test_a_choice_made_in_settings_needs_no_notice(self):
        usage_stats.set_consent(False)
        self.assertFalse(usage_stats.should_notify())
        usage_stats.set_consent(True)
        self.assertFalse(usage_stats.should_notify())
        self.assertTrue(usage_stats.enabled())

    def test_no_collector_means_no_notice_and_no_counting(self):
        usage_stats.mark_noticed()
        with mock.patch.object(usage_stats, "COLLECTOR_URL", ""):
            MemorySettings.values.pop(usage_stats.NOTICE_KEY)
            self.assertFalse(usage_stats.should_notify())
            usage_stats.set_consent(True)
            self.stats.note("runs")
        self.assertNotIn(usage_stats.COUNTS_KEY, MemorySettings.values)

    def test_a_day_the_plugin_loaded_goes_out_without_runs(self):
        usage_stats.mark_noticed()
        self.stats.note(usage_stats.ACTIVE)
        manager = mock.Mock(post=lambda request, body: Reply())
        self.today = "2026-10-18"
        with (
            mock.patch.object(usage_stats.QgsNetworkAccessManager, "instance", return_value=manager),
            mock.patch.object(usage_stats, "payload", wraps=usage_stats.payload) as built,
        ):
            self.stats.flush()
        install, day, counts = built.call_args.args
        self.assertEqual(day, "2026-10-17")
        body = usage_stats.payload(install, day, counts)
        self.assertEqual((body["runs"], body["applies"], body["tools"]), (0, 0, {}))

    def test_a_day_waits_a_week_for_the_next_start(self):
        usage_stats.mark_noticed()
        self.stats.note("runs")
        posted = []
        manager = mock.Mock(post=lambda request, body: posted.append(body) or Reply())
        self.today = "2026-10-24"
        with mock.patch.object(usage_stats.QgsNetworkAccessManager, "instance", return_value=manager):
            self.stats.flush()
        self.assertEqual(len(posted), 1)

    def test_the_test_profile_never_counts(self):
        # The profile helper runs before the plugin is importable, so it spells the setting out.
        source = (pathlib.Path(__file__).parent / "real_qgis_smoke.py").read_text(encoding="utf-8")
        assignment = next(
            node
            for node in ast.parse(source).body
            if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "USAGE_OPT_OUT"
        )
        self.assertEqual(ast.literal_eval(assignment.value), (usage_stats.CONSENT_KEY, usage_stats.CONSENT_NO))

    def test_names_are_counted_and_anything_else_is_dropped(self):
        usage_stats.set_consent(True)
        for kind, name in (("runs", ""), ("tools", "query_layer"), ("tools", "query_layer"), ("tools", "Bad Name!")):
            self.stats.note(kind, name)
        self.assertEqual(self.counts()["tools"], {"query_layer": 2})
        self.assertEqual(self.counts()["runs"], 1)

    def test_a_day_that_is_over_is_sent_once_and_cleared(self):
        usage_stats.set_consent(True)
        self.stats.note("runs")
        self.stats.note("skills", "style")
        posted = []
        manager = mock.Mock()
        manager.post = lambda request, body: posted.append(request) or Reply()
        with mock.patch.object(usage_stats.QgsNetworkAccessManager, "instance", return_value=manager):
            self.stats.flush()
            self.assertEqual(posted, [], "today waits for its delay")
            self.today = "2026-10-18"
            self.stats.flush()
        self.assertIn(usage_stats.PENDING_KEY, MemorySettings.values)
        self.assertIsNotNone(self.stats._reply, "the day that ended went out")
        self.stats._sent()
        self.assertNotIn(usage_stats.PENDING_KEY, MemorySettings.values)

    def test_a_failed_send_keeps_the_day_for_the_next_try(self):
        usage_stats.set_consent(True)
        self.stats.note("runs")
        self.today = "2026-10-18"
        manager = mock.Mock(post=lambda request, body: Reply(status=500, error=5))
        with mock.patch.object(usage_stats.QgsNetworkAccessManager, "instance", return_value=manager):
            self.stats.flush()
        self.stats._sent()
        self.assertIn(usage_stats.PENDING_KEY, MemorySettings.values)

    def test_a_day_the_collector_would_refuse_is_dropped_not_retried(self):
        usage_stats.set_consent(True)
        self.stats.note("runs")
        self.today = "2026-10-25"
        self.stats.flush()
        self.assertIsNone(self.stats._reply, "a week-old day went out")
        self.assertNotIn(usage_stats.PENDING_KEY, MemorySettings.values)
        self.today = "2026-10-26"
        self.stats.note("runs")
        self.today = "2026-10-27"
        manager = mock.Mock(post=lambda request, body: Reply(status=400, error=302))
        with mock.patch.object(usage_stats.QgsNetworkAccessManager, "instance", return_value=manager):
            self.stats.flush()
        self.stats._sent()
        self.assertNotIn(usage_stats.PENDING_KEY, MemorySettings.values, "a refused day came back")

    def send_all(self, replies):
        days = []

        def post(request, body):
            days.append(json.loads(bytes(body))["day"])
            return replies.pop(0)

        manager = mock.Mock(post=post)
        with (
            mock.patch.object(usage_stats.QgsNetworkAccessManager, "instance", return_value=manager),
            mock.patch.object(usage_stats, "QByteArray", side_effect=lambda raw: raw),
        ):
            self.stats.flush()
            while self.stats._reply is not None:
                self.stats._sent()
        return days

    def test_today_goes_out_a_minute_after_a_change_and_stays_counted(self):
        usage_stats.mark_noticed()
        self.stats.note(usage_stats.ACTIVE)
        self.assertTrue(self.stats._timer.isActive(), "the first notice gets a minute to be answered")
        self.stats.note("runs")
        self.assertEqual(self.stats._timer.started, 1, "more counts do not push the send back")
        sent = []

        def post(request, body):
            sent.append(json.loads(bytes(body)))
            return Reply()

        manager = mock.Mock(post=post)
        with (
            mock.patch.object(usage_stats.QgsNetworkAccessManager, "instance", return_value=manager),
            mock.patch.object(usage_stats, "QByteArray", side_effect=lambda raw: raw),
        ):
            self.stats._timer.fire()
            self.stats._sent()
            self.assertEqual([(ping["day"], ping["runs"]) for ping in sent], [("2026-10-17", 1)])
            self.assertEqual(self.counts()["runs"], 1, "the day goes out whole again once it is over")
            self.stats.note("runs")
            self.stats._timer.fire()
            self.stats._sent()
            self.today = "2026-10-18"
            self.stats.flush()
            self.stats._sent()
        self.assertEqual([(ping["day"], ping["runs"]) for ping in sent], [("2026-10-17", runs) for runs in (1, 2, 2)])
        self.assertNotIn(usage_stats.PENDING_KEY, MemorySettings.values)

    def test_today_never_leaves_once_counting_is_turned_off(self):
        usage_stats.mark_noticed()
        self.stats.note(usage_stats.ACTIVE)
        usage_stats.set_consent(False)
        manager = mock.Mock()
        with mock.patch.object(usage_stats.QgsNetworkAccessManager, "instance", return_value=manager):
            self.stats._timer.fire()
        manager.post.assert_not_called()

    def test_a_day_that_ends_while_today_is_on_its_way_still_goes_out_whole(self):
        usage_stats.set_consent(True)
        self.stats.note("runs")
        manager = mock.Mock(post=lambda request, body: Reply())
        with mock.patch.object(usage_stats.QgsNetworkAccessManager, "instance", return_value=manager):
            self.stats._timer.fire()
            self.today = "2026-10-18"
            self.stats.note("runs")
            self.assertIn(usage_stats.PENDING_KEY, MemorySettings.values)
            self.stats._sent()
        waiting = json.loads(MemorySettings.values[usage_stats.PENDING_KEY])
        self.assertEqual([entry["day"] for entry in waiting], ["2026-10-17"], "the earlier ping held part of it")
        self.assertIsNotNone(self.stats._reply, "the finished day follows at once")

    def test_unloading_stops_the_wait(self):
        usage_stats.set_consent(True)
        self.stats.note("runs")
        self.stats.stop()
        self.assertFalse(self.stats._timer.isActive())

    def test_days_missed_offline_go_out_oldest_first(self):
        usage_stats.set_consent(True)
        for day in ("2026-10-17", "2026-10-18", "2026-10-19"):
            self.today = day
            self.stats.note("runs")
        self.today = "2026-10-20"
        self.assertEqual(self.send_all([Reply(), Reply(), Reply()]), ["2026-10-17", "2026-10-18", "2026-10-19"])
        self.assertNotIn(usage_stats.PENDING_KEY, MemorySettings.values)

    def test_only_the_latest_missed_days_wait(self):
        usage_stats.set_consent(True)
        for number in range(10, 18):
            self.today = f"2026-10-{number}"
            self.stats.note("runs")
        self.today = "2026-10-18"
        sent = self.send_all([Reply() for _ in range(usage_stats.MAX_PENDING_DAYS)])
        self.assertEqual(sent, [f"2026-10-{number}" for number in range(18 - usage_stats.MAX_PENDING_DAYS, 18)])

    def test_a_day_saved_by_the_previous_version_still_goes_out(self):
        usage_stats.set_consent(True)
        MemorySettings.values[usage_stats.PENDING_KEY] = json.dumps({"day": "2026-10-16", "counts": {"runs": 2}})
        self.assertEqual(self.send_all([Reply()]), ["2026-10-16"])

    def test_a_body_the_collector_turns_away_is_dropped_and_a_busy_one_waits(self):
        usage_stats.set_consent(True)
        for day in ("2026-10-17", "2026-10-18"):
            self.today = day
            self.stats.note("runs")
        self.today = "2026-10-19"
        sent = self.send_all([Reply(status=413, error=299), Reply(status=429, error=299)])
        self.assertEqual(sent, ["2026-10-17", "2026-10-18"])
        waiting = json.loads(MemorySettings.values[usage_stats.PENDING_KEY])
        self.assertEqual([entry["day"] for entry in waiting], ["2026-10-18"])

    def test_the_ping_carries_counts_and_versions_only(self):
        sent = usage_stats.payload("1f0e…", "2026-10-17", {"runs": 3, "applies": 1, "tools": {"query_layer": 2}})
        self.assertEqual(
            set(sent),
            {
                "v",
                "install",
                "day",
                "plugin",
                "qgis",
                "os",
                "locale",
                "provider",
                "dialect",
                "configured",
                "runs",
                "applies",
                "failures",
                "tools",
                "tool_errors",
                "skills",
            },
        )
        self.assertEqual(sent["v"], 2)
        self.assertEqual((sent["provider"], sent["locale"], sent["plugin"]), ("local", "ru", "0.4.0"))
        self.assertIn(sent["os"], ("macos", "windows", "linux", "other"))
        self.assertIs(sent["configured"], True)
        self.assertNotIn("localhost", json.dumps(sent), "the address itself never goes out")

    def test_failed_tool_calls_are_counted_beside_the_calls(self):
        usage_stats.set_consent(True)
        for kind, name in (("tools", "run_python"), ("tools", "run_python"), ("tool_errors", "run_python")):
            self.stats.note(kind, name)
        sent = usage_stats.payload("1f0e…", "2026-10-17", self.counts())
        self.assertEqual((sent["tools"], sent["tool_errors"]), ({"run_python": 2}, {"run_python": 1}))
        self.assertEqual(usage_stats.payload("1f0e…", "2026-10-17", {"runs": 1})["tool_errors"], {})


class SavedModelTest(unittest.TestCase):
    def setUp(self):
        MemorySettings.values = {}
        patcher = mock.patch.object(settings, "QgsSettings", MemorySettings)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_defaults_alone_do_not_count_as_a_configured_model(self):
        self.assertFalse(settings.has_saved_model())
        MemorySettings.values["ai_agent/api_url"] = "http://localhost:11434/v1"
        self.assertFalse(settings.has_saved_model(), "an address without a model")
        MemorySettings.values["ai_agent/model"] = "  "
        self.assertFalse(settings.has_saved_model(), "a blank model name")
        MemorySettings.values["ai_agent/model"] = "qwen3"
        self.assertTrue(settings.has_saved_model())


if __name__ == "__main__":
    unittest.main()
