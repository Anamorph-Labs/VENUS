import json
import tempfile
import unittest
from pathlib import Path

from alvenus import pictures as P


class PicturesTest(unittest.TestCase):
    def test_icons_are_bundled_and_searchable(self):
        self.assertGreater(len(P.icons()), 5000)
        names = [n for n, _, _ in P.search("battery")]
        self.assertEqual(names[0], "battery")
        self.assertIn("snowflake", [n for n, _, _ in P.search("cold winter snow")][:5])

    def test_path_parser(self):
        # a square with relative moves and an arc that ends where it should
        (pts, closed), = P.path_points("M4 4h16v16h-16z")
        self.assertTrue(closed)
        self.assertEqual(pts[0], (4.0, 4.0))
        self.assertIn((20.0, 20.0), pts)
        (arc, _), = P.path_points("M3 12a9 9 0 1 0 18 0")
        self.assertAlmostEqual(arc[-1][0], 21.0, places=4)
        self.assertAlmostEqual(arc[-1][1], 12.0, places=4)
        self.assertGreater(max(y for _, y in arc), 20.5)  # it bulges down (sweep flag 0 from the left)

    def test_problems_in_plain_words(self):
        self.assertIsNone(P.problem("icon:device-mobile+snowflake"))
        self.assertIsNone(P.problem("scene:city"))
        self.assertIn("close ones", P.problem("icon:batery"))
        self.assertIn("choose one of", P.problem("scene:moon-base"))
        self.assertIn("at most five", P.problem("icon:a,b,c,d,e,f"))

    def test_every_layout_and_scene_draws(self):
        specs = ["icon:battery", "icon:device-mobile+snowflake", "icon:bulb>pencil>rocket", "icon:car/bike",
                 "icon:sun,cloud,cloud-rain"] + [f"scene:{k}" for k in P.SCENES]
        for paint in ("dark", "paper"):
            for s in specs:
                img = P.render(s, 160, 90, paint, "#FFD23F")
                self.assertEqual(img.size, (160, 90))
                lo, hi = img.convert("L").getextrema()
                self.assertGreater(hi - lo, 60, f"{s} on {paint} looks empty")

    def test_paint_follows_the_style(self):
        self.assertEqual(P.paint_for({"style": "vox-paper"})[0], "paper")
        self.assertEqual(P.paint_for({"style": "mono-editorial"})[0], "mono")
        self.assertEqual(P.paint_for({"style": "archive-doc"})[0], "archive")
        self.assertEqual(P.paint_for({"style": "explainer"}), ("dark", "#FFD23F"))
        self.assertEqual(P.paint_for({"style": "editorial"})[0], "ink")

    def test_storyboard_draws_named_pictures_once(self):
        from alvenus import story

        d = Path(tempfile.mkdtemp())
        sb = {"aspect": "1:1", "style": "vox-paper", "scenes": [
            {"type": "image", "file": "icon:battery", "seconds": 2},
            {"type": "split", "left": {"file": "icon:car"}, "right": {"file": "scene:city"}, "seconds": 2}]}
        (d / "sb.json").write_text(json.dumps(sb))
        a = story.load(d / "sb.json")
        f = Path(a["scenes"][0]["file"])
        self.assertTrue(f.exists() and f.suffix == ".png")
        self.assertEqual(a["scenes"][0]["_picture"], "icon:battery")
        self.assertTrue(Path(a["scenes"][1]["right"]["file"]).exists())
        stamp = f.stat().st_mtime_ns
        b = story.load(d / "sb.json")
        self.assertEqual(Path(b["scenes"][0]["file"]).stat().st_mtime_ns, stamp)  # drawn once, then kept
        (d / "bad.json").write_text(json.dumps({"scenes": [{"type": "image", "file": "icon:nope-nope", "seconds": 2}]}))
        with self.assertRaises(SystemExit) as e:
            story.load(d / "bad.json")
        self.assertIn("no icon called", str(e.exception))


if __name__ == "__main__":
    unittest.main()
