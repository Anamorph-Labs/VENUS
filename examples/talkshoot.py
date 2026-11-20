"""Stand-in talking-head footage for testing the talk, documentary and
travel looks: a person at a desk in a warm room, mouth moving with the
voice, off centre like a real framing. The voice is Flite (free, offline).

    python examples/talkshoot.py /tmp/talk            # 1920x1080, one take per line
    python examples/talkshoot.py /tmp/talk --flubs    # plus a flubbed take on two lines

Never a real person: the face is drawn shapes, so nothing personal is ever
committed with the tests.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, str(Path(__file__).parent))
from fakeshoot import SR, concat, dur, speak, tone  # noqa: E402

W, H, FPS = 1920, 1080, 30


def room(rng) -> Image.Image:
    """A warm room behind the speaker: soft wall gradient, a shelf, out-of-focus lamps."""
    y = np.linspace(0, 1, H)[:, None]
    x = np.linspace(0, 1, W)[None, :]
    wall = np.stack([62 + 40 * (1 - y) + 18 * x, 52 + 30 * (1 - y) + 10 * x, 46 + 22 * (1 - y) + 0 * x], -1)
    img = Image.fromarray(np.clip(wall, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(img)
    d.rectangle([1150, 380, 1900, 400], fill=(40, 30, 26))  # shelf
    for i in range(7):  # books
        bx = 1180 + i * 70 + int(rng.integers(0, 20))
        d.rectangle([bx, 250 + int(rng.integers(0, 40)), bx + 50, 380], fill=tuple(int(v) for v in rng.integers(60, 150, 3)))
    d.rectangle([0, 900, W, H], fill=(48, 36, 30))  # desk
    img = img.filter(ImageFilter.GaussianBlur(9))
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    g = ImageDraw.Draw(glow)
    for _ in range(9):  # bokeh lamps
        cx, cy, r = int(rng.integers(1100, 1900)), int(rng.integers(80, 700)), int(rng.integers(25, 60))
        g.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 196, 120))
    glow = glow.filter(ImageFilter.GaussianBlur(14))
    return Image.fromarray(np.clip(np.asarray(img, np.int32) + np.asarray(glow, np.int32) * 0.45, 0, 255).astype(np.uint8))


def person() -> tuple[Image.Image, tuple[int, int]]:
    """Head and shoulders as one RGBA layer; returns it and the mouth centre."""
    lay = Image.new("RGBA", (900, 1000), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    d.ellipse([90, 620, 810, 1300], fill=(34, 58, 92, 255))  # shoulders, navy shirt
    d.polygon([(380, 640), (450, 760), (520, 640)], fill=(230, 230, 225, 255))  # collar
    d.rectangle([395, 470, 505, 660], fill=(196, 140, 108, 255))  # neck
    d.ellipse([300, 170, 600, 560], fill=(214, 160, 126, 255))  # face
    d.ellipse([285, 130, 615, 360], fill=(38, 28, 24, 255))  # hair
    d.ellipse([292, 300, 330, 400], fill=(205, 150, 118, 255))  # ears
    d.ellipse([570, 300, 608, 400], fill=(205, 150, 118, 255))
    for ex in (390, 510):
        d.ellipse([ex - 18, 345, ex + 18, 368], fill=(250, 248, 244, 255))
        d.ellipse([ex - 8, 348, ex + 8, 365], fill=(40, 30, 26, 255))
        d.line([ex - 26, 325, ex + 22, 320], fill=(50, 36, 30, 255), width=7)  # brows
    d.line([450, 380, 440, 430, 458, 432], fill=(170, 112, 88, 255), width=5)  # nose
    lay = lay.filter(ImageFilter.GaussianBlur(1.6))
    return lay, (450, 475)


def main(out_dir: str, flubs: bool) -> None:
    here = Path(__file__).parent
    lines = [l.strip() for l in (here / "talk/script.txt").read_text().splitlines() if l.strip()]
    out = Path(out_dir)
    (out / "clips").mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp())
    gap = tone(tmp / "gap.wav", 1.0)
    wavs = [gap]
    for i, line in enumerate(lines):
        if flubs and i in (2, 6):
            wavs += [speak(" ".join(line.split()[:4]), tmp / f"f{i}.wav", tmp), gap]
        wavs += [speak(line, tmp / f"l{i}.wav", tmp), gap]
    voice = tmp / "voice.wav"
    concat(wavs, voice, tmp)
    T = dur(voice)
    audio = np.frombuffer(subprocess.run(["ffmpeg", "-v", "error", "-i", str(voice), "-f", "s16le", "-ac", "1", "-ar", str(SR), "-"],
                                         capture_output=True).stdout, np.int16).astype(np.float32) / 32768
    hop = SR // FPS
    rms = np.array([np.sqrt((audio[i * hop:(i + 1) * hop] ** 2).mean() + 1e-9) for i in range(int(T * FPS))])
    rms = np.clip(rms / (rms.max() + 1e-9) * 1.6, 0, 1)
    rng = np.random.default_rng(4)
    bg, (lay, (mx, my)) = room(rng), person()
    ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
                           "-i", "-", "-i", str(voice), "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
                           "-c:a", "aac", "-shortest", str(out / "clips" / "talk.mp4")], stdin=subprocess.PIPE)
    px, py = 280, 130  # the speaker sits left of centre, like a real framing
    for f in range(len(rms)):
        t = f / FPS
        fr = bg.copy()
        p = lay.copy()
        d = ImageDraw.Draw(p)
        o = rms[f] * 34
        d.ellipse([mx - 34, my - 6 - o * 0.2, mx + 34, my + 6 + o], fill=(92, 36, 38, 255))  # mouth
        if (t % 4.3) < 0.12:  # blink
            for ex in (390, 510):
                d.rectangle([ex - 20, 340, ex + 20, 372], fill=(214, 160, 126, 255))
        sway = int(10 * np.sin(t * 0.9) + 4 * np.sin(t * 2.3))
        fr.paste(p, (px + sway, py + int(3 * np.sin(t * 1.7))), p)
        ff.stdin.write(fr.tobytes())
    ff.stdin.close()
    ff.wait()
    (out / "script.txt").write_text((here / "talk/script.txt").read_text())
    print(f"wrote {out / 'clips' / 'talk.mp4'} ({T:.1f}s)")


if __name__ == "__main__":
    main(sys.argv[1], "--flubs" in sys.argv)
