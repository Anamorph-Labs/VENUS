"""Stand-in travel footage for testing montage and the travel look: six
short drawn "shots" (mountains at sunset, the sea, a city at night, a desert
road, a lantern market, a forest with light rays), each with a slow camera
move, plus a 120 bpm music bed. Everything is drawn with numpy and FFmpeg,
so nothing real or licensed is ever used.

    python examples/travelshoot.py /tmp/travel
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np

W, H, FPS, SECS = 960, 540, 30, 5.0
yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
Y, X = yy / H, xx / W


def sky(top, bottom):
    t = Y[..., None]
    return np.array(top, np.float32) * (1 - t) + np.array(bottom, np.float32) * t


def ridge(x, seed, base, amp):
    r = np.random.default_rng(seed)
    f = sum(r.uniform(0.3, 1) * np.sin(x * k * 6.28 * r.uniform(0.6, 1.4) + r.uniform(0, 6)) / k for k in (1, 2, 4, 8))
    return base - amp * f


def blend(img, mask, col):
    m = np.clip(mask, 0, 1)[..., None]
    return img * (1 - m) + np.array(col, np.float32) * m


def disc(cx, cy, r, soft=1.0):
    d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    return np.clip((r - d) / max(soft, 1e-3), 0, 1)


def mountains(t):
    p = t / SECS
    img = sky((70, 60, 120), (255, 150, 90))
    img = blend(img, disc(W * 0.62, H * 0.52, 48, 3) * 0.95, (255, 220, 170))
    img = img + (disc(W * 0.62, H * 0.52, 220, 220) * 60)[..., None] * np.array([1, 0.6, 0.3])
    for k, (col, base, amp, speed) in enumerate([((120, 80, 110), 0.62, 0.08, 20), ((80, 50, 80), 0.72, 0.09, 45), ((40, 25, 45), 0.84, 0.07, 90)]):
        top = ridge((X + p * speed / W * 3), 10 + k, base, amp)
        img = blend(img, (Y - top) * H / 2, col)
    return img


def sea(t):
    img = sky((90, 150, 210), (250, 210, 170))
    hz = 0.52
    water = (Y > hz)
    w = np.array([20, 70, 110], np.float32) * (1 - (Y[..., None] - hz)) + np.array([10, 40, 70], np.float32) * (Y[..., None] - hz)
    img = np.where(water[..., None], w, img)
    glit = (np.sin(X * 140 + t * 3 + np.sin(Y * 90) * 2) * np.sin(Y * 260 - t * 4) > 0.85) * water * np.exp(-((X - 0.5 - t * 0.01) ** 2) * 18)
    img = img + glit[..., None] * np.array([255, 230, 180]) * 0.9
    img = blend(img, disc(W * (0.5 + t * 0.01), H * 0.42, 34, 2), (255, 236, 200))
    return img


def city(t):
    img = sky((10, 12, 30), (40, 30, 70))
    r = np.random.default_rng(5)
    shift = t * 12
    for b in range(26):
        x0 = (b * 42 - shift) % (W + 60) - 40
        bw, top = r.integers(28, 40), H * r.uniform(0.25, 0.6)
        m = ((xx >= x0) & (xx < x0 + bw) & (yy > top)).astype(np.float32)
        img = blend(img, m, (14, 14, 22))
        win = m * ((xx - x0) % 8 < 4) * ((yy - top) % 10 < 5) * (np.sin(xx * 3.1 + yy * 7.7 + b) > 0.2)
        img = img + win[..., None] * np.array([230, 190, 110]) * 0.85
    for k in range(14):
        cx = (k * 83 + t * 30) % W
        img = img + (disc(cx, H * 0.9, 26, 26) * 0.5)[..., None] * np.array([255, 120 + k * 8, 80])
    return img


def desert(t):
    img = sky((120, 170, 220), (250, 220, 180))
    for k, (col, base) in enumerate([((214, 160, 110), 0.6), ((196, 130, 80), 0.75)]):
        img = blend(img, (Y - ridge(X + t * 0.01 * (k + 1), 30 + k, base, 0.05)) * H / 2, col)
    road = (Y > 0.62) * (np.abs(X - 0.5) < (Y - 0.6) * 0.9)
    img = blend(img, road.astype(np.float32), (60, 56, 58))
    dash = road * (np.abs(X - 0.5) < (Y - 0.6) * 0.04) * (np.sin(1 / (Y - 0.59) * 3 + t * 9) > 0.3)
    return blend(img, dash.astype(np.float32), (240, 220, 160))


def market(t):
    img = sky((30, 15, 20), (60, 30, 25))
    r = np.random.default_rng(9)
    for k in range(34):
        cx, cy = (r.uniform(0, W) + t * r.uniform(-14, 14)) % W, r.uniform(0.05, 0.75) * H
        rad = r.uniform(14, 40)
        col = np.array([255, r.uniform(90, 180), r.uniform(30, 90)])
        img = img + (disc(cx, cy, rad, rad * 0.6) * 0.75)[..., None] * col
    return img


def forest(t):
    img = sky((200, 220, 170), (60, 90, 50))
    rays = np.clip(np.sin((X - Y * 0.6) * 30 + t * 0.3) * 0.5 + 0.3, 0, 1) * (1 - Y) * 0.45
    img = img + rays[..., None] * np.array([255, 240, 190])
    r = np.random.default_rng(3)
    for k in range(16):
        x0 = (r.uniform(0, W) - t * (8 + k * 3)) % (W + 80) - 40
        img = blend(img, ((np.abs(xx - x0) < r.uniform(6, 22))).astype(np.float32) * (0.6 + k / 40), (25 + k, 40 + k, 22))
    return img


SHOTS = {"mountains-sunset": mountains, "sea-morning": sea, "city-night": city, "desert-road": desert,
         "lantern-market": market, "forest-light": forest}


def render(name: str, fn, out: Path) -> None:
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
                          "-i", "-", "-vf", "scale=1920:1080:flags=bicubic,noise=alls=3:allf=t", "-c:v", "libx264",
                          "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", str(out / f"{name}.mp4")], stdin=subprocess.PIPE)
    for f in range(int(SECS * FPS)):
        p.stdin.write(np.clip(fn(f / FPS), 0, 255).astype(np.uint8).tobytes())
    p.stdin.close()
    p.wait()


def music(out: Path, secs: float = 32.0) -> None:
    b = 0.5  # 120 bpm
    expr = (f"0.55*sin(2*PI*52*t)*exp(-mod(t,{b})*14)"
            f"+0.10*(random(0)-0.5)*exp(-mod(t+{b / 2},{b})*40)"
            f"+0.07*(sin(2*PI*220*t)+sin(2*PI*277.2*t)+sin(2*PI*329.6*t))*(0.6+0.4*sin(2*PI*t/8))")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"aevalsrc='{expr}':s=44100:d={secs}",
                    "-af", "afade=t=in:d=0.5,afade=t=out:st={:.1f}:d=1.5".format(secs - 1.5), str(out / "song.wav")], check=True)


if __name__ == "__main__":
    out = Path(sys.argv[1])
    (out / "clips").mkdir(parents=True, exist_ok=True)
    for name, fn in SHOTS.items():
        render(name, fn, out / "clips")
    music(out)
    print(f"wrote 6 clips and song.wav to {out}")
