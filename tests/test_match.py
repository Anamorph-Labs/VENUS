"""Run with: python -m unittest discover tests"""

import unittest

from alvenus.match import Take, assign, choose, join_paused, words
from alvenus.cli import apply_picks, find_room_tone, scene_breaks
from alvenus.cut import Clip, hide_jump_cuts, take_clips
from alvenus.finish import line_spans
from alvenus.style import _t as _ass_time, ass_colour, chunks
from alvenus.delivery import Delivery, judge
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

    def test_delivery_breaks_a_tie(self):
        line = SCRIPT[1]
        takes = [take(1, line, 0, 3.0), take(2, line, 5, 3.0)]
        assign(takes, SCRIPT)
        takes[0].delivery = Delivery(-16.0, 1.0, 1.0, 0.0, 3.0)
        takes[1].delivery = Delivery(-30.0, 1.0, 1.0, 0.0, 3.0)  # later but quiet
        judge(takes)
        self.assertEqual(takes[1].delivery.issues, ["quiet, low energy"])
        c = choose(takes, SCRIPT)[1]
        self.assertEqual(c.take.index, 1)
        self.assertIn("better delivery", c.reason)

    def test_rushed_take_flagged_and_other_not_called_slow(self):
        line = SCRIPT[1]
        takes = [take(1, line, 0, 3.0), take(2, line, 5, 2.1)]
        assign(takes, SCRIPT)
        takes[0].delivery = Delivery(-16.0, 1.0, 1.0, 0.0, 3.0)
        takes[1].delivery = Delivery(-16.0, 1.0, 1.0, 0.0, 4.3)
        judge(takes)
        self.assertIn("rushed", takes[1].delivery.issues)
        c = choose(takes, SCRIPT)[1]
        self.assertEqual(c.take.index, 1)
        self.assertFalse(any("slower" in n for n in takes[0].notes))

    def test_punch_in_alternates_on_same_camera(self):
        clips = [Clip(0, 0, 1, 0), Clip(0, 2, 3, 1), Clip(0, 4, 5, 2), Clip(1, 0, 1, 3), Clip(1, 2, 3, 4)]
        hide_jump_cuts(clips)
        self.assertEqual([c.zoom for c in clips], [1.0, 1.12, 1.0, 1.0, 1.12])

    def test_scene_breaks_from_blank_lines(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.txt"
            p.write_text("# note\n\nOne.\nTwo.\n\nThree.\n", encoding="utf-8")
            self.assertEqual(scene_breaks(p), {1})

    def test_room_tone_is_longest_quiet(self):
        pieces = [(0, 0.5, 2.0), (0, 4.0, 5.0), (1, 0.0, 9.0)]
        self.assertEqual(find_room_tone(pieces, 0, 6.0), (0, 2.1, 3.9))

    def test_tail_held_when_footage_ends(self):
        c = take_clips(None, 0, 0, 1.0, 4.9, 5.0, tail=0.4, max_pause=None, hold_short=True)[0]
        self.assertAlmostEqual(c.end, 4.95)
        self.assertAlmostEqual(c.hold, 0.35)

    def test_line_spans_on_timeline(self):
        clips = [Clip(0, 0, 2, 0), Clip(0, 3, 4, 0, hold=0.5), Clip(1, 0, 1, 2)]
        self.assertEqual(line_spans(clips), {0: (0.0, 3.5), 2: (3.5, 4.5)})

    def test_ass_time(self):
        self.assertEqual(_ass_time(3661.25), "1:01:01.25")

    def test_plan_round_trip(self):
        import argparse, tempfile
        from pathlib import Path
        from alvenus import plan
        from alvenus.finish import Cutaway
        from alvenus.match import Choice
        with tempfile.TemporaryDirectory() as d:
            a = argparse.Namespace(script="s.txt", takes=["clips"], out="cut.mp4", aspect="9:16", captions=True,
                                   pick=["2=5", "3=none"], keep_pauses=False, max_pause=0.4, beat=0.25, scene_beat=0.9,
                                   no_punch_in=True, music=None, music_lufs=-22.0, title="Hi", end_card=None, model="small.en",
                                   look="film", caption_style="pop", accent="#FFD23F")
            p = Path(d) / "cut.plan.json"
            plan.write(p, a, [Choice(0, None, "", [])], [Cutaway(1, Path("/x/b.mp4"), 4.5)])
            back = plan.load(p)
        self.assertEqual(back["pick"], ["2=5", "3=none"])
        self.assertEqual(back["broll"], ["2=/x/b.mp4@4.5"])
        self.assertTrue(back["no_punch_in"])
        self.assertEqual((back["aspect"], back["max_pause"], back["title"]), ("9:16", 0.4, "Hi"))

    def test_ass_colour_and_chunks(self):
        from alvenus.wordtime import Word
        self.assertEqual(ass_colour("#FFD23F"), "&H003FD2FF")
        ws = [Word(t, i, i + 1) for i, t in enumerate("So we visit him, and we lose track of it.".split())]
        self.assertEqual([[w.text for w in g] for g in chunks(ws, vertical=True)],
                         [["So", "we", "visit", "him,"], ["and", "we", "lose", "track"], ["of", "it."]])

    def test_word_placement_follows_syllables(self):
        from alvenus.wordtime import place, syllables
        self.assertEqual([syllables(w) for w in ["the", "market", "opens", "favourite", "3"]], [1, 2, 2, 3, 1])
        ws = place(["one", "two", "three"], [0.2, 0.6, 1.0], 0.1, 1.2)
        self.assertEqual(ws[0].start, 0.1)
        self.assertTrue(ws[0].end <= ws[1].start + 1e-9 and ws[1].start < ws[2].start)

    def test_transitions_overlap_timeline(self):
        from alvenus.cut import positions, total_length
        clips = [Clip(0, 0, 2, 0), Clip(0, 3, 5, 1, transition="dip", tdur=0.5)]
        self.assertEqual(positions(clips), [0.0, 1.5])
        self.assertEqual(total_length(clips), 3.5)

    def test_reframe_crop_expression(self):
        from alvenus.reframe import crop_x
        self.assertEqual(crop_x([(0.0, 0.5)], 1920, 608), "656.0")
        self.assertEqual(crop_x([(0.0, 0.0)], 1920, 608), "0.0")  # never past the edge
        self.assertIn("if(lt(t,2.00)", crop_x([(0.0, 0.75), (2.0, 0.25)], 1920, 608))

    def test_presets_fill_settings(self):
        from alvenus.presets import PRESETS, defaults
        self.assertEqual(defaults("reels-punchy")["aspect"], "9:16")
        self.assertTrue(all("about" in p and "look" in p for p in PRESETS.values()))
        with self.assertRaises(SystemExit):
            defaults("nope")

    def test_filler_is_cut_out_of_a_take(self):
        clips = take_clips(None, 0, 0, 1.0, 3.0, 10.0, max_pause=None, remove=[(1.8, 2.2)])
        self.assertEqual(len(clips), 2)
        self.assertLess(clips[0].end, 1.9)
        self.assertGreater(clips[1].start, 2.1)

    def test_highlight_marks_phrase(self):
        from alvenus.graphics import mark, parse_highlights
        from alvenus.wordtime import Word
        script = ["He repairs broken clocks for free."]
        ws = [Word(t, i, i + 1, line=0) for i, t in enumerate(script[0].split())]
        mark(ws, parse_highlights(["1=broken clocks"], script))
        self.assertEqual([w.text for w in ws if w.mark], ["broken", "clocks"])

    def test_stat_and_chart_parse_and_count(self):
        from alvenus.graphics import count_frames, parse_charts, parse_stats
        st = parse_stats(["3=$1,200|raised"], 5)[0]
        self.assertEqual((st.line, st.label), (2, "raised"))
        frames = count_frames("$1,200")
        self.assertEqual(frames[-1], "$1,200")
        self.assertTrue(all(f.startswith("$") for f in frames))
        ch = parse_charts(["2=Fruit 4, Lamps 7.5|Sales"], 5)[0]
        self.assertEqual([b[1] for b in ch.bars], [4.0, 7.5])
        with self.assertRaises(SystemExit):
            parse_charts(["2=Fruit 4"], 5)  # one bar is not a chart

    def test_auto_broll_matches_names_and_spaces_out(self):
        import tempfile
        from pathlib import Path
        from unittest import mock
        from alvenus.finish import auto_broll
        script = ["Intro line.", "Every stall sells fruit.", "He repairs clocks.", "Time runs out.", "Goodbye."]
        with tempfile.TemporaryDirectory() as d:
            for n in ("market_stalls.mp4", "clock.mp4", "time.mp4", "intro.mp4"):
                (Path(d) / n).write_bytes(b"")
            with mock.patch("alvenus.finish.has_video", return_value=True):
                cw, _ = auto_broll(script, Path(d), set(), set())
                self.assertEqual([(c.line, c.path.name) for c in cw], [(1, "market_stalls.mp4"), (3, "time.mp4")])
                cw, _ = auto_broll(script, Path(d), {1}, set())  # line 2 is a card
                self.assertEqual([c.line for c in cw], [2])

    def test_beat_grid_finds_tempo_and_kick(self):
        import numpy as np
        from alvenus.beats import SR, beat_grid
        n = int(10 * SR)
        y = np.zeros(n)
        t = np.arange(int(0.3 * SR)) / SR
        kick = np.sin(2 * np.pi * (50 + 100 * np.exp(-t / 0.03)) * t) * np.exp(-t / 0.06)
        hat = np.random.default_rng(0).standard_normal(len(t)) * np.exp(-t / 0.01) * 0.3
        for k, b in enumerate(np.arange(0.4, 10, 0.3125)):  # 96 BPM kicks, hats between
            i = int(b * SR)
            s = kick if k % 2 == 0 else hat
            e = min(n, i + len(s))
            y[i:e] += s[: e - i]
        period, first, conf = beat_grid(y)
        self.assertAlmostEqual(60 / period, 96, delta=1.5)
        self.assertAlmostEqual(first, 0.4, delta=0.06)

    def test_scene_start_slides_onto_beat(self):
        from alvenus.beats import sync
        from alvenus.cut import positions
        clips = [Clip(0, 0.0, 2.0, 0), Clip(0, 5.0, 7.0, 1)]
        notes = sync(clips, [1.0, 2.3, 3.6], {1}, {0: 2.1})
        self.assertTrue(notes)
        self.assertAlmostEqual(positions(clips)[1], 2.3, places=3)
        self.assertAlmostEqual(clips[0].end, 2.05, places=3)  # real quiet footage first...
        self.assertAlmostEqual(clips[0].hold, 0.25, places=3)  # ...then a held frame

    def test_push_in_spans_the_whole_line(self):
        from alvenus.cut import push_in
        clips = [Clip(0, 0, 1, 0), Clip(0, 2, 5, 1), Clip(0, 6, 7, 1)]
        push_in(clips, {1}, 0.08)
        self.assertIsNone(clips[0].push)
        self.assertEqual(clips[1].push[0], 1.0)
        self.assertAlmostEqual(clips[1].push[1], clips[2].push[0])
        self.assertAlmostEqual(clips[2].push[1], 1.08)

    def test_sound_effects_track(self):
        import tempfile, wave
        from pathlib import Path
        from alvenus.sfx import write_track
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "fx.wav"
            write_track(p, [(0.5, "whoosh"), (1.0, "pop"), (1.5, "hit")], 3.0)
            with wave.open(str(p)) as w:
                self.assertEqual((w.getnchannels(), w.getframerate()), (2, 48000))
                self.assertAlmostEqual(w.getnframes() / 48000, 3.0, places=2)

    def test_line_chart_and_quote_parse(self):
        from alvenus.graphics import line_chart_events, parse_line_charts, parse_quotes, progress_events
        pts = ", ".join(f"{2000 + i} {i * i}" for i in range(12))
        ch = parse_line_charts([f"2={pts}|Growth"], 3)[0]
        self.assertEqual((ch.line, len(ch.bars), ch.title), (1, 12, "Growth"))
        self.assertTrue(line_chart_events(ch, 1.0, 4.0, 1920, 1080, "#FFD23F"))
        q = parse_quotes(["3=Mara"], ["a", "b", "Time is the thing."])[0]
        self.assertEqual((q.line, q.who, q.text), (2, "Mara", "Time is the thing."))
        self.assertEqual(len(progress_events(10.0, 1080, 1920, "#FFD23F", [4.0])), 3)

    def test_drawn_out_fillers(self):
        from alvenus.match import is_filler
        self.assertTrue(all(is_filler(w) for w in ("um", "umm", "uhhh", "hmm", "mm")))
        self.assertFalse(any(is_filler(w) for w in ("the", "a", "am", "summer")))


if __name__ == "__main__":
    unittest.main()
