"""Batch 2 of lessons from real edits: a measured mix, fewer varied effects, music that
repeats on the bar, caption cards placed by the picture, clean type, own fonts, locked
approvals, repeated shots, picture-to-line, and how-to videos."""

import json
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

from alvenus import listen, mix, placement, style
from alvenus.wordtime import Word

SR = listen.SR


def tone(parts, total, level=0.3, sr=SR):
    y = np.zeros(int(total * sr), np.float32)
    for a, b in parts:
        t = np.arange(int((b - a) * sr)) / sr
        y[int(a * sr): int(a * sr) + len(t)] += (level * np.sin(2 * np.pi * 180 * t)).astype(np.float32)
    return y


class MixTests(unittest.TestCase):
    def test_voice_kept_clear_of_music(self):
        phrases = [(1.0, 3.0), (5.0, 7.0)]
        voice = tone(phrases, 9.0, 0.2)
        music = (0.2 * np.sin(2 * np.pi * 110 * np.arange(9 * SR) / SR)).astype(np.float32)  # as loud as the voice
        keys = listen.duck_keys(phrases, 9.0, 2.0)  # a shallow dip someone set
        keys, gaps = mix.fit_under_voice(voice, music, keys, phrases, gap=10.0)
        self.assertTrue(all(g >= 9.7 for _, _, g in gaps), gaps)
        self.assertEqual(listen.moves_on_words(keys, phrases), [])  # still only moves between lines

    def test_effects_never_stacked_and_not_too_many(self):
        ev = [(1.0, "pop"), (1.2, "hit"), (2.0, "pop"), (2.6, "pop"), (3.0, "pop"), (3.4, "tick")]
        kept, dropped = mix.tidy(ev)
        self.assertIn((1.2, "hit"), kept)  # the stronger of two stacked sounds stays
        self.assertNotIn((1.0, "pop"), kept)
        times = [t for t, _ in kept]
        self.assertTrue(all(b - a >= 0.45 for a, b in zip(times, times[1:])))
        self.assertGreater(dropped, 0)

    def test_quiet_effects_are_lifted(self):
        bed = (0.3 * np.sin(2 * np.pi * 200 * np.arange(4 * SR) / SR)).astype(np.float32)
        lifts = mix.effect_gains([(1.0, "tick"), (2.0, "boom")], bed)
        self.assertGreater(lifts[0], 3.0)
        self.assertGreaterEqual(lifts[1], 0.0)
        self.assertTrue(all(0 <= x <= 9 for x in lifts))

    def test_short_song_repeats_on_a_bar_with_no_jump(self):
        sr = 48000
        t = np.arange(int(8 * sr)) / sr
        y = 0.1 * np.sin(2 * np.pi * 220 * t)
        for b in np.arange(0, 8, 0.5):  # 120 BPM
            i = int(b * sr)
            y[i: i + 2000] += 0.6 * np.hanning(2000)
        with tempfile.TemporaryDirectory() as d:
            src, out = Path(d) / "s.wav", Path(d) / "long.wav"
            with wave.open(str(src), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(sr)
                w.writeframes((np.clip(y, -1, 1) * 32767).astype("<i2").tobytes())
            got, joins, jumps = listen.extend_music(src, 20.0, out)
            self.assertEqual(got, out)
            self.assertGreaterEqual(len(joins), 2)
            self.assertTrue(all(j < 2.0 for j in jumps), jumps)
            with wave.open(str(out)) as w:
                self.assertGreaterEqual(w.getnframes() / w.getframerate(), 20.0)
            same, j2, _ = listen.extend_music(src, 5.0, out)
            self.assertEqual((same, j2), (src, []))


class CaptionTests(unittest.TestCase):
    def words(self, text):
        return [Word(x, i * 0.3, i * 0.3 + 0.28, 0) for i, x in enumerate(text.split())]

    def test_cards_two_to_six_words_never_ending_on_a_joining_word(self):
        for vertical in (False, True):
            cards = style.chunks(self.words("Every line stays clear when the music knows where the voice is, and nobody notices"), vertical)
            self.assertTrue(all(2 <= len(c) <= 6 for c in cards), cards)
            self.assertFalse(any(c[-1].text.lower() in style._JOIN for c in cards[:-1]))

    def test_creator_chosen_card_size(self):
        from alvenus.story import card_words

        self.assertEqual(card_words("3-5"), (3, 5))
        self.assertEqual(card_words([5, 2]), (2, 5))
        self.assertEqual(card_words(None), (2, 6))
        style.CARD_WORDS = (2, 3)
        try:
            self.assertTrue(all(len(c) <= 3 for c in style.chunks(self.words("one two three four five six seven"), False)))
        finally:
            style.CARD_WORDS = (2, 6)

    def test_card_goes_where_the_picture_is_calm_and_never_on_skin(self):
        rng = np.random.default_rng(0)
        f = np.full((90, 160, 3), 40, np.uint8)
        f[45:] = rng.integers(0, 255, (45, 160, 3))  # busy bottom half
        p = placement.Planner(None, 1280, 720, frames=(f[None], 0.5))
        self.assertTrue(p.place(0, 1, 400, 60).startswith("top"))
        g = np.full((90, 160, 3), 40, np.uint8)
        g[60:, 50:110] = (214, 160, 130)  # skin tone at the bottom centre
        q = placement.Planner(None, 1280, 720, frames=(g[None], 0.5))
        self.assertNotEqual(q.place(0, 1, 400, 60), "bottom")
        fixed = placement.Planner(None, 1280, 720, fixed={0: "top-left"}, frames=(f[None], 0.5))
        self.assertEqual(fixed.place(0, 1, 400, 60, line=0), "top-left")
        self.assertEqual(placement.parse_place("Bottom Left"), "bottom-left")
        self.assertIsNone(placement.parse_place("auto"))

    def test_tall_video_cards_stay_clear_of_app_buttons(self):
        L, T, R, B = placement.safe_box(1080, 1920)
        self.assertLessEqual(B, 0.8 * 1920)
        self.assertLessEqual(R, 0.88 * 1080)
        for name in placement.slots(1080, 1920):
            an, x, y = placement.Planner(None, 1080, 1920, frames=(np.zeros((0, 1, 1, 3), np.uint8), 0.5)).anchor(name)
            self.assertTrue(L <= x <= R and T <= y <= B)

    def test_clean_type_check_finds_a_lone_word(self):
        from alvenus.selfcheck import _type

        with tempfile.TemporaryDirectory() as d:
            ass = Path(d) / "a.ass"
            ass.write_text("[Events]\nDialogue: 2,0:00:01.00,0:00:02.00,Cap,,0,0,0,,{\\an2\\pos(640,660)}one two three four\\Nfive\n"
                           "Dialogue: 2,0:00:03.00,0:00:04.00,Cap,,0,0,0,,{\\an2\\pos(640,660)}a clean card\n", encoding="utf-8")
            notes = [str(n) for n in _type(ass, 1280, 720)]
        self.assertEqual(len([n for n in notes if "alone" in n]), 1)
        self.assertFalse(any("3.0s" in n for n in notes))

    def test_brand_fonts_replace_venus_fonts_everywhere(self):
        from alvenus import brand

        f = Path(style.FONTS) / "LibreBaskerville-Regular.ttf"
        try:
            notes = brand.font_setup({"heading": str(f), "body": "No Such Font Anywhere"})
            self.assertEqual(style.FONT_MAP.get("Inter Display Black"), "Libre Baskerville")
            self.assertNotIn("Inter ExtraBold", style.FONT_MAP)  # a font that isn't here: said plainly, not faked
            self.assertTrue(any("isn't installed" in n for n in notes))
            with tempfile.TemporaryDirectory() as d:
                p = Path(d) / "t.ass"
                style.write_ass(p, 1280, 720, "#1F3A93", title="Hello", cut_len=3.0, extras=False)
                self.assertIn("Libre Baskerville", p.read_text(encoding="utf-8"))
                self.assertIn(f.name, {x.name for x in style.fonts_dir().iterdir()})
        finally:
            brand.reset_fonts()
        self.assertEqual(style.FONT_MAP, {})


class StoryTests(unittest.TestCase):
    def test_approved_parts_stay_locked(self):
        from alvenus import approval

        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "sb.json"
            sb = {"aspect": "16:9", "scenes": [{"type": "text", "text": "One", "seconds": 2},
                                               {"type": "text", "text": "Two", "seconds": 2}]}
            p.write_text(json.dumps(sb), encoding="utf-8")
            approval.approve(p, "test")
            self.assertEqual(approval.changed_since(p), [])
            sb["scenes"].insert(0, {"type": "text", "text": "New first", "seconds": 2})  # adding a scene isn't changing others
            sb["scenes"][2]["seconds"] = 3
            p.write_text(json.dumps(sb), encoding="utf-8")
            self.assertEqual(approval.changed_since(p), [("scene 2 (now scene 3)", ["seconds"])])

    def test_repeat_shot_and_how_to_checks(self):
        from alvenus.storycheck import check

        sb = {"brief": {"kind": "how-to"}, "scenes": [
            {"type": "clip", "file": "a.mp4", "from": 0, "seconds": 3, "text": "Click the download button"},
            {"type": "clip", "file": "b.mp4", "seconds": 3, "text": "Or you can ask your AI"},
            {"type": "clip", "file": "a.mp4", "from": 1, "seconds": 3, "text": "the mockup of the page"}]}
        codes = {f.code for f in check(sb, learn=False)}
        self.assertTrue({"repeat-shot", "stand-in", "other-way-mixed", "no-path"} <= codes, codes)
        sb["scenes"][2]["repeat_ok"] = True
        sb["scenes"][1]["alternative"] = "Another way"
        codes = {f.code for f in check(sb, learn=False)}
        self.assertNotIn("repeat-shot", codes)
        self.assertNotIn("other-way-mixed", codes)

    def test_how_to_is_a_kind(self):
        from alvenus.brief import KINDS, RECIPES

        self.assertIn("how-to", KINDS)
        self.assertEqual(RECIPES["how-to"]["beats"][1][0], "need")

    def test_weakest_picture_match(self):
        from alvenus.fit import weakest

        self.assertEqual(weakest([0.30, 0.32, 0.33, 0.19]), [3])
        self.assertEqual(weakest([0.30, 0.31, 0.29]), [])


class ScreenTests(unittest.TestCase):
    def test_camera_pushes_in_on_typing_and_out_on_a_new_page(self):
        from alvenus.screencam import path_of

        fr = np.full((40, 90, 160), 240, np.uint8)
        for i in range(5, 20):  # typing in a small box
            fr[i:, 60:64, 100 + (i - 5) * 2: 102 + (i - 5) * 2] = 0
        fr[25:] = 120  # the whole page changes
        keys = path_of(fr)
        z = [k[1] for k in keys]
        self.assertGreater(max(z[5:20]), 1.4)
        self.assertLess(z[-1], 1.15)
        self.assertTrue(all(abs(b - a) < 0.35 for a, b in zip(z, z[1:])))  # eased, never a jump
        self.assertGreater(keys[19][2], 0.55)  # it went right, toward the typing


if __name__ == "__main__":
    unittest.main()
