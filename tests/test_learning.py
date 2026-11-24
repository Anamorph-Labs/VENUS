"""Lessons from real edits: setup before payoff, the same faces throughout, and pace."""

import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np

from alvenus import cast, storycheck


def codes(sb):
    return [f.code for f in storycheck.check(sb, learn=False)]


class LearningTests(unittest.TestCase):
    def test_answer_without_a_question(self):
        sb = {"scenes": [{"type": "text", "text": "He had no answer.", "seconds": 3},
                         {"type": "text", "text": "Out there, time bent.", "seconds": 3},
                         {"type": "text", "text": "Seven years passed at home.", "seconds": 3}]}
        self.assertIn("answer-unasked", codes(sb))
        sb["scenes"].insert(0, {"type": "text", "text": "She asked only one thing: when?", "seconds": 3})
        self.assertNotIn("answer-unasked", codes(sb))

    def test_reveal_spent_early(self):
        point = "some promises are kept by the one who waits"
        sb = {"brief": {"point": point}, "scenes": [{"type": "text", "text": t, "seconds": 3} for t in [
            "A bag by the door.", "Some promises are kept by the one who waits.", "She asked when.", "He left anyway.",
            "Years went by.", "She kept the watch.", "Some promises are kept by the one who waits."]]}
        self.assertIn("payoff-early", codes(sb))

    def test_story_opening_on_what_happened_next(self):
        sb = {"brief": {"kind": "story"}, "scenes": [{"type": "text", "text": t, "seconds": 3} for t in
                                                     ["So he gave her a watch.", "Time bent.", "She waited."]]}
        self.assertIn("setup-missing", codes(sb))

    def test_people_untagged_asks_for_cast(self):
        sb = {"scenes": [{"type": "image", "file": f"{i}.jpg", "text": t, "seconds": 3} for i, t in
                         enumerate(["Her father packed a bag.", "He kissed his daughter goodbye.", "The road was empty."])]}
        self.assertIn("cast-untagged", codes(sb))
        for sc in sb["scenes"]:
            sc["cast"] = ["father"]
        self.assertNotIn("cast-untagged", codes(sb))

    def test_odd_picture_out(self):
        rng = np.random.default_rng(0)
        base = rng.normal(size=16)
        emb = np.stack([base + rng.normal(scale=0.15, size=16) for _ in range(3)] + [rng.normal(size=16)])
        emb /= np.linalg.norm(emb, axis=1, keepdims=True)
        self.assertEqual([k for k, _ in cast.odd_ones(emb)], [3])

    def test_cast_sheet_without_the_model(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            files = []
            for i, c in enumerate([(200, 30, 30), (190, 40, 30)]):
                p = Path(d) / f"{i}.png"
                Image.new("RGB", (64, 48), c).save(p)
                files.append(str(p))
            sb = {"scenes": [{"type": "image", "file": f, "cast": ["father"]} for f in files]}
            notes, data = cast.check(sb, Path(d) / "cast.jpg", measure=False)
            self.assertEqual([r["scene"] for r in data["father"]], [1, 2])
            self.assertTrue((Path(d) / "cast.jpg").exists())

    def test_lone_quick_shot_is_flagged_but_a_flash_is_not(self):
        from alvenus.selfcheck import review
        with tempfile.TemporaryDirectory() as d:
            for name, mid in (("blip", "blue"), ("flash", "white")):
                v = Path(d) / f"{name}.mp4"
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=red:s=160x90:d=2:r=25", "-f", "lavfi",
                                "-i", f"color=c={mid}:s=160x90:d=0.2:r=25", "-f", "lavfi", "-i", "color=c=green:s=160x90:d=2:r=25",
                                "-f", "lavfi", "-i", "anoisesrc=a=0.01:r=48000", "-filter_complex", "[0][1][2]concat=n=3[v]",
                                "-map", "[v]", "-map", "3", "-t", "4.2", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(v)], check=True)
                kinds = [getattr(f, "kind", "") for f in review(v)]
                self.assertEqual("pace" in kinds, name == "blip", name)


if __name__ == "__main__":
    unittest.main()
