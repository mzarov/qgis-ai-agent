import unittest
from unittest import mock

from qgis.PyQt.QtWidgets import QWidget

from ai_agent.core.agent.loop import AgentLoop
from ai_agent.core.agent.skills import load_skill, requested_skills
from ai_agent.core.llm.transport import ToolCall
from ai_agent.qgis_tools.processing import utils as processing_utils
from ai_agent.ui import settings_fields
from ai_agent.ui.composer import MENTION, Composer, mention_query, mention_text
from ai_agent.ui.conversation import ConversationView
from ai_agent.ui.skill_popup import SkillPopup

LAYERS = [("Main roads", "line, EPSG:4326", "layer"), ("rivers", "line", "layer")]


def call(tool, **arguments):
    return ToolCall(id="c1", name=tool, arguments=arguments)


class FailedRunKeepsTheQueueTest(unittest.TestCase):
    def setUp(self):
        self.loop = AgentLoop()
        self.loop._loaded_skills = ["inspect", "style"]
        self.loop._batch._calls.append(call("set_opacity", layer_name="roads", opacity=0.5))
        self.cards = []
        self.errors = []
        self.loop.confirm_needed.connect(lambda calls, text: self.cards.append(list(calls)))
        self.loop.failed.connect(self.errors.append)

    def test_a_transport_error_still_offers_the_prepared_steps(self):
        self.loop._fail("HTTP 401")
        self.assertEqual(self.errors, ["HTTP 401"])
        self.assertEqual(len(self.cards), 1)
        self.assertTrue(self.loop.has_pending_writes)

    def test_a_failed_staged_run_applies_as_a_final_batch(self):
        self.loop._staged = True
        self.loop._fail("timeout")
        self.assertFalse(self.loop._staged)

    def test_a_final_answer_is_never_a_stage(self):
        self.loop._staged = True
        self.loop._complete("done")
        self.assertFalse(self.loop._staged)
        self.assertEqual(len(self.cards), 1)


class LoadSeveralSkillsTest(unittest.TestCase):
    def test_names_and_the_older_single_name_are_both_read(self):
        self.assertEqual(requested_skills({"names": ["style", "osm", "style"]}), ["style", "osm"])
        self.assertEqual(requested_skills({"name": "style"}), ["style"])
        self.assertEqual(requested_skills({"names": "style"}), ["style"])
        self.assertEqual(requested_skills({}), [])

    def test_several_skills_load_in_one_call(self):
        loaded = ["inspect"]
        result, fresh = load_skill(call("load_skill", names=["style", "processing"]), loaded)
        self.assertTrue(result.ok)
        self.assertEqual(fresh, ["style", "processing"])
        self.assertIn("run_processing", result.payload["tools"])
        self.assertIn("set_symbol", result.payload["tools"])

    def test_an_unknown_name_next_to_a_known_one_is_reported_not_fatal(self):
        result, fresh = load_skill(call("load_skill", names=["style", "nope"]), ["inspect"])
        self.assertTrue(result.ok)
        self.assertEqual(result.payload["not_found"], ["nope"])
        self.assertEqual(fresh, ["style"])

    def test_only_unknown_names_are_an_error(self):
        result, fresh = load_skill(call("load_skill", names=["nope"]), ["inspect"])
        self.assertFalse(result.ok)
        self.assertEqual(fresh, [])


class BudgetParsingTest(unittest.TestCase):
    def test_readable_forms(self):
        for raw, expected in (("200000", 200000), ("200 000", 200000), ("200k", 200000), ("1.5m", 1500000), ("", 0)):
            with self.subTest(raw=raw):
                self.assertEqual(settings_fields.parsed_budget(raw), expected)

    def test_unreadable_and_negative_values_are_refused(self):
        for raw in ("ten", "-5", "10x", "k"):
            with self.subTest(raw=raw):
                self.assertIsNone(settings_fields.parsed_budget(raw))


class EmptyOutputTest(unittest.TestCase):
    def test_an_empty_output_layer_is_named(self):
        layer = mock.Mock()
        layer.name.return_value = "buffer"
        with (
            mock.patch.object(processing_utils, "resolve_layer", return_value=layer),
            mock.patch.object(processing_utils, "feature_count_if_cheap", return_value=0),
        ):
            warnings = processing_utils.empty_output_warnings({"OUTPUT": "id1"})
        self.assertEqual(len(warnings), 1)
        self.assertIn("'buffer' has no features", warnings[0])

    def test_a_populated_output_gives_no_warning(self):
        with (
            mock.patch.object(processing_utils, "resolve_layer", return_value=mock.Mock()),
            mock.patch.object(processing_utils, "feature_count_if_cheap", return_value=12),
        ):
            self.assertEqual(processing_utils.empty_output_warnings({"OUTPUT": "id1"}), [])

    def test_a_raster_or_a_number_gives_no_warning(self):
        with mock.patch.object(processing_utils, "feature_count_if_cheap", return_value=None):
            self.assertEqual(processing_utils.empty_output_warnings({"OUTPUT": 3.5, "X": None}), [])


class MentionTest(unittest.TestCase):
    def test_an_at_sign_after_a_space_opens_a_mention(self):
        self.assertEqual(mention_query("colour @ro", 10), (7, "ro"))
        self.assertEqual(mention_query("@", 1), (0, ""))

    def test_an_email_address_is_not_a_mention(self):
        self.assertIsNone(mention_query("mail me@ro", 10))

    def test_a_space_after_the_mention_closes_it(self):
        self.assertIsNone(mention_query("@roads now", 10))

    def test_names_with_spaces_are_quoted(self):
        self.assertEqual(mention_text("Main roads"), f'{MENTION}"Main roads"')
        self.assertEqual(mention_text("rivers"), f"{MENTION}rivers")


class ComposerRecoveryTest(unittest.TestCase):
    def test_restore_fills_an_empty_prompt_only(self):
        composer = Composer()
        texts = []
        composer._edit.toPlainText = lambda: ""
        composer._edit.setPlainText = texts.append
        composer.restore("colour the rivers")
        self.assertEqual(texts, ["colour the rivers"])
        composer._edit.toPlainText = lambda: "already typing"
        composer.restore("colour the rivers")
        self.assertEqual(texts, ["colour the rivers"])

    def test_tab_without_a_match_does_not_send(self):
        composer = Composer()
        composer.set_popup_host(QWidget())
        sent = []
        composer.submitted.connect(sent.append)
        composer._edit.toPlainText = lambda: "/zzz"
        composer._popup.show_matches("zzz", [], QWidget())
        composer._on_complete()
        self.assertEqual(sent, [])


class PopupMouseTest(unittest.TestCase):
    def test_a_click_chooses_the_row(self):
        popup = SkillPopup(QWidget())
        chosen = []
        popup.chosen.connect(chosen.append)
        popup.show_matches("", LAYERS, QWidget(), MENTION)
        popup._rows[1].mousePressEvent(None)
        self.assertEqual(chosen, ["rivers"])

    def test_hover_moves_the_keyboard_selection(self):
        popup = SkillPopup(QWidget())
        popup.show_matches("", LAYERS, QWidget(), MENTION)
        popup._rows[1].enterEvent(None)
        self.assertEqual(popup.current_name(), "rivers")


class PartialAnswerTest(unittest.TestCase):
    def test_a_stopped_stream_keeps_its_text(self):
        view = ConversationView()
        view.append_draft("half an ")
        view.append_draft("answer")
        self.assertEqual(view.keep_draft(), "half an answer")
        self.assertIsNone(view._draft)

    def test_nothing_streamed_keeps_nothing(self):
        self.assertEqual(ConversationView().keep_draft(), "")


if __name__ == "__main__":
    unittest.main()
