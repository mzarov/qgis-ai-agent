import unittest
from unittest.mock import patch

from ai_agent.qgis_tools.common.editing import edit_session
from tests.test_edit import EditableLayer


class EditSessionTest(unittest.TestCase):
    def setUp(self):
        self.layer = EditableLayer(["value"], [(1, {"value": "original"})])

    def test_success_commits_once_and_closes_session(self):
        with edit_session(self.layer, "the test edit"):
            self.layer.changeAttributeValue(1, 0, "changed")
        self.assertEqual(self.layer.commit_calls, 1)
        self.assertFalse(self.layer.editing)
        self.assertFalse(self.layer.rolled_back)
        self.assertEqual(self.layer._features[0].attributes["value"], "changed")

    def test_failure_after_one_change_restores_uncommitted_values(self):
        with self.assertRaisesRegex(ValueError, "conversion failed"), edit_session(self.layer, "the test edit"):
            self.layer.changeAttributeValue(1, 0, "changed")
            raise TypeError("conversion failed")
        self.assertEqual(self.layer.commit_calls, 0)
        self.assertFalse(self.layer.editing)
        self.assertEqual(self.layer._features[0].attributes["value"], "original")

    def test_refused_start_does_not_touch_the_layer(self):
        with (
            patch.object(self.layer, "startEditing", return_value=False),
            self.assertRaisesRegex(ValueError, "cannot be switched into editing mode"),
            edit_session(self.layer, "the test edit"),
        ):
            self.fail("must not mutate a read-only layer")
        self.assertEqual(self.layer.commit_calls, 0)
        self.assertFalse(self.layer.rolled_back)

    def test_commit_exception_warns_about_provider_partial_changes(self):
        with (
            patch.object(self.layer, "commitChanges", side_effect=RuntimeError("connection lost")),
            self.assertRaises(ValueError) as caught,
            edit_session(self.layer, "the test edit"),
        ):
            self.layer.changeAttributeValue(1, 0, "changed")
        self.assertTrue(self.layer.rolled_back)
        self.assertIn("connection lost", str(caught.exception))
        self.assertIn("may already contain partial changes", str(caught.exception))

    def test_rollback_refusal_does_not_claim_recovery(self):
        with (
            patch.object(self.layer, "rollBack", return_value=False),
            self.assertRaises(ValueError) as caught,
            edit_session(self.layer, "the test edit"),
        ):
            raise ValueError("mutation failed")
        self.assertIn("mutation failed", str(caught.exception))
        self.assertIn("could not roll back", str(caught.exception))
        self.assertNotIn("were discarded", str(caught.exception))

    def test_rollback_exception_preserves_both_failures(self):
        with (
            patch.object(self.layer, "rollBack", side_effect=RuntimeError("rollback unavailable")),
            self.assertRaises(ValueError) as caught,
            edit_session(self.layer, "the test edit"),
        ):
            raise ValueError("mutation failed")
        self.assertIn("mutation failed", str(caught.exception))
        self.assertIn("rollback unavailable", str(caught.exception))
        self.assertNotIn("were discarded", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
