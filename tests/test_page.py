import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from alvenus import motion, page, story
from alvenus.cut import join_pair
from alvenus.finish import stop
from alvenus.media import load_audio
from alvenus.stills import settled
from alvenus.storycheck import words_of
from alvenus.style import restyle

W, H, FPS = 192, 108, 10


def _frames(p, d):
    return list(motion.frames_of(str(p), W, H, FPS, 0, d))


class Page(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.pic = self.dir / "p.png"
        Image.fromarray(np.tile(np.linspace(30, 220, 160, dtype=np.uint8)[None, :, None], (90, 1, 3))).save(self.pic)

    def test_page_draws_words_and_picture_on_ivory(self):
        out = self.dir / "a.mp4"
        sc = {"type": "image", "file": str(self.pic), "page": {"text": "Paste one line. Press *Enter.*", "label": "Mac", "note": "tea"}}
        self.assertTrue(motion.has_picture(sc))
        motion.picture(sc, 2.0, W, H, FPS, out)
        f = _frames(out, 2.0)
        self.assertEqual(len(f), 20)
        self.assertGreater(f[-1][5:15, 5:15].mean(), 200)  # the page is light
        self.assertLess(f[-1][:, : W // 2].min(), 90)  # ink words on the left
        self.assertGreater(np.abs(f[-1].astype(int) - f[0]).mean(), 1)  # things arrive

    def test_words_only_page_and_problems(self):
        out = self.dir / "b.mp4"
        motion.picture({"type": "text", "text": "One *sentence.*", "page": {}}, 1.0, W, H, FPS, out)
        self.assertEqual(len(_frames(out, 1.0)), 10)
        self.assertIn("page needs", " ".join(page.problems({"type": "text", "page": {}}, 0)))
        self.assertIn("drop works", " ".join(page.problems({"type": "title", "drop": True}, 0)))
        self.assertIn("Enter.", words_of({"type": "image", "page": {"text": "Press *Enter.*"}}))

    def test_drops_pile_up_with_cuts_between(self):
        scenes = [{"type": "image", "file": str(self.pic), "drop": True} for _ in range(3)] + [{"type": "text", "text": "x"}]
        page.piles(scenes)
        self.assertEqual([len(s.get("_pile") or []) for s in scenes], [0, 1, 2, 0])
        self.assertEqual([s.get("transition") for s in scenes[:3]], [None, "cut", "cut"])
        out = self.dir / "c.mp4"
        motion.picture(scenes[2], 1.0, W, H, FPS, out)
        f = _frames(out, 1.0)
        self.assertLess(f[0].mean(), f[0][:4, :4].mean() + 1)  # the earlier prints are already there at the start


class Options(unittest.TestCase):
    def test_crop_box(self):
        self.assertEqual(story.crop_box({"x": 0, "y": 0.35, "w": 1, "h": 0.3}), (0.0, 0.35, 1.0, 0.3))
        self.assertIsNone(story.crop_box({"x": 1.2}))
        self.assertIsNone(story.crop_box([0, 0, 1, 1]))

    def test_crop_applies_once_to_the_file(self):
        d = Path(tempfile.mkdtemp())
        f = d / "t.png"
        Image.new("RGB", (100, 200), (200, 0, 0)).save(f)
        sc = [{"type": "image", "file": str(f), "crop": {"x": 0, "y": 0.25, "w": 1, "h": 0.5}}]
        story.apply_crops(sc, d / "c")
        self.assertEqual(Image.open(sc[0]["file"]).size, (100, 100))
        self.assertEqual(sc[0]["_uncropped"], str(f))

    def test_plain_cut_between_blended_scenes(self):
        d = Path(tempfile.mkdtemp())
        out = d / "j.mp4"
        g = join_pair("0:v", "1:v", "v", "cut", 0.4, 1.0, f"{W}x{H}", FPS, 1)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=black:s={W}x{H}:r={FPS}:d=1.4",
                        "-f", "lavfi", "-i", f"color=white:s={W}x{H}:r={FPS}:d=1", "-filter_complex", g, "-map", "[v]",
                        "-pix_fmt", "yuv420p", str(out)], check=True)
        f = _frames(out, 2.0)
        self.assertLess(f[9].mean(), 30)
        self.assertGreater(f[10].mean(), 220)  # no blend: black, then white

    def test_cut_then_blend_joins(self):
        d = Path(tempfile.mkdtemp())
        for first in ("cut", "ink"):
            g = join_pair("0:v", "1:v", "v1", first, 0.4, 1.0, f"{W}x{H}", FPS, 1) + ";" + \
                join_pair("v1", "2:v", "v", "crossfade", 0.4, 1.6, f"{W}x{H}", FPS, 2)
            ins = sum([["-f", "lavfi", "-i", f"color={c}:s={W}x{H}:r={FPS}:d=2"] for c in ("black", "white", "red")], [])
            subprocess.run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", g, "-map", "[v]", "-pix_fmt", "yuv420p",
                            str(d / f"{first}.mp4")], check=True)  # a later crossfade accepts what the cut made

    def test_music_stops_dead(self):
        d = Path(tempfile.mkdtemp())
        wav = d / "m.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=f=330:d=3", "-ar", "48000", "-ac", "2", str(wav)], check=True)
        stop(wav, 1.5)
        a = load_audio(wav, 16000)
        self.assertGreater(np.abs(a[8000:20000]).mean(), 0.05)
        self.assertLess(np.abs(a[25000:]).max(), 1e-3)

    def test_font_stays_after_each_word(self):
        row = "Dialogue: 7,0:00:00.00,0:00:02.00,CardText,,0,0,0,,{\\an1}{\\fs54}Every{\\r} {\\fs54}story{\\r}"
        out = restyle([row], {"font": "hand"}, 1920, 1080)[0]
        self.assertEqual(out.count("\\fnNothing You Could Do"), 3)

    def test_stills_wait_for_everything_to_arrive(self):
        sc = {"stamp": {"at": 2.5}, "notes": [{"at": 0.5}]}
        self.assertAlmostEqual(settled(sc, 10.0, 14.0), 13.2)
        self.assertAlmostEqual(settled({}, 0.0, 1.0), 0.8)


if __name__ == "__main__":
    unittest.main()
