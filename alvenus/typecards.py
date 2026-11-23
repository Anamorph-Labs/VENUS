"""Full-picture type cards, from the Venus 1 board (23 Nov):

  - slam: the trailer credit. A huge word slams in, cropped by the frame,
    over old newsprint, red paint or charcoal, with a hard light sweeping
    across; then it settles small and centred under a little line ("Based on
    the writings of"); a black brush stroke wipes it away.
  - date: the last trailer card. A spaced-out date or line glowing over red
    smoke and flickering once, like a projector catching.
  - scramble: the video-essay word. A word on grey paper keeps swapping its
    letters for symbols and look-alikes (TAXES -> F€$Y£), stutters with
    glitch slices, then lands on what it really means (or on itself).

Each card is drawn frame by frame here with PIL and numpy (no downloads) and
handed to FFmpeg. The words are part of the picture, so nothing is added on
top later. Each card also says which sounds belong to it (see moments())."""

from __future__ import annotations

import subprocess
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_DIR = Path(__file__).with_name("fonts")
TEXTURES = ("newsprint", "red", "charcoal", "paper")
KINDS = ("slam", "date", "scramble")


def _font(px: int, name: str) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_DIR / name), max(8, int(px)))


@lru_cache(maxsize=512)
def _has(name: str, ch: str) -> bool:
    """Whether the font draws this character (not the empty box it uses for missing ones)."""
    f = _font(64, name)
    return bytes(f.getmask(ch)) != bytes(f.getmask("\uffff"))


def _drawable(text: str, plain: str, name: str) -> str:
    """Swap any character the font can't draw back to the plain letter."""
    return "".join(c if _has(name, c) else (plain[i] if i < len(plain) else "") for i, c in enumerate(text))


def _noise(w: int, h: int, rng, octaves=((6, 1.0), (20, 0.5), (60, 0.25))) -> np.ndarray:
    out = np.zeros((h, w), np.float32)
    for cells, amp in octaves:
        small = Image.fromarray((rng.random((max(2, cells * h // max(w, 1)), cells)) * 255).astype(np.uint8))
        out += amp * np.asarray(small.resize((w, h), Image.BICUBIC), np.float32) / 255
    out -= out.min()
    return out / max(1e-6, out.max())


def _newsprint(w: int, h: int, rng) -> np.ndarray:
    """Old newspaper, greyed: columns of tiny grey text lines, a few heavy
    headline bars, fold shadows and grain."""
    im = Image.new("L", (w, h), 200)
    d = ImageDraw.Draw(im)
    cols = max(4, w // 260)
    gap = w // (cols * 14)
    cw = (w - gap * (cols + 1)) / cols
    line = max(3, h // 150)
    for c in range(cols):
        x0 = gap + c * (cw + gap)
        y = int(rng.integers(0, h // 6))
        while y < h:
            if rng.random() < 0.07:  # a headline
                hh = int(line * rng.uniform(3, 6))
                d.rectangle([x0, y, x0 + cw * rng.uniform(0.6, 1.0), y + hh], fill=int(rng.uniform(40, 90)))
                y += hh + line * 2
                continue
            words_x = x0
            while words_x < x0 + cw:  # a line of "words": short dark dashes
                ww = rng.uniform(cw * 0.04, cw * 0.18)
                d.rectangle([words_x, y, min(x0 + cw, words_x + ww), y + line * 0.55], fill=int(rng.uniform(95, 140)))
                words_x += ww + line * 0.8
            y += line * 1.6
        d.line([x0 + cw + gap / 2, 0, x0 + cw + gap / 2, h], fill=120, width=1)
    a = np.asarray(im, np.float32) / 255
    a = a * (0.75 + 0.25 * _noise(w, h, rng)) * (0.92 + 0.08 * rng.random((h, w)))
    fold = 1 - 0.18 * np.exp(-((np.arange(w)[None, :] - w * rng.uniform(0.3, 0.7)) / (w * 0.02)) ** 2)
    return np.repeat((a * fold)[..., None], 3, 2)


def _red(w: int, h: int, rng) -> np.ndarray:
    """Deep red paint dragged across black: brushy streaks along a diagonal,
    darker at the edges."""
    n = _noise(w, h, rng, ((4, 1.0), (14, 0.6), (50, 0.3)))
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    diag = (xx / w * 0.8 + yy / h * 0.45)
    streak = 0.5 + 0.5 * np.sin(diag * rng.uniform(16, 24) + n * 5)
    paint = np.clip((n * 0.9 + streak * 0.5 - 0.55) * 2.2, 0, 1)
    v = 0.18 + 0.82 * np.exp(-(((xx - w / 2) / (w * 0.7)) ** 2 + ((yy - h / 2) / (h * 0.75)) ** 2))
    base = np.stack([0.06 + 0.66 * paint, 0.02 + 0.06 * paint, 0.03 + 0.08 * paint], 2)
    return base * v[..., None]


def _charcoal(w: int, h: int, rng) -> np.ndarray:
    n = _noise(w, h, rng)
    a = 0.08 + 0.12 * n + 0.04 * rng.random((h, w))
    return np.repeat(a[..., None], 3, 2)


def _paper(w: int, h: int, rng) -> np.ndarray:
    """Light grey essay paper with a faint grid and grain."""
    n = _noise(w, h, rng, ((10, 1.0), (40, 0.4)))
    a = 0.84 + 0.06 * n + 0.03 * rng.random((h, w))
    step = max(24, w // 40)
    a[::step, :] -= 0.05
    a[:, ::step] -= 0.05
    return np.repeat(a[..., None], 3, 2) * np.array([1.0, 1.0, 0.985])


def texture(kind: str, w: int, h: int, k: int) -> np.ndarray:
    rng = np.random.default_rng(4100 + k)
    return {"newsprint": _newsprint, "red": _red, "charcoal": _charcoal, "paper": _paper}[kind](w, h, rng).astype(np.float32)


def _text_layer(w: int, h: int, text: str, px: int, font: str, cx: float, cy: float, spacing: float = 0.0,
                rot: float = 0.0) -> np.ndarray:
    """0..1 mask of text centred at (cx, cy), with optional letter spacing."""
    f = _font(px, font)
    if spacing:
        widths = [f.getlength(c) for c in text]
        total = sum(widths) + spacing * px * (len(text) - 1)
    else:
        total = f.getlength(text)
    pad = px
    im = Image.new("L", (int(total + pad * 2), int(px * 1.6 + pad)), 0)
    d = ImageDraw.Draw(im)
    if spacing:
        x = pad
        for c, cw in zip(text, widths):
            d.text((x, pad / 2), c, font=f, fill=255)
            x += cw + spacing * px
    else:
        d.text((pad, pad / 2), text, font=f, fill=255)
    bb = im.getbbox() or (0, 0, 1, 1)
    im = im.crop(bb)
    if rot:
        im = im.rotate(rot, resample=Image.BICUBIC, expand=True)
    out = Image.new("L", (w, h), 0)
    out.paste(im, (int(cx - im.width / 2), int(cy - im.height / 2)))
    return np.asarray(out, np.float32) / 255


@lru_cache(maxsize=4)
def _diag(w: int, h: int) -> np.ndarray:
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    return (xx / w + (h - yy) / h * 0.55) / 1.55


@lru_cache(maxsize=4)
def _brush_base(w: int, h: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    rough = _noise(w, h, rng, ((3, 1.0), (30, 0.5), (120, 0.4)))
    return (xx / w * 1.0 - yy / h * 0.35 + 0.35) / 1.35 - (rough - 0.5) * 0.18


def _sweep(w: int, h: int, p: float, width: float = 0.22) -> np.ndarray:
    """A hard white light band crossing the frame on a diagonal (p: 0..1 across)."""
    u = _diag(w, h)
    c = -0.2 + 1.4 * p
    return np.clip(1 - np.abs(u - c) / width, 0, 1) ** 1.5


def _brush(w: int, h: int, p: float, rng_seed: int) -> np.ndarray:
    """A black brush stroke wiping across on a slant; returns 0..1 cover."""
    edge = -0.1 + 1.25 * p
    return np.clip((edge - _brush_base(w, h, rng_seed)) * 14, 0, 1)


def _smoke(w: int, h: int, k: int, t: float, big: np.ndarray) -> np.ndarray:
    H, W = big.shape
    ox = int((W - w) / 2 + np.sin(t * 0.35 + k) * (W - w) * 0.45)
    oy = int((H - h) / 2 - t * (H - h) * 0.08 % max(1, H - h - 1) * 0.5)
    return big[oy:oy + h, ox:ox + w]


def _ease(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 3


GLYPHS = {"A": "4Λ@", "B": "8", "C": "¢(", "E": "€3Σ", "G": "6", "I": "!1|", "L": "£", "O": "0Ø◯", "S": "$5§",
          "T": "7†", "X": "×Ж", "Y": "¥", "Z": "2", "N": "И", "R": "Я", "U": "µ", "D": "Ð", "H": "#", "K": "Ҝ"}


def scrambled(word: str, rng) -> str:
    return "".join(rng.choice(list(GLYPHS[c.upper()])) if c.upper() in GLYPHS and rng.random() < 0.7 else c for c in word)


def frames(sc: dict, d: float, w: int, h: int, fps: float, k: int, accent: str):
    """Yield the card's frames as uint8 RGB arrays."""
    kind = sc["type"]
    n = max(1, round(d * fps))
    scale = min(w, h) / 1080
    vertical = h > w
    tex_kind = sc.get("texture") or {"slam": "newsprint", "date": "red", "scramble": "paper"}[kind]
    tex = texture(tex_kind, w, h, k)
    acc = np.array([int(accent[i:i + 2], 16) for i in (1, 3, 5)], np.float32) / 255
    rng = np.random.default_rng(77 + k)
    text = str(sc.get("text") or "").strip()
    if kind == "slam":
        word = text.upper()
        small = str(sc.get("small") or "").upper()
        ink = np.array([0.93, 0.93, 0.9]) if tex_kind != "newsprint" else np.array([0.95, 0.95, 0.93])
        settle_at = float(sc.get("settle", 0.42))  # where in the card the big word gives way to the small credit
        wipe = 0.0 if sc.get("wipe") is False else min(0.4, d * 0.18)
        big_px = int(h * (0.62 if not vertical else 0.3))
        for i in range(n):
            t = i / fps
            p = t / d
            img = tex.copy()
            if tex_kind == "newsprint":
                img = img * (0.35 + 0.65 * _sweep(w, h, (p * 1.3) % 1.4, 0.3)[..., None]) + 0.0
                img = img * 0.85
            else:
                img = img + _sweep(w, h, (p * 1.1) % 1.3, 0.18)[..., None] * 0.18
            if p < settle_at:  # the big word, cropped, slamming in then drifting slowly
                q = _ease(t / 0.18)
                s = 1.35 - 0.35 * q + 0.04 * p
                shake = (rng.normal(0, 1, 2) * 10 * scale * (1 - q)) if t < 0.3 else (0, 0)
                m = _text_layer(w, h, word, int(big_px * s), "BigShoulders-Bold.ttf",
                                w * (0.42 - 0.08 * p) + shake[0], h * 0.55 + shake[1], spacing=0.02)
                bright = 0.75 + 0.25 * _sweep(w, h, p * 1.6, 0.25)
                img = img * (1 - m[..., None]) + (m * bright)[..., None] * ink
                if t < 0.06:  # the frame of impact flashes
                    img = img * 0.4 + 0.6
            else:  # settled: small line + the word, centred, slow push
                q = _ease((p - settle_at) / 0.12)
                push = 1 + 0.05 * (p - settle_at)
                wpx = int(h * (0.13 if not vertical else 0.07) * push)
                m = _text_layer(w, h, word, wpx, "BigShoulders-Bold.ttf", w / 2, h * 0.52, spacing=0.04)
                if small:
                    m = np.maximum(m, _text_layer(w, h, small, int(wpx * 0.24), "Inter-SemiBold.otf", w / 2, h * 0.52 - wpx * 0.78, spacing=0.12))
                img = img * (1 - 0.55 * q) if tex_kind == "newsprint" else img
                img = img * (1 - m[..., None] * q) + (m * q)[..., None] * ink
                if q < 1:  # motion smear while it snaps in
                    img = img + _sweep(w, h, 0.5, 0.5)[..., None] * (1 - q) * 0.25
            if wipe and t > d - wipe:
                cover = _brush(w, h, (t - (d - wipe)) / wipe, 900 + k)
                img = img * (1 - cover[..., None]) + cover[..., None] * 0.02
            g = rng.normal(0, 0.035, (h // 2, w // 2)).astype(np.float32)
            img = img + np.kron(g, np.ones((2, 2), np.float32))[:h, :w, None]
            yield (np.clip(img, 0, 1) * 255).astype(np.uint8)
    elif kind == "date":
        big = _noise(int(w * 1.6), int(h * 1.6), np.random.default_rng(300 + k), ((3, 1.0), (9, 0.6), (30, 0.3)))
        line = text.upper()
        sub = str(sc.get("small") or "").upper()
        px = int(h * (0.075 if not vertical else 0.045))
        m = _text_layer(w, h, line, px, "BigShoulders-Bold.ttf", w / 2, h * 0.5, spacing=0.35)
        if sub:
            m = np.maximum(m, _text_layer(w, h, sub, int(px * 0.32), "Inter-SemiBold.otf", w / 2, h * 0.5 + px * 1.0, spacing=0.3))
        dark = tex * 0.55
        for i in range(n):
            t = i / fps
            smoke = _smoke(w, h, k, t, big)
            img = dark + (smoke ** 2)[..., None] * np.array([0.45, 0.05, 0.05]) * 0.9
            fade = _ease(t / 0.9)
            flick = 0.35 if 0.9 < t < 0.97 else 1.0
            img = img * (1 - m[..., None] * fade) + (m * fade * flick)[..., None] * np.array([0.95, 0.93, 0.9])
            embers = (rng.random((h // 4, w // 4)) > 0.9995).astype(np.float32)
            img = img + np.kron(embers, np.ones((4, 4), np.float32))[:h, :w, None] * acc * 0.9
            img = img * (1 - _ease((t - (d - 0.5)) / 0.5) * 0.9)
            g = rng.normal(0, 0.03, (h // 2, w // 2)).astype(np.float32)
            img = img + np.kron(g, np.ones((2, 2), np.float32))[:h, :w, None]
            yield (np.clip(img, 0, 1) * 255).astype(np.uint8)
    else:  # scramble
        word = text
        final = str(sc.get("to") or word)
        px = int(h * (0.22 if not vertical else 0.1))
        if len(max(word, final, key=len)) > 8:
            px = int(px * 8 / len(max(word, final, key=len)))
        land = 0.62  # where the letters stop swapping and land on the last word
        fonts = ["BigShoulders-Bold.ttf", "InterDisplay-Black.otf", "LibreBaskerville-Regular.ttf", "DMMono-Regular.ttf"]
        ink = np.array([0.08, 0.08, 0.08])
        cur, font_i, step = word, 0, max(1, round(fps * 0.09))
        for i in range(n):
            t = i / fps
            p = t / d
            if p < land and i % step == 0:
                cur = scrambled(word if p < land * 0.5 else final, rng) if rng.random() < 0.75 else (word if p < land * 0.5 else final)
                font_i = int(rng.integers(0, len(fonts)))
            elif p >= land:
                cur, font_i = final, 0
            plain = (word if p < land * 0.5 else final).upper()
            m = _text_layer(w, h, _drawable(cur.upper(), plain, fonts[font_i]), px, fonts[font_i], w / 2, h / 2, spacing=0.06 if font_i != 2 else 0.02)
            img = tex.copy()
            if p < land and rng.random() < 0.35:  # glitch: slices of the picture slide sideways
                rows = rng.integers(0, h, 4)
                for r in rows:
                    hh = int(rng.integers(h // 60, h // 14))
                    m[r:r + hh] = np.roll(m[r:r + hh], int(rng.integers(-w // 12, w // 12)), axis=1)
            bar = p >= land and sc.get("box", True)
            if bar:  # it lands inverted in a black block, like a stamp
                ys, xs = np.nonzero(m > 0.3)
                if len(xs):
                    padx, pady = px * 0.25, px * 0.18
                    x0, x1, y0, y1 = xs.min() - padx, xs.max() + padx, ys.min() - pady, ys.max() + pady
                    q = _ease((p - land) / 0.08)
                    x1 = x0 + (x1 - x0) * q
                    img[int(y0):int(y1), int(x0):int(x1)] = ink
                    img = img * (1 - m[..., None]) + m[..., None] * np.array([0.95, 0.95, 0.93])
                else:
                    img = img * (1 - m[..., None]) + m[..., None] * ink
            else:
                img = img * (1 - m[..., None]) + m[..., None] * ink
                if p < land and rng.random() < 0.25:  # a red slice through the word
                    r = int(rng.integers(h // 3, 2 * h // 3))
                    img[r:r + max(2, h // 120)] = acc
            g = rng.normal(0, 0.02, (h // 2, w // 2)).astype(np.float32)
            img = img + np.kron(g, np.ones((2, 2), np.float32))[:h, :w, None]
            yield (np.clip(img, 0, 1) * 255).astype(np.uint8)


def moments(sc: dict, t0: float, t1: float) -> list[tuple[float, str]]:
    """The sounds a card asks for, as (time, sound) in the whole video."""
    d = t1 - t0
    if sc["type"] == "slam":
        ev = [(t0 + 0.0, "boom"), (t0 + 0.0, "riser")] if t0 > 2.5 else [(t0, "boom")]
        ev += [(t0 + d * float(sc.get("settle", 0.42)), "whoosh")]
        if sc.get("wipe") is not False:
            ev.append((t1 - min(0.4, d * 0.18) * 0.4, "whoosh"))
        return ev
    if sc["type"] == "date":
        return [(t0 + 0.05, "braam"), (t0 + 0.92, "snap")]
    ev = [(t0 + x, "glitch") for x in np.arange(0.1, d * 0.6, 0.45)]
    return ev + [(t0 + d * 0.62, "hit")]


def scene_video(sc: dict, d: float, w: int, h: int, fps: float, out: Path, k: int, accent: str) -> None:
    cmd = ["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
           "-r", f"{fps:g}", "-i", "-", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "14",
           "-pix_fmt", "yuv420p", str(out)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        for f in frames(sc, d, w, h, fps, k, accent):
            p.stdin.write(f.tobytes())
    finally:
        p.stdin.close()
        if p.wait() != 0:
            raise RuntimeError(f"could not render the {sc['type']} card")
