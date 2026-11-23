"""Studio's preview picture of a clip still shows a frame when the asked
time falls past the clip's end (a clip shorter than its scene)."""

import subprocess
import tempfile
import unittest
from pathlib import Path


class FrameAt(unittest.TestCase):
    def test_time_past_the_end_gives_the_last_frame(self):
        from alvenus.paper import _frame_at
        with tempfile.TemporaryDirectory() as d:
            v = Path(d) / "short.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=0x806040:s=160x90:d=1:r=10",
                            "-pix_fmt", "yuv420p", str(v)], check=True)
            self.assertEqual(_frame_at(str(v), 0.2).size, (160, 90))
            self.assertEqual(_frame_at(str(v), 30.0).size, (160, 90))


if __name__ == "__main__":
    unittest.main()
