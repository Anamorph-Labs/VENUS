"""Run with: python -m unittest discover tests"""

import unittest

from alvenus.match import Take, assign, choose, words

SCRIPT = [
    "Every night at three, Mara unlocks the bakery on Juniper Street.",
    "She starts the ovens before the city wakes up.",
]


def take(i, text, start, length=3.0):
    return Take(i, start, start + length, text, -0.2)


class MatchTests(unittest.TestCase):
    def test_words_normalise(self):
        self.assertEqual(words("You're up at 3!"), ["you", "are", "up", "at", "three"])

    def test_wrong_word_loses_to_exact_take(self):
        takes = [
            take(1, "Every night at three, Mara unlocks the bakery on Jupiter Street.", 0),
            take(2, "Every night at three, Mara unlocks the bakery on Juniper Street.", 5),
        ]
        assign(takes, SCRIPT)
        c = choose(takes, SCRIPT)[0]
        self.assertEqual(c.take.index, 2)

    def test_false_start_and_chatter(self):
        takes = [
            take(1, "She starts the", 0, 1.0),
            take(2, "Sorry, going again.", 2, 1.0),
            take(3, "She starts the ovens before the city wakes up.", 4),
        ]
        assign(takes, SCRIPT)
        self.assertEqual(takes[0].line, 1)
        self.assertIsNone(takes[1].line)
        c = choose(takes, SCRIPT)[1]
        self.assertEqual(c.take.index, 3)
        self.assertIn("incomplete (false start or cut off)", takes[0].notes)

    def test_hidden_hesitation_prefers_tighter_take(self):
        line = SCRIPT[1]
        takes = [take(1, line, 0, 3.0), take(2, line, 5, 3.8)]
        assign(takes, SCRIPT)
        c = choose(takes, SCRIPT)[1]
        self.assertEqual(c.take.index, 1)

    def test_equal_takes_prefer_later(self):
        line = SCRIPT[1]
        takes = [take(1, line, 0, 3.0), take(2, line, 5, 3.05)]
        assign(takes, SCRIPT)
        self.assertEqual(choose(takes, SCRIPT)[1].take.index, 2)

    def test_missing_line(self):
        takes = [take(1, SCRIPT[0], 0)]
        assign(takes, SCRIPT)
        self.assertIsNone(choose(takes, SCRIPT)[1].take)


if __name__ == "__main__":
    unittest.main()
