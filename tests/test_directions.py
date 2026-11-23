import unittest

from alvenus import directions as dr

SB = {"brief": {"kind": "explainer", "point": "Warm it and the charge comes back.", "seconds": 30,
                "facts": [{"fact": "about 20% near 0 C", "source": "data sheets"}]},
      "aspect": "9:16", "style": "hype", "accent": "#00FF00",
      "scenes": [
          {"type": "text", "text": "Your phone is cold, not broken.", "seconds": 2.6, "beat": "hook"},
          {"type": "title", "text": "Why does it die at 30%?", "seconds": 3.2, "beat": "question"},
          {"type": "image", "file": "icon:battery", "caption": "Cold slows the chemistry", "seconds": 5, "beat": "step"},
          {"type": "image", "file": "scene:weather", "caption": "Ions crawl instead of run", "seconds": 5, "beat": "step"},
          {"type": "text", "text": "But the charge isn't gone.", "seconds": 4, "beat": "turn"},
          {"type": "text", "text": "Warm it, and the charge comes back.", "seconds": 6, "beat": "payoff"}]}


class DirectionsTest(unittest.TestCase):
    def test_three_directions(self):
        a, b, c = dr.make(SB)
        self.assertEqual([a["tag"], b["tag"], c["tag"]], ["A", "B", "C"])
        self.assertEqual(a["style"], "hype")
        self.assertEqual(a["storyboard"]["accent"], "#00FF00")  # your look keeps your colour
        self.assertEqual(b["style"], "vox-paper")  # punchy and tall -> calm and designed
        self.assertNotIn("accent", b["storyboard"])
        self.assertEqual(len(c["storyboard"]["scenes"]), 5)  # the question beat went
        self.assertNotIn("question", [s["beat"] for s in c["storyboard"]["scenes"]])
        self.assertLess(c["seconds"], a["seconds"])
        self.assertEqual(c["storyboard"]["brief"]["seconds"], round(c["seconds"]))
        for s in c["storyboard"]["scenes"]:
            self.assertGreaterEqual(s["seconds"], 1.6)
        self.assertEqual(len(a["glance"]), 4)
        self.assertEqual(len(SB["scenes"]), 6)  # the original is untouched

    def test_calm_goes_punchy(self):
        _, b, _ = dr.make({**SB, "style": "editorial", "aspect": "16:9"})
        self.assertEqual(b["style"], "reels-punchy")

    def test_key_frames(self):
        self.assertEqual(dr.key_scenes(7), [0, 3, 6])
        self.assertEqual(dr.key_scenes(2), [0, 1])


if __name__ == "__main__":
    unittest.main()
