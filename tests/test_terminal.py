import json
import struct
import tempfile
import unittest
from pathlib import Path

from alvenus import motion, terminal
from alvenus.terminal import Screen, read, retime


def _mac(events, path: Path) -> None:
    b = struct.pack("<QQII", 0, 1700000000, 0, ord("s"))
    for t, d in events:
        s = 1700000000 + t
        b += struct.pack("<QQII", len(d), int(s), int(round((s % 1) * 1e6)), ord("i"))  # typed keys are skipped
        b += d
        b += struct.pack("<QQII", len(d), int(s), int(round((s % 1) * 1e6)), ord("o")) + d
    b += struct.pack("<QQII", 0, 1700000099, 0, ord("e"))
    path.write_bytes(b)


EVENTS = [(0.0, b"$ "), (0.5, b"l"), (0.6, b"s"), (0.9, b"\r\n"), (1.0, b"one  two\r\n$ "), (9.0, b"done\r\n")]


class Reading(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def test_macos_script_r(self):
        p = self.dir / "rec.typescript"
        _mac(EVENTS, p)
        (self.dir / "rec.termsize").write_text("33 117\n")
        ev, meta = read(p)
        self.assertEqual(meta["kind"], "script -r")
        self.assertEqual((meta["cols"], meta["rows"]), (117, 33))
        self.assertEqual(b"".join(b for _, b in ev), b"".join(b for _, b in EVENTS))
        self.assertAlmostEqual(ev[-1][0], 9.0, places=3)

    def test_asciinema_v2_and_v3(self):
        v2 = self.dir / "a.cast"
        v2.write_text(json.dumps({"version": 2, "width": 60, "height": 10, "title": "Install"}) + "\n" +
                      "\n".join(json.dumps([t, "o", b.decode()]) for t, b in EVENTS))
        ev, meta = read(v2)
        self.assertEqual((meta["kind"], meta["cols"], meta["rows"], meta["title"]), ("asciinema", 60, 10, "Install"))
        self.assertAlmostEqual(ev[-1][0], 9.0)
        v3 = self.dir / "b.cast"
        gaps = [EVENTS[0][0]] + [b[0] - a[0] for a, b in zip(EVENTS, EVENTS[1:])]
        v3.write_text(json.dumps({"version": 3, "term": {"cols": 50, "rows": 12}}) + "\n" +
                      "\n".join(json.dumps([g, "o", b.decode()]) for g, (_, b) in zip(gaps, EVENTS)))
        ev, meta = read(v3)
        self.assertEqual((meta["cols"], meta["rows"]), (50, 12))
        self.assertAlmostEqual(ev[-1][0], 9.0)

    def test_linux_timing(self):
        body = b"".join(b for _, b in EVENTS)
        (self.dir / "ts").write_bytes(b'Script started on 2026-01-01 [COMMAND="x"]\n' + body)
        lines, last = [], 0.0
        for t, b in EVENTS:
            lines.append(f"{t - last:.6f} {len(b)}")
            last = t
        (self.dir / "tm").write_text("\n".join(lines))
        ev, meta = read(self.dir / "ts", self.dir / "tm")
        self.assertEqual(b"".join(b for _, b in ev), body)
        self.assertAlmostEqual(ev[-1][0], 9.0)


class TheTerminal(unittest.TestCase):
    def test_lines_wrap_and_erase(self):
        s = Screen(10, 4)
        s.feed(b"abcdefghij")  # fills the row; the wrap waits for the next character
        self.assertEqual((s.y, s.text().splitlines()[0]), (0, "abcdefghij"))
        s.feed(b"k\r\n12345\x1b[3D\x1b[K")
        self.assertEqual(s.text().splitlines()[1:3], ["k", "12"])

    def test_progress_bar_redraws_in_place(self):
        s = Screen(20, 3)
        for p in (10, 50, 100):
            s.feed(f"\r{p:3d}% \x1b[32m{'#' * (p // 10)}\x1b[0m".encode())
        self.assertEqual(s.text().splitlines()[0], "100% ##########")
        self.assertEqual(s.grid[0][5].fg, 2)

    def test_scrolls_split_characters_and_alternate_screen(self):
        s = Screen(8, 2)
        s.feed(b"a\r\nb\r\nc")
        self.assertEqual(s.text(), "b\nc")
        s.feed("\r\n✓ é".encode()[:4])  # a character split between two pieces
        s.feed("\r\n✓ é".encode()[4:])
        self.assertEqual(s.text(), "c\n✓ é")
        s.feed(b"\x1b[?1049hfull\x1b[?1049l")
        self.assertEqual(s.text(), "c\n✓ é")
        s.feed(b"\x1b]0;My title\x07")
        self.assertEqual(s.title, "My title")

    def test_long_waits_are_cut_and_speed_applies(self):
        ev = retime(EVENTS, speed=2.0, max_wait=1.0)
        self.assertAlmostEqual(ev[-1][0], (1.0 + 1.0) / 2)  # the 8 s wait became 1 s
        self.assertAlmostEqual(retime(EVENTS, max_wait=0)[-1][0], 9.0)


class Private(unittest.TestCase):
    def test_home_name_computer_and_given_text_are_hidden(self):
        ev = [(0.0, b"asha@Ashas-Laptop ~ % ls /Users/as"), (1.0, b"ha/.cache\r\nAshas-Laptop token tk-99\r\n")]
        out = terminal.scrub(ev, terminal.private_pairs(ev, ["tk-99"]))
        text = b"".join(b for _, b in out)
        self.assertEqual(text, b"you@computer ~ % ls ~/.cache\r\ncomputer token ***\r\n")
        self.assertEqual([t for t, _ in out], [0.0, 1.0])
        self.assertNotIn(b"asha", text.lower())
        kept = terminal.scrub(ev, terminal.private_pairs(ev, keep_home=True))
        self.assertEqual(kept, ev)


class TheClip(unittest.TestCase):
    def test_renders_every_frame_and_shows_the_text(self):
        d = Path(tempfile.mkdtemp())
        p = d / "rec.cast"
        p.write_text(json.dumps({"version": 2, "width": 30, "height": 6}) + "\n" +
                     "\n".join(json.dumps([t, "o", b.decode()]) for t, b in EVENTS + [(9.2, "━━━ ▉ ⠋".encode())]))
        out = d / "t.mp4"
        r = terminal.render(p, out, size="320x180", fps=10, max_wait=0.5, hold=1.0, lead=0.0)
        self.assertIn("one  two", r["screen"])
        frames = list(motion.frames_of(str(out), 320, 180, 10, 0, r["seconds"]))
        self.assertEqual(len(frames), r["frames"])
        self.assertLess(r["seconds"], 4.0)
        self.assertGreater(abs(frames[-1].astype(int) - frames[0]).mean(), 0.3)  # the screen filled up
        for theme in ("paper", "colour"):
            terminal.render(p, d / f"{theme}.mp4", size="180x320", fps=5, theme=theme, hold=0.2, end=1.0)


if __name__ == "__main__":
    unittest.main()
