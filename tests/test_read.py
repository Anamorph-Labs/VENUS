"""Reading references shot by shot, and blending them. Run with: python -m unittest discover -s tests

All offline: the reference is drawn here, CLIP is not used."""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np

from alvenus import blend, read


def write_video(path: Path, frames: np.ndarray, fps: int = 24) -> None:
    h, w = frames.shape[1:3]
    p = subprocess.Popen(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
                          "-r", str(fps), "-i", "-", "-c:v", "libx264", "-crf", "12", "-pix_fmt", "yuv420p", str(path)],
                         stdin=subprocess.PIPE)
    p.stdin.write(frames.tobytes())
    p.stdin.close()
    p.wait()


def reference(fps: int = 24) -> tuple[np.ndarray, list[int]]:
    """A small creative edit: a figure on white, its negative, a white flash, a
    black beat, a held photo-like shot. Returns frames and where shots start."""
    w, h = 96, 160
    fig = np.full((h, w, 3), 245, np.uint8)
    fig[60:110, 40:56] = (120, 60, 30)
    fig[45:60, 43:53] = (150, 90, 60)
    rng = np.random.default_rng(1)
    busy = rng.integers(0, 255, (h // 8, w // 8, 3), dtype=np.uint8).repeat(8, 0).repeat(8, 1)
    shots = [(fig, 6), (255 - fig, 4), (np.full((h, w, 3), 255, np.uint8), 2), (np.zeros((h, w, 3), np.uint8), 3),
             (busy, 30)]
    out, starts = [], []
    for img, n in shots:
        starts.append(len(out))
        for i in range(n):
            f = img.copy()
            if img is busy:  # a slow drift, so it is one shot that moves, not many
                f = np.roll(img, i, axis=1)
            out.append(f)
    return np.stack(out), starts


class ReadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("ffmpeg"):
            raise unittest.SkipTest("needs ffmpeg")
        cls.dir = Path(tempfile.mkdtemp())
        frames, cls.starts = reference()
        cls.path = cls.dir / "ref.mp4"
        write_video(cls.path, frames)
        cls.r = read.read(cls.path, cls.dir, see=False, say=lambda *a: None)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_every_cut_found_to_the_frame(self):
        self.assertEqual([s["frames"] for s in self.r["shots"]], [6, 4, 2, 3, 30])

    def test_what_each_shot_is(self):
        kinds = [s["kinds"] for s in self.r["shots"]]
        self.assertIn("plain", kinds[0])
        self.assertIn("negative", kinds[1])
        self.assertIn("white", kinds[2])
        self.assertIn("black", kinds[3])
        self.assertFalse({"white", "black", "negative"} & set(kinds[4]))

    def test_a_small_figure_on_white_is_not_a_flash(self):
        self.assertNotIn("white", self.r["shots"][0]["kinds"])
        self.assertLess(self.r["shots"][0]["subject_height"], 0.5)

    def test_files_and_words(self):
        for f in ("ref.read.json", "ref.read.md", "ref.shots.jpg"):
            self.assertTrue((self.dir / f).exists(), f)
        self.assertIn("5 shots", self.r["in_one_line"])
        self.assertTrue(self.r["parts"])

    def test_parts_follow_the_pace(self):
        shots = [{"seconds": x, "n": i + 1} for i, x in enumerate([0.08] * 12 + [1.2] * 6)]
        self.assertEqual(read.sections(shots), [(0, 12), (12, 18)])


class BlendTests(unittest.TestCase):
    def reading(self, bpm=120.0):
        shots = [{"n": 1, "start": 0.0, "seconds": 0.25, "kinds": ["white"], "light": 255, "palette": [["#FFFFFF", 1.0]],
                  "motion": {"busy": 0}},
                 {"n": 2, "start": 0.25, "seconds": 0.25, "kinds": ["plain", "negative"], "background": "#000000",
                  "subject_height": 0.2, "light": 20, "palette": [["#000000", 0.9]], "motion": {"busy": 2}},
                 {"n": 3, "start": 0.5, "seconds": 1.0, "kinds": ["lines", "mono", "burst"], "light": 200,
                  "palette": [["#EEEEEE", 0.8]], "motion": {"busy": 5}}]
        return {"name": "r", "seconds": 1.5, "frame": {"fps": 24, "shape": "9:16"}, "shots": shots,
                "music": {"beat_seconds": 60 / bpm}}

    def test_rhythm_moves_to_the_new_tempo(self):
        rec = {"parts": [{"ref": "A"}], "on_beat": True}
        sl = blend.slots(rec, {"A": self.reading(120)}, music_beat=0.6)  # 100 bpm song
        self.assertAlmostEqual(sum(x["seconds"] for x in sl), 1.5 * 0.6 / 0.5, delta=0.04)

    def test_tempo_fold_keeps_the_feel(self):
        self.assertEqual(blend._tempo_fold(0.5, 1.0), 0.5)  # a 60 bpm song counts a 120 bpm reel in half beats
        self.assertEqual(blend._tempo_fold(0.5, 0.55), 1.0)

    def test_length_and_whole_frames(self):
        rec = {"parts": [{"ref": "A", "from": 0, "to": 1.5}], "length": 3.0, "on_beat": False}
        sl = blend.slots(rec, {"A": self.reading()}, music_beat=None)
        self.assertEqual(sum(x["frames"] for x in sl), 90)
        self.assertTrue(all(x["frames"] >= 1 for x in sl))

    def test_effects_for_each_kind(self):
        sl = blend.slots({"parts": [{"ref": "A"}], "on_beat": False}, {"A": self.reading()}, None)
        fx = [blend.effects_for(x) for x in sl[1:]]
        self.assertEqual(fx[0][0], ["solid"])  # the negative lives in the plain colour: subject inverted on black
        self.assertTrue(fx[0][1]["solid.invert"])
        self.assertEqual(fx[0][1]["solid.size"], 0.2)
        self.assertEqual(fx[1][0], ["sketch", "burst"])  # one look only, light last

    def test_take_rhythm_only_drops_effects(self):
        rec = {"parts": [{"ref": "A", "take": ["rhythm"]}], "on_beat": False}
        sl = blend.slots(rec, {"A": self.reading()}, None)
        self.assertTrue(all(not x["kinds"] for x in sl))

    def test_bad_recipe_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "r.json"
            p.write_text(json.dumps({"refs": {"A": "a.mp4"}, "parts": [{"ref": "B"}]}))
            with self.assertRaises(SystemExit):
                blend.load_recipe(p)


if __name__ == "__main__":
    unittest.main()
