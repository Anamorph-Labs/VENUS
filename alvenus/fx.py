"""Creative-edit effects: the tricks of fast, surreal music edits, done on the
frames of one shot.

Every effect takes the shot's frames and gives back new ones. Effects chain in
the order given ("solid,speedlines" puts the subject on a plain colour, then
sends it off with speed lines). Effects marked * need the subject cut out
(see cutout.py); the cut-out is found once per shot and shared.

Silhouettes and cut-outs
  silhouette* the subject as a solid black shape against a glowing rim of
              light (red by default), the background gone dark
  glow*       the subject filled with glowing colour, the rest black and white;
              with copies=N, smaller glowing copies pop in one by one, each
              arriving with a one-frame flicker of another colour
  solid*      the subject alone on a plain colour; the colour flips every two
              frames (white, black, orange by default) and the subject turns
              negative on black. size= sets its height (0.22 = small,
              centred, held in the same place shot after shot: line up seed,
              sprout, plant, or stone, wheel, tyre)
  speedlines* the subject shoots off to the side, leaving white speed lines
  pop*        black and white, with the subject turning to full colour halfway
  words*      words between the background and the subject, one at a time
              (words="HIGHS AND LOWS"); the middle word small, in red
Light
  strobe-light quick flashes of light every few frames (white, then colour)
  burst       a light burst as the shot starts: a long horizontal streak,
              a bloom and rays, fading over a third of a second
  starburst   a four-point star flash on the first frame
  lightning   blue-white lightning that draws on and flickers (ink=1: drawn
              as a black ink line on white)
  sparks      sparks flying out, like a firework
  burn        the shot burns to white by its end
  endstrobe   the last frames strobe white and black
Looks
  sketch / blueprint / chalk   the picture as a pencil drawing, a technical
              blueprint, or chalk on a dark board
  flick       the picture flickers between itself and its drawing every two
              frames (with=sketch|blueprint|chalk)
  negative    colours turned inside out
  xray        an x-ray: inside-out, cool blue, glowing
  poster      two-colour poster (purple to peach by default)
  pixel       big pixel blocks on the first and last frames
  repeat      the picture three times side by side
  strip       the picture squeezed into a thin strip across white
  smear       a sideways smear on the first frames, like a whip of the camera
Shapes
  dots        the picture becomes glowing dots that scatter and (with
              shape=infinity|heart|circle|any text) gather into a shape
  arrows      hand-drawn arrows pop in around the frame, one per beat
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

FONT_DIR = Path(__file__).parent / "fonts"

NEEDS_CUTOUT = {"silhouette", "glow", "solid", "speedlines", "pop", "words"}
EFFECTS = ("silhouette", "glow", "solid", "speedlines", "pop", "words",
           "strobe-light", "burst", "starburst", "lightning", "sparks", "burn", "endstrobe",
           "sketch", "blueprint", "chalk", "flick", "negative", "xray", "poster", "pixel", "repeat", "strip", "smear",
           "dots", "arrows")


def hexrgb(s: str) -> np.ndarray:
    s = str(s).lstrip("#")
    return np.array([int(s[i:i + 2], 16) for i in (0, 2, 4)], np.float32)


def blur(a: np.ndarray, r: float) -> np.ndarray:
    """Gaussian blur of a float image (H x W or H x W x 3, any range)."""
    from PIL import Image

    if r <= 0:
        return a
    if a.ndim == 3:
        return np.dstack([blur(a[..., c], r) for c in range(a.shape[2])])
    # Work small: a wide blur on a smaller copy looks the same and is far quicker.
    h, w = a.shape
    k = max(1, int(r // 4))
    x = a.astype(np.float32)
    if k > 1:
        x = np.asarray(Image.fromarray(x, "F").resize((max(1, w // k), max(1, h // k)), Image.BILINEAR), np.float32)
    rr = r / k
    box = max(1, int(round(math.sqrt(12 * rr * rr / 3 + 1))))  # three box passes make a gaussian
    for _ in range(3):
        x = _box_blur(_box_blur(x, box, 0), box, 1)
    if k > 1:
        x = np.asarray(Image.fromarray(x, "F").resize((w, h), Image.BILINEAR), np.float32)
    return x


def _box_blur(x: np.ndarray, n: int, axis: int) -> np.ndarray:
    if n <= 1:
        return x
    lo, hi = n // 2, n - 1 - n // 2
    pad = [(0, 0), (0, 0)]
    pad[axis] = (lo + 1, hi)
    c = np.cumsum(np.pad(x, pad, mode="edge"), axis=axis, dtype=np.float64)
    if axis == 0:
        return ((c[n:] - c[:-n]) / n).astype(np.float32)
    return ((c[:, n:] - c[:, :-n]) / n).astype(np.float32)


def grey(f: np.ndarray) -> np.ndarray:
    return f[..., 0] * 0.299 + f[..., 1] * 0.587 + f[..., 2] * 0.114


def screen(base: np.ndarray, light: np.ndarray) -> np.ndarray:
    """Add light the way film does: never past white. Both 0..255."""
    return 255 - (255 - base) * (255 - np.clip(light, 0, 255)) / 255


def u8(a: np.ndarray) -> np.ndarray:
    return np.clip(a, 0, 255).astype(np.uint8)


@dataclass
class Shot:
    """The frames of one shot while effects work on them."""
    frames: np.ndarray  # N x H x W x 3 uint8 (changes as effects run)
    fps: float
    opts: dict = field(default_factory=dict)
    seed: int = 0
    original: np.ndarray | None = None
    _mask: np.ndarray | None = None

    def __post_init__(self):
        if self.original is None:
            self.original = self.frames.copy()
        self.rng = np.random.default_rng(self.seed)

    @property
    def n(self) -> int:
        return len(self.frames)

    @property
    def size(self) -> tuple[int, int]:
        return self.frames.shape[2], self.frames.shape[1]

    def mask(self) -> np.ndarray:
        if self._mask is None:
            from .cutout import masks

            self._mask = masks(self.original, str(self.opts.get("cutout", "auto")))
        return self._mask

    current: str = ""  # the effect running now; "glow.colour" beats a plain "colour" for it

    def opt(self, k: str, default):
        v = self.opts.get(f"{self.current}.{k}", self.opts.get(k, default))
        if isinstance(default, bool):
            return str(v).lower() in ("1", "true", "yes", "on")
        if isinstance(default, (int, float)) and not isinstance(v, (int, float)):
            try:
                return type(default)(float(v))
            except ValueError:
                return default
        return v


# --- silhouettes and cut-outs -----------------------------------------------------

def silhouette(s: Shot) -> None:
    rim = hexrgb(s.opt("colour", "#E3101A"))
    w, h = s.size
    out = []
    for i, (f, m) in enumerate(zip(s.frames, s.mask())):
        box = _box(m)
        cx, cy = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2) if box else (w / 2, h / 2)
        rad = (max(box[2] - box[0], box[3] - box[1]) * 0.62) if box else min(w, h) * 0.35
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        d = np.sqrt((xx - cx - rad * 0.18) ** 2 + (yy - cy) ** 2)
        disc = np.clip((rad - d) / (rad * 0.08), 0, 1)[..., None]
        halo = np.exp(-np.maximum(d - rad, 0) / (rad * 0.25))[..., None] * 0.35
        bg = rim * (disc * 0.95 + halo)
        # The rim: a thin line of light just inside the outline, as if lit from behind.
        edge = np.clip(m * (1 - blur(m, max(2, h / 260))) * 2.2, 0, 1)[..., None]
        img = bg * (1 - m[..., None]) + np.array([4, 4, 6], np.float32) * m[..., None]
        img = screen(img, rim * edge * 1.6)
        out.append(u8(img))
    s.frames = np.stack(out)


def _box(m: np.ndarray):
    from .cutout import bbox

    return bbox(m)


def _paste(dst_m: np.ndarray, m: np.ndarray, scale: float, cx: float, bottom: float) -> np.ndarray:
    """Place a scaled copy of mask m with its centre at x=cx and its foot at y=bottom."""
    from PIL import Image

    h, w = m.shape
    box = _box(m)
    if not box:
        return dst_m
    x0, y0, x1, y1 = box
    crop = m[y0:y1, x0:x1]
    nw, nh = max(1, int((x1 - x0) * scale)), max(1, int((y1 - y0) * scale))
    sm = np.asarray(Image.fromarray((crop * 255).astype(np.uint8)).resize((nw, nh), Image.BILINEAR), np.float32) / 255
    px, py = int(cx - nw / 2), int(bottom - nh)
    ax0, ay0, ax1, ay1 = max(0, px), max(0, py), min(w, px + nw), min(h, py + nh)
    if ax1 <= ax0 or ay1 <= ay0:
        return dst_m
    out = dst_m.copy()
    out[ay0:ay1, ax0:ax1] = np.maximum(out[ay0:ay1, ax0:ax1], sm[ay0 - py:ay1 - py, ax0 - px:ax1 - px])
    return out


def glow(s: Shot) -> None:
    col = hexrgb(s.opt("colour", "#FFD54A"))
    flick = [hexrgb(c) for c in ("#9FB4FF", "#E8E2C8", "#1E3FD0")]
    copies = s.opt("copies", 3)
    w, h = s.size
    ms = s.mask()
    box = _box(ms[0])
    bottom = box[3] if box else h * 0.9
    tall = (box[3] - box[1]) if box else h * 0.5
    # Copies stand to the right of the subject, smaller the further away, like the reel's crowd.
    spots = []
    for j in range(copies):
        sc = float(np.clip(0.75 - 0.12 * j + s.rng.uniform(-0.05, 0.05), 0.3, 0.9))
        x = (box[2] if box else w * 0.4) + (j + 0.6) * (w - (box[2] if box else w * 0.4)) / (copies + 0.4)
        x = min(w - tall * sc * 0.25, x)
        spots.append((sc, x, bottom - tall * (1 - sc) * 0.35, int((j + 1) * s.n / (copies + 1.5))))
    out = []
    for i, (f, m) in enumerate(zip(s.frames, ms)):
        g = grey(f.astype(np.float32))
        bg = np.repeat((g * 0.55)[..., None], 3, axis=2)
        allm = m.copy()
        tint = None
        for k, (sc, x, foot, at) in enumerate(spots):
            if i >= at:
                allm = _paste(allm, m, sc, x, foot)
                if i == at:
                    tint = (flick[k % len(flick)], _paste(np.zeros_like(m), m, sc, x, foot))
        lum = (g / 255)[..., None]
        fill = col * (0.62 + 0.5 * lum)  # keep a little of the picture inside the glow
        img = bg * (1 - allm[..., None]) + fill * allm[..., None]
        if i < 2:  # the first frames arrive white-hot
            img = img * (1 - allm[..., None]) + 255 * allm[..., None]
        if tint is not None:  # a new copy arrives as a one-frame flicker of another colour
            c, tm = tint
            img = img * (1 - tm[..., None]) + (c * 0.85) * tm[..., None]
        halo = np.clip(blur(allm, max(3, h / 80)) - allm * 0.7, 0, 1)[..., None]  # glow spills outward, not over the figure
        img = screen(img, col * halo * 0.9)
        out.append(u8(img))
    s.frames = np.stack(out)


def solid(s: Shot) -> None:
    cols = [hexrgb(c) for c in str(s.opt("colours", "#FFFFFF,#000000,#F07A10")).split(",")]
    every = max(1, s.opt("every", 2))
    size = s.opt("size", 0.0)
    invert = s.opt("invert", True)
    w, h = s.size
    ms = s.mask()
    boxes = [b for b in (_box(m) for m in ms) if b]
    out, newm = [], []
    if size and boxes:
        x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
        x1, y1 = max(b[2] for b in boxes), max(b[3] for b in boxes)
        sc = size * h / max(1, y1 - y0)
        ox, oy = w / 2 - (x0 + x1) / 2 * sc, h / 2 - (y0 + y1) / 2 * sc
    else:
        sc, ox, oy = 1.0, 0.0, 0.0
    from PIL import Image

    for i, (f, m) in enumerate(zip(s.frames, ms)):
        if sc != 1.0:
            M = (1 / sc, 0, -ox / sc, 0, 1 / sc, -oy / sc)
            fi = np.asarray(Image.fromarray(f).transform((w, h), Image.AFFINE, M, Image.BILINEAR))
            mi = np.asarray(Image.fromarray((m * 255).astype(np.uint8)).transform((w, h), Image.AFFINE, M, Image.BILINEAR), np.float32) / 255
        else:
            fi, mi = f, m
        bg = cols[(i // every) % len(cols)]
        sub = fi.astype(np.float32)
        if invert and bg.mean() < 60:
            sub = 255 - sub
        img = bg * (1 - mi[..., None]) + sub * mi[..., None]
        out.append(u8(img))
        newm.append(mi)
    s.frames, s._mask = np.stack(out), np.stack(newm)


def speedlines(s: Shot) -> None:
    w, h = s.size
    ms = s.mask()
    start = int(s.n * s.opt("from", 0.55))
    out, newm = [], []
    from PIL import Image, ImageDraw

    for i, (f, m) in enumerate(zip(s.frames, ms)):
        if i < start:
            out.append(f)
            newm.append(m)
            continue
        u = (i - start + 1) / max(1, s.n - start)
        box = _box(m)
        if not box:
            out.append(f)
            newm.append(m)
            continue
        shift = int((u ** 1.6) * (w - box[0] + 20))
        bgc = np.median(np.concatenate([f[:4].reshape(-1, 3), f[-4:].reshape(-1, 3)]), axis=0)
        sub = np.roll(f, shift, axis=1)
        sm = np.roll(m, shift, axis=1)
        if shift:
            sm[:, :shift] = 0
        img = bgc * (1 - sm[..., None]) + sub * sm[..., None]
        im = Image.fromarray(u8(img))
        d = ImageDraw.Draw(im)
        line = (0, 0, 0) if bgc.mean() > 128 else (255, 255, 255)
        bx0, by0, bx1, by1 = box
        for k, yy in enumerate((0.35, 0.5, 0.62)):
            y = int(by0 + (by1 - by0) * yy)
            d.line([(0, y), (bx0 + shift + (bx1 - bx0) * 0.2, y)], fill=line, width=max(2, h // (120 + 40 * k)))
        out.append(np.asarray(im))
        newm.append(sm)
    s.frames, s._mask = np.stack(out), np.stack(newm)


def pop(s: Shot) -> None:
    turn = int(s.n * s.opt("at", 0.45))
    out = []
    for i, (f, m) in enumerate(zip(s.frames, s.mask())):
        ff = f.astype(np.float32)
        g = np.repeat(grey(ff)[..., None], 3, axis=2)
        if i < turn:
            sub = g
        else:
            sub = np.clip(g + (ff - g) * 1.35, 0, 255)  # a touch richer than life
        img = g * (1 - m[..., None]) + sub * m[..., None]
        if i == turn:
            img = screen(img, 255 * blur(m, s.size[1] / 60)[..., None] * 0.8)
        out.append(u8(img))
    s.frames = np.stack(out)


def _font(px: int, name: str = "InterDisplay-Black.otf"):
    from PIL import ImageFont

    return ImageFont.truetype(str(FONT_DIR / name), max(8, px))


def words(s: Shot) -> None:
    from PIL import Image, ImageDraw

    ws = str(s.opt("words", "HIGHS AND LOWS")).split()
    w, h = s.size
    big = int(min(w, h) * 0.16)
    accent = tuple(int(x) for x in hexrgb(s.opt("accent", "#E3101A")))
    span = max(1, int(s.n * 0.6))
    layout = []
    last = max(1, len(ws) - 1)
    for k, word in enumerate(ws):
        small = len(ws) >= 3 and k == len(ws) // 2 and len(word) <= 4
        size = int(big * (0.45 if small else 1))
        tw = _font(size).getlength(word)
        # A staircase: the first word on the left, the last on the right, each a line lower.
        x = int(w * 0.05 + (w * 0.9 - tw) * (k / last))
        y = int(h * 0.12 + k * big * (0.75 if len(ws) > 2 else 0.95))
        layout.append((word, size, x, y, small, int(k * span / len(ws))))
    out = []
    for i, (f, m) in enumerate(zip(s.frames, s.mask())):
        light = grey(f.astype(np.float32)).mean() > 128
        im = Image.fromarray(f)
        d = ImageDraw.Draw(im)
        for word, size, x, y, small, at in layout:
            if i >= at:
                d.text((x, y), word, font=_font(size), fill=accent if small else ((15, 15, 15) if light else (245, 245, 245)))
        txt = np.asarray(im, np.float32)
        img = txt * (1 - m[..., None]) + f.astype(np.float32) * m[..., None]  # the subject stays in front
        out.append(u8(img))
    s.frames = np.stack(out)


# --- light -------------------------------------------------------------------

def strobe_light(s: Shot) -> None:
    col = hexrgb(s.opt("colour", "#FFE9A8"))
    every = max(2, s.opt("every", 3))
    out = []
    for i, f in enumerate(s.frames):
        ff = f.astype(np.float32)
        k = i % every
        if k == 0:
            img = screen(ff, np.full_like(ff, 255) * 0.85)
        elif k == 1:
            img = screen(ff * 0.9, col * 0.55 + 0 * ff)
        else:
            img = ff * 0.92
        out.append(u8(img))
    s.frames = np.stack(out)


def _burst_layer(w: int, h: int, cx: float, cy: float, col: np.ndarray, rng) -> np.ndarray:
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    dx, dy = xx - cx, yy - cy
    r = np.sqrt(dx * dx + dy * dy) + 1e-3
    s = min(w, h)
    streak = np.exp(-(dy / (s * 0.012)) ** 2) * np.exp(-(dx / (w * 0.7)) ** 2)
    bloom = np.exp(-(r / (s * 0.2)) ** 2)
    ang = np.arctan2(dy, dx)
    rays = np.zeros_like(r)
    for k, a in enumerate(rng.uniform(0, 2 * math.pi, 7)):
        rays += np.cos(ang * (5 + k) + a) ** 40
    rays = rays / 7 * np.exp(-r / (s * 0.45))
    core = np.exp(-(r / (s * 0.04)) ** 2)
    lum = streak * 1.2 + bloom * 0.8 + rays * 0.9 + core * 1.5
    return lum[..., None] * col[None, None] + core[..., None] * 255 * 0.6


def burst(s: Shot) -> None:
    col = hexrgb(s.opt("colour", "#FFE14A"))
    w, h = s.size
    cy = h * s.opt("y", 0.5)
    layer = _burst_layer(w, h, w / 2, cy, col, s.rng)
    out = []
    for i, f in enumerate(s.frames):
        t = i / s.fps
        k = math.exp(-t / s.opt("seconds", 0.3))
        ff = f.astype(np.float32)
        img = screen(ff * (1 - 0.5 * k), layer * (1.4 * k))
        if i == 0:
            img = screen(img, np.full_like(img, 255) * 0.7)
        out.append(u8(img))
    s.frames = np.stack(out)


def starburst(s: Shot) -> None:
    w, h = s.size
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    dx, dy = np.abs(xx - w / 2), np.abs(yy - h / 2)
    sz = min(w, h)
    star = (np.exp(-dx / (sz * 0.006)) * np.exp(-dy / (sz * 0.35)) + np.exp(-dy / (sz * 0.006)) * np.exp(-dx / (sz * 0.35)))
    r = np.sqrt(dx * dx + dy * dy)
    star += np.exp(-(r / (sz * 0.06)) ** 2) * 1.5 + np.exp(-r / (sz * 0.25)) * 0.35
    fil = blur(s.rng.random((h, w)).astype(np.float32), 1.5) ** 6 * np.exp(-r / (sz * 0.35)) * 3  # fine filaments
    layer = np.clip(star + fil, 0, 1.5)[..., None] * 255
    frames = s.frames.astype(np.float32)
    frames[0] = screen(frames[0] * 0.15, layer)
    if s.n > 1:
        frames[1] = screen(frames[1] * 0.6, layer * 0.4)
    s.frames = u8(frames)


def _bolt(a, b, rng, rough: float, depth: int = 7) -> list[tuple[float, float]]:
    pts = [a, b]
    off = rough
    for _ in range(depth):
        new = [pts[0]]
        for p, q in zip(pts, pts[1:]):
            mx, my = (p[0] + q[0]) / 2, (p[1] + q[1]) / 2
            dx, dy = q[0] - p[0], q[1] - p[1]
            L = math.hypot(dx, dy) or 1
            n = rng.normal(0, off)
            new += [(mx - dy / L * n, my + dx / L * n), q]
        pts = new
        off /= 1.9
    return pts


def lightning(s: Shot) -> None:
    from PIL import Image, ImageDraw

    w, h = s.size
    ink = s.opt("ink", False)
    every = max(2, s.opt("every", 4))
    out, bolts = [], []
    for i, f in enumerate(s.frames):
        if i % every == 0:  # a fresh bolt now and then
            a = (s.rng.uniform(0.1, 0.9) * w, s.rng.uniform(-0.05, 0.25) * h)
            b = (s.rng.uniform(0.1, 0.9) * w, s.rng.uniform(0.6, 1.0) * h)
            main = _bolt(a, b, s.rng, h * 0.12)
            branches = []
            for _ in range(3):
                k = int(s.rng.integers(len(main) // 5, len(main) * 3 // 4))
                p = main[k]
                q = (p[0] + s.rng.normal(0, w * 0.18), p[1] + abs(s.rng.normal(h * 0.15, h * 0.08)))
                branches.append(_bolt(p, q, s.rng, h * 0.05, 5))
            bolts = [main] + branches
        age = i % every
        grow = min(1.0, (age + 1) / 2)  # draws on over two frames
        bright = [1.0, 1.0, 0.35, 0.8, 0.5][age % 5]
        im = Image.new("L", (w, h), 0)
        d = ImageDraw.Draw(im)
        for k, bolt in enumerate(bolts):
            n = max(2, int(len(bolt) * grow))
            d.line(bolt[:n], fill=255 if k == 0 else 170, width=max(2, h // (300 if k == 0 else 500)))
        core = np.asarray(im, np.float32) / 255 * bright
        ff = f.astype(np.float32)
        if ink:
            dark = np.clip(core + blur(core, 2) * 1.5, 0, 1)[..., None]
            img = ff * (1 - dark) + 10 * dark
        else:
            g1, g2 = blur(core, max(2, h / 160)), blur(core, max(6, h / 45))
            light = core[..., None] * 255 + g1[..., None] * np.array([140, 180, 255]) * 2.2 + g2[..., None] * np.array([60, 110, 255]) * 2.5
            img = screen(ff, light)
        out.append(u8(img))
    s.frames = np.stack(out)


def sparks(s: Shot) -> None:
    w, h = s.size
    n = s.opt("count", 220)
    cx, cy = w * s.opt("x", 0.5), h * s.opt("y", 0.45)
    ang = s.rng.uniform(0, 2 * math.pi, n)
    spd = s.rng.uniform(0.2, 1.0, n) * min(w, h) * 0.9
    hue = s.rng.choice([np.array([255, 170, 60]), np.array([255, 90, 40]), np.array([255, 230, 160]), np.array([255, 80, 200])], n)
    out = []
    for i, f in enumerate(s.frames):
        t = (i + 1) / s.fps
        layer = np.zeros((h, w, 3), np.float32)
        for tt, fade in ((t, 1.0), (t - 0.02, 0.7), (t - 0.04, 0.5), (t - 0.06, 0.35), (t - 0.08, 0.2)):  # short trails
            if tt <= 0:
                continue
            x = cx + np.cos(ang) * spd * tt * np.exp(-tt * 1.2)
            y = cy + np.sin(ang) * spd * tt * np.exp(-tt * 1.2) + 0.5 * h * 0.5 * tt * tt
            ok = (x >= 0) & (x < w - 1) & (y >= 0) & (y < h - 1)
            life = max(0.0, 1 - t / 1.6) * fade
            np.add.at(layer, (y[ok].astype(int), x[ok].astype(int)), hue[ok] * life)
        from PIL import Image, ImageFilter

        size = max(3, (min(w, h) // 140) | 1)
        fat = np.dstack([np.asarray(Image.fromarray(u8(layer[..., c] * 3)).filter(ImageFilter.MaxFilter(size)), np.float32) for c in range(3)])
        layer = fat * 1.4 + blur(fat, max(3, min(w, h) / 120)) * 3
        out.append(u8(screen(f.astype(np.float32), layer)))
    s.frames = np.stack(out)


def burn(s: Shot) -> None:
    start = s.opt("from", 0.55)
    col = hexrgb(s.opt("colour", "#FFF6E0"))
    out = []
    for i, f in enumerate(s.frames):
        u = i / max(1, s.n - 1)
        k = 0 if u < start else ((u - start) / (1 - start)) ** 1.5
        ff = f.astype(np.float32)
        img = screen(ff * (1 + k * 0.8), col * min(1.0, k * 1.15))
        out.append(u8(img))
    s.frames = np.stack(out)


def endstrobe(s: Shot) -> None:
    k = min(s.n, max(2, int(s.opt("frames", 6))))
    for j in range(k):
        s.frames[s.n - k + j] = 255 if (j // 2) % 2 == 0 else 0


# --- looks ---------------------------------------------------------------------

def drawing(f: np.ndarray, mode: str) -> np.ndarray:
    """The picture as a drawing: pencil on paper, a blueprint, or chalk."""
    g = grey(f.astype(np.float32))
    h, w = g.shape
    b = blur(255 - g, max(1.5, w / 220))
    dodge = np.clip(g * 255 / np.maximum(1, 255 - b), 0, 255)
    line = np.clip(1 - dodge / 255, 0, 1) ** 0.7
    line = np.clip(line * 2.2, 0, 1)
    if mode == "blueprint":
        bg = np.array([20, 62, 138], np.float32)
        yy, xx = np.mgrid[0:h, 0:w]
        step = max(12, w // 28)
        grid = (((xx % step) == 0) | ((yy % step) == 0)).astype(np.float32) * 0.18
        a = np.clip(line + grid, 0, 1)[..., None]
        return u8(bg * (1 - a) + np.array([232, 240, 255]) * a)
    if mode == "chalk":
        bg = np.array([36, 40, 38], np.float32)
        a = line[..., None] * (0.75 + 0.25 * np.random.default_rng(1).random((h, w, 1)))
        return u8(bg * (1 - a) + 235 * a)
    paper = np.array([244, 240, 230], np.float32)
    grain = np.random.default_rng(2).normal(0, 3, (h, w, 1))
    a = line[..., None]
    return u8(paper * (1 - a) + np.array([40, 40, 44]) * a + grain)


def _look(mode: str):
    def f(s: Shot) -> None:
        s.frames = np.stack([drawing(x, mode) for x in s.frames])
    return f


def flick(s: Shot) -> None:
    mode = str(s.opt("with", "sketch"))
    every = max(1, s.opt("every", 2))
    s.frames = np.stack([drawing(f, mode) if (i // every) % 2 else f for i, f in enumerate(s.frames)])


def negative(s: Shot) -> None:
    s.frames = 255 - s.frames


def xray(s: Shot) -> None:
    out = []
    for f in s.frames:
        g = 255 - grey(f.astype(np.float32))
        g = np.clip((g - 30) * 1.25, 0, 255)
        img = np.dstack([g * 0.78, g * 0.9, g * 1.0 + 8])
        img = screen(img, blur(img, max(2, s.size[1] / 90)) * 0.6)
        out.append(u8(img))
    s.frames = np.stack(out)


def poster(s: Shot) -> None:
    c1, c2 = hexrgb(s.opt("dark", "#3B1F4F")), hexrgb(s.opt("light", "#F7C9A0"))
    levels = max(2, s.opt("levels", 5))
    out = []
    for f in s.frames:
        g = grey(f.astype(np.float32)) / 255
        q = np.round(g * (levels - 1)) / (levels - 1)
        out.append(u8(c1 * (1 - q[..., None]) + c2 * q[..., None]))
    s.frames = np.stack(out)


def pixel(s: Shot) -> None:
    from PIL import Image

    w, h = s.size
    k = max(4, w // s.opt("blocks", 24))
    for i in [0, 1, s.n - 2, s.n - 1]:
        if 0 <= i < s.n:
            small = Image.fromarray(s.frames[i]).resize((max(1, w // k), max(1, h // k)), Image.BILINEAR)
            big = np.asarray(small.resize((w, h), Image.NEAREST)).astype(np.float32)
            s.frames[i] = u8(np.round(big / 64) * 64)


def repeat(s: Shot) -> None:
    from PIL import Image

    w, h = s.size
    out = []
    for f in s.frames:
        small = np.asarray(Image.fromarray(f).resize((w // 2, h // 2), Image.BILINEAR))
        canvas = np.zeros_like(f)
        y = (h - h // 2) // 2
        for x in (-w // 4, w // 4, 3 * w // 4):
            x0, x1 = max(0, x), min(w, x + w // 2)
            canvas[y:y + h // 2, x0:x1] = small[:, x0 - x:x1 - x]
        out.append(canvas)
    s.frames = np.stack(out)


def strip(s: Shot) -> None:
    w, h = s.size
    band = s.opt("band", 0.33)
    bh = int(h * band) if w >= h else int(h * band * 0.6)
    y0 = (h - bh) // 2
    out = []
    for f in s.frames:
        c = np.full_like(f, 250)
        c[y0:y0 + bh] = f[y0:y0 + bh]
        out.append(c)
    s.frames = np.stack(out)


def smear(s: Shot) -> None:
    w = s.size[0]
    for i, k in ((0, w // 6), (1, w // 14)):
        if i < s.n:
            f = s.frames[i].astype(np.float32)
            c = np.cumsum(np.pad(f, ((0, 0), (k, 0), (0, 0)), mode="edge"), axis=1)
            sm = (c[:, k:] - c[:, :-k]) / k
            s.frames[i] = u8(sm * 1.15)


# --- shapes --------------------------------------------------------------------

def _shape_points(shape: str, w: int, h: int, n: int, rng) -> np.ndarray:
    from PIL import Image, ImageDraw

    s = min(w, h)
    if shape in ("infinity", "heart", "circle"):
        t = rng.uniform(0, 2 * math.pi, n)
        if shape == "infinity":  # a lemniscate, with a little thickness
            d = 1 + np.sin(t) ** 2
            x, y = np.cos(t) / d, np.sin(t) * np.cos(t) / d
            x, y = x * s * 0.42, y * s * 0.42
        elif shape == "heart":
            x = 16 * np.sin(t) ** 3
            y = -(13 * np.cos(t) - 5 * np.cos(2 * t) - 2 * np.cos(3 * t) - np.cos(4 * t))
            x, y = x * s * 0.022, y * s * 0.022
        else:
            x, y = np.cos(t) * s * 0.3, np.sin(t) * s * 0.3
        jit = rng.normal(0, s * 0.012, (2, n))
        return np.stack([w / 2 + x + jit[0], h / 2 + y + jit[1]], axis=1)
    im = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(im)
    font = _font(int(s * 0.5 / max(1, len(shape)) * 1.6))
    bb = d.textbbox((0, 0), shape, font=font)
    d.text(((w - (bb[2] - bb[0])) / 2 - bb[0], (h - (bb[3] - bb[1])) / 2 - bb[1]), shape, font=font, fill=255)
    ys, xs = np.nonzero(np.asarray(im) > 128)
    if not len(xs):
        return np.stack([np.full(n, w / 2), np.full(n, h / 2)], axis=1)
    k = rng.integers(0, len(xs), n)
    return np.stack([xs[k] + rng.uniform(-1, 1, n), ys[k] + rng.uniform(-1, 1, n)], axis=1).astype(np.float32)


def dots(s: Shot) -> None:
    from PIL import Image, ImageFilter

    w, h = s.size
    step = max(5, w // s.opt("across", 80))
    shape = str(s.opt("shape", ""))
    ys, xs = np.mgrid[step // 2:h:step, step // 2:w:step]
    p0 = np.stack([xs.ravel(), ys.ravel()], axis=1).astype(np.float32)
    flip = grey(s.frames[0].astype(np.float32)).mean() > 128  # on a light picture the dark parts become the dots

    def light(f):
        g = grey(f.astype(np.float32))[ys.ravel(), xs.ravel()] / 255
        return 1 - g if flip else g
    lit = light(s.frames[0])
    # Only the brighter parts become dots (a busy picture would otherwise fill the frame), and
    # never so many that a shape can't read.
    keep = lit > max(0.12, float(np.percentile(lit, 60)))
    idx = np.nonzero(keep)[0]
    if len(idx) > 2600:
        keep[:] = False
        keep[s.rng.choice(idx, 2600, replace=False)] = True
    p0, base = p0[keep], lit[keep]
    if len(p0) == 0:
        return
    n = len(p0)
    drift = s.rng.normal(0, 1, (n, 2)).astype(np.float32)
    drift /= np.linalg.norm(drift, axis=1, keepdims=True) + 1e-6
    drift *= s.rng.uniform(0.2, 1.0, (n, 1)) * min(w, h) * 0.22
    target = _shape_points(shape, w, h, n, s.rng) if shape else None
    if target is not None:  # each dot heads for the target point nearest its own angle around the centre
        a0 = np.arctan2(p0[:, 1] - h / 2, p0[:, 0] - w / 2)
        a1 = np.arctan2(target[:, 1] - h / 2, target[:, 0] - w / 2)
        target = target[np.argsort(a1)][np.argsort(np.argsort(a0))]
    out = []
    for i, f in enumerate(s.frames):
        u = i / max(1, s.n - 1)
        live = light(f)[keep]
        b = np.where(u < 0.3, live, base)
        sc = np.clip((u - 0.15) / 0.4, 0, 1)
        sc = sc * sc * (3 - 2 * sc)
        p = p0 + drift * sc * (1 if target is None else (1 - np.clip((u - 0.35) / 0.4, 0, 1)))
        if target is not None:  # gathers over the middle of the shot, then holds so the shape can be read
            g = np.clip((u - 0.35) / 0.4, 0, 1)
            g = g * g * (3 - 2 * g)
            p = p * (1 - g) + target * g
            b = b * (1 - g) + 0.95 * g
        elif u > 0.6:
            b = b * (1 - (u - 0.6) / 0.4)
        canvas = np.zeros((h, w), np.float32)
        ix, iy = np.clip(p[:, 0].astype(int), 0, w - 1), np.clip(p[:, 1].astype(int), 0, h - 1)
        np.maximum.at(canvas, (iy, ix), b)
        im = Image.fromarray(u8(canvas * 255)).filter(ImageFilter.MaxFilter(max(3, (step // 2) | 1)))
        dot = np.asarray(im.filter(ImageFilter.GaussianBlur(step * 0.18)), np.float32)
        dot = np.clip(dot * 1.4, 0, 255)
        img = np.repeat(dot[..., None], 3, axis=2) + blur(dot, step)[..., None] * 0.6
        out.append(u8(img))
    s.frames = np.stack(out)


def _arrow(d, x: float, y: float, size: float, angle: float, col, wobble) -> None:
    ca, sa = math.cos(angle), math.sin(angle)

    def P(u, v):
        return (x + (u * ca - v * sa) * size, y + (u * sa + v * ca) * size)
    shaft = [P(-0.5, wobble[0]), P(-0.1, wobble[1]), P(0.28, 0)]
    d.line(shaft, fill=col, width=max(3, int(size * 0.16)), joint="curve")
    d.polygon([P(0.55, 0), P(0.18, -0.26), P(0.22, 0.24)], fill=col)


def arrows(s: Shot) -> None:
    from PIL import Image, ImageDraw

    w, h = s.size
    k = s.opt("count", 6)
    col = tuple(int(x) for x in hexrgb(s.opt("colour", "#FFD54A")))
    spots = []
    for j in range(k):
        side = j % 2
        x = (s.rng.uniform(0.05, 0.3) if side == 0 else s.rng.uniform(0.7, 0.95)) * w
        y = s.rng.uniform(0.1, 0.9) * h
        spots.append((x, y, min(w, h) * s.rng.uniform(0.12, 0.2), s.rng.uniform(-2.2, -0.6),
                      s.rng.normal(0, 0.05, 2), int(j * s.n / (k + 1))))
    out = []
    for i, f in enumerate(s.frames):
        im = Image.fromarray(f)
        d = ImageDraw.Draw(im)
        for x, y, size, ang, wob, at in spots:
            if i >= at:
                age = i - at
                pop_ = [0.6, 1.18, 1.0][min(age, 2)]
                _arrow(d, x, y, size * pop_, ang, col, wob)
        out.append(np.asarray(im))
    s.frames = np.stack(out)


RUN = {
    "silhouette": silhouette, "glow": glow, "solid": solid, "speedlines": speedlines, "pop": pop, "words": words,
    "strobe-light": strobe_light, "burst": burst, "starburst": starburst, "lightning": lightning, "sparks": sparks,
    "burn": burn, "endstrobe": endstrobe,
    "sketch": _look("sketch"), "blueprint": _look("blueprint"), "chalk": _look("chalk"), "flick": flick,
    "negative": negative, "xray": xray, "poster": poster, "pixel": pixel, "repeat": repeat, "strip": strip, "smear": smear,
    "dots": dots, "arrows": arrows,
}


def parse(spec: str | list) -> list[str]:
    names = [x.strip() for x in (spec.split(",") if isinstance(spec, str) else spec) if str(x).strip()]
    bad = [x for x in names if x not in RUN]
    if bad:
        raise SystemExit(f"unknown effect(s) {', '.join(bad)}; choose from: {', '.join(EFFECTS)}")
    return names


def apply(frames: np.ndarray, fps: float, effects: list[str], opts: dict | None = None, seed: int = 0,
          mask: np.ndarray | None = None) -> np.ndarray:
    s = Shot(frames.copy(), fps, dict(opts or {}), seed)
    s._mask = mask
    for name in parse(effects):
        s.current = name
        RUN[name](s)
    return s.frames
