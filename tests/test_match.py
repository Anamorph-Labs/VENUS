"""Run with: python -m unittest discover tests"""

import unittest

from alvenus.match import Take, as_said, assign, choose, edge_word_heard, join_paused, words
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

    def test_montage_plan_follows_the_music(self):
        from alvenus.montage import ClipInfo, plan
        def clip(name, n, motion):
            return ClipInfo(name, n / 4, (1280, 720), [motion] * n, [8.0] * n, [120.0] * n, [60.0] * n)
        clips = [clip("a.mp4", 60, 0.1), clip("b.mp4", 60, 0.5), clip("c.mp4", 60, 0.9)]
        beats = [i * 0.5 for i in range(40)]
        energy = [0.1] * 16 + [1.0] * 24  # quiet, then a drop at 8 s
        shots = plan(clips, beats, energy, 0, 20.0)
        self.assertAlmostEqual(sum(s.length for s in shots), 20.0, places=2)
        starts = [sum(s.length for s in shots[:i]) for i in range(len(shots))]
        self.assertTrue(all(abs(t / 0.5 - round(t / 0.5)) < 1e-6 for t in starts))  # every cut on a beat
        self.assertTrue(all(a.clip != b.clip for a, b in zip(shots, shots[1:])))  # never the same clip twice running
        quiet = [s for s, t in zip(shots, starts) if t < 8]
        loud = [s for s, t in zip(shots, starts) if t >= 8.5]
        self.assertGreater(min(s.length for s in quiet), max(s.length for s in loud) - 1e-6)
        drop = [s for s, t in zip(shots, starts) if abs(t - 8) < 1e-6]
        self.assertTrue(drop and drop[0].flash and drop[0].speed_end is not None)

    def test_map_and_timeline_parse(self):
        from alvenus.graphics import parse_maps, parse_timelines, pin_events, timeline_events
        mc = parse_maps(["2=city.png|0.3,0.6 Old port; 0.7,0.4 Market"], 3)[0]
        self.assertEqual((mc.line, mc.image, [p.label for p in mc.pins]), (1, "city.png", ["Old port", "Market"]))
        self.assertTrue(pin_events(mc.pins, 0, 4, 1920, 1080, "#FFD23F"))
        tl = parse_timelines(["1=1990 First stall, 2024 500 stalls|Growth"], 3)[0]
        self.assertEqual(tl.items, [("1990", "First stall"), ("2024", "500 stalls")])
        rows = timeline_events(tl, 0, 4, 1920, 1080, "#FFD23F")
        self.assertTrue(all(r.startswith("Dialogue: ") and r.split(",")[3] in ("Card", "CardText") for r in rows))
        with self.assertRaises(SystemExit):
            parse_maps(["2=city.png|1.5,0.2 Off the map"], 3)

    def test_storyboard_checks_and_beat_snap(self):
        import json, tempfile
        from pathlib import Path
        from pathlib import Path
        from alvenus.story import _beat_snap, load
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "sb.json"
            p.write_text(json.dumps({"scenes": [{"type": "clip"}, {"type": "wobble"}]}))
            with self.assertRaises(SystemExit) as e:
                load(p)
            self.assertIn("needs \"file\"", str(e.exception))
            self.assertIn("wobble", str(e.exception))
        self.assertEqual(_beat_snap([3.0, 4.0], None), [3.0, 4.0])


class Run3(unittest.TestCase):
    def test_custom_transitions_join_through_a_small_mask(self):
        from alvenus.cut import TRANSITIONS, join_pair
        for name, kind in TRANSITIONS.items():
            g = join_pair("a", "b", "o", name, 0.5, 2.0, "1080x1920", 30, 1)
            self.assertTrue(g.endswith("[o]"))
            if kind == "custom":  # never a full-size per-pixel expression (far too slow)
                self.assertIn("maskedmerge", g)
                self.assertNotIn("xfade", g)

    def test_every_title_style_draws(self):
        from alvenus.style import TITLE_STYLES, title_events
        for k in TITLE_STYLES:
            ev = title_events("Tea at midnight", 1080, 1920, "#FFD23F", 0.0, 3.0, True, k)
            self.assertTrue(ev and all(e.startswith("Dialogue:") for e in ev))

    def test_packs_use_known_parts(self):
        from alvenus.cut import TRANSITIONS
        from alvenus.presets import PRESETS, pack
        from alvenus.style import LOOKS, TITLE_STYLES
        for p in PRESETS.values():
            self.assertIn(p["transition"], TRANSITIONS)
            self.assertIn(p["title_style"], TITLE_STYLES)
            self.assertIn(p["look"], LOOKS)
        self.assertEqual(pack("hype", "transition", "nope"), {"transition": "glitch"})
        self.assertEqual(pack(None, "look"), {})

    def test_storyboard_rejects_unknown_style(self):
        import json, tempfile
        from pathlib import Path
        from pathlib import Path
        from alvenus.story import load
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "sb.json"
            p.write_text(json.dumps({"title_style": "wobble", "scenes": [{"type": "title", "text": "Hi"}]}))
            with self.assertRaises(SystemExit) as e:
                load(p)
            self.assertIn("title_style", str(e.exception))

    def test_selfcheck_reading_time(self):
        import tempfile
        from pathlib import Path
        from alvenus.selfcheck import _reading, text_events
        from alvenus.style import title_events, write_ass
        with tempfile.TemporaryDirectory() as d:
            a = Path(d) / "x.ass"
            write_ass(a, 1280, 720, "#FFD23F", extra_rows=title_events("one two three four five six", 1280, 720, "#FFD23F", 1, 1.5, True)
                      + title_events("Hello", 1280, 720, "#FFD23F", 3, 6, True, "type"))
            ev = text_events(a)
            self.assertEqual(sorted(t for *_, t in ev), ["Hello", "one two three four five six"])  # bars left out
            notes = _reading(ev, 10.0)
            self.assertEqual(len(notes), 1)
            self.assertIn("one two three", notes[0])
            self.assertEqual(_reading(ev, 10.0, ["One, two, three, four, five and six."]), [])  # heard as it is read


class Run4(unittest.TestCase):
    def test_autofix_lengthens_darkens_and_calms(self):
        from alvenus.selfcheck import Finding
        from alvenus.story import autofix
        sb = {"transition": "glitch", "end_card": "Bye", "scenes": [
            {"type": "title", "text": "A long title here", "seconds": 1.5},
            {"type": "clip", "file": "x.mp4", "seconds": 3},
            {"type": "chart", "bars": [["a", 1]], "seconds": 3}],
            "_spans": {0: (0.0, 1.5), 1: (1.5, 4.5), 2: (4.5, 7.5)}}
        found = [Finding("short", "reading", [0.2], need=2.0, shown=1.3),
                 Finding("faint", "contrast", [2.0]),
                 Finding("flash", "flash", [4.4]),
                 Finding("end", "reading", [7.6], need=1.5, shown=1.0),
                 Finding("chart text", "contrast", [5.0])]  # a chart draws its own panel: nothing to darken
        done = autofix(sb, found)
        sc = sb["scenes"]
        self.assertEqual(sc[0]["seconds"], 2.6)
        self.assertEqual(sc[1]["darken"], 0.15)
        self.assertEqual(sc[2]["transition"], "crossfade")
        self.assertEqual(sb["end_card_seconds"], 3.4)
        self.assertNotIn("darken", sc[2])
        self.assertEqual(len(done), 4)
        self.assertEqual(autofix(sb, []), [])

    def test_draft_shrinks_and_speeds_up(self):
        from alvenus import media
        from alvenus.draft import enable, fast_args
        sizes = {"16:9": "1920x1080", "4:5": "1080x1350"}
        old = media.DRAFT
        try:
            enable(sizes)
            self.assertEqual(sizes, {"16:9": "640x360", "4:5": "360x450"})
            self.assertTrue(media.DRAFT)
        finally:
            media.DRAFT = old
        self.assertEqual(fast_args(["ffmpeg", "-preset", "medium", "-crf", "14", "o.mp4"]),
                         ["ffmpeg", "-preset", "ultrafast", "-crf", "26", "o.mp4"])

    def test_backgrounds_and_packs(self):
        from alvenus.backgrounds import KINDS, source
        from alvenus.presets import PRESETS
        for k in KINDS:
            src, vf = source(k, 1080, 1920, 30, 2.0, "#3DF5C8")
            self.assertTrue(src and vf.endswith("yuv420p") or "vignette" in vf)
        for p in PRESETS.values():
            self.assertIn(p["background"], KINDS)
        with self.assertRaises(ValueError):
            source("lava", 640, 360, 30, 1.0)


class Run5(unittest.TestCase):
    def test_list_compare_callout_events(self):
        from alvenus.graphics import callout_events, compare_events, list_events
        rows = list_events("Why", ["One", "Two", "Three"], 1.0, 7.0, 1920, 1080, "#FF6B35")
        self.assertEqual(sum(1 for r in rows if r.endswith("}2")), 1)  # the number sits in its badge
        self.assertFalse(any("Comment:" in r or "m 0 0 l 1920" in r for r in rows))  # no panel over the background
        rows = compare_events(("Day", ["a"]), ("Night", ["b", "c"]), 0, 6, 1080, 1920, "#FF6B35")
        self.assertTrue(rows[-1].endswith("}vs"))
        rows = callout_events(0.8, 0.2, "Here", 0, 4, 1920, 1080, "#FF6B35")
        box = next(r for r in rows if "\\fscx0\\t(0,220" in r)
        self.assertIn("\\an7\\pos(", box)
        x = int(box.split("\\pos(")[1].split(",")[0])
        self.assertLess(x, 0.8 * 1920)  # label goes to the side with room

    def test_disc_is_centred_on_its_box(self):
        from alvenus.graphics import _disc
        pts = [int(v) for v in _disc(10).replace("m", "").replace("b", "").split()]
        self.assertEqual((min(pts), max(pts)), (0, 20))

    def test_templates_load_and_hook_fast(self):
        import json, tempfile
        from pathlib import Path
        from alvenus import story
        from alvenus.templates import TEMPLATES
        for name, sb in TEMPLATES.items():
            with self.subTest(name):
                self.assertLessEqual(sb["scenes"][0]["seconds"], 2.6)
                self.assertLessEqual(len(sb["scenes"][0]["text"].split()), 7)
                with tempfile.TemporaryDirectory() as d:
                    p = Path(d) / "sb.json"
                    p.write_text(json.dumps(sb))
                    self.assertEqual(len(story.load(p)["scenes"]), len(sb["scenes"]))


class Runs6to9(unittest.TestCase):
    def test_scene_key_ignores_words_but_not_pictures(self):
        from alvenus.story import _scene_key
        a = {"type": "list", "title": "Why", "items": ["a", "b"], "_bg": "ink", "_accent": "#FF0000", "_dir": 1}
        b = {**a, "items": ["c", "d", "e"], "title": "Other"}
        self.assertEqual(_scene_key(a, 4.0, 640, 360, 30), _scene_key(b, 4.0, 640, 360, 30))
        self.assertNotEqual(_scene_key(a, 4.0, 640, 360, 30), _scene_key({**a, "_bg": "grid"}, 4.0, 640, 360, 30))
        self.assertNotEqual(_scene_key(a, 4.0, 640, 360, 30), _scene_key(a, 4.5, 640, 360, 30))

    def test_explain_names_the_hook_and_reading_time(self):
        from alvenus.story import explain
        sb = {"scenes": [{"type": "text", "text": "Your battery is lying.", "seconds": 2},
                         {"type": "list", "items": ["one two", "three"], "seconds": 4}],
              "_spans": {0: (0.0, 2.0), 1: (2.0, 6.2)},
              "_why": {"asked": [2, 4], "got": [2.0, 4.2], "beat": True, "trans": "ink", "td": 0.9}}
        md = explain(sb)
        self.assertIn("an ink", md)
        self.assertIn("the hook", md)
        self.assertIn("so the cut falls on the beat", md)
        self.assertIn("3 words on screen", md)

    def test_xml_timeline_has_switched_off_alternates_and_markers(self):
        import tempfile
        import xml.etree.ElementTree as ET
        from pathlib import Path
        from alvenus.cut import Clip
        from alvenus.handoff import write_xml
        from alvenus.match import Choice, Take
        t1 = Take(1, 1.0, 3.0, "hello there", 0.0, line=0, score=1.0, recall=1.0, source=0)
        t2 = Take(2, 5.0, 7.5, "hello there", 0.0, line=0, score=0.95, recall=1.0, source=0)
        t3 = Take(3, 9.0, 11.0, "second line", 0.0, line=1, score=1.0, recall=1.0, source=1)
        clips = [Clip(0, 1.0, 3.0, 0), Clip(1, 9.0, 11.0, 1)]
        choices = [Choice(0, t1, "same words, better delivery", [t1, t2]), Choice(1, t3, "only take of this line", [t3])]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "cut.xml"
            n = write_xml(p, "cut", [Path(d) / "a.mov", Path(d) / "b.mp4"], clips, ["hello there", "second line"], 30.0,
                          "1920x1080", choices)
            root = ET.parse(p).getroot()
        self.assertEqual(n, 1)
        vt = root.find("sequence/media/video").findall("track")
        self.assertEqual(len(vt), 2)
        self.assertEqual(vt[1].findtext("enabled"), "FALSE")
        self.assertEqual([c.findtext("start") for c in vt[0].findall("clipitem")], ["0", "60"])
        self.assertEqual(len(root.findall("sequence/marker")), 2)
        self.assertTrue(root.find(".//pathurl").text.startswith("file://localhost/"))
        defs = [f.get("id") for f in root.iter("file") if f.find("pathurl") is not None]
        self.assertEqual(sorted(defs), ["file-1", "file-2"])  # each file described once

    def test_phone_files_rotation_and_frame_rate(self):
        import json
        from types import SimpleNamespace
        from alvenus import media
        old = media.run
        try:
            media.run = lambda args: SimpleNamespace(stdout=json.dumps({"streams": [{"width": 1920, "height": 1080,
                                                     "side_data_list": [{"rotation": -90}]}]}))
            self.assertEqual(media.video_size("x.mov"), (1080, 1920))
            media.run = lambda args: SimpleNamespace(stdout="30/1,\n")
            self.assertEqual(media.frame_rate("x.mov"), 30.0)
        finally:
            media.run = old

    def test_learned_packs_load_without_shadowing(self):
        import json, os, tempfile
        from pathlib import Path
        from alvenus.learnstyle import MATCH, _filter, load_user_packs
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "my-doc.json").write_text(json.dumps({"about": "x", "aspect": "16:9", "look": "learned-my-doc",
                                                             "grade": "eq=saturation=0.8", "colour": {"saturation": 0.2}}))
            (Path(d) / "hype.json").write_text(json.dumps({"about": "evil", "grade": "eq"}))
            old = os.environ.get("ALVENUS_PACKS")
            os.environ["ALVENUS_PACKS"] = d
            try:
                presets, looks = {"hype": {"about": "built in"}}, {}
                load_user_packs(presets, looks)
            finally:
                if old is None:
                    os.environ.pop("ALVENUS_PACKS")
                else:
                    os.environ["ALVENUS_PACKS"] = old
        self.assertEqual(presets["hype"]["about"], "built in")
        self.assertEqual(looks["learned-my-doc"], "eq=saturation=0.8")
        self.assertIn("learned-my-doc", MATCH)
        f = _filter({"sat": 9, "con": 0.1, "warm": 0, "tint": 0, "glow": 0, "lift": 0, "roll": 0, "vignette": False})
        self.assertIn("contrast=0.700:saturation=1.700", f)  # wild guesses are held to sane limits

    def test_clip_tokenizer_matches_openai(self):
        from alvenus.footage import FILES, _Tokenizer, model_dir
        path = model_dir() / "tokenizer.json"
        if not path.exists():
            self.skipTest("footage-search model not downloaded")
        self.assertEqual(_Tokenizer(path).encode("a photo of a cat"), [49406, 320, 1125, 539, 320, 2368, 49407])


class PhoneFootage(unittest.TestCase):
    def test_captions_follow_what_was_said(self):
        self.assertEqual(as_said("So I walked to the café down the street.", "I walked to the cafe down the street."),
                         "I walked to the café down the street.")
        self.assertEqual(as_said("And that's where everything changed.", "and that's where everything's changed."),
                         "And that's where everything changed.")
        self.assertEqual(as_said("We went home.", "We, um, finally went home."), "We finally went home.")
        self.assertEqual(as_said("It costs $20 a month.", "It costs twenty dollars a month."), "It costs $20 a month.")

    def test_speech_at_file_edge_is_fine_when_the_word_is_whole(self):
        script = ["And that's where everything changed."]
        whole = Take(1, 0.0, 1.8, "and that's where everything's changed.", -0.2, line=0)
        lost = Take(2, 0.0, 1.6, "that's where everything changed.", -0.2, line=0)
        self.assertTrue(edge_word_heard(whole, script, first=True))
        self.assertTrue(edge_word_heard(whole, script, first=False))
        self.assertFalse(edge_word_heard(lost, script, first=True))

    def test_no_long_fade_on_a_clip_that_opens_its_file(self):
        from alvenus.cut import _clip_filters
        _, af = _clip_filters(Clip(0, 0.0, 1.8, 0), None, 1080, 1920, 25, False)
        self.assertIn("afade=t=in:d=0.002", af)
        _, af = _clip_filters(Clip(0, 0.5, 1.8, 0), None, 1080, 1920, 25, False)
        self.assertIn("afade=t=in:d=0.03", af)


class Designs(unittest.TestCase):
    def test_markup_roles(self):
        from alvenus.paper import parse, plain
        got = parse("NEXT taught him *precision.* _so_ ==fast== now", {"next"})
        self.assertEqual(got, [("NEXT", "big"), ("taught", "plain"), ("him", "plain"), ("precision.", "serif"),
                               ("so", "light"), ("fast", "mark"), ("now", "plain")])
        self.assertEqual(plain("a *b c* ==d=="), "a b c d")

    def test_words_fit_their_box(self):
        from alvenus.paper import word_events
        ev, lands = word_events("Every morning the *same* cup of ==coffee.==", {"same"}, 0, 3, 1080, 1920, "mono",
                                "#D4F01E", (90, 200, 900, 400), False)
        self.assertEqual(len(lands), 7)
        self.assertTrue(all(b > a for a, b in zip(lands, lands[1:])))
        import re
        xs = [int(m.group(1)) for m in (re.search(r"\\move\((\d+),", e) for e in ev) if m]
        self.assertTrue(all(90 <= x <= 990 for x in xs))

    def test_print_layout_stays_in_frame(self):
        from alvenus.paper import layout
        for w, h in ((1080, 1920), (1920, 1080), (1080, 1350)):
            for words in (True, False):
                for a in (0.5, 1.0, 2.0):
                    x, y, pw, ph = layout(w, h, words, a)
                    self.assertTrue(x >= 0 and y >= 0 and x + pw <= w and y + ph <= h, (w, h, words, a))

    def test_design_packs(self):
        from alvenus.presets import PRESETS
        self.assertEqual(PRESETS["mono-editorial"]["design"], "mono")
        self.assertEqual(PRESETS["vox-paper"]["design"], "paper")


class Nodes(unittest.TestCase):
    SB = {"style": "mono-editorial", "accent": "#D4F01E", "music": "song.mp3", "scenes": [
        {"type": "title", "text": "Same Cup", "subtitle": "a ritual", "seconds": 2.6, "_hook": "keep me"},
        {"type": "image", "file": "cup.jpg", "caption": "Every *same* cup", "seconds": 3, "words_size": 1.2,
         "picture_shape": "none", "transition": "whip", "darken": 0.1},
        {"type": "image", "file": "m.jpg", "caption": "Broken", "callout": {"x": 0.5, "y": 0.4, "label": "no power"}, "note": "hm"},
        {"type": "chart", "bars": [["A", 1], ["B", 2]], "title": "What", "caption": "c"},
        {"type": "stat", "value": "500", "label": "stalls", "file": "bg.jpg"},
        {"type": "split", "left": {"file": "a.mp4", "label": "Day"}, "right": {"file": "b.mp4", "label": "Night"}},
    ]}

    def doc(self):
        import copy
        from alvenus import nodes as nd
        return nd.to_nodes(copy.deepcopy(self.SB))

    def test_round_trip_loses_nothing(self):
        from alvenus import nodes as nd
        from alvenus.story import EXAMPLE
        from alvenus.templates import TEMPLATES
        for sb in [self.SB, EXAMPLE, *TEMPLATES.values()]:
            doc = nd.to_nodes(sb)
            self.assertEqual(nd.to_storyboard(doc), sb)
            self.assertEqual(nd.check(doc), [])

    def test_parts_hold_the_right_keys(self):
        from alvenus import nodes as nd
        doc = self.doc()
        self.assertEqual(nd.find(doc, "scene2.words")["params"], {"caption": "Every *same* cup", "size": 1.2})
        self.assertEqual(nd.find(doc, "scene2.picture")["params"], {"file": "cup.jpg", "shape": "none", "darken": 0.1})
        self.assertEqual(nd.find(doc, "scene2.in")["params"], {"transition": "whip"})
        self.assertEqual(nd.find(doc, "scene3.mark")["params"]["note"], "hm")
        self.assertEqual(nd.find(doc, "scene5.graphic")["params"], {"value": "500", "label": "stalls"})
        self.assertEqual(nd.find(doc, "scene5.picture")["params"], {"file": "bg.jpg"})
        self.assertIn("left", nd.find(doc, "scene6.graphic")["params"])

    def test_set_makes_parts_and_explains_mistakes(self):
        from alvenus import nodes as nd
        doc = self.doc()
        nd.set_param(doc, "scene1.picture.shape", "blob")  # a part that wasn't there yet
        self.assertEqual(nd.to_storyboard(doc)["scenes"][0]["picture_shape"], "blob")
        nd.set_param(doc, "scene2.words.sise", 1)
        self.assertTrue(any("did you mean size" in p for p in nd.check(doc)))
        nd.set_param(doc, "scene2.words.sise", None)
        nd.set_param(doc, "scene6.graphic.left.label", "Dawn")  # nested
        self.assertEqual(nd.to_storyboard(doc)["scenes"][5]["left"], {"file": "a.mp4", "label": "Dawn"})
        self.assertEqual(nd.check(doc), [])
        with self.assertRaises(SystemExit):
            nd.set_param(doc, "scen2.words.size", 1)

    def test_locks_guard_and_freeze(self):
        from alvenus import nodes as nd
        doc = self.doc()
        nd.lock(doc, ["scene2"])
        with self.assertRaises(SystemExit):
            nd.set_param(doc, "scene2.words.size", 1.5)
        nd.set_param(doc, "scene2.words.size", 1.5, force=True)  # forced: still locked, lock re-stamped
        self.assertEqual(nd.check(doc), [])
        nd.find(doc, "scene2.words")["params"]["size"] = 0.9  # edited by hand behind the lock
        self.assertTrue(any("locked" in p for p in nd.check(doc)))
        self.assertEqual(nd.frozen(doc), {"1:seconds", "1:darken", "1:transition"})

    def test_autofix_leaves_locked_scenes_alone(self):
        from types import SimpleNamespace
        from alvenus.story import autofix
        sb = {"scenes": [{"type": "text", "text": "a b c d e f", "seconds": 1.0}, {"type": "text", "text": "x", "seconds": 2}],
              "_spans": {0: (0.0, 1.0), 1: (1.0, 3.0)}}
        f = SimpleNamespace(kind="reading", times=[0.5], extra={"need": 2.0, "shown": 1.0})
        self.assertEqual(autofix(sb, [f], frozen={"0:seconds"}), [])
        self.assertTrue(autofix(sb, [f]))

    def test_styles_wire_into_scenes(self):
        from alvenus import nodes as nd
        doc = self.doc()
        nd.use(doc, "calm", ["scene2", "scene3"])
        nd.set_param(doc, "calm.words.size", 0.8)
        nd.set_param(doc, "calm.picture.shape", "blob")
        nd.set_param(doc, "calm.dark", True)
        sc = nd.to_storyboard(doc)["scenes"]
        self.assertEqual(sc[1]["words_size"], 1.2)  # the scene's own setting wins
        self.assertEqual((sc[2]["words_size"], sc[2]["picture_shape"], sc[2]["dark"]), (0.8, "blob", True))
        nd.set_param(doc, "scene3.picture.shape", None)
        nd.set_param(doc, "calm.bogus", 1)
        self.assertTrue(any("calm" in p for p in nd.check(doc)))
        nd.remove(doc, "calm")
        self.assertNotIn("use", nd.find(doc, "scene2"))

    def test_move_copy_remove(self):
        from alvenus import nodes as nd
        doc = self.doc()
        new = nd.copy_scene(doc, "scene2")
        self.assertEqual(new, "scene7")
        nd.move(doc, "scene7", first=True)
        doc = nd.tidy(doc)
        self.assertEqual([n["id"] for n in nd.scenes_of(doc)][:2], ["scene7", "scene1"])
        self.assertEqual(nd.find(doc, "scene7.words")["of"], "scene7")
        self.assertEqual(nd.remove(doc, "scene7"), ["scene7", "scene7.in", "scene7.words", "scene7.picture"])
        self.assertEqual(nd.to_storyboard(doc), self.SB)

    def test_changes_since_last_build(self):
        from alvenus import nodes as nd
        doc = self.doc()
        last = {"hashes": {n["id"]: nd.node_hash(n) for n in doc["nodes"]}}
        nd.set_param(doc, "scene3.words.caption", "Fixed")
        nd.remove(doc, "scene6")
        self.assertEqual(sorted(nd.changes(doc, last)), ["-scene6", "-scene6.graphic", "scene3.words"])

    def test_controls_are_checked(self):
        from alvenus.paper import control_problem
        self.assertIsNone(control_problem("words_size", 1.3))
        self.assertIsNotNone(control_problem("words_size", 9))
        self.assertIsNotNone(control_problem("picture_shape", "star"))
        self.assertIsNone(control_problem("picture_shape_colour", "accent"))
        self.assertIsNotNone(control_problem("mark_colour", "red"))

    def test_controls_change_the_drawing(self):
        from alvenus.paper import print_plate, word_events
        a, _ = word_events("one two three", set(), 0, 3, 1080, 1920, "mono", "#D4F01E", (90, 200, 900, 600), False)
        b, lands = word_events("one two three", set(), 0, 3, 1080, 1920, "mono", "#D4F01E", (90, 200, 900, 600), False,
                               size=0.5, speed=0.1, delay=1.0)
        self.assertEqual([round(t, 2) for t in lands], [1.0, 1.1, 1.2])
        size = lambda ev: max(int(x) for x in __import__("re").findall(r"\\fs(\d+)", "".join(ev)))
        self.assertLess(size(b), size(a))
        _, under, _ = print_plate("mono", 540, 960, 0, (100, 300, 300, 400), "#D4F01E", shape="none")
        self.assertIsNone(under.getbbox())
        _, under, _ = print_plate("mono", 540, 960, 0, (100, 300, 300, 400), "#D4F01E", shape="blob")
        self.assertIsNotNone(under.getbbox())

    def test_scene_cache_ignores_word_controls(self):
        from alvenus.story import _scene_key
        sc = {"type": "image", "file": "x.jpg", "_design": "mono", "_k": 1}
        k = _scene_key(sc, 3, 1080, 1920, 30)
        self.assertEqual(k, _scene_key({**sc, "words_size": 1.4, "mark_colour": "#112233", "note": "n"}, 3, 1080, 1920, 30))
        self.assertNotEqual(k, _scene_key({**sc, "picture_shape": "blob"}, 3, 1080, 1920, 30))
        self.assertNotEqual(k, _scene_key({**sc, "_k": 2}, 3, 1080, 1920, 30))


class Studio(unittest.TestCase):
    def doc(self):
        from alvenus import nodes as nd
        return nd.to_nodes({"design": "paper", "scenes": [
            {"type": "title", "text": "Hi", "seconds": 2},
            {"type": "image", "file": "cup.jpg", "caption": "A cup", "seconds": 3, "words_size": 1.0}]})

    def test_plain_asks_are_understood(self):
        from alvenus.nodes import understand
        got, rest = understand("much bigger, no shape and make it feel like a punch", "words")
        self.assertEqual([(a, b) for a, b, _ in got], [("words", "size"), ("picture", "shape")])
        self.assertEqual(rest, ["make it feel like a punch"])
        got, rest = understand("picture bigger, tilt left, red, 4 seconds, whip", "scene")
        self.assertEqual([(a, b) for a, b, _ in got], [("picture", "size"), ("picture", "angle"), ("picture", "shape_colour"),
                                                       ("scene", "seconds"), ("in", "transition")])
        self.assertEqual(rest, [])

    def test_describe_applies_and_keeps_the_ask_for_the_ai(self):
        from alvenus import nodes as nd
        doc = self.doc()
        did = nd.describe(doc, "scene2.words", "bigger and slower, but more tense")
        self.assertEqual(did, ["words.size = 1.2", "words.speed = 0.42"])
        a = nd.find(doc, "scene2.words")["ask"]
        self.assertEqual((a["status"], a["left"]), ("waiting", ["more tense"]))
        self.assertIn("for you to do: more tense", nd.asks_text(doc, "v.nodes.json"))
        nd.answer(doc, "scene2.words", "held the last word longer")
        self.assertEqual(nd.asks(doc), [])
        nd.describe(doc, "scene2.picture", "no shape", stage="shape")  # a part that wasn't there yet
        self.assertEqual(nd.find(doc, "scene2.picture")["params"]["shape"], "none")
        self.assertEqual(nd.check(doc), [])

    def test_asks_do_not_break_locks(self):
        from alvenus import nodes as nd
        doc = self.doc()
        nd.lock(doc, ["scene1"])
        with self.assertRaises(SystemExit):
            nd.describe(doc, "scene1.words", "bigger")
        old = nd.node_hash(nd.find(doc, "scene2.words"))
        nd.find(doc, "scene2.words")["ask"] = {"text": "x", "status": "done"}
        self.assertEqual(nd.node_hash(nd.find(doc, "scene2.words")), old)

    def test_switching_a_stage_off(self):
        from alvenus import nodes as nd
        doc = self.doc()
        nd.switch(doc, "scene2", "words", on=False)
        nd.switch(doc, "scene2", "shape", on=False)
        sc = nd.to_storyboard(doc)["scenes"][1]
        self.assertNotIn("caption", sc)
        self.assertEqual(sc["picture_shape"], "none")
        nd.switch(doc, "scene2", "words", on=True)
        nd.switch(doc, "scene2", "shape", on=True)
        self.assertEqual(nd.to_storyboard(doc)["scenes"][1]["caption"], "A cup")
        self.assertNotIn("off", nd.find(doc, "scene2.words"))
        with self.assertRaises(SystemExit):
            nd.switch(doc, "scene2", "picture", on=False)

    def test_studio_schema_covers_every_stage(self):
        from alvenus import nodes as nd
        from alvenus.studio import schema
        sc = schema()
        for stage, part, params in nd.STAGES:
            for p in params:
                self.assertIn(p, sc[stage], (stage, p))


class Graph(unittest.TestCase):
    """A scene as a node graph: layer order and tool nodes."""

    def doc(self):
        from alvenus import nodes as nd
        return nd.to_nodes({"design": "paper", "scenes": [
            {"type": "title", "text": "Hi", "seconds": 2},
            {"type": "image", "file": "cup.jpg", "caption": "A cup", "seconds": 3,
             "layers": ["shape", "words", "picture", "marks"],
             "tools": [{"tool": "blur", "on": "background", "amount": 0.4}, {"tool": "glow", "on": "words", "off": True}]}]})

    def test_tools_and_layers_survive_the_round_trip(self):
        from alvenus import nodes as nd
        doc = self.doc()
        self.assertEqual([n["id"] for n in nd.tools_of(doc, "scene2")], ["scene2.blur", "scene2.glow"])
        self.assertEqual(nd.find(doc, "scene2.glow")["off"], ["tool"])
        sb = nd.to_storyboard(doc)
        self.assertEqual(sb["scenes"][1]["layers"], ["shape", "words", "picture", "marks"])
        self.assertEqual(sb["scenes"][1]["tools"], [{"name": "blur", "tool": "blur", "on": "background", "amount": 0.4},
                                                    {"name": "glow", "tool": "glow", "on": "words", "off": True}])
        self.assertEqual(nd.to_storyboard(nd.to_nodes(sb)), sb)
        self.assertEqual(nd.check(doc), [])

    def test_bad_tools_are_refused_in_plain_words(self):
        from alvenus import nodes as nd
        doc = self.doc()
        nd.find(doc, "scene2.blur")["params"]["on"] = "words!"
        nd.find(doc, "scene2.glow")["params"]["amount"] = 4
        got = " ".join(nd.check(doc))
        self.assertIn("blur can sit on", got)
        self.assertIn("glow amount must be a number from 0 to 1", got)
        with self.assertRaises(SystemExit):
            nd.add_tool(self.doc(), "scene2", "vignette", "words")

    def test_describing_changes_the_graph(self):
        from alvenus import nodes as nd
        doc = self.doc()
        nd.set_layers(doc, "scene2", [])
        self.assertNotIn("layers", nd.find(doc, "scene2")["params"])  # the usual order is not written
        did = nd.describe(doc, "scene2", "words behind the picture, soft glow on the picture, add a vignette, no blur")
        self.assertEqual(nd.find(doc, "scene2")["params"]["layers"], ["shape", "words", "picture", "marks"])
        tools = {n["id"]: n["params"] for n in nd.tools_of(doc, "scene2")}
        self.assertEqual(tools["scene2.glow2"], {"tool": "glow", "on": "picture"})
        self.assertEqual(tools["scene2.vignette"]["on"], "output")
        self.assertNotIn("scene2.blur", tools)
        self.assertEqual(len(did), 4)

    def test_a_scene_lock_covers_its_tools(self):
        from alvenus import nodes as nd
        doc = self.doc()
        nd.lock(doc, ["scene2"])
        with self.assertRaises(SystemExit):
            nd.add_tool(doc, "scene2", "blur", "picture")
        nd.find(doc, "scene2.blur")["params"]["amount"] = 0.9  # edited by hand
        self.assertTrue(any("locked" in x for x in nd.check(doc)))

    def test_copy_and_remove_take_the_tools_along(self):
        from alvenus import nodes as nd
        doc = self.doc()
        new = nd.copy_scene(doc, "scene2")
        self.assertEqual([n["id"] for n in nd.tools_of(doc, new)], [f"{new}.blur", f"{new}.glow"])
        gone = nd.remove(doc, "scene2")
        self.assertIn("scene2.blur", gone)
        self.assertEqual(nd.check(doc), [])

    def test_words_are_drawn_into_the_scene_only_when_something_sits_over_them(self):
        from alvenus.paper import ass_tools, inside
        self.assertFalse(inside({"type": "image"}))
        self.assertFalse(inside({"type": "image", "tools": [{"tool": "blur", "on": "words"}]}))
        self.assertTrue(inside({"type": "image", "layers": ["shape", "words", "picture", "marks"]}))
        self.assertTrue(inside({"type": "image", "tools": [{"tool": "vignette", "on": "output"}]}))
        self.assertFalse(inside({"type": "image", "tools": [{"tool": "vignette", "on": "output", "off": True}]}))
        ev = ["Dialogue: 20,0:00:00.00,0:00:01.00,Card,,0,0,0,,{\\an7\\bord0}HI"]
        out = ass_tools(ev, [{"tool": "glow", "on": "words", "amount": 0.5}], 1080, "#D4F01E")
        self.assertEqual(len(out), 2)
        self.assertTrue(out[0].startswith("Dialogue: 19,"))
        self.assertIn("\\bord6.5\\blur8.6", out[0])  # the halo comes after the event's own \\bord0, so it wins

    def test_the_scene_cache_keys_on_words_only_when_they_are_drawn_in(self):
        from alvenus.story import _scene_key
        sc = {"type": "image", "caption": "one", "_design": "paper", "_k": 1}
        self.assertEqual(_scene_key(sc, 3, 640, 360, 30), _scene_key({**sc, "caption": "two"}, 3, 640, 360, 30))
        sc["layers"] = ["shape", "words", "picture", "marks"]
        self.assertNotEqual(_scene_key(sc, 3, 640, 360, 30), _scene_key({**sc, "caption": "two"}, 3, 640, 360, 30))


class Genres(unittest.TestCase):
    """Talking head layouts, documentary and travel touches."""

    def test_the_director_opens_graphics_and_keeps_hook_and_payoff_on_the_face(self):
        from alvenus.talk import direct
        spans = {i: (i * 3.0, i * 3.0 + 3.0) for i in range(8)}
        kinds = direct(spans, graphic={4}, wordish={2}, full=set(), overrides={})
        self.assertEqual(kinds[0], "full")
        self.assertEqual(kinds[7], "full")
        self.assertEqual(kinds[4], "graphic")
        self.assertEqual(kinds[2], "words")
        self.assertEqual(direct(spans, {4}, set(), set(), {4: "full", 0: "side"})[4], "full")
        self.assertEqual(direct(spans, set(), set(), set(), {0: "side"})[0], "words")

    def test_layouts_and_chapters_are_checked(self):
        from alvenus.talk import parse_chapters, parse_layouts
        self.assertEqual(parse_layouts(["3=side"], 5), {2: "side"})
        with self.assertRaises(SystemExit):
            parse_layouts(["3=left"], 5)
        self.assertEqual(parse_chapters(["1=Intro"], 5), {0: "Intro"})

    def test_the_set_geometry_fits_the_frame_and_is_even(self):
        from alvenus.talk import geometry
        for w, h in ((1920, 1080), (1080, 1920), (1080, 1350)):
            for flip in (False, True):
                (fx, fy, fw, fh), (px, py, pw, ph), side = geometry(w, h, flip)
                self.assertEqual(side, w / h >= 1.2)
                for v in (fx, fy, fw, fh, px, py, pw, ph):
                    self.assertEqual(v % 2, 0)
                self.assertLessEqual(max(fx + fw, px + pw), w)
                self.assertLessEqual(max(fy + fh, py + ph), h)

    def test_panel_words_keep_the_key_word_in_serif(self):
        from alvenus.talk import key_words, panel_words
        from alvenus.wordtime import Word
        ws = [Word(t, i * 0.4, i * 0.4 + 0.3, 3) for i, t in enumerate("they slow to a crawl.".split())]
        self.assertEqual(key_words(ws, set()), {"crawl"})
        rows = panel_words(ws, 0.0, 3.0, 800, 700, "#7FA7E0", set())
        self.assertEqual(len(rows), 5)
        self.assertIn("Instrument Serif", rows[-1])

    def test_letterbox_bars_and_the_panel_inside_them(self):
        from alvenus import genre, graphics
        genre.EXTRAS = {"letterbox": 2.39}
        try:
            self.assertEqual(genre.matte(1920, 1080), 138)
            self.assertEqual(genre.matte(1080, 1920), 0)  # no bars on a tall frame
            self.assertIn("pos(0,138)", graphics._panel(0, 1, 1920, 1080))
            self.assertEqual(sum(r.startswith("Dialogue: 0,") for r in genre.events(1920, 1080, 10, "#C9A86A")), 2)
        finally:
            genre.EXTRAS = {}
        self.assertEqual(genre.events(1920, 1080, 10, "#C9A86A"), [])

    def test_new_title_styles(self):
        from alvenus.style import TITLE_STYLES, title_events
        for kind, text in (("chapter", "Part one|The night shift"), ("place", "Lisbon|Portugal|38.72 N, 9.14 W")):
            self.assertIn(kind, TITLE_STYLES)
            rows = title_events(text, 1080, 1920, "#FFB347", 0.2, 3.0, centre=True, kind=kind)
            self.assertGreaterEqual(len(rows), 3)
        self.assertIn("LISBON", "".join(title_events("Lisbon", 1920, 1080, "#FFB347", 0, 2, True, "place")))

    def test_doc_name_tags_follow_the_setting(self):
        from alvenus import genre
        from alvenus.graphics import LowerThird, lower_third_events
        genre.EXTRAS = {"lower_third_style": "doc"}
        try:
            rows = lower_third_events(LowerThird(0, "Asha Rao", "Engineer"), 0.0, 1920, 1080, "#C9A86A")
        finally:
            genre.EXTRAS = {}
        self.assertTrue(any("Libre Baskerville" in r for r in rows))
        self.assertTrue(any("ENGINEER" in r for r in rows))

    def test_presets_exist_and_carry_their_touches(self):
        from alvenus.presets import defaults
        self.assertTrue(defaults("talk-studio")["talk"])
        self.assertEqual(defaults("documentary")["lower_third_style"], "doc")
        self.assertEqual(defaults("travel-reel")["title_style"], "place")

    # --- archive documentary (Venus board, 21 Nov) ---

    def test_new_reveals_build_their_graphs(self):
        from alvenus.cut import TRANSITIONS, join_pair
        for name in ("bloom", "cloud", "tear", "tiles"):
            self.assertEqual(TRANSITIONS[name], "custom")
            g = join_pair("0:v", "1:v", "out", name, 1.0, 2.0, "1920x1080", 30, 0)
            self.assertIn("maskedmerge", g)
            self.assertTrue(g.endswith("[out]"))
        self.assertIn("flags=neighbor", join_pair("0:v", "1:v", "o", "tiles", 1.0, 2.0, "1920x1080", 30, 1))
        self.assertIn("0xEDE6D8", join_pair("0:v", "1:v", "o", "tear", 1.0, 2.0, "1920x1080", 30, 1))  # the torn paper strip

    def test_archive_looks(self):
        from alvenus.style import LOOKS
        for name in ("sepia", "archive"):
            self.assertIn("hue=s=0", LOOKS[name])

    def test_archive_words_sit_away_from_the_print(self):
        from alvenus import genre
        left = "".join(genre.archive_card("1908", "Arrival", "First day", 0, 4, 1920, 1080, "#C8102E", k=1))
        right = "".join(genre.archive_card("1908", "Arrival", "First day", 0, 4, 1920, 1080, "#C8102E", k=0))
        self.assertIn("ARRIVAL", left)
        self.assertIn("1908", left)
        self.assertIn("pos(115,", left)  # odd scene: print on the right, words on the left
        self.assertIn("pos(1805,", right)  # even scene: year bottom right
        rows = genre.verse_card("We never thought the street would forget us.", "Letter, 1931", 0, 5, 1920, 1080, "#C8102E")
        self.assertTrue(any("LETTER, 1931" in r for r in rows))
        corners = [genre.credit("Written by", "Asha Rao", 0, 3, 1920, 1080, k)[1] for k in range(4)]
        self.assertEqual(len({c.split("pos(")[1].split(")")[0] for c in corners}), 4)  # each credit in a new corner
        self.assertIn("ASHA RAO", corners[0])

    def test_storyboard_takes_archive_scenes_frames_and_credits(self):
        import json
        import tempfile
        from pathlib import Path
        from alvenus.story import load
        with tempfile.TemporaryDirectory() as d:
            Path(d, "p.jpg").write_bytes(b"x")
            sb = {"scenes": [{"type": "archive", "file": "p.jpg", "year": "1908", "frame": "cloud", "credit": "Written by|Asha Rao"}],
                  "quote_style": "verse", "credits": [["Music", "Ironhorse"]]}
            Path(d, "sb.json").write_text(json.dumps(sb))
            self.assertEqual(load(Path(d, "sb.json"))["scenes"][0]["type"], "archive")
            for bad in ({"frame": "smoke"}, {"credit": "no bar here"}):
                sb2 = json.loads(json.dumps(sb))
                sb2["scenes"][0].update(bad)
                Path(d, "sb.json").write_text(json.dumps(sb2))
                with self.assertRaises(SystemExit):
                    load(Path(d, "sb.json"))

    def test_match_cut_finds_the_same_framing(self):
        import numpy as np
        from alvenus.matchcut import chain, distance, line_up, look_at, reframe_filter, runs

        def disc(cx, cy, r):
            yy, xx = np.mgrid[0:54, 0:96]
            return np.where(np.hypot(xx - cx, yy - cy) < r, 30.0, 200.0)

        def bars(k):
            yy, xx = np.mgrid[0:54, 0:96]
            return 120 + 80 * np.sin(xx / (3 + k))

        looks = [look_at(disc(48, 27, 12)), look_at(bars(0)), look_at(disc(52, 25, 10)), look_at(bars(1)), look_at(disc(46, 28, 13))]
        self.assertLess(distance(looks[0], looks[2]), distance(looks[0], looks[1]))
        order = chain(looks)
        groups = runs(looks, order)
        self.assertIn(sorted([0, 2, 4]), [sorted(g) for g in groups if len(g) == 3])
        z, x0, y0 = line_up(looks[0], look_at(disc(70, 20, 6)))
        self.assertGreater(z, 1.0)
        self.assertTrue(0 <= x0 <= z - 1 and 0 <= y0 <= z - 1)
        self.assertIsNone(line_up(looks[0], looks[0]))
        self.assertIn("crop=1920:1080", reframe_filter([1.5, 0.2, 0.1], 1920, 1080))

    def test_archive_presets(self):
        from alvenus.presets import defaults
        self.assertEqual(defaults("archive-doc")["transition"], "bloom")
        self.assertEqual(defaults("sepia-film")["look"], "sepia")


class IdeaToStoryboard(unittest.TestCase):
    """Phase 2, run 1: brief, recipe, story check, approval gate."""

    def _sb(self):
        from alvenus.brief import new, skeleton

        b = new("why cold kills phone batteries")
        b.update(audience="phone users", point="Cold slows the battery, it doesn't empty it.", kind="explainer",
                 seconds=30, aspect="9:16", mood="curious", facts=[{"fact": "40% less at -10C", "source": "test"}])
        sb = skeleton(b)
        texts = ["Your battery isn't empty.", "Why phones die in the cold", None, None, "It looks empty. But it isn't.", None,
                 "Cold slows your battery; it doesn't empty it."]
        for sc, t in zip(sb["scenes"], texts):
            if t:
                sc["text"] = t
        s = sb["scenes"]
        s[2].update(title="Inside", items=["Liquid thickens", "Charge slows"])
        s[3].update(left={"title": "Warm", "points": ["flows"]}, right={"title": "Cold", "points": ["crawls"]})
        s[5].update(value="40%", label="less charge")
        return sb

    def test_brief_needs_its_answers(self):
        from alvenus.brief import new, problems

        p = problems(new("an idea"))
        self.assertTrue(any(x.startswith("point") for x in p) and any(x.startswith("kind") for x in p))
        b = new("x")
        b.update(audience="a", point="one thing", kind="travel", seconds=20, aspect="9:16", mood="calm", material="none")
        self.assertTrue(any("footage" in x for x in problems(b)))

    def test_recipe_lays_out_beats_to_length(self):
        from alvenus.brief import RECIPES, lengths

        for kind in RECIPES:
            ls = lengths(kind, 30)
            self.assertLessEqual(ls[0], 2.8)
            self.assertAlmostEqual(sum(ls), 30, delta=3)

    def test_good_storyboard_passes(self):
        from alvenus.storycheck import check, weak

        self.assertEqual([f.line() for f in weak(check(self._sb()))], [])

    def test_weak_points_are_named(self):
        from alvenus.storycheck import check, weak

        sb = self._sb()
        s = sb["scenes"]
        s[0]["text"] = "Hi everyone, welcome back"
        s[4]["text"] = "Phones are bad in winter. Everyone knows that."
        s[5]["value"] = "65%"
        s[6]["text"] = "Keep it in your pocket."
        found = " | ".join(f.line() for f in weak(check(sb)))
        for bit in ("greeting", "says 2 things", "\"65%\"", "doesn't turn", "doesn't say the point"):
            self.assertIn(bit, found)

    def test_empty_and_too_long(self):
        from alvenus.storycheck import check, weak

        sb = self._sb()
        sb["scenes"][2]["items"] = []
        sb["scenes"][3]["seconds"] = 12
        found = " | ".join(f.line() for f in weak(check(sb)))
        self.assertIn("no items yet", found)
        self.assertIn("long for one scene", found)

    def test_approval_fingerprint(self):
        import json
        import tempfile
        from pathlib import Path

        from alvenus.approval import approve, require, status

        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "sb.json"
            sb = self._sb()
            p.write_text(json.dumps(sb))
            self.assertFalse(status(p)[0])
            with self.assertRaises(SystemExit):
                require(p)
            approve(p, "Asha")
            self.assertTrue(status(p)[0])
            sb["_how_to_fill"] = "notes for the AI don't count"
            p.write_text(json.dumps(sb))
            self.assertTrue(status(p)[0])
            sb["scenes"][0]["text"] = "Changed"
            p.write_text(json.dumps(sb))
            ok, why = status(p)
            self.assertFalse(ok)
            self.assertIn("changed since Asha", why)

    def test_marked_word_keeps_its_punctuation(self):
        from alvenus.paper import parse

        self.assertEqual(parse("It looks *empty*. Yes", set())[2], ("empty.", "serif"))


class Community(unittest.TestCase):
    """Ideas and add-ons from users: data-only add-ons, private-bits check, the form link."""

    def test_example_addons_are_valid_and_load(self):
        import json
        import shutil
        import tempfile
        from pathlib import Path

        from alvenus import community as cm
        from alvenus.brief import RECIPES
        from alvenus.presets import PRESETS

        root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as d:
            for kind, f, name in (("styles", "addon-style.json", "test-market"), ("recipes", "addon-recipe.json", "test-before-after")):
                (Path(d) / kind).mkdir()
                shutil.copy(root / "examples" / f, Path(d) / kind / f"{name}.json")
            (Path(d) / "styles" / "bad.json").write_text(json.dumps({"about": "x", "by": "y", "look": "neon", "run": "rm -rf /"}))
            cm.load_addons(Path(d))
        try:
            self.assertEqual(PRESETS["test-market"]["addon"], "Your name here")
            self.assertEqual(RECIPES["test-before-after"]["beats"][0][0], "hook")
            self.assertNotIn("bad", PRESETS)
            self.assertTrue(any("bad.json" in n and "run: not a style setting" in n for n in cm.NOTES))
        finally:
            PRESETS.pop("test-market", None)
            RECIPES.pop("test-before-after", None)

    def test_addons_cannot_replace_built_ins(self):
        from alvenus.community import recipe_problems, style_problems

        self.assertTrue(any("built-in" in p for p in style_problems("explainer", {"about": "x", "by": "y"})))
        self.assertTrue(any("built-in" in p for p in recipe_problems("travel", {"about": "x", "by": "y", "beats": []})))

    def test_private_bits_are_caught(self):
        from alvenus.community import private_bits

        self.assertEqual(private_bits("a lyric overlay on the beat"), [])
        for bad in ("mail me at a.b@c.com", "key sk-abcdefghijklmnopqrstuv", "ghp_" + "a" * 30, "/Users/sam/clips/x.mov",
                    "password: hunter2"):
            self.assertTrue(private_bits(bad), bad)

    def test_suggestion_needs_answers_and_gives_a_link(self):
        from alvenus.community import REPO, form_link, new_suggestion, suggestion_problems

        s = new_suggestion("lyrics on the beat")
        self.assertTrue(suggestion_problems(s))
        s.update(title="Lyric overlay", why="saves hours", example="a 20 s montage", credit_name="Asha")
        self.assertEqual(suggestion_problems(s), [])
        url, paste = form_link(s)
        self.assertTrue(url.startswith(f"https://github.com/{REPO}/issues/new?template=suggest-feature.yml"))
        self.assertIn("lyrics", paste)

    def test_guard_only_allows_addon_data(self):
        import importlib.util
        from pathlib import Path

        spec = importlib.util.spec_from_file_location("guard", Path(__file__).resolve().parent.parent / "tools" / "addon_guard.py")
        g = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(g)
        self.assertTrue(g.ALLOWED.match("alvenus/addons/styles/night-market.json"))
        for bad in ("alvenus/cli.py", "alvenus/addons/styles/x.py", ".github/workflows/x.yml", "alvenus/addons/styles/../cli.json"):
            self.assertFalse(g.ALLOWED.match(bad), bad)


if __name__ == "__main__":
    unittest.main()
