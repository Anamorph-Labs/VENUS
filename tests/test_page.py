import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from alvenus import media, motion, page, story
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


    def test_words_land_on_the_voice_and_hold(self):
        self.assertEqual(page.land_times(3, 3.0, [0.4, 0.8, 1.2]), [0.4, 0.8, 1.2])
        fast = page.land_times(4, 3.0)
        self.assertLess(fast[-1], 0.5)  # no voice: every word down within half a second
        late = page.land_times(3, 2.0, [0.5, 1.2, 1.9])
        self.assertLessEqual(late[-1] + page.LAND + page.HOLD, 2.0 + 1e-6)  # squeezed so the last word can be read

    def test_pages_meet_without_a_dissolve(self):
        sc = [{"type": "title", "file": str(self.pic), "text": "Made from *one line.*"},
              {"type": "image", "file": str(self.pic), "page": {"text": "One"}},
              {"type": "image", "file": str(self.pic), "page": {"text": "Two"}},
              {"type": "text", "text": "x", "page": {}, "transition": "whip"}]
        notes = page.plan(sc, {"transition": "crossfade"})
        self.assertTrue(sc[0]["page"]["full"] and notes)  # the title takes the page's serif
        self.assertEqual([s.get("transition") for s in sc], [None, "cut", "cut", "whip"])
        self.assertTrue(sc[0]["_exit"] and sc[1]["_from_full"] and sc[1]["_keep_card"] and sc[2]["_card_stays"])
        for s in sc[:3]:
            s["_len"] = 1.0
            motion.picture(s, 1.0, W, H, FPS, self.dir / "p.mp4")
        f = _frames(self.dir / "p.mp4", 1.0)
        self.assertEqual(len(f), 10)

    def test_a_stray_frame_before_a_cut_is_skipped(self):
        clip = self.dir / "two.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=black:s={W}x{H}:r=30:d=1",
                        "-f", "lavfi", "-i", f"color=white:s={W}x{H}:r=30:d=1", "-filter_complex", "[0:v][1:v]concat=n=2:v=1[v]",
                        "-map", "[v]", "-pix_fmt", "yuv420p", str(clip)], check=True)
        self.assertAlmostEqual(media.first_cut(clip, 0.9), 0.1, delta=0.04)
        self.assertIsNone(media.first_cut(clip, 0.3))

    def test_stills_catch_a_page_before_its_words_leave(self):
        self.assertAlmostEqual(settled({"page": {}, "_exit": True, "notes": [{"at": 3.0}]}, 0.0, 4.0), 3.55)


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


class PageStyle(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.pic = self.dir / "p.png"
        rng = np.random.default_rng(1)
        Image.fromarray(rng.integers(0, 255, (90, 160, 3), dtype=np.uint8)).save(self.pic)

    def _draw(self, sc, d=1.6):
        out = self.dir / "s.mp4"
        motion.picture(sc, d, W, H, FPS, out)
        return _frames(out, d)

    def test_screen_or_photo_is_measured(self):
        flat = np.full((90, 160, 3), 240, np.uint8)
        flat[10:20, 10:60] = 20
        self.assertTrue(page.screenish(flat))
        self.assertFalse(page.screenish(np.asarray(Image.open(self.pic))))
        t = page.tone(np.asarray(Image.open(self.pic)))
        self.assertGreater(t[..., 0].mean(), t[..., 2].mean())  # sepia is warm

    def test_line_breaks_and_stress_carry_over(self):
        from PIL import ImageDraw
        d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
        up, it = page._faces({}, 20)
        lines = page._lines(d, "Paste *one\nline.* Press", up, it, 2000)
        self.assertEqual([[w for w, _, _ in ln] for ln in lines], [["Paste", "one"], ["line.", "Press"]])
        self.assertTrue(lines[1][0][1])  # "line." is still stressed
        self.assertFalse(lines[1][1][1])

    def test_cards_join_and_need_no_text(self):
        sc = {"type": "text", "page": {"cards": ["A computer", "Your AI"], "label": "What you need", "note": "the one you use"}}
        self.assertEqual(page.problems(sc, 0), [])
        f = self._draw(sc)
        self.assertGreater(f[-1].mean(), 200)
        self.assertGreater(np.abs(f[-1].astype(int) - f[0]).mean(), 0.5)  # the cards arrive
        self.assertIn("1 to 3", " ".join(page.problems({"type": "text", "page": {"cards": []}}, 0)))

    def test_pill_doodle_big_and_also_draw(self):
        other = self.dir / "o.png"
        Image.new("RGB", (160, 90), (30, 30, 40)).save(other)
        sc = {"type": "image", "file": str(self.pic), "page": {
            "text": "Run it *twice.*", "note": "Go make tea.", "doodle": "cup", "pill": "Free models",
            "big": "x2", "also": {"file": str(other), "note": "or ask"}}}
        plain = self._draw({"type": "image", "file": str(self.pic), "page": {"text": "Run it *twice.*"}})
        f = self._draw(sc)
        self.assertGreater(np.abs(f[-1].astype(int) - plain[-1]).mean(), 1)  # the extras are on the page
