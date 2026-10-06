import unittest

from qgis.PyQt.QtWidgets import QWidget

from ai_agent.ui.question import QuestionCard


class QuestionCardTest(unittest.TestCase):
    def setUp(self):
        self.card = QuestionCard("Which roads layer?", ["roads_2024", "roads_old"], QWidget().palette())
        self.sent: list[str] = []
        self.card.answered.connect(self.sent.append)

    def test_a_picked_answer_is_sent_and_the_card_folds(self):
        self.assertEqual([row.text for row in self.card.rows], ["roads_2024", "roads_old"])
        self.card.rows[1].clicked.emit("roads_old")
        self.assertEqual(self.sent, ["roads_old"])
        self.assertFalse(self.card.is_open)

    def test_an_own_answer_needs_text(self):
        self.card._send("   ")
        self.assertEqual(self.sent, [])
        self.card._send(" both ")
        self.assertEqual(self.sent, ["both"])


if __name__ == "__main__":
    unittest.main()
