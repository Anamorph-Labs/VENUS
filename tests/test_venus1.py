"""The Venus 1 board styles: trailer and essay type cards, the new sounds,
two-line charts with a shaded slope, interview captions and words behind the
speaker, and the ultra-wide band."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np


class TypeCards(unittest.TestCase):
    def test_every_card_draws_frames_of_the_right_size(self):
        from alvenus.typecards import frames
        for sc in ({"type": "slam", "text": "Bruce Lee", "small": "Based on the writings of"},
                   {"type": "slam", "text": "Banshee", "texture": "red", "wipe": False},
                   {"type": "date", "text": "2019", "small": "Coming soon"},
                   {"type": "scramble", "text": "Taxes", "to": "F€$Y£"}):
            with self.subTest(sc["type"]):
                fs = list(frames(sc, 1.0, 320, 180, 12, 0, "#C0392B"))
                self.assertEqual(len(fs), 12)
                self.assertEqual(fs[0].shape, (180, 320, 3))
                self.assertGreater(np.std(np.stack(fs)), 5)  # not a blank card

    def test_vertical_cards_fit(self):
        from alvenus.typecards import frames
        fs = list(frames({"type": "slam", "text": "A Very Long Credit Name"}, 0.5, 180, 320, 10, 1, "#C0392B"))
        self.assertEqual(fs[-1].shape, (320, 180, 3))

    def test_scramble_lands_on_its_last_word_in_a_block(self):
        from alvenus.typecards import frames
        fs = list(frames({"type": "scramble", "text": "Taxes", "to": "Fees"}, 1.0, 320, 180, 20, 0, "#E3101A"))
        last = fs[-1].astype(float)
        self.assertLess(last[80:100, 140:180].mean(), 120)  # the black stamp block sits in the middle

    def test_cards_bring_their_sounds(self):
        from alvenus.typecards import moments
        self.assertIn("boom", [k for _, k in moments({"type": "slam"}, 5.0, 8.0)])
        self.assertIn("riser", [k for _, k in moments({"type": "slam"}, 5.0, 8.0)])
        self.assertNotIn("riser", [k for _, k in moments({"type": "slam"}, 0.0, 3.0)])  # no room for it at the start
        self.assertIn("braam", [k for _, k in moments({"type": "date"}, 0.0, 3.0)])
        self.assertIn("glitch", [k for _, k in moments({"type": "scramble"}, 0.0, 3.0)])

    def test_storyboard_knows_the_cards(self):
        from alvenus import story
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "sb.json"
            p.write_text(json.dumps({"scenes": [{"type": "slam", "text": "X"}, {"type": "date", "text": "2027"},
                                                 {"type": "scramble", "text": "a", "to": "b"}]}))
            self.assertEqual(len(story.load(p)["scenes"]), 3)
            p.write_text(json.dumps({"scenes": [{"type": "slam", "text": ""}]}))
            with self.assertRaises(SystemExit):
                story.load(p)
            p.write_text(json.dumps({"scenes": [{"type": "slam", "text": "X", "texture": "velvet"}]}))
            with self.assertRaises(SystemExit):
                story.load(p)


class Sounds(unittest.TestCase):
    def test_every_sound_is_finite_and_not_silent(self):
        from alvenus import sfx
        for name, (make, level, peak) in sfx.KINDS.items():
            with self.subTest(name):
                y = make()
                self.assertEqual(y.shape[1], 2)
                self.assertTrue(np.isfinite(y).all())
                self.assertGreater(np.abs(y).max(), 0)

    def test_pack_exports_wavs(self):
        from alvenus.sfx import KINDS, export_pack
        with tempfile.TemporaryDirectory() as d:
            files = export_pack(Path(d) / "pack")
            self.assertEqual({f.stem for f in files}, set(KINDS))
            self.assertTrue(all(f.stat().st_size > 1000 for f in files))

    def test_riser_peaks_on_its_moment(self):
        from alvenus import sfx
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.wav"
            sfx.write_track(p, [(3.0, "riser")], 4.0)
            import wave
            with wave.open(str(p)) as w:
                a = np.frombuffer(w.readframes(w.getnframes()), "<i2").reshape(-1, 2)
            loud = np.argmax(np.abs(a[:, 0])) / sfx.SR
            self.assertAlmostEqual(loud, 3.0, delta=0.15)


class Charts(unittest.TestCase):
    def test_two_lines_a_slope_and_a_note(self):
        from alvenus.graphics import Chart, line_chart_events
        ch = Chart(0, [("0", 0), ("10", 150), ("20", 300)], "Pay", more=[("Rent", [0, 240, 480])],
                   slope={"from": 0, "to": 1, "label": "What is slope?"}, notes=[(2, "same hours")], name="Pay")
        rows = "\n".join(line_chart_events(ch, 0, 5, 1920, 1080, "#E06C75"))
        self.assertIn("What is slope?", rows)
        self.assertIn("SAME HOURS", rows)
        self.assertIn("Rent", rows)
        plain = "\n".join(line_chart_events(Chart(0, [("a", 1), ("b", 2)]), 0, 5, 1920, 1080, "#E06C75"))
        self.assertNotIn("slope", plain)

    def test_storyboard_checks_extra_lines(self):
        from alvenus import story
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "sb.json"
            p.write_text(json.dumps({"scenes": [{"type": "line_chart", "points": [["a", 1], ["b", 2]],
                                                  "lines": [{"name": "x", "values": [1]}]}]}))
            with self.assertRaises(SystemExit):
                story.load(p)

    def test_last_pin_keeps_pulsing(self):
        from alvenus.graphics import Pin, pin_events
        rows = pin_events([Pin(0.5, 0.5, "Here")], 0, 6, 1920, 1080, "#E06C75")
        self.assertGreater(sum("fscx260" in r for r in rows), 2)


class Captions(unittest.TestCase):
    def words(self):
        from alvenus.wordtime import Word
        return [Word("Lower", 0.0, 0.4, 0), Word("your", 0.4, 0.6, 0), Word("resting", 0.6, 1.0, 0),
                Word("heart", 1.0, 1.3, 0), Word("rate.", 1.3, 1.7, 0)]

    def test_bracket_and_keyword_modes(self):
        from alvenus import style
        try:
            style.CAPTION_MODE = "bracket"
            rows = style.caption_events(self.words(), 1080, 1920, "#C8102E")
            self.assertEqual(len(rows), 5)
            self.assertIn("[heart]", "".join(rows))
            style.CAPTION_MODE = "keyword"
            rows = style.caption_events(self.words(), 1080, 1920, "#E8B04A")
            self.assertTrue(any("Instrument Serif" in r and "resting" in r for r in rows))  # the longest real word leads
        finally:
            style.CAPTION_MODE = "pop"


class Behind(unittest.TestCase):
    def test_words_stay_behind_the_person(self):
        from alvenus.fx import apply
        frames = np.full((6, 180, 120, 3), 20, np.uint8)
        frames[:, 20:180, 40:80] = 200  # the "person"
        mask = np.zeros((6, 180, 120), np.float32)
        mask[:, 20:180, 40:80] = 1
        out = apply(frames, 30, ["behind"], {"words": "IDEAL MOMENT", "beat": 0.01}, mask=mask)
        self.assertTrue((out[:, 20:180, 40:80] == 200).all())  # the person untouched
        self.assertGreater(out[-1, :90, :40, 0].max(), 150)  # red words on the wall beside them

    def test_spans_change_only_their_stretch(self):
        from alvenus.fxrender import apply_spans
        with tempfile.TemporaryDirectory() as d:
            v = Path(d) / "v.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=0x303030:s=160x90:d=2:r=10", "-f", "lavfi",
                            "-i", "sine=d=2", "-shortest", "-pix_fmt", "yuv420p", str(v)], check=True)
            apply_spans(v, [(0.5, 1.0, ["negative"], {})])
            from alvenus.fxrender import read_frames
            f, _ = read_frames(v)
            self.assertEqual(len(f), 20)
            self.assertLess(abs(float(f[2].mean()) - float(f[15].mean())), 3)  # outside: untouched
            self.assertGreater(abs(float(f[7].mean()) - float(f[2].mean())), 5)  # inside: changed
            out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(v)],
                                 capture_output=True, text=True).stdout
            self.assertIn("audio", out)


class Band(unittest.TestCase):
    def test_band_on_a_vertical_frame(self):
        from alvenus import genre
        try:
            genre.EXTRAS = {"band": 4.74, "band_words": [("Speak louder than words.", 1, 4)],
                            "band_end": ("Bali", "Lives forever in the heart", 8, 10)}
            bar = genre.matte(1080, 1920)
            self.assertAlmostEqual(1920 - 2 * bar, 1080 / 4.74, delta=2)
            rows = "\n".join(genre.events(1080, 1920, 10, "#E8D9B0"))
            self.assertIn("LOUDER", rows)
            self.assertIn("BALI", rows)
        finally:
            genre.EXTRAS = {}

    def test_presets_are_complete(self):
        from alvenus.presets import PRESETS
        for k in ("trailer", "video-essay", "interview-wall", "podcast-gold", "data-explainer", "wide-band"):
            self.assertIn(k, PRESETS)
            self.assertIn("about", PRESETS[k])


if __name__ == "__main__":
    unittest.main()
