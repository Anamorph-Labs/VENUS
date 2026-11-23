import json
import unittest
from pathlib import Path

from alvenus import storycheck


class CiStoryboardTest(unittest.TestCase):
    def test_the_test_machine_storyboard_passes_the_story_check(self):
        # GitHub's test render approves this storyboard; a stricter story check must not block it
        sb = json.loads((Path(__file__).parent.parent / "tools" / "ci-storyboard.json").read_text())
        self.assertEqual([x.line() for x in storycheck.weak(storycheck.check(sb))], [])


if __name__ == "__main__":
    unittest.main()
