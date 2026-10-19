import ast
import json
import pathlib
import unittest
from unittest import mock

from ai_agent.core import usage_stats


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
            self.assertEqual(posted, [], "today is not over yet")
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
                "runs",
                "applies",
                "failures",
                "tools",
                "skills",
            },
        )
        self.assertEqual((sent["provider"], sent["locale"], sent["plugin"]), ("local", "ru", "0.4.0"))
        self.assertIn(sent["os"], ("macos", "windows", "linux", "other"))


if __name__ == "__main__":
    unittest.main()
