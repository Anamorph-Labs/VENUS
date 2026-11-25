"""The stack caption look: the small words and the big word can each be moved on their own."""

import re
import unittest
from types import SimpleNamespace as W

from alvenus import stackcaps


def _words():
    return [W(text="One", start=0.0, end=0.3, line=0), W(text="for", start=0.3, end=0.6, line=0),
            W(text="him.", start=0.6, end=1.2, line=0, mark=True)]


def _pos(evs, word):
    for e in evs:
        if e.endswith("}" + word):
            x, y = re.search(r"\\pos\(([\d.]+),([\d.]+)\)", e).groups()
            return float(x), float(y)
    raise AssertionError(word)


class StackCaptions(unittest.TestCase):
    def test_small_words_go_above_or_below_the_big_word(self):
        texts = ["One", "for", "him"]
        above = stackcaps.layout(texts, 2, 3, 1080, 1920, 900)
        below = stackcaps.layout(texts, 2, 3, 1080, 1920, 900, side="below")
        assert [r[1] for r in above["rows"]] == [stackcaps.SMALL_FILE, stackcaps.BIG_FILE]
        assert [r[1] for r in below["rows"]] == [stackcaps.BIG_FILE, stackcaps.SMALL_FILE]

    def test_moving_the_small_row_leaves_the_big_word_where_it_was(self):
        base = stackcaps.stack_events(_words(), 1080, 1920, "&H00FFFFFF&")
        stackcaps.NUDGE[0] = (-0.1, 0.05, 0.0, 0.0)
        try:
            moved = stackcaps.stack_events(_words(), 1080, 1920, "&H00FFFFFF&")
        finally:
            stackcaps.NUDGE.clear()
        (x0, y0), (x1, y1) = _pos(base, "One"), _pos(moved, "One")
        assert round(x0 - x1) == 108 and round(y1 - y0) == 96
        assert _pos(base, "him") == _pos(moved, "him")

    def test_a_moved_row_stays_inside_the_frame(self):
        stackcaps.NUDGE[0] = (-0.5, 0.0, 0.5, 0.0)
        try:
            evs = stackcaps.stack_events(_words(), 1080, 1920, "&H00FFFFFF&")
        finally:
            stackcaps.NUDGE.clear()
        assert 0 < _pos(evs, "One")[0] < 1080 and 0 < _pos(evs, "him")[0] < 1080
