"""Listening: phrases, music dips that never move on a word, and cuts that never split joined words."""

import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

from alvenus import listen

SR = listen.SR


def speech(parts, total, sr=SR):
    """A stand-in voice: a buzzing tone where each (start, end) is spoken, quiet elsewhere."""
    y = np.random.default_rng(1).normal(0, 0.0005, int(total * sr)).astype(np.float32)
    for a, b in parts:
        t = np.arange(int((b - a) * sr)) / sr
        y[int(a * sr): int(a * sr) + len(t)] += (0.3 * np.sin(2 * np.pi * 180 * t) * (1 + 0.3 * np.sin(2 * np.pi * 4 * t))).astype(np.float32)
    return y


def write(path, y, sr=SR):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(y, -1, 1) * 32767).astype("<i2").tobytes())


class ListenTests(unittest.TestCase):
    def test_words_close_together_are_one_phrase(self):
        y = speech([(0.5, 1.2), (1.3, 2.0), (4.0, 5.0)], 6.0)
        ph = listen.phrases_of(listen.loudness(y))
        self.assertEqual(len(ph), 2)
        self.assertAlmostEqual(ph[0][0], 0.5, delta=0.05)
        self.assertAlmostEqual(ph[0][1], 2.0, delta=0.05)

    def test_music_never_moves_on_a_word(self):
        phrases = [(0.0, 2.0), (2.6, 4.0), (6.5, 8.0), (8.3, 9.0), (12.0, 13.0)]
        keys = listen.duck_keys(phrases, 15.0, 12.0)
        self.assertEqual(listen.moves_on_words(keys, phrases), [])
        self.assertEqual(keys[0], (0.0, -12.0))  # speech at the very start: music starts down
        self.assertAlmostEqual(listen.gain_at(keys, 2.3), -12.0)  # a short breath: stays down
        self.assertAlmostEqual(listen.gain_at(keys, 5.2), 0.0)  # a real gap: it comes back up
        self.assertAlmostEqual(listen.gain_at(keys, 14.5), 0.0)

    def test_room_for_effects_only_when_music_is_up(self):
        keys = listen.duck_keys([(2.0, 4.0)], 10.0, 12.0)
        roomy = listen.make_room(keys, [7.0, 3.0], 10.0, dip_db=3.0)
        self.assertAlmostEqual(listen.gain_at(roomy, 7.1), -3.0, places=1)
        self.assertAlmostEqual(listen.gain_at(roomy, 3.0), -12.0, places=1)

    def test_joined_words_are_never_cut(self):
        y = speech([(0.5, 3.0)], 4.0)  # one long run: no quiet anywhere inside
        db = listen.loudness(y)
        self.assertIsNone(listen.quiet_point(db, 1.7, 0.06))
        y2 = speech([(0.5, 1.5), (1.9, 3.0)], 4.0)
        q = listen.quiet_point(listen.loudness(y2), 1.65, 0.12)
        self.assertIsNotNone(q)
        self.assertTrue(1.5 <= q <= 1.9)

    def test_take_cut_inside_joined_speech_is_taken_back(self):
        from alvenus.cut import Clip, keep_joined_words
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "v.wav"
            write(p, speech([(0.5, 3.0), (4.0, 5.0)], 6.0))
            clips = keep_joined_words(p, [Clip(0, 0.4, 1.7, 0), Clip(0, 1.75, 3.6, 0), Clip(0, 3.8, 5.2, 0)])
            self.assertEqual(len(clips), 2)  # the cut at 1.7 split a word: joined back
            self.assertAlmostEqual(clips[0].end, 3.6, delta=0.1)

    def test_music_map_reads_tempo_sections_and_stops(self):
        sr = SR
        t = np.arange(int(24 * sr)) / sr
        y = np.zeros_like(t, dtype=np.float32)
        for b in np.arange(0.25, 24, 0.5):  # 120 BPM clicks
            i = int(b * sr)
            y[i: i + 800] += np.hanning(800).astype(np.float32) * (0.15 if b < 12 else 0.6)
        y += (np.sin(2 * np.pi * 110 * t) * np.where(t < 12, 0.02, 0.12)).astype(np.float32)
        y[int(16 * sr): int(16.6 * sr)] = 0  # it stops dead
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "m.wav"
            write(p, y)
            m = listen.music_map(p)
        self.assertAlmostEqual(m["tempo"], 120, delta=3)
        self.assertTrue(any("lifts" in s["feel"] for s in m["sections"]))
        self.assertTrue(any(abs(a - 16.0) < 0.15 for a, _ in m["stops"]))
        self.assertIn("BPM", listen.report(m))

    def test_sound_controls_in_studio_and_sfx_volume(self):
        from alvenus import sfx
        from alvenus.studio import schema
        sound = schema()["sound"]
        self.assertIn("music_duck", sound)
        self.assertIn("sfx_volume", sound)
        with tempfile.TemporaryDirectory() as d:
            peaks = []
            for g in (0.0, -6.0):
                p = Path(d) / f"fx{g}.wav"
                sfx.write_track(p, [(0.5, "pop")], 1.5, g)
                with wave.open(str(p)) as w:
                    peaks.append(np.abs(np.frombuffer(w.readframes(w.getnframes()), "<i2")).max())
        self.assertAlmostEqual(peaks[1] / peaks[0], 10 ** (-6 / 20), delta=0.02)


if __name__ == "__main__":
    unittest.main()
