"""Studio: media, word looks, render choices, saved versions and recent videos."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


def project(d: Path) -> Path:
    from alvenus import nodes as nd

    doc = nd.to_nodes({"scenes": [{"type": "title", "text": "Hello there", "seconds": 2},
                                  {"type": "text", "text": "A second line", "seconds": 3}]})
    f = d / "v.nodes.json"
    f.write_text(json.dumps(doc), encoding="utf-8")
    return f


class WordLook(unittest.TestCase):
    ROW = "Dialogue: 5,0:00:01.00,0:00:02.00,Cap,,0,0,0,,{\\an5\\pos(100,200)\\fnInter ExtraBold\\b1\\1c&H00FFFFFF&}Hi {\\1c&H003FD2FF&}big"

    def test_font_colour_weight_and_place(self):
        from alvenus.style import restyle
        out = restyle([self.ROW], {"font": "typewriter", "weight": "regular", "colour": "#2B4A78", "x": 0.1, "y": -0.05},
                      1000, 1000, "#FFD23F")[0]
        self.assertIn("\\pos(200,150)", out)
        self.assertIn("\\fnDM Mono", out)
        self.assertNotIn("Inter", out)
        self.assertIn("\\b0", out)
        self.assertNotIn("\\b1", out)
        self.assertNotIn("\x08", out)  # (a bold tag once came out as a backspace)
        self.assertIn("\\1c&H00784A2B&", out)
        self.assertIn("\\1c&H003FD2FF&", out)  # the accent stays on the big word

    def test_drawn_shapes_move_but_keep_colour(self):
        from alvenus.style import restyle
        row = "Dialogue: 2,0:00:01.00,0:00:02.00,Card,,0,0,0,,{\\pos(0,0)\\1c&H00FFFFFF&\\clip(10,10,50,50)\\p1}m 0 0 l 9 9{\\p0}"
        out = restyle([row], {"colour": "#000000", "x": 0.1}, 100, 100)[0]
        self.assertIn("\\pos(10,0)", out)
        self.assertIn("\\clip(20,10,60,50)", out)
        self.assertIn("\\1c&H00FFFFFF&", out)

    def test_sans_weight_picks_the_family(self):
        from alvenus.style import restyle
        out = restyle([self.ROW], {"weight": "heavy"}, 100, 100)[0]
        self.assertIn("\\fnInter Display Black", out)

    def test_only_rows_in_the_scene(self):
        from alvenus import style
        later = self.ROW.replace("0:00:01.00,0:00:02.00", "0:00:05.00,0:00:06.00")
        style.WORD_LOOK = [(0.0, 3.0, {"font": "serif"})]
        try:
            a, b = style.restyle_timed([self.ROW, later], 100, 100)
        finally:
            style.WORD_LOOK = []
        self.assertIn("Libre Baskerville", a)
        self.assertNotIn("Libre Baskerville", b)

    def test_storyboard_checks_the_new_controls(self):
        from alvenus.paper import control_problem
        self.assertIsNone(control_problem("words_font", "hand"))
        self.assertIsNotNone(control_problem("words_font", "Comic"))
        self.assertIsNotNone(control_problem("words_colour", "blue"))
        self.assertIsNotNone(control_problem("words_x", 2))
        self.assertIsNone(control_problem("words_weight", "bold"))

    def test_studio_offers_the_controls(self):
        from alvenus.studio import schema
        w = schema()["words"]
        for k in ("font", "weight", "colour", "x", "y"):
            self.assertIn(k, w)
        self.assertTrue(w["colour"]["swatches"])


class NumberScene(unittest.TestCase):
    def test_a_number_value_does_not_break_studio(self):
        from alvenus import nodes as nd
        from alvenus.studio import Studio
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "v.nodes.json"
            f.write_text(json.dumps(nd.to_nodes({"scenes": [{"type": "stat", "value": 3200000, "label": "people", "seconds": 3}]})))
            self.assertEqual(Studio(f).state()["scenes"][0]["label"], "3200000")


class RenderChoices(unittest.TestCase):
    def test_jobs(self):
        from alvenus.studio import export_job
        self.assertIsNone(export_job(None))
        self.assertIsNone(export_job({"for": "made", "size": "1080", "quality": "standard"}))
        yt = export_job({"for": "youtube", "size": "4k", "quality": "best"})
        self.assertEqual((yt["scale"], yt["tag"]), (2, "youtube-4k-best"))
        self.assertIn("-maxrate", yt["rate"])
        ig = export_job({"for": "instagram", "size": "1080", "quality": "standard"})
        self.assertEqual((ig["scale"], ig["tag"]), (1, "instagram"))
        self.assertEqual(export_job({"quality": "small"})["tag"], "small")


class Versions(unittest.TestCase):
    def test_save_change_and_go_back(self):
        from alvenus.studio import Studio
        with tempfile.TemporaryDirectory() as d:
            st = Studio(project(Path(d)))
            first = st.save_version("Before")
            self.assertEqual(first["name"], "Before")
            from alvenus import nodes as nd
            title = lambda: (nd.find(st.doc, "settings").get("params") or {}).get("title")
            st.change(lambda doc: nd.set_param(doc, "settings.title", "Changed"))
            self.assertEqual(title(), "Changed")
            st.restore_version(first["id"])
            self.assertIsNone(title())
            st.undo()  # undo brings the change back
            self.assertEqual(title(), "Changed")
            self.assertEqual([v["name"] for v in st.versions()], ["Before"])
            with self.assertRaises(ValueError):
                st.restore_version("../../etc")


class Recent(unittest.TestCase):
    def test_remembered_videos(self):
        from alvenus import studio
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"VENUS_HOME": d}):
            f = project(Path(d))
            studio.remember(f, "My video")
            studio.remember(Path(d) / "gone.nodes.json")
            got = studio.recent()
            self.assertEqual([(r["name"], r["path"]) for r in got], [("My video", str(f))])


class Media(unittest.TestCase):
    def test_upload_stays_in_the_project(self):
        import io
        from alvenus.studio import Studio
        with tempfile.TemporaryDirectory() as d:
            st = Studio(project(Path(d)))
            rel = st.upload("../../moon photo.jpg", io.BytesIO(b"x" * 10), 10)
            self.assertTrue(rel.startswith("media/"))
            self.assertTrue((Path(d) / rel).exists())
            with self.assertRaises(ValueError):
                st._inside("../outside.jpg")


class LiftWords(unittest.TestCase):
    """Moving words on the picture: the words come off the picture as their own layers."""

    def test_words_lift_off_the_picture(self):
        from alvenus.studio import Studio
        with tempfile.TemporaryDirectory() as d:
            st = Studio(project(Path(d)))
            sid = [s["id"] for s in st.state()["scenes"]][1]
            got = st.lift(sid)
            self.assertTrue(got["layers"], got)
            lay = got["layers"][0]
            self.assertEqual(lay["part"], "all")
            x0, y0, x1, y1 = lay["ink"]
            self.assertTrue(0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1)
            png = st.cache / lay["url"].split("name=")[1]
            from PIL import Image
            im = Image.open(png)
            self.assertEqual(im.mode, "RGBA")
            self.assertEqual(im.getpixel((0, 0))[3], 0)  # see-through where there are no words
            self.assertEqual(st.lift(sid), got)  # kept, so the second ask is instant


if __name__ == "__main__":
    unittest.main()
