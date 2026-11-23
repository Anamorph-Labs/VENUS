import os
import tempfile
import unittest
from pathlib import Path

from alvenus import storycheck as sc
from alvenus import taste


def sb(*texts, **brief):
    b = {"idea": "why you wake up at 3 am", "audience": "people who sleep badly", "kind": "explainer",
         "point": "Waking at night is normal; the worry keeps you up.", "facts": [{"fact": "a sleep cycle is 90 minutes", "source": "t"}]}
    b.update(brief)
    scenes = [{"type": "text", "text": t, "seconds": 3} for t in texts]
    scenes[0]["beat"], scenes[-1]["beat"] = "hook", "payoff"
    return {"brief": b, "scenes": scenes}


def codes(s, level=None):
    return [f.code for f in sc.check(s, learn=False) if level is None or f.level == level]


class CraftTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.old = os.environ.get("VENUS_HOME")
        os.environ["VENUS_HOME"] = self.home.name

    def tearDown(self):
        if self.old is None:
            os.environ.pop("VENUS_HOME", None)
        else:
            os.environ["VENUS_HOME"] = self.old
        self.home.cleanup()

    def good(self):
        return sb("You wake at 3 am, and it is normal", "Sleep comes in 90 minutes cycles", "Each cycle ends with a light wake",
                  "But the worry wakes you fully", "Waking is normal; the worry keeps you up.")

    def test_a_good_storyboard_stays_quiet(self):
        self.assertEqual(codes(self.good(), "weak"), [])
        self.assertEqual(sc.openings(self.good()), [])
        self.assertEqual(sc.question(self.good(), sc.check(self.good(), learn=False)), "")

    def test_every_finding_points_at_its_moment(self):
        f = [x for x in sc.check(sb("Hi everyone, welcome back", "b c d", "e f g", "h i j"), learn=False) if x.scene == 1]
        self.assertTrue(f and all(x.at == "0:00-0:03" for x in f))
        self.assertIn("at 0:00-0:03", f[0].line())

    def test_weak_opening_gets_up_to_three_better_ones_from_its_own_scenes(self):
        s = sb("Hi everyone, welcome back", "Sleep comes in 90 minutes cycles", "But the worry wakes you fully",
               "Each cycle ends with a light wake", "Waking is normal; the worry keeps you up.")
        ops = sc.openings(s)
        self.assertTrue(1 <= len(ops) <= 3)
        self.assertEqual(ops[0]["kind"], "number")
        self.assertTrue(all(o["why"] and o["scene"] > 1 for o in ops))
        q = sc.question(s, sc.check(s, learn=False))
        self.assertIn("Hi everyone", q)
        self.assertTrue(q.count("?") == 1)

    def test_a_promised_count_must_be_delivered(self):
        s = self.good()
        s["scenes"].insert(1, {"type": "text", "text": "Here are 3 reasons you wake", "seconds": 3})
        s["scenes"].insert(2, {"type": "list", "items": ["Cycles end", "Room checks"], "seconds": 3})
        self.assertIn("setup-unpaid", codes(s, "weak"))
        s["scenes"][2]["items"].append("Worry")
        self.assertNotIn("setup-unpaid", codes(s))

    def test_the_opening_question_must_be_answered(self):
        s = sb("Why do you wake at 3 am?", "Sleep comes in cycles", "Light changes everything", "Breathe slowly, then dream.")
        self.assertIn("hook-unanswered", codes(s, "weak"))
        self.assertNotIn("hook-unanswered", codes(self.good()))

    def test_cut_mid_thought_repeat_and_jargon(self):
        s = self.good()
        s["scenes"][1]["text"] = "Your brain checks the room at the end of"
        self.assertIn("mid-thought", codes(s, "weak"))
        s = self.good()
        s["scenes"][2]["text"] = "Sleep comes in cycles of 90 minutes"
        self.assertIn("repeat", codes(s))
        s = self.good()
        s["scenes"][2]["text"] = "Each REM cycle ends with a light wake"
        self.assertIn("unexplained", codes(s))
        s["scenes"][2]["text"] = "EACH CYCLE ENDS WITH A LIGHT WAKE"
        self.assertNotIn("unexplained", codes(s))

    def test_the_same_shot_held_too_long(self):
        s = self.good()
        for k in (1, 2, 3):
            s["scenes"][k] = {"type": "clip", "file": "a.mp4", "seconds": 4}
        self.assertIn("still", codes(s))

    def test_venus_learns_what_this_creator_sets_aside(self):
        s = sb("Hi everyone, welcome back", "Sleep comes in 90 minutes cycles", "But the worry wakes you fully",
               "Waking is normal; the worry keeps you up.")
        self.assertIn("hook-greeting", [f.code for f in sc.weak(sc.check(s))])
        for _ in range(2):
            taste.approved(Path("x.json"), s, sc.check(s))  # approved as it is, twice
        after = sc.check(s)
        self.assertNotIn("hook-greeting", [f.code for f in sc.weak(after)])
        self.assertIn("usually keep this", " ".join(f.what for f in after))
        self.assertIn("hook-greeting", taste.summary()["quiet"])
        self.assertTrue(Path(self.home.name, "taste.json").exists())

    def test_facts_never_go_quiet(self):
        s = self.good()
        s["scenes"][2]["text"] = "Most people wake 12 times a night"
        for _ in range(3):
            taste.mark("fact", False)
        self.assertIn("fact", [f.code for f in sc.weak(sc.check(s))])

    def test_a_note_that_disappears_was_taken(self):
        s = sb("Hi everyone, welcome back", "b c d", "e f g", "h i j")
        taste.seen(Path("y.json"), sc.check(s))
        s["scenes"][0]["text"] = "You wake at 3 am?"
        taste.seen(Path("y.json"), sc.check(s))
        self.assertGreaterEqual(taste.load()["notes"]["hook-greeting"]["kept"], 1)

    def test_openings_follow_what_the_creator_picks(self):
        s = sb("Hi everyone, welcome back", "Sleep comes in 90 minutes cycles", "But the worry wakes you fully",
               "Each cycle ends with a light wake", "Waking is normal; the worry keeps you up.")
        taste.pick("opening-turn")
        self.assertEqual(sc.openings(s)[0]["kind"], "turn")


if __name__ == "__main__":
    unittest.main()
