import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from alvenus import ideas, nodes as nd, story


class IdeasTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.env = mock.patch.dict(os.environ, {"VENUS_HOME": str(self.tmp / "home")})
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_idea_to_laid_out_video(self):
        e = ideas.create("a 30 second reel on why cold kills phone batteries", self.tmp / "videos")
        self.assertEqual((e["kind"], e["seconds"], e["aspect"]), ("explainer", 30.0, "9:16"))  # read from the idea itself
        p = Path(e["nodes"])
        sb = nd.to_storyboard(nd.read(p))
        self.assertEqual([s["beat"] for s in sb["scenes"]][0], "hook")
        self.assertEqual(sb["_idea"]["status"], "waiting")
        story.load(p, sb)  # unwritten beats don't stop Studio from opening it
        self.assertEqual([x["id"] for x in ideas.entries("waiting")], [e["id"]])
        self.assertIn("alvenus ideas start", ideas.instructions(e))

        with self.assertRaises(SystemExit):  # the brief is not filled yet
            ideas.start(e["id"])
        b = json.loads(Path(e["brief"]).read_text())
        b.update(audience="people in cold places", point="Warm it and the charge comes back.", mood="curious", seconds=20)
        Path(e["brief"]).write_text(json.dumps(b))
        ideas.start(e["id"])
        sb = nd.to_storyboard(nd.read(p))
        self.assertEqual(sb["_idea"]["status"], "writing")
        self.assertLess(sum(s["seconds"] for s in sb["scenes"]), 25)  # laid out again at the new length

    def test_names_and_guesses(self):
        self.assertEqual(ideas.slug("Why cold weather drains your phone, in 30 seconds"), "cold-weather-drains-your")
        self.assertEqual(ideas._guess("top 5 habits that save money as a reel")["kind"], "list")
        self.assertEqual(ideas._guess("a 2 minute youtube story of the bicycle")["seconds"], 120)
        with self.assertRaises(ValueError):
            ideas.create("hi", self.tmp)


if __name__ == "__main__":
    unittest.main()
