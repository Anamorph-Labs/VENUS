import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from alvenus import motion
from alvenus.cut import join_pair
from alvenus.finish import muffle, open_spec
from alvenus.media import load_audio

W, H, FPS = 72, 128, 10


def _frames(path: Path, d: float):
    return list(motion.frames_of(str(path), W, H, FPS, 0.0, d))


class Effects(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        y = np.linspace(0, 1, H)[:, None, None]
        pic = np.clip(np.concatenate([np.full((H, W, 1), 90.0), 110 + 90 * (1 - y) * np.ones((1, W, 1)),
                                      np.full((H, W, 1), 160.0)], axis=2), 0, 255).astype(np.uint8)
        pic[int(H * 0.6):] //= 3
        self.still = self.dir / "still.png"
        Image.fromarray(pic).save(self.still)
        self.clip = self.dir / "clip.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=s={W}x{H}:r={FPS}:d=2",
                        "-pix_fmt", "yuv420p", str(self.clip)], check=True)

    def _plain(self, d=2.0) -> Path:
        out = self.dir / "scene.mp4"
        w = motion.Writer(out, W, H, FPS)
        for f in motion.frames_of(str(self.still), W, H, FPS, 0, d):
            w.put(f)
        w.close()
        return out

    def test_stamp_lands_at_its_time_and_stays(self):
        out = self._plain()
        before = _frames(out, 2.0)
        motion.overlay(out, {"stamp": {"text": "Kept", "at": 0.8}, "_accent": "#2B4A78"}, 2.0, W, H, FPS)
        after = _frames(out, 2.0)
        self.assertEqual(len(after), 20)
        self.assertLess(np.abs(after[3].astype(int) - before[3]).mean(), 2)  # nothing yet
        self.assertGreater(np.abs(after[15].astype(int) - before[15]).mean(), 2)  # the stamp is on

    def test_strike_and_notes_draw(self):
        out = self._plain()
        before = _frames(out, 2.0)
        motion.overlay(out, {"strike": {"old": "Almost", "new": "Ready", "at": 0.3},
                             "notes": [{"kind": "circle", "x": 0.5, "y": 0.3, "at": 0.2}]}, 2.0, W, H, FPS)
        after = _frames(out, 2.0)
        self.assertGreater(np.abs(after[-1].astype(int) - before[-1]).mean(), 2)

    def test_pictures_make_every_frame(self):
        for sc in ({"type": "image", "file": str(self.still), "alive": ["rain", "clouds", "depth", "ripples"]},
                   {"type": "image", "file": str(self.still), "scan_lift": {"to": str(self.clip)}},
                   {"type": "clip", "file": str(self.clip), "card": {"text": "A promise", "from_full": True}}):
            out = self.dir / "p.mp4"
            self.assertTrue(motion.has_picture(sc))
            motion.picture(sc, 2.0, W, H, FPS, out)
            self.assertEqual(len(_frames(out, 2.0)), 20, sc)

    def test_alive_moves(self):
        out = self.dir / "a.mp4"
        motion.picture({"type": "image", "file": str(self.still), "alive": ["depth"]}, 2.0, W, H, FPS, out)
        f = _frames(out, 2.0)
        self.assertGreater(np.abs(f[0].astype(int) - f[-1]).mean(), 0.5)

    def test_problems_are_plain(self):
        p = motion.problems({"type": "title", "alive": ["fog"], "notes": [{"kind": "squiggle"}], "strike": {"old": "a"}},
                            0, self.dir)
        text = " ".join(p)
        for bit in ("alive", "works on a clip or image", "kind is one of", "strike needs"):
            self.assertIn(bit, text)
        sc = {"type": "image", "file": "x", "scan_lift": {"to": "nope.mp4"}}
        self.assertIn("not found", " ".join(motion.problems(sc, 0, self.dir)))
        self.assertTrue(Path(sc["scan_lift"]["to"]).is_absolute())

    def test_horizon_is_found(self):
        img = np.asarray(Image.open(self.still).convert("RGB"))
        self.assertAlmostEqual(motion.horizon(img), 0.6, delta=0.08)


class LightTrailAndMuffle(unittest.TestCase):
    def test_light_trail_cut_renders(self):
        d = Path(tempfile.mkdtemp())
        out = d / "t.mp4"
        g = join_pair("0:v", "1:v", "v", "trail", 0.5, 0.5, f"{W}x{H}", FPS, 1, colour="#2B4A78")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=black:s={W}x{H}:r={FPS}:d=1",
                        "-f", "lavfi", "-i", f"color=gray:s={W}x{H}:r={FPS}:d=1", "-filter_complex", g, "-map", "[v]",
                        "-pix_fmt", "yuv420p", str(out)], check=True)
        f = list(motion.frames_of(str(out), W, H, FPS, 0, 1.5))
        self.assertGreater(f[7].max(), 200)  # the streak of light, mid-cut

    def test_muffled_then_open(self):
        d = Path(tempfile.mkdtemp())
        wav = d / "m.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anoisesrc=d=3:c=white:a=0.3",
                        "-ar", "48000", "-ac", "2", str(wav)], check=True)
        muffle(wav, *open_spec({"at": 1.5, "over": 0.3}))
        a = load_audio(wav, 16000)

        def hi(seg):
            f = np.abs(np.fft.rfft(seg))
            fr = np.fft.rfftfreq(len(seg), 1 / 16000)
            return f[fr > 2000].sum() / f.sum()
        self.assertLess(hi(a[4000:16000]), 0.2)
        self.assertGreater(hi(a[32000:44000]), 0.5)
        self.assertEqual(open_spec(4), (0.0, 4.0, 0.8))
        self.assertIsNone(open_spec(None))


if __name__ == "__main__":
    unittest.main()
