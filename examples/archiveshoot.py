"""Stand-in material for testing the archive documentary styles and match
cuts. Everything is drawn here (numpy), so nothing real, personal or licensed
is ever used:

  photos/  six "old photographs": four portraits of made-up people (drawn
           shapes, never a real face), a street of houses, a steam train;
  clips/   short shots for match cuts: five eye close-ups (different irises,
           slightly different framings), four figures on the same horizon
           under different skies, and three unrelated shots (a road, rain on
           glass, a candle);
  song.wav a slow 80 bpm bed.

    python examples/archiveshoot.py /tmp/archive
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from travelshoot import music as _music  # noqa: E402

W, H, FPS, SECS = 960, 540, 30, 4.0
yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
Y, X = yy / H, xx / W


def soft(d, edge):
    return np.clip(0.5 - d / max(edge, 1e-3), 0, 1)


def ellipse(cx, cy, rx, ry, edge=2.0, gx=xx, gy=yy):
    d = (np.sqrt(((gx - cx) / rx) ** 2 + ((gy - cy) / ry) ** 2) - 1) * min(rx, ry)
    return soft(d, edge)


def grain(img, rng, amt=10):
    return img + rng.normal(0, amt, img.shape[:2])[..., None]


# --- photographs -------------------------------------------------------------

def portrait(seed: int, size=(900, 1100)) -> np.ndarray:
    """A made-up studio portrait in black and white: backdrop, shoulders and a
    coat, a head with soft light from one side, hair or a hat, a moustache or
    beard on some, a collar."""
    r = np.random.default_rng(seed)
    w, h = size
    gy, gx = np.mgrid[0:h, 0:w].astype(np.float32)
    back = 150 + 50 * (1 - np.hypot(gx / w - 0.4, gy / h - 0.35)) + r.normal(0, 3, (h, w))
    img = back[..., None].repeat(3, -1)
    cx = w * r.uniform(0.46, 0.54)
    head_y, hr = h * 0.4, w * r.uniform(0.15, 0.18)
    def put(mask, val):
        nonlocal img
        img = img * (1 - mask[..., None]) + np.asarray(val, np.float32) * mask[..., None]
    coat = ellipse(cx, h * 1.02, w * 0.48, h * 0.36, 3, gx, gy)
    put(coat, (40 + r.uniform(0, 30),) * 3)
    put(ellipse(cx, h * 0.68, w * 0.07, h * 0.06, 2, gx, gy) * (r.random() < 0.7), (225, 225, 220))  # collar
    neck = ellipse(cx, h * 0.6, hr * 0.5, h * 0.09, 2, gx, gy)
    put(neck, (150, 150, 150))
    face = ellipse(cx, head_y, hr, hr * 1.28, 2, gx, gy)
    light = 0.75 + 0.35 * np.clip((gx - (cx - hr)) / (2 * hr), 0, 1) * (1 if seed % 2 else -1) + (0.3 if seed % 2 == 0 else 0)
    skin = r.uniform(140, 200) * light
    img = img * (1 - face[..., None]) + (skin[..., None] * np.ones(3)) * face[..., None]
    for ex in (-0.38, 0.38):  # eyes and brows
        put(ellipse(cx + ex * hr, head_y - 0.05 * hr, hr * 0.13, hr * 0.07, 1.5, gx, gy), (40, 40, 40))
        put(ellipse(cx + ex * hr, head_y - 0.3 * hr, hr * 0.2, hr * 0.045, 1.5, gx, gy), (60, 60, 60))
    put(ellipse(cx, head_y + 0.25 * hr, hr * 0.08, hr * 0.2, 2, gx, gy) * 0.35, (90, 90, 90))  # nose shadow
    put(ellipse(cx, head_y + 0.62 * hr, hr * 0.3, hr * 0.06, 1.5, gx, gy) * 0.8, (85, 70, 70))  # mouth
    if r.random() < 0.5:  # moustache / beard
        put(ellipse(cx, head_y + 0.5 * hr, hr * 0.42, hr * 0.12, 3, gx, gy), (70, 70, 70))
        if r.random() < 0.6:
            put(ellipse(cx, head_y + 0.95 * hr, hr * 0.7, hr * 0.45, 6, gx, gy) * (gy > head_y + 0.55 * hr), (200, 200, 200) if seed % 3 == 0 else (60, 60, 60))
    if r.random() < 0.5:  # a hat
        put(ellipse(cx, head_y - 0.95 * hr, hr * 1.5, hr * 0.18, 2, gx, gy), (30, 30, 30))
        put(ellipse(cx, head_y - 1.25 * hr, hr * 0.85, hr * 0.45, 2, gx, gy) * (gy < head_y - 0.95 * hr), (35, 35, 35))
    else:  # hair
        put(ellipse(cx, head_y - 0.75 * hr, hr * 1.02, hr * 0.62, 3, gx, gy) * (gy < head_y - 0.45 * hr), (r.uniform(30, 200),) * 3)
    img = grain(img, r, 9)
    return np.clip(img.mean(-1, keepdims=True).repeat(3, -1), 0, 255)


def street(seed=7, size=(1400, 950)) -> np.ndarray:
    r = np.random.default_rng(seed)
    w, h = size
    gy, gx = np.mgrid[0:h, 0:w].astype(np.float32)
    img = (215 - 60 * gy / h)[..., None].repeat(3, -1)
    x = 0
    while x < w:
        bw = int(r.uniform(140, 260)); top = int(h * r.uniform(0.15, 0.4)); tone = r.uniform(70, 150)
        img[top:int(h * 0.8), x:x + bw] = tone
        for wy in range(top + 30, int(h * 0.75), 70):
            for wx in range(x + 20, x + bw - 30, 55):
                img[wy:wy + 38, wx:wx + 26] = tone * 0.45
        x += bw + int(r.uniform(4, 20))
    img[int(h * 0.8):] = (110 - 30 * (gy[int(h * 0.8):] / h))[..., None]
    for k in range(5):  # people on the pavement
        px = r.uniform(0.1, 0.9) * w
        img = img * (1 - ellipse(px, h * 0.8, 16, 60, 2, gx, gy)[..., None]) + 25 * ellipse(px, h * 0.8, 16, 60, 2, gx, gy)[..., None]
        img = img * (1 - ellipse(px, h * 0.8 - 72, 12, 14, 2, gx, gy)[..., None]) + 25 * ellipse(px, h * 0.8 - 72, 12, 14, 2, gx, gy)[..., None]
    return np.clip(grain(img, r, 10), 0, 255)


def train(seed=9, size=(1400, 900)) -> np.ndarray:
    r = np.random.default_rng(seed)
    w, h = size
    gy, gx = np.mgrid[0:h, 0:w].astype(np.float32)
    img = (225 - 40 * gy / h)[..., None].repeat(3, -1)
    smoke = sum(ellipse(w * (0.28 - 0.05 * k), h * (0.25 - 0.04 * k), w * (0.06 + 0.02 * k), h * (0.06 + 0.015 * k), 20, gx, gy) for k in range(5))
    img = img - 50 * np.clip(smoke, 0, 1)[..., None]
    img[int(h * 0.45):int(h * 0.75), int(w * 0.2):int(w * 0.85)] = 45  # boiler and cab
    img[int(h * 0.32):int(h * 0.45), int(w * 0.27):int(w * 0.31)] = 40  # chimney
    img[int(h * 0.35):int(h * 0.75), int(w * 0.68):int(w * 0.85)] = 38
    for wx in (0.3, 0.45, 0.6, 0.74):
        m = ellipse(w * wx, h * 0.77, h * 0.07, h * 0.07, 2, gx, gy)
        img = img * (1 - m[..., None]) + 20 * m[..., None]
    img[int(h * 0.84):int(h * 0.86)] = 30
    return np.clip(grain(img, r, 10), 0, 255)


# --- clips -------------------------------------------------------------------

def eye(seed: int):
    r = np.random.default_rng(seed)
    iris = np.array(r.choice([(70, 120, 170), (120, 75, 35), (90, 130, 90), (140, 100, 50), (80, 100, 140)]), np.float32)
    ox, oy, sc = r.uniform(-0.03, 0.05) * W, r.uniform(-0.04, 0.04) * H, r.uniform(0.85, 1.1)
    skin = np.array([200, 150, 130], np.float32) * r.uniform(0.6, 1.1)

    def f(t):
        cx, cy = W / 2 + ox + 6 * np.sin(t * 0.9), H / 2 + oy
        img = skin * (0.75 + 0.25 * (1 - Y[..., None]))
        white = ellipse(cx, cy, 300 * sc, 150 * sc, 6)
        img = img * (1 - white[..., None]) + np.array([235, 228, 222]) * white[..., None]
        d = np.hypot(xx - cx, yy - cy) / (110 * sc)
        ring = np.clip(1 - d, 0, 1)
        pattern = 0.75 + 0.25 * np.sin(np.arctan2(yy - cy, xx - cx) * 40 + d * 8)
        ir = (d < 1) * white
        img = img * (1 - ir[..., None]) + (iris * pattern[..., None] * (0.6 + 0.6 * ring[..., None])) * ir[..., None]
        pup = ellipse(cx, cy, (38 + 6 * np.sin(t * 2)) * sc, (38 + 6 * np.sin(t * 2)) * sc, 2) * white
        img = img * (1 - pup[..., None]) + 10 * pup[..., None]
        glint = ellipse(cx - 35 * sc, cy - 40 * sc, 14 * sc, 12 * sc, 3)
        img = img + 200 * glint[..., None]
        lid = np.clip(((yy - cy) / (150 * sc)) ** 2 + ((xx - cx) / (330 * sc)) ** 2 - 1, 0, 1)
        return img * (1 - 0.5 * lid[..., None])
    return f


def figure(seed: int):
    r = np.random.default_rng(seed)
    top, bottom = [np.array(c, np.float32) for c in r.choice(
        [[(40, 50, 110), (250, 150, 80)], [(20, 30, 60), (200, 90, 110)], [(90, 120, 170), (250, 200, 150)], [(50, 30, 70), (255, 120, 60)]])]
    fx = r.uniform(0.42, 0.58) * W
    lean = r.uniform(-0.4, 0.4)

    def f(t):
        img = top * (1 - Y[..., None]) + bottom * Y[..., None]
        img = img + 18 * np.sin(X * 20 + Y * 6 + t * 0.4 + seed)[..., None] * (Y[..., None] < 0.6)
        hill = Y > 0.72 + 0.02 * np.sin(X * 5 + seed)
        img[hill] = 12
        bx = fx + 8 * t
        body = ellipse(bx + lean * 40, H * 0.6, 26, 72, 2) + ellipse(bx + lean * 70, H * 0.44, 18, 20, 2)
        arm = (np.abs((yy - H * 0.52) - (xx - bx) * (0.8 * lean - 0.5)) < 6) * (np.abs(xx - bx - 60) < 70)
        m = np.clip(body + arm, 0, 1)
        return img * (1 - m[..., None]) + 12 * m[..., None]
    return f


def road(t):
    img = np.where(Y[..., None] < 0.5, np.array([150, 170, 190]) * (1 - Y[..., None]), np.array([60, 60, 60]))
    lane = (np.abs(X - 0.5) < 0.01 * (Y - 0.5) * 4) & (np.sin((1 / np.maximum(Y - 0.5, 0.01)) * 2 + t * 8) > 0) & (Y > 0.5)
    img[lane] = 230
    return img


def rain(t):
    r = np.random.default_rng(int(t * FPS))
    img = np.array([40, 60, 80], np.float32) + 30 * np.sin(X * 3 + t)[..., None]
    drops = r.random((H, W)) > 0.9985
    return img + 160 * drops[..., None]


def candle(t):
    img = np.full((H, W, 3), 12, np.float32)
    flick = 1 + 0.08 * np.sin(t * 13) + 0.05 * np.sin(t * 7.3)
    glow = np.exp(-((xx - W * 0.3) ** 2 + (yy - H * 0.45) ** 2) / (2 * (120 * flick) ** 2))
    img += glow[..., None] * np.array([255, 170, 80])
    img += 255 * ellipse(W * 0.3, H * 0.45, 10, 26 * flick, 3)[..., None]
    return img


def render(fn, out: Path) -> None:
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
                          "-i", "-", "-vf", "scale=1920:1080:flags=bicubic,noise=alls=3:allf=t", "-c:v", "libx264",
                          "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE)
    for k in range(int(SECS * FPS)):
        p.stdin.write(np.clip(fn(k / FPS), 0, 255).astype(np.uint8).tobytes())
    p.stdin.close()
    p.wait()


def main(out: Path) -> None:
    (out / "photos").mkdir(parents=True, exist_ok=True)
    (out / "clips").mkdir(parents=True, exist_ok=True)
    for k in range(4):
        Image.fromarray(portrait(k + 1).astype(np.uint8)).save(out / "photos" / f"portrait{k + 1}.jpg", quality=92)
    Image.fromarray(street().astype(np.uint8)).save(out / "photos" / "street.jpg", quality=92)
    Image.fromarray(train().astype(np.uint8)).save(out / "photos" / "train.jpg", quality=92)
    shots = {f"eye{k + 1}": eye(k + 11) for k in range(5)}
    shots.update({f"horizon{k + 1}": figure(k + 21) for k in range(4)})
    shots.update({"road": road, "rain": rain, "candle": candle})
    for name, fn in shots.items():
        render(fn, out / "clips" / f"{name}.mp4")
    _music(out, 36.0)
    print(f"wrote 6 photos, {len(shots)} clips and song.wav to {out}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
