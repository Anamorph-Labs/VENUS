"""The brand kit comes first: kit colours pass, others are flagged, contrast is suggested."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from alvenus import brand, storycheck

KIT = {"colours": {"ivory": "#F4EFE6", "ink": "#151515", "deep blue": "#1F3A93"},
       "background": "ivory", "text": "ink", "accent": "deep blue"}


class BrandTests(unittest.TestCase):
    def test_kit_colours_and_blends_pass_others_do_not(self):
        kit = brand.load(dict(KIT))
        self.assertTrue(brand.in_kit("#1F3A93", kit))
        self.assertTrue(brand.in_kit("#848079", kit))  # half ivory, half ink: a soft edge
        self.assertFalse(brand.in_kit("#5A3A22", kit))  # brown
        self.assertFalse(brand.in_kit("#8EC5FF", kit))  # light blue
        self.assertEqual(brand.name_of("#5A3A22"), "brown")

    def test_storyboard_off_brand_colour_is_weak_until_excepted(self):
        sb = {"brand": dict(KIT), "accent": "#FFD23F", "scenes": [{"type": "text", "text": "One clear line", "seconds": 3}]}
        codes = [f.code for f in storycheck.check(sb, learn=False)]
        self.assertIn("off-brand", codes)
        sb["brand_exceptions"] = ["#FFD23F"]
        self.assertNotIn("off-brand", [f.code for f in storycheck.check(sb, learn=False)])
        sb["brand"] = False
        sb.pop("brand_exceptions")
        self.assertNotIn("off-brand", [f.code for f in storycheck.check(sb, learn=False)])

    def test_kit_fills_accent_and_suggests_on_poor_contrast(self):
        sb = {}
        brand.apply(sb, brand.load(dict(KIT)))
        self.assertEqual(sb["accent"], "#1F3A93")
        weak = dict(KIT, text="deep blue", colours=dict(KIT["colours"], **{"deep blue": "#C9C2B5"}))
        found = []
        brand.board_findings({"brand": weak, "scenes": []}, lambda *a: found.append(a[0]))
        self.assertIn("brand-contrast", found)

    def test_saved_kit_is_found(self):
        with tempfile.TemporaryDirectory() as d:
            old = os.environ.get("VENUS_HOME")
            os.environ["VENUS_HOME"] = d
            try:
                Path(d, "brand.json").write_text('{"colours": {"ink": "#151515"}}')
                self.assertEqual(brand.load()["colours"], {"ink": "#151515"})
            finally:
                os.environ.pop("VENUS_HOME") if old is None else os.environ.__setitem__("VENUS_HOME", old)

    def test_video_check_finds_off_kit_flat_colour(self):
        with tempfile.TemporaryDirectory() as d:
            v = Path(d) / "v.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0xF4EFE6:s=160x90:d=2", "-f", "lavfi",
                            "-i", "color=c=0x5A3A22:s=160x90:d=2", "-filter_complex", "[0][1]concat=n=2", str(v)], check=True)
            notes = brand.check_video(v, brand.load(dict(KIT)))
        self.assertEqual(len(notes), 1)
        self.assertIn("brown", notes[0])


if __name__ == "__main__":
    unittest.main()
