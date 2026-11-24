"""A small "Made with Venus" mark at the end of every finished video.

The mark is the Venus logo with "made with" beside it, in the bottom right
corner, for the last two seconds only (a third of a very short video). It
fades in and stays to the end; it never covers the story itself.

It is on unless the creator turns it off, in any of these ways (the first
that says something wins):
- for one video: --no-mark on the command, or "venus_mark": false in the
  storyboard (the Video settings node in Studio has a switch for it);
- for every video on this computer: alvenus mark off (alvenus mark on brings
  it back), kept in VENUS_HOME/mark.json.

The logo files are used as they are: the ink one on a light corner, the
ivory one on a dark corner, picked by looking at that corner of the video."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from .media import duration, run, video_size

HERE = Path(__file__).with_name("mark")
SECONDS = 2.0


def _home() -> Path:
    return Path(os.environ.get("VENUS_HOME") or Path.home() / ".venus") / "mark.json"


def home_default() -> bool:
    """On, unless the creator turned it off for this computer."""
    try:
        return bool(json.loads(_home().read_text(encoding="utf-8")).get("on", True))
    except (OSError, ValueError, AttributeError):
        return True


def set_home(on: bool) -> Path:
    p = _home()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"on": bool(on)}), encoding="utf-8")
    return p


def wanted(flag_off: bool = False, storyboard: dict | None = None) -> bool:
    """Whether this video gets the mark: the command, then the storyboard, then this computer."""
    if flag_off:
        return False
    if storyboard and storyboard.get("venus_mark") is not None:
        return bool(storyboard["venus_mark"])
    return home_default()


def _corner_is_dark(path: Path, at: float, w: int, h: int, box: tuple[int, int, int, int]) -> bool:
    """Look at the very spot the mark will sit on, a moment before the end."""
    pw, ph = 128, max(8, round(128 * h / max(1, w)))
    proc = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0.0, at):.3f}", "-i", str(path), "-frames:v", "1",
                           "-vf", f"scale={pw}:{ph},format=gray", "-f", "rawvideo", "-"], capture_output=True)
    if proc.returncode != 0 or len(proc.stdout) < pw * ph:
        return False
    img = np.frombuffer(proc.stdout[:pw * ph], dtype=np.uint8).reshape(ph, pw)
    x0, y0, x1, y1 = (int(box[0] * pw / w), int(box[1] * ph / h), max(int(box[2] * pw / w), 1), max(int(box[3] * ph / h), 1))
    spot = img[max(0, y0):max(y0 + 1, y1), max(0, x0):max(x0 + 1, x1)]
    return float(spot.mean()) < 128


def place(w: int, h: int) -> tuple[int, int, int]:
    """Logo height, side margin and bottom margin in pixels: small, the same share of the short side on
    every shape, and high enough to clear a torn paper edge or a caption band at the very bottom."""
    short = min(w, h)
    return max(16, round(short * 0.045)), max(12, round(short * 0.04)), max(12, round(h * 0.06))


def apply(path: str | Path) -> str:
    """Put the mark on a finished video, in place. Returns a line saying what happened."""
    path = Path(path)
    size = video_size(path)
    if not size:
        return "no picture, so no Venus mark"
    w, h = size
    total = duration(path)
    seconds = min(SECONDS, total / 3)
    start = max(0.0, total - seconds)
    tall, margin, bottom = place(w, h)
    wide = round(tall * 984 / 204)  # the mark's own shape
    dark = _corner_is_dark(path, total - seconds / 2, w, h, (w - margin - wide, h - bottom - tall, w - margin, h - bottom))
    logo = HERE / f"made-with-venus-{'dark' if dark else 'light'}.png"
    fade = min(0.4, seconds / 3)
    graph = (f"[1:v]scale=-2:{tall},format=rgba,colorchannelmixer=aa=0.92,"
             f"fade=t=in:st={start:.3f}:d={fade:.3f}:alpha=1[m];"
             f"[0:v][m]overlay=W-w-{margin}:H-h-{bottom}:enable='gte(t,{start:.3f})':shortest=1:format=auto[v]")
    with tempfile.TemporaryDirectory(prefix="venus-mark-", dir=path.parent) as d:
        tmp = Path(d) / path.name
        run(["ffmpeg", "-y", "-v", "error", "-i", str(path), "-loop", "1", "-framerate", "30", "-i", str(logo),
             "-filter_complex", graph, "-map", "[v]", "-map", "0:a?", "-t", f"{total:.3f}",
             "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-maxrate", "14M", "-bufsize", "28M", "-pix_fmt", "yuv420p",
             "-c:a", "copy", "-movflags", "+faststart", str(tmp)])
        tmp.replace(path)
    return (f"added the small \"Made with Venus\" mark for the last {seconds:.1f} s "
            "(turn it off with --no-mark, \"venus_mark\": false, or alvenus mark off)")
