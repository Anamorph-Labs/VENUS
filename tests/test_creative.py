"""Creative-edit effects and cut-outs. Run with: python -m unittest discover -s tests

All offline: pictures on a plain background are cut out without a model."""

import unittest

import numpy as np

from alvenus import cutout, fx
from alvenus.montage import Shot, plan


def plain_frames(n=8, w=96, h=160, bg=(250, 250, 250)):
    """A dark figure walking across a plain light background."""
    f = np.zeros((n, h, w, 3), np.uint8)
    f[:] = bg
    for i in range(n):
        x = 30 + i * 2
        f[i, 50:120, x:x + 20] = (90, 50, 30)
        f[i, 35:52, x + 4:x + 16] = (120, 80, 60)
    return f


class CutoutTests(unittest.TestCase):
    def test_plain_background_found_and_subject_kept(self):
        f = plain_frames(1)[0]
        self.assertTrue(cutout.is_plain(f))
        m = cutout.plain_mask(f)
        self.assertGreater(m[80, 40], 0.9)  # on the figure
        self.assertLess(m[5, 5], 0.05)  # the background
        self.assertEqual(cutout.choose(plain_frames()), "plain")

    def test_busy_picture_is_not_plain(self):
        rng = np.random.default_rng(0)
        f = rng.integers(0, 255, (120, 80, 3), dtype=np.uint8)
        self.assertFalse(cutout.is_plain(f))

    def test_bbox(self):
        m = np.zeros((50, 40), np.float32)
        m[10:20, 5:15] = 1
        self.assertEqual(cutout.bbox(m), (5, 10, 15, 20))
        self.assertIsNone(cutout.bbox(np.zeros((5, 5))))

    def test_unknown_kind_refused(self):
        with self.assertRaises(SystemExit):
            cutout.masks(plain_frames(1), "magic")


class EffectTests(unittest.TestCase):
    def test_every_effect_runs_and_keeps_the_shape(self):
        frames = plain_frames()
        for name in fx.EFFECTS:
            out = fx.apply(frames, 30.0, [name], {"cutout": "plain", "words": "HIGHS AND LOWS", "shape": "infinity"}, seed=1)
            self.assertEqual(out.shape, frames.shape, name)
            self.assertEqual(out.dtype, np.uint8, name)
            self.assertFalse(np.array_equal(out, frames), f"{name} changed nothing")

    def test_unknown_effect_refused(self):
        with self.assertRaises(SystemExit):
            fx.parse("glow,sparkle-magic")

    def test_solid_flips_the_background_every_two_frames(self):
        out = fx.apply(plain_frames(6), 30.0, ["solid"], {"cutout": "plain", "colours": "#FFFFFF,#000000"})
        corners = [int(o[2, 2].mean()) for o in out]
        self.assertEqual(corners, [255, 255, 0, 0, 255, 255])

    def test_silhouette_subject_is_dark(self):
        out = fx.apply(plain_frames(2), 30.0, ["silhouette"], {"cutout": "plain"})
        self.assertLess(out[0, 90, 40].mean(), 60)

    def test_settings_for_one_effect_only(self):
        s = fx.Shot(plain_frames(2), 30.0, {"colour": "#000000", "glow.colour": "#FF0000"})
        s.current = "glow"
        self.assertEqual(s.opt("colour", "#FFFFFF"), "#FF0000")
        s.current = "burst"
        self.assertEqual(s.opt("colour", "#FFFFFF"), "#000000")

    def test_endstrobe_ends_white_and_black(self):
        out = fx.apply(plain_frames(8), 30.0, ["endstrobe"], {"frames": 4})
        self.assertEqual([int(o.mean()) for o in out[-4:]], [255, 255, 0, 0])

    def test_dots_gather_into_a_shape(self):
        f = np.zeros((10, 120, 120, 3), np.uint8)
        f[:, 30:90, 30:90] = 200
        out = fx.apply(f, 30.0, ["dots"], {"shape": "circle", "across": 30})
        last = out[-1].mean(axis=2)
        self.assertLess(last[60, 60], 40)  # the circle is hollow in the middle
        self.assertGreater(last.max(), 150)


class CreativePlanTests(unittest.TestCase):
    def test_fast_cuts_land_on_half_beats(self):
        from alvenus.montage import ClipInfo

        clips = [ClipInfo(f"c{i}.png", 3.0, (1080, 1920), [0.0] * 12, [5.0] * 12, [120.0] * 12, [40.0] * 12) for i in range(4)]
        beats = [i * 0.5 for i in range(17)]
        shots = plan(clips, beats, [0.9] * 17, 0, 8.0, fast=True)
        self.assertTrue(all(abs(s.length / 0.25 - round(s.length / 0.25)) < 1e-6 for s in shots[:-1]))
        self.assertLessEqual(max(s.length for s in shots[:-1]), 0.5 + 1e-6)

    def test_in_order_keeps_the_story(self):
        from alvenus.montage import ClipInfo

        clips = [ClipInfo(f"c{i}.png", 3.0, (1080, 1920), [0.0] * 12, [5.0] * 12, [120.0] * 12, [40.0] * 12) for i in range(3)]
        shots = plan(clips, [i * 0.5 for i in range(13)], [0.9] * 13, 0, 6.0, fast=True, in_order=True)
        self.assertEqual([s.clip for s in shots[:6]], ["c0.png", "c1.png", "c2.png"] * 2)

    def test_shot_effects_survive_the_plan_file(self):
        import json
        import tempfile
        from pathlib import Path

        from alvenus.montage import load_plan, save_plan

        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.montage.json"
            save_plan(p, [Shot("a.mp4", 0.0, 0.5, fx=["glow"], fxo={"copies": 2})], {"music": "m.wav"})
            shots, _ = load_plan(p)
            self.assertEqual(shots[0].fx, ["glow"])
            self.assertEqual(shots[0].fxo, {"copies": 2})
            self.assertIn("fx", json.loads(p.read_text())["shots"][0])


if __name__ == "__main__":
    unittest.main()
