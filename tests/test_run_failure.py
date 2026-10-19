import unittest

from ai_agent.core.agent.run_failure import (
    CONFIGURED_ENDPOINT,
    RUN_FAILED,
    address_label,
    explain_run_failure,
    host_label,
)
from ai_agent.core.llm import failure_kinds as kinds


class LabelTest(unittest.TestCase):
    def test_the_host_drops_the_scheme_credentials_and_path(self):
        with_credentials = "https://user:secret@api.example.com:8443/v1/"  # pragma: allowlist secret
        self.assertEqual(host_label(with_credentials), "api.example.com:8443")

    def test_the_address_keeps_the_path_but_never_the_query(self):
        self.assertEqual(address_label("https://api.example.com/raw/v/?key=secret#top"), "api.example.com/raw/v")

    def test_an_unreadable_address_is_named_by_its_role(self):
        self.assertEqual(host_label(""), CONFIGURED_ENDPOINT)
        self.assertEqual(address_label("http://[broken"), CONFIGURED_ENDPOINT)


class ExplainTest(unittest.TestCase):
    def test_a_wrong_path_names_the_address_and_the_model_and_holds_retry_back(self):
        failure = explain_run_failure(kinds.NOT_FOUND, "404", "https://api.example.com/raw/v", "deepseek")
        self.assertIn("api.example.com/raw/v", failure.detail)
        self.assertIn("deepseek", failure.detail)
        self.assertTrue(failure.fixed_in_settings)
        self.assertFalse(failure.retry_helps)

    def test_a_refused_key_and_a_missing_setup_wait_for_the_settings(self):
        self.assertFalse(explain_run_failure(kinds.AUTH, "401").retry_helps)
        self.assertFalse(explain_run_failure(kinds.SETUP, "No API URL").retry_helps)

    def test_passing_failures_may_be_retried(self):
        for kind in (kinds.CONNECTION, kinds.TIMEOUT, kinds.BUSY, kinds.QUOTA):
            with self.subTest(kind=kind):
                self.assertTrue(explain_run_failure(kind, "x", "http://localhost:9").retry_helps)

    def test_an_unknown_kind_shows_the_message_itself(self):
        failure = explain_run_failure("", "Something odd")
        self.assertEqual((failure.kind, failure.title, failure.detail), (kinds.OTHER, RUN_FAILED, "Something odd"))
        self.assertTrue(failure.retry_helps)


if __name__ == "__main__":
    unittest.main()
