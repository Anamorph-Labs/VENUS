"""Run with: python -m unittest discover tests"""

import unittest

from alvenus.match import Take, assign, choose, join_paused, words
from alvenus.cli import apply_picks
from alvenus.reference import _shape, suggest
from alvenus.refine import has_restart
from alvenus.review import word_diff
from alvenus.timeline import _tc

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

    def test_line_split_by_a_pause_is_joined(self):
        takes = [
            take(1, "She starts the ovens", 0, 1.2),
            take(2, "before the city wakes up.", 2.0, 1.5),
            take(3, "Sorry, going again.", 5.0, 1.0),
        ]
        joined = join_paused(takes, SCRIPT)
        self.assertEqual(len(joined), 2)
        self.assertEqual(joined[0].end, 3.5)
        assign(joined, SCRIPT)
        self.assertEqual(choose(joined, SCRIPT)[1].take.index, 1)

    def test_takes_in_different_files_are_not_joined(self):
        a, b = take(1, "She starts the ovens", 0, 1.2), take(2, "before the city wakes up.", 2.0, 1.5)
        b.source = 1
        self.assertEqual(len(join_paused([a, b], SCRIPT)), 2)

    def test_edl_timecode(self):
        self.assertEqual(_tc(3600 + 1.5, 30), "01:00:01:15")

    def test_near_miss_word_is_not_perfect(self):
        takes = [take(1, "She starts the ovens before the city wakes up.", 0),
                 take(2, "She starts the ovens before the city wakes pup.", 5)]
        assign(takes, SCRIPT)
        self.assertEqual(choose(takes, SCRIPT)[1].take.index, 1)

    def test_restart_detected(self):
        t = take(1, "She starts the, she starts the ovens before the city wakes up.", 0)
        self.assertTrue(has_restart(t, SCRIPT[1]))
        self.assertFalse(has_restart(take(2, SCRIPT[1], 0), SCRIPT[1]))

    def test_word_diff(self):
        self.assertEqual(word_diff(SCRIPT[1], "She starts the ovens before the town wakes up."), (["city"], ["town"]))

    def test_picks_override(self):
        takes = [take(1, SCRIPT[0], 0), take(2, SCRIPT[1], 5), take(3, SCRIPT[1], 10)]
        assign(takes, SCRIPT)
        choices = choose(takes, SCRIPT)
        apply_picks(choices, takes, ["2=2", "1=none"], len(SCRIPT))
        self.assertEqual(choices[1].take.index, 2)
        self.assertIsNone(choices[0].take)

    def test_reference_suggestions(self):
        self.assertEqual(_shape(1080, 1920), "9:16")
        style = {"frame": {"shape": "9:16"}, "audio": {"median_pause_seconds": 0.25}}
        self.assertEqual(suggest(style), ["--aspect 9:16", "--max-pause 0.4"])


if __name__ == "__main__":
    unittest.main()
