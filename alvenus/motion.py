"""Moving pictures drawn frame by frame: effects FFmpeg's filters can't make.

Overlays drawn over any scene:
- `"stamp"`: a word slams onto the picture like a rubber stamp, with uneven ink;
- `"strike"`: a word is struck through by hand and a new one is written in;
- `"notes"`: hand-drawn underlines, circles, arrows, crosses and short notes.

Pictures:
- `"scan_lift"` (image scene): a line of light scans the still print, then the
  print lifts up into a full-screen moving shot (`"to"`: a clip);
- `"card"` (clip or image scene): the shot as a tilted card beside its words,
  optionally shrinking into the card from full screen;
- `"alive"` (image scene): a still brought to life: rain, drifting clouds,
  ripples on water, and a slow 3D camera move.

Everything is drawn with numpy and Pillow and streamed through FFmpeg, on the
computer, with no models and nothing downloaded."""

from __future__ import annotations

import math
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .style import FONTS

VERSION = 6  # raise when a drawing here changes, so cached scenes are drawn again
IVORY, INK, DEEP_BLUE = (244, 241, 234), (27, 27, 31), (43, 74, 120)


# ---------------------------------------------------------------- frames in and out

def _still(f: str) -> bool:
    return Path(f).suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff")


def frames_of(path: str, w: int, h: int, fps: float, start: float, d: float):
    """Every frame of `path` from `start` for `d` seconds, covering w x h (rgb, uint8).
    A still repeats; a clip that runs out holds its last frame."""
    n = max(1, round(d * fps))
    vf = f"fps={fps:g},scale={w}:{h}:force_original_aspect_ratio=increase:flags=bicubic,crop={w}:{h},setsar=1"
    if _still(path):
        img = np.asarray(Image.open(path).convert("RGB"))
        one = cover(img, w, h)
        for _ in range(n):
            yield one
        return
    args = ["ffmpeg", "-nostdin", "-v", "error", "-ss", f"{max(0.0, start):.3f}", "-t", f"{d + 0.5:.3f}", "-i", str(path),
            "-vf", vf, "-an", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    size, last = w * h * 3, None
    try:
        for _ in range(n):
            buf = p.stdout.read(size)
            if len(buf) == size:
                last = np.frombuffer(buf, np.uint8).reshape(h, w, 3)
            if last is None:
                last = np.zeros((h, w, 3), np.uint8)
            yield last
    finally:
        p.stdout.close()
        p.kill()
        p.wait()


def cover(img: np.ndarray, w: int, h: int) -> np.ndarray:
    ih, iw = img.shape[:2]
    s = max(w / iw, h / ih)
    pic = Image.fromarray(img).resize((max(w, round(iw * s)), max(h, round(ih * s))), Image.BICUBIC)
    x, y = (pic.width - w) // 2, (pic.height - h) // 2
    return np.asarray(pic.crop((x, y, x + w, y + h)))


class Writer:
    def __init__(self, out: Path, w: int, h: int, fps: float):
        self.p = subprocess.Popen(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                                   "-s", f"{w}x{h}", "-r", f"{fps:g}", "-i", "-", "-an", "-c:v", "libx264", "-preset", "veryfast",
                                   "-crf", "14", "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE, stderr=subprocess.PIPE)

    def put(self, frame: np.ndarray) -> None:
        self.p.stdin.write(np.ascontiguousarray(frame, dtype=np.uint8).tobytes())

    def close(self) -> None:
        self.p.stdin.close()
        err = self.p.stderr.read().decode(errors="replace")
        if self.p.wait() != 0:
            raise RuntimeError(f"writing frames failed: {err[-600:]}")


# ---------------------------------------------------------------- small helpers

def _rgb(c, default=(255, 255, 255)) -> tuple[int, int, int]:
    if isinstance(c, (list, tuple)) and len(c) >= 3:
        return tuple(int(x) for x in c[:3])
    s = str(c or "").lstrip("#")
    if len(s) == 6:
        try:
            return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            pass
    return default


def _font(sc: dict, role: str, size: int):
    """The scene's font for a role: brand fonts first (heading, body), else Venus's own."""
    own = {"stamp": "BigShoulders-Bold.ttf", "heading": "InterDisplay-Bold.otf", "hand": "NothingYouCouldDo-Regular.ttf",
           "serif": "InstrumentSerif-Italic.ttf"}[role]
    fonts = sc.get("_fonts") or {}
    pick = fonts.get("heading") if role in ("heading",) else None
    for f in (pick, FONTS / own):
        if f and Path(f).exists():
            try:
                return ImageFont.truetype(str(f), max(6, int(size)))
            except OSError:
                continue
    return ImageFont.load_default()


def _ease(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def _ease_out(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 3


def _bright(frame: np.ndarray, x: float, y: float, r: int) -> float:
    h, w = frame.shape[:2]
    cx, cy = int(x * w), int(y * h)
    patch = frame[max(0, cy - r):cy + r, max(0, cx - r):cx + r]
    return float(patch.mean()) if patch.size else 128.0


def _lum(c) -> float:
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def _legible(want, frame: np.ndarray, x: float, y: float, r: int):
    """`want` where it reads against the picture there; else ivory on dark, ink on light."""
    under = _bright(frame, x, y, r)
    if abs(_lum(want) - under) >= 80:
        return want
    return IVORY if under < 128 else INK


def _wobble(pts: list[tuple[float, float]], amp: float, rng, n: int = 6) -> list[tuple[float, float]]:
    """A hand-drawn version of a line through `pts`: resampled, with a little tremor."""
    out = []
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        L = math.hypot(x1 - x0, y1 - y0)
        k = max(2, int(L / max(1.0, amp * n)))
        for i in range(k):
            u = i / k
            out.append((x0 + (x1 - x0) * u, y0 + (y1 - y0) * u))
    out.append(pts[-1])
    phase = rng.uniform(0, 6.28)
    return [(x + amp * 0.5 * math.sin(i * 0.7 + phase), y + amp * math.sin(i * 0.45 + phase * 1.3))
            for i, (x, y) in enumerate(out)]


def _partial(pts: list[tuple[float, float]], p: float) -> list[tuple[float, float]]:
    """The first fraction `p` of a polyline, by length."""
    if p >= 1 or len(pts) < 2:
        return pts
    seg = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:])]
    goal, run, out = sum(seg) * max(0.0, p), 0.0, [pts[0]]
    for (a, b), L in zip(zip(pts, pts[1:]), seg):
        if run + L >= goal:
            u = (goal - run) / L if L else 0
            out.append((a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u))
            return out
        out.append(b)
        run += L
    return out


def _stroke(draw: ImageDraw.ImageDraw, pts, width: int, fill) -> None:
    if len(pts) < 2:
        return
    draw.line(pts, fill=fill, width=width, joint="curve")
    r = width / 2
    for x, y in (pts[0], pts[-1]):
        draw.ellipse([x - r, y - r, x + r, y + r], fill=fill)


# ---------------------------------------------------------------- overlays

class Layer:
    """An RGBA layer drawn at 2x and brought down, for soft hand-drawn edges."""

    def __init__(self, w: int, h: int, s: int = 2):
        self.w, self.h, self.s = w, h, s
        self.img = Image.new("RGBA", (w * s, h * s), (0, 0, 0, 0))
        self.draw = ImageDraw.Draw(self.img)

    def done(self) -> Image.Image:
        return self.img.resize((self.w, self.h), Image.LANCZOS) if self.s != 1 else self.img


def _stamp_image(sc: dict, spec: dict, w: int, h: int, colour) -> Image.Image:
    """The stamp itself, upright, with uneven ink (alpha only where ink took)."""
    u = min(w, h)
    text = str(spec.get("text", "")).upper()
    size = int(u * float(spec.get("size", 0.16)))
    f = _font(sc, "stamp", size)
    box = ImageDraw.Draw(Image.new("L", (1, 1))).textbbox((0, 0), text, font=f)
    tw, th = box[2] - box[0], box[3] - box[1]
    pad, line = int(size * 0.32), max(3, size // 14)
    W, H = tw + pad * 2 + line * 4, th + pad * 2 + line * 4
    a = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(a)
    d.rounded_rectangle([line, line, W - line, H - line], radius=size // 6, outline=255, width=line)
    d.rounded_rectangle([line * 3, line * 3, W - line * 3, H - line * 3], radius=size // 9, outline=255, width=max(1, line // 2))
    d.text(((W - tw) / 2 - box[0], (H - th) / 2 - box[1]), text, font=f, fill=255)
    rng = np.random.default_rng(len(text) * 7 + 3)
    ink = np.asarray(a, np.float32) / 255
    grain = rng.random(ink.shape)
    blot = np.asarray(Image.fromarray((rng.random((H // 8 + 1, W // 8 + 1)) * 255).astype(np.uint8)).resize((W, H), Image.BICUBIC),
                      np.float32) / 255
    took = np.clip(0.7 + 0.5 * blot - 0.4 * (grain > 0.9), 0, 1)  # patches where the ink is thin, specks where none took
    alpha = (ink * took * 0.92 * 255).astype(np.uint8)
    img = Image.new("RGBA", (W, H), colour + (0,))
    img.putalpha(Image.fromarray(alpha))
    return img


def _stamp_at(sc, spec, t, w, h, frame, cache):
    at = float(spec.get("at", 0.4))
    if t < at:
        return None
    if "img" not in cache:
        colour = _rgb(spec.get("colour")) if spec.get("colour") else \
            _legible(_rgb(sc.get("_accent"), DEEP_BLUE), frame, float(spec.get("x", 0.5)), float(spec.get("y", 0.5)), min(w, h) // 6)
        cache["img"] = _stamp_image(sc, spec, w, h, colour)
    u = (t - at) / 0.13
    scale = 1.0 + 0.75 * (1 - _ease_out(u)) if u < 1 else 1.0
    shake = 0.0
    if 1 <= u < 3.5:
        shake = math.sin((u - 1) * 9) * math.exp(-(u - 1) * 1.6) * 0.012 * min(w, h)
    angle = float(spec.get("angle", -8))
    img = cache["img"]
    if scale != 1.0:
        img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.BICUBIC)
        a = np.asarray(img.getchannel("A"), np.float32) * min(1.0, 0.35 + u)
        img.putalpha(Image.fromarray(a.astype(np.uint8)))
    img = img.rotate(angle, resample=Image.BICUBIC, expand=True)
    x = float(spec.get("x", 0.5)) * w - img.width / 2 + shake
    y = float(spec.get("y", 0.5)) * h - img.height / 2
    return img, (round(x), round(y)), u >= 3.5


def _strike_layer(sc, spec, t, w, h, frame, cache):
    u = min(w, h)
    size = int(u * float(spec.get("size", 0.1)))
    x, y = float(spec.get("x", 0.5)) * w, float(spec.get("y", 0.5)) * h
    show, at = float(spec.get("show", 0.15)), float(spec.get("at", 1.0))
    if t < show:
        return None
    if "geo" not in cache:
        f = _font(sc, "heading", size)
        old = str(spec.get("old", ""))
        b = ImageDraw.Draw(Image.new("L", (1, 1))).textbbox((0, 0), old, font=f)
        ow, oh = b[2] - b[0], b[3] - b[1]
        light = _bright(frame, spec.get("x", 0.5), spec.get("y", 0.5), size) > 140
        cache["geo"] = (f, old, b, ow, oh, INK if light else IVORY)
        rng = np.random.default_rng(11)
        x0, x1 = x - ow / 2 - size * 0.12, x + ow / 2 + size * 0.12
        cache["line"] = _wobble([(x0, y + oh * 0.08), (x1, y - oh * 0.12)], size * 0.03, rng)
    f, old, b, ow, oh, fg = cache["geo"]
    if "accent" not in cache:
        cache["accent"] = _rgb(spec.get("colour")) if spec.get("colour") else \
            _legible(_rgb(sc.get("_accent"), DEEP_BLUE), frame, float(spec.get("x", 0.5)), float(spec.get("y", 0.5)) - 0.06, size)
    accent = cache["accent"]
    L = Layer(w, h)
    s = L.s
    fade = min(1.0, (t - show) / 0.25)
    L.draw.text(((x - ow / 2 - b[0]) * s, (y - oh / 2 - b[1]) * s), old,
                font=_font(sc, "heading", size * s), fill=fg + (int(255 * fade),))
    p = (t - at) / 0.35
    if p > 0:
        _stroke(L.draw, [(px * s, py * s) for px, py in _partial(cache["line"], p)], max(4, size // 9) * s, accent + (255,))
    q = (t - at - 0.45) / 0.55
    done = q >= 1.2
    if q > 0:
        new = str(spec.get("new", ""))
        hf = _font(sc, "hand", int(size * 1.5 * s))
        nb = L.draw.textbbox((0, 0), new, font=hf)
        nw, nh = nb[2] - nb[0], nb[3] - nb[1]
        words = Image.new("RGBA", (nw + 8 * s, nh + 8 * s), (0, 0, 0, 0))
        ImageDraw.Draw(words).text((4 * s - nb[0], 4 * s - nb[1]), new, font=hf, fill=accent + (255,))
        cut = int(words.width * _ease(min(1.0, q)))  # written left to right
        m = Image.new("L", words.size, 0)
        ImageDraw.Draw(m).rectangle([0, 0, cut, words.height], fill=255)
        words.putalpha(Image.fromarray(np.minimum(np.asarray(words.getchannel("A")), np.asarray(m))))
        words = words.rotate(float(spec.get("angle", 4)), resample=Image.BICUBIC, expand=True)
        where = spec.get("where", "above")
        nx = x * s + (ow * 0.15 * s if where == "above" else ow * 0.55 * s + size * 0.2 * s)
        ny = (y - oh * 1.35) * s if where == "above" else (y - oh * 0.5) * s
        L.img.alpha_composite(words, (round(nx - words.width / 2 if where == "above" else nx), round(ny - words.height / 2 if where == "above" else ny - words.height * 0.2)))
    return L.done(), (0, 0), done


NOTE_KINDS = ("underline", "circle", "arrow", "note", "cross", "box", "tick")


def _note_paths(n: dict, w: int, h: int, k: int) -> list[list[tuple[float, float]]]:
    rng = np.random.default_rng(31 + k)
    kind = n.get("kind", "underline")
    x, y = float(n.get("x", 0.5)) * w, float(n.get("y", 0.5)) * h
    bw, bh = float(n.get("w", 0.3)) * w, float(n.get("h", 0.1)) * h
    amp = min(w, h) * 0.004
    if kind == "underline":
        return [_wobble([(x - bw / 2, y), (x + bw / 2, y - bh * 0.06)], amp, rng)]
    if kind == "circle":
        pts = [(x + bw / 2 * 1.08 * math.cos(a) * (1 + 0.04 * math.sin(3 * a)), y + bh / 2 * 1.15 * math.sin(a))
               for a in np.linspace(-2.6, -2.6 + 2 * math.pi * 1.08, 80)]
        return [_wobble(pts, amp, rng, 2)]
    if kind == "box":
        return [_wobble([(x - bw / 2, y - bh / 2), (x + bw / 2, y - bh / 2), (x + bw / 2, y + bh / 2), (x - bw / 2, y + bh / 2),
                         (x - bw / 2, y - bh / 2 - amp * 2)], amp, rng)]
    if kind == "cross":
        return [_wobble([(x - bw / 2, y - bh / 2), (x + bw / 2, y + bh / 2)], amp, rng),
                _wobble([(x + bw / 2, y - bh / 2), (x - bw / 2, y + bh / 2)], amp, rng)]
    if kind == "tick":
        return [_wobble([(x - bw / 2, y), (x - bw / 8, y + bh / 2), (x + bw / 2, y - bh / 2)], amp, rng)]
    if kind in ("arrow", "note"):
        to = n.get("to") or [n.get("x", 0.5) + 0.12, n.get("y", 0.5) + 0.1]
        tx, ty = float(to[0]) * w, float(to[1]) * h
        if kind == "note" and not n.get("to"):
            return []
        mx, my = (x + tx) / 2 - (ty - y) * 0.22, (y + ty) / 2 + (tx - x) * 0.22  # a gentle curve
        curve = [((1 - u) ** 2 * x + 2 * (1 - u) * u * mx + u * u * tx, (1 - u) ** 2 * y + 2 * (1 - u) * u * my + u * u * ty)
                 for u in np.linspace(0, 1, 30)]
        ang = math.atan2(ty - curve[-4][1], tx - curve[-4][0])
        head = min(w, h) * 0.03
        a1 = (tx - head * math.cos(ang - 0.5), ty - head * math.sin(ang - 0.5))
        a2 = (tx - head * math.cos(ang + 0.5), ty - head * math.sin(ang + 0.5))
        return [_wobble(curve, amp, rng, 2), [a1, (tx, ty), a2]]
    return []


def _notes_layer(sc, notes, t, w, h, frame, cache):
    accent = _rgb(sc.get("_accent"), DEEP_BLUE)
    L, any_on, settled = None, False, True
    for k, n in enumerate(notes):
        at = float(n.get("at", 0.5 + 0.6 * k))
        if t < at:
            settled = False
            continue
        L = L or Layer(w, h)
        s = L.s
        any_on = True
        if ("col", k) not in cache:
            cache[("col", k)] = _rgb(n.get("colour")) if n.get("colour") else \
                _legible(accent, frame, float(n.get("x", 0.5)), float(n.get("y", 0.5)), min(w, h) // 8)
        col = cache[("col", k)] + (255,)
        width = max(3, int(min(w, h) * float(n.get("weight", 0.007)))) * s
        if k not in cache:
            cache[k] = _note_paths(n, w, h, k)
        paths = cache[k]
        p = (t - at) / float(n.get("speed", 0.5))
        lengths = [len(x) for x in paths] or [1]
        total = sum(lengths)
        run = 0
        for path in paths:  # strokes drawn one after another, like a hand
            share = len(path) / total
            sp = min(1.0, max(0.0, (p - run) / share))
            run += share
            if sp > 0:
                _stroke(L.draw, [(a * s, b * s) for a, b in _partial(path, sp)], width, col)
        if n.get("text"):
            f = _font(sc, "hand", int(min(w, h) * float(n.get("size", 0.075)) * s))
            q = _ease(min(1.0, (p - 0.6) / 0.6)) if n.get("kind") in ("arrow", "note") else _ease(min(1.0, p - 0.3))
            if q > 0:
                tx = float(n.get("x", 0.5)) * w * s
                ty = float(n.get("y", 0.5)) * h * s
                b = L.draw.textbbox((0, 0), n["text"], font=f)
                tw, th = b[2] - b[0], b[3] - b[1]
                kind = n.get("kind")
                ox = tx - tw / 2 - b[0]
                oy = ty - th - b[1] - width * 2 if kind in ("arrow", "note") else ty + width * 2 - b[1]
                words = Image.new("RGBA", L.img.size, (0, 0, 0, 0))
                ImageDraw.Draw(words).text((ox, oy), n["text"], font=f, fill=col)
                m = Image.new("L", L.img.size, 0)
                ImageDraw.Draw(m).rectangle([ox - 4, 0, ox + (tw + 8) * q, L.img.height], fill=255)
                words.putalpha(Image.fromarray(np.minimum(np.asarray(words.getchannel("A")), np.asarray(m))))
                L.img.alpha_composite(words)
        if p < 2.2:
            settled = False
    if not any_on:
        return None
    return L.done(), (0, 0), settled


def has_overlay(sc: dict) -> bool:
    return bool(sc.get("stamp") or sc.get("strike") or sc.get("notes"))


def _paste(frame: np.ndarray, img: Image.Image, xy: tuple[int, int]) -> np.ndarray:
    h, w = frame.shape[:2]
    x, y = xy
    x0, y0, x1, y1 = max(0, x), max(0, y), min(w, x + img.width), min(h, y + img.height)
    if x1 <= x0 or y1 <= y0:
        return frame
    a = np.asarray(img, np.float32)[y0 - y:y1 - y, x0 - x:x1 - x]
    al = a[..., 3:4] / 255
    out = frame.copy()
    out[y0:y1, x0:x1] = (out[y0:y1, x0:x1] * (1 - al) + a[..., :3] * al).astype(np.uint8)
    return out


def overlay(out: Path, sc: dict, d: float, w: int, h: int, fps: float) -> None:
    """Draw the scene's stamps, strikes and notes over its finished picture."""
    specs = []
    for s in (sc["stamp"] if isinstance(sc.get("stamp"), list) else [sc.get("stamp")] if sc.get("stamp") else []):
        specs.append((_stamp_at, {"text": s} if isinstance(s, str) else s))
    if sc.get("strike"):
        specs.append((_strike_layer, sc["strike"]))
    if sc.get("notes"):
        specs.append((_notes_layer, list(sc["notes"])))
    raw = out.with_name(out.stem + ".under.mp4")
    out.replace(raw)
    wr = Writer(out, w, h, fps)
    caches = [dict() for _ in specs]
    held: list = [None] * len(specs)
    try:
        for i, frame in enumerate(frames_of(str(raw), w, h, fps, 0.0, d)):
            t = i / fps
            for j, (fn, spec) in enumerate(specs):
                if held[j] is not None:
                    got = held[j]
                else:
                    got = fn(sc, spec, t, w, h, frame, caches[j])
                    if got is not None and got[2]:
                        held[j] = got  # settled: the same picture from here on
                if got is not None:
                    frame = _paste(frame, got[0], got[1])
            wr.put(frame)
    finally:
        wr.close()
        raw.unlink(missing_ok=True)


def stamp_times(sc: dict, t0: float) -> list[float]:
    """When each stamp lands, on the video's timeline (for its sound)."""
    st = sc.get("stamp")
    st = st if isinstance(st, list) else [st] if st else []
    return [t0 + float((s if isinstance(s, dict) else {}).get("at", 0.4)) for s in st]


# ---------------------------------------------------------------- pictures

def has_picture(sc: dict) -> bool:
    if isinstance(sc.get("page"), dict) and sc.get("type") in ("clip", "image", "title", "text"):
        return True
    return sc.get("type") in ("clip", "image") and bool(sc.get("file")) and bool(sc.get("scan_lift") or sc.get("card") or sc.get("alive")
                                                                                  or sc.get("drop"))


def picture(sc: dict, d: float, w: int, h: int, fps: float, out: Path) -> None:
    if isinstance(sc.get("page"), dict):
        from .page import page_scene

        return page_scene(sc, d, w, h, fps, out)
    if sc.get("drop"):
        from .page import drop_scene

        if "_drop" not in sc:  # built alone: it lands on an empty page
            from .page import drop_spec

            sc["_drop"] = drop_spec(sc, 0)
        return drop_scene(sc, d, w, h, fps, out)
    if sc.get("scan_lift"):
        return _scan_lift(sc, d, w, h, fps, out)
    if sc.get("card"):
        return _card(sc, d, w, h, fps, out)
    return _alive(sc, d, w, h, fps, out)


def _shadowed(img: Image.Image, blur: int, offset: int, strength: float = 0.55) -> tuple[Image.Image, int]:
    pad = blur * 3 + abs(offset)
    canvas = Image.new("RGBA", (img.width + pad * 2, img.height + pad * 2), (0, 0, 0, 0))
    sh = Image.new("L", canvas.size, 0)
    sh.paste(img.getchannel("A"), (pad, pad + offset))
    sh = sh.filter(ImageFilter.GaussianBlur(blur)).point(lambda v: int(v * strength))
    canvas.paste((0, 0, 0, 255), (0, 0), sh)
    canvas.alpha_composite(img, (pad, pad))
    return canvas, pad


def _backdrop(sc: dict, w: int, h: int, still: np.ndarray | None = None) -> np.ndarray:
    """What a print or card sits on: the picture itself, blurred and dark, or plain ink."""
    if still is not None and (sc.get("scan_lift") or {}).get("backdrop", "blur") == "blur":
        b = Image.fromarray(cover(still, w, h)).filter(ImageFilter.GaussianBlur(min(w, h) // 30))
        return (np.asarray(b, np.float32) * 0.35).astype(np.uint8)
    paper = (sc.get("card") or {}).get("paper") if isinstance(sc.get("card"), dict) else False
    base = np.full((h, w, 3), IVORY if paper else INK, np.uint8)
    rng = np.random.default_rng(5)
    return np.clip(base.astype(np.int16) + rng.integers(-6, 7, (h, w, 1)), 0, 255).astype(np.uint8)


def _scan_lift(sc: dict, d: float, w: int, h: int, fps: float, out: Path) -> None:
    spec = sc["scan_lift"] if isinstance(sc["scan_lift"], dict) else {"to": sc["scan_lift"]}
    still = np.asarray(Image.open(sc["file"]).convert("RGB")) if _still(sc["file"]) else next(frames_of(sc["file"], w, h, fps, float(sc.get("from", 0)), 0.05))
    full = cover(still, w, h)
    back = _backdrop(sc, w, h, still)
    scan_a, scan_d = float(spec.get("scan_at", 0.3)), float(spec.get("scan", 1.1))
    lift_a, lift_d = float(spec.get("at", scan_a + scan_d + 0.2)), float(spec.get("lift", 0.9))
    small = float(spec.get("size", 0.66))
    angle = float(spec.get("angle", -2.0))
    to = spec.get("to")
    moving = frames_of(to, w, h, fps, float(spec.get("from", 0)), max(0.1, d - lift_a)) if to else None
    border = max(4, int(min(w, h) * 0.018))
    wr = Writer(out, w, h, fps)
    try:
        for i in range(max(1, round(d * fps))):
            t = i / fps
            lift = _ease((t - lift_a) / lift_d)
            if moving is not None and t >= lift_a:
                pic = next(moving, full)
                mix = _ease((t - lift_a) / (lift_d * 0.7))
                content = (full * (1 - mix) + pic * mix).astype(np.uint8)
            else:
                content = full
            # the scan: a line of light running down the print, brightening what it passes
            if t < lift_a + 0.2:
                y = (t - scan_a) / scan_d
                if -0.1 < y < 1.15:
                    rows = np.arange(h, dtype=np.float32)[:, None] / h
                    band = np.exp(-((rows - y) / 0.035) ** 2)[..., None]
                    passed = np.clip((y - rows) / 0.05, 0, 1)[..., None] * 0.06
                    core = np.exp(-((rows - y) / 0.004) ** 2)[..., None]
                    c = content.astype(np.float32)
                    c = c * (1 + passed) + band * 70 + core * 180
                    content = np.clip(c, 0, 255).astype(np.uint8)
            sc_ = small + (1 - small) * lift
            ang = angle * (1 - lift)
            bw = int(border * (1 - lift))
            pw, ph = max(2, round(w * sc_)), max(2, round(h * sc_))
            card = Image.fromarray(content).resize((pw, ph), Image.BICUBIC).convert("RGBA")
            if bw > 0:
                framed = Image.new("RGBA", (pw + bw * 2, ph + bw * 2), IVORY + (255,))
                framed.paste(card, (bw, bw))
                card = framed
            if lift < 0.999:
                card = card.rotate(ang, resample=Image.BICUBIC, expand=True)
                card, pad = _shadowed(card, max(2, int(min(w, h) * 0.02 * (1 - lift))), int(min(w, h) * 0.012 * (1 - lift)))
                frame = _paste(back if lift < 0.01 else (back * (1 - lift)).astype(np.uint8), card,
                               (round((w - card.width) / 2), round((h - card.height) / 2)))
            else:
                frame = content
            wr.put(frame)
    finally:
        wr.close()


def _rounded(img: Image.Image, r: int) -> Image.Image:
    m = Image.new("L", img.size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, img.width - 1, img.height - 1], radius=r, fill=255)
    img = img.convert("RGBA")
    img.putalpha(m)
    return img


def _wrap(draw, text: str, font, width: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        trial = (cur + " " + word).strip()
        if draw.textlength(trial, font=font) <= width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    return lines + ([cur] if cur else [])


def _card(sc: dict, d: float, w: int, h: int, fps: float, out: Path) -> None:
    spec = sc["card"] if isinstance(sc["card"], dict) else {}
    vertical = h > w
    side = spec.get("side", "left")
    angle = float(spec.get("angle", -4 if side == "left" else 4))
    text = str(spec.get("text") or sc.get("text") or "")
    back = _backdrop(sc, w, h)
    paper = bool(spec.get("paper"))
    fg = INK if paper else IVORY
    accent = _rgb(sc.get("_accent"), DEEP_BLUE)
    if vertical:
        cw = int(w * 0.8)
        ch = int(cw * 1.1)
        cx, cy = w / 2, h * 0.36
        tbox = (int(w * 0.1), int(h * 0.66), int(w * 0.8), int(h * 0.26))
    else:
        cw = int(w * 0.5)
        ch = int(cw * 0.62)
        cx = w * (0.32 if side == "left" else 0.68)
        cy = h / 2
        tx = int(w * 0.6) if side == "left" else int(w * 0.07)
        tbox = (tx, int(h * 0.2), int(w * 0.33), int(h * 0.6))
    from_full = bool(spec.get("from_full"))
    shrink = float(spec.get("shrink", 0.9))
    r = int(min(cw, ch) * 0.045)
    src = frames_of(sc["file"], cw, ch, fps, float(sc.get("from", 0)), d) if not from_full else None
    full_src = frames_of(sc["file"], w, h, fps, float(sc.get("from", 0)), d) if from_full else None
    # the words, laid out once
    size = int(min(w, h) * float(spec.get("size", 0.058 if not vertical else 0.08)))
    f = _font(sc, "heading", size)
    tl = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    td = ImageDraw.Draw(tl)
    lines = _wrap(td, text, f, tbox[2])
    lh = int(size * 1.18)
    y0 = tbox[1] + max(0, (tbox[3] - lh * len(lines)) // 2) if not vertical else tbox[1]
    for k, line in enumerate(lines):
        td.text((tbox[0], y0 + k * lh), line, font=f, fill=fg + (255,))
    if lines:
        td.rectangle([tbox[0], y0 - size * 0.55, tbox[0] + size * 1.2, y0 - size * 0.55 + max(3, size // 12)], fill=accent + (255,))
    wr = Writer(out, w, h, fps)
    try:
        for i in range(max(1, round(d * fps))):
            t = i / fps
            if from_full:
                fr = next(full_src)
                p = _ease(t / shrink)
            else:
                fr = next(src)
                p = 1.0
            if p < 1.0:  # shrinking from full screen into the card
                rw, rh = w + (cw - w) * p, h + (ch - h) * p
                px, py = w / 2 + (cx - w / 2) * p, h / 2 + (cy - h / 2) * p
                pic = Image.fromarray(cover(fr, max(2, round(rw)), max(2, round(rh))))
                pic = _rounded(pic, int(r * p))
                pic = pic.rotate(angle * p, resample=Image.BICUBIC, expand=True)
                frame = (back.astype(np.float32) * p).astype(np.uint8)
                if p > 0.05:
                    pic, pad = _shadowed(pic, max(2, int(min(w, h) * 0.02 * p)), int(min(w, h) * 0.014 * p))
                frame = _paste(frame, pic, (round(px - pic.width / 2), round(py - pic.height / 2)))
            else:
                pic = Image.fromarray(fr if not from_full else cover(fr, cw, ch))
                if pic.size != (cw, ch):
                    pic = Image.fromarray(cover(np.asarray(pic), cw, ch))
                pic = _rounded(pic, r).rotate(angle, resample=Image.BICUBIC, expand=True)
                pic, pad = _shadowed(pic, max(2, int(min(w, h) * 0.02)), int(min(w, h) * 0.014))
                frame = _paste(back, pic, (round(cx - pic.width / 2), round(cy - pic.height / 2)))
            # words arrive after the card has settled
            q = _ease((t - (shrink if from_full else 0.0) - 0.15) / 0.5)
            if q > 0 and lines:
                words = tl if q >= 1 else Image.fromarray(np.dstack([np.asarray(tl)[..., :3], (np.asarray(tl)[..., 3] * q).astype(np.uint8)]))
                frame = _paste(frame, words, (0, round(size * 0.4 * (1 - q))))
            wr.put(frame)
    finally:
        wr.close()


# ---------------------------------------------------------------- a still brought to life

ALIVE = ("rain", "clouds", "ripples", "depth", "snow", "mist")


def _blur(a: np.ndarray, r: int) -> np.ndarray:
    img = Image.fromarray(np.clip(a * 255, 0, 255).astype(np.uint8))
    return np.asarray(img.filter(ImageFilter.GaussianBlur(r)), np.float32) / 255


def _sample(img: np.ndarray, mx: np.ndarray, my: np.ndarray) -> np.ndarray:
    """Bilinear lookup of img at (mx, my), edges clamped."""
    h, w = img.shape[:2]
    mx = np.clip(mx, 0, w - 1.001)
    my = np.clip(my, 0, h - 1.001)
    x0, y0 = mx.astype(np.int32), my.astype(np.int32)
    fx, fy = (mx - x0)[..., None], (my - y0)[..., None]
    a, b = img[y0, x0], img[y0, x0 + 1]
    c, d = img[y0 + 1, x0], img[y0 + 1, x0 + 1]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def horizon(img: np.ndarray) -> float:
    """Where the land (or water) meets the sky, as a fraction down the picture (measured:
    the row where the picture turns from smooth and bright above to busy or dark below)."""
    h, w = img.shape[:2]
    f = img.astype(np.float32).mean(axis=2) / 255
    gy, gx = np.gradient(f)
    det = np.hypot(gx, gy).mean(axis=1)
    lum = f.mean(axis=1)
    k = max(4, h // 30)
    best, at = -1e9, 0.5
    for y in range(int(h * 0.2), int(h * 0.82)):
        score = (lum[max(0, y - k):y].mean() - lum[y:y + k].mean()) * 1.0 + (det[y:y + k].mean() - det[max(0, y - k):y].mean()) * 6
        if score > best:
            best, at = score, y / h
    return at


def masks(img: np.ndarray, sky_to: float | None = None, water_from: float | None = None):
    """Measured guesses of where the sky, the water and the near ground are (0..1 each).
    The sky is above the horizon, the water (when asked for) below it; nearer is lower and
    busier. `sky_to` / `water_from` (fractions down the picture) overrule the guess."""
    h, w = img.shape[:2]
    f = img.astype(np.float32) / 255
    lum = f.mean(axis=2)
    gy, gx = np.gradient(lum)
    detail = _blur(np.clip(np.hypot(gx, gy) * 12, 0, 1), max(2, min(w, h) // 60))
    rows = np.linspace(0, 1, h, dtype=np.float32)[:, None] * np.ones((1, w), np.float32)
    hz = horizon(img)
    top = float(sky_to) if sky_to is not None else hz
    low = float(water_from) if water_from is not None else hz
    soft = 0.03
    sky = _blur(np.clip((top - soft - rows) / soft, 0, 1) * np.clip(1.25 - detail * 2.2, 0.1, 1), max(3, min(w, h) // 60))
    water = _blur(np.clip((rows - low - soft) / soft, 0, 1) * np.clip(1.3 - detail * 2.5, 0, 1), max(3, min(w, h) // 60))
    near = _blur(np.clip(np.clip((rows - top) / max(0.05, 1 - top), 0, 1) * 0.85 + detail * 0.4, 0, 1), max(4, min(w, h) // 25))
    return sky, water, near


def _alive(sc: dict, d: float, w: int, h: int, fps: float, out: Path) -> None:
    want = sc["alive"]
    want = {k: 1.0 for k in ([want] if isinstance(want, str) else want)} if not isinstance(want, dict) else {k: float(v) for k, v in want.items()}
    src = np.asarray(Image.open(sc["file"]).convert("RGB")) if _still(sc["file"]) else next(frames_of(sc["file"], w, h, fps, float(sc.get("from", 0)), 0.05))
    m = 1.08 if "depth" in want else 1.0  # a little room round the edges for the camera to move
    big = cover(src, round(w * m), round(h * m)).astype(np.float32)
    BH, BW = big.shape[:2]
    sky, water, near = masks(big.astype(np.uint8), sc.get("sky_to"), sc.get("water_from"))
    gy, gx = np.mgrid[0:h, 0:w].astype(np.float32)
    ox, oy = (BW - w) / 2, (BH - h) / 2
    rng = np.random.default_rng(int(sc.get("_k", 0)) + 17)
    drops = rng.random((int(260 * want.get("rain", 0) * w * h / (1080 * 1920)) + 1, 4))
    flakes = rng.random((int(180 * want.get("snow", 0) * w * h / (1080 * 1920)) + 1, 4))
    mist = _blur(rng.random((h // 8 + 1, w // 4 + 1)).astype(np.float32), 2) if "mist" in want else None
    move = sc.get("camera_move", "in")
    n = max(1, round(d * fps))
    wr = Writer(out, w, h, fps)
    try:
        for i in range(n):
            t = i / fps
            u = i / max(1, n - 1)
            mx, my = gx + ox, gy + oy
            if "depth" in want:
                a = want["depth"]
                nz = _sample(near[..., None], mx, my)[..., 0]
                zoom = 1 + 0.05 * a * _ease(u) * (0.4 + 0.6 * nz) * (1 if move == "in" else -1)
                pan = (u - 0.5) * 0.035 * a * w * (0.3 + 0.7 * nz) * (1 if move != "left" else -1)
                cx, cy = BW / 2, BH / 2
                mx = cx + (mx - cx) / zoom - pan
                my = cy + (my - cy) / zoom
            if "ripples" in want:
                a = want["ripples"]
                wm = _sample(water[..., None], mx, my)[..., 0]
                depth_y = np.clip((my / BH - 0.45) * 2, 0.1, 1.2)
                dx = np.sin(my / (6 + 24 * depth_y) * 2.2 - t * 3.1) * 2.2 * a * depth_y
                dy = np.sin(mx / (40 + 90 * depth_y) + my / 9 - t * 2.3) * 1.6 * a * depth_y
                mx, my = mx + dx * wm, my + dy * wm
            frame = _sample(big, mx, my)
            if "clouds" in want:
                a = want["clouds"]
                sm = _sample(sky[..., None], mx, my)
                shift = t * 0.012 * w * a + 0.5
                drift = _sample(big, np.abs(((mx - shift) + BW) % (2 * BW) - BW) % BW, my)  # mirrored, so no seam
                frame = frame * (1 - sm) + drift * sm
            if mist is not None:
                a = want["mist"]
                mm = np.asarray(Image.fromarray((mist * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC), np.float32) / 255
                mm = np.roll(mm, int(t * w * 0.02), axis=1)[..., None]
                frame = frame * (1 - 0.25 * a * mm) + 235 * 0.25 * a * mm
            if "rain" in want or "snow" in want:
                layer = Image.new("L", (w, h), 0)
                dr = ImageDraw.Draw(layer)
                if "rain" in want:
                    frame = frame * (1 - 0.1 * want["rain"])
                    L = min(w, h) * 0.05
                    for x0, y0, sp, ln in drops:
                        y = (y0 + t * (1.4 + sp)) % 1.2 - 0.1
                        x = (x0 + y * 0.12) % 1.0
                        dr.line([(x * w, y * h), (x * w + L * 0.12 * ln, y * h + L * (0.6 + ln))], fill=int(90 + 80 * sp),
                                width=max(1, w // 700))
                if "snow" in want:
                    for x0, y0, sp, sz in flakes:
                        y = (y0 + t * (0.08 + 0.1 * sp)) % 1.1 - 0.05
                        x = (x0 + 0.02 * math.sin(t * 1.3 + sp * 9)) % 1.0
                        r = max(1.0, min(w, h) * 0.003 * (0.5 + sz))
                        dr.ellipse([x * w - r, y * h - r, x * w + r, y * h + r], fill=int(170 + 70 * sp))
                rain = np.asarray(layer.filter(ImageFilter.GaussianBlur(0.6)), np.float32)[..., None] / 255
                frame = frame * (1 - rain * 0.8) + 238 * rain * 0.8
            wr.put(np.clip(frame, 0, 255).astype(np.uint8))
    finally:
        wr.close()


# ---------------------------------------------------------------- checking a storyboard's settings

def problems(sc: dict, i: int, base: Path) -> list[str]:
    """What is wrong with a scene's effects, in plain words; resolves the files they name."""
    out, n = [], f"scene {i + 1}"
    st = sc.get("stamp")
    for s in (st if isinstance(st, list) else [st] if st else []):
        if not str((s.get("text") if isinstance(s, dict) else s) or "").strip():
            out.append(f"{n}: a stamp needs \"text\" (a word or two)")
    if sc.get("strike") is not None:
        s = sc["strike"]
        if not (isinstance(s, dict) and str(s.get("old", "")).strip() and str(s.get("new", "")).strip()):
            out.append(f"{n}: strike needs {{\"old\": word, \"new\": word}}")
    if sc.get("notes") is not None:
        if not isinstance(sc["notes"], list):
            out.append(f"{n}: notes is a list of {{\"kind\", \"x\", \"y\", ...}}")
        else:
            for k, x in enumerate(sc["notes"]):
                if not isinstance(x, dict) or x.get("kind", "underline") not in NOTE_KINDS:
                    out.append(f"{n}: note {k + 1}: kind is one of {', '.join(NOTE_KINDS)}")
                elif x.get("kind") == "note" and not (x.get("text") and x.get("to")):
                    out.append(f"{n}: note {k + 1}: a note needs \"text\" and \"to\" (where its arrow points)")
    pic = [k for k in ("scan_lift", "card", "alive") if sc.get(k)]
    if pic and sc.get("type") not in ("clip", "image"):
        out.append(f"{n}: {pic[0]} works on a clip or image scene")
    if len(pic) > 1:
        out.append(f"{n}: use one of scan_lift, card and alive in a scene, not {' and '.join(pic)}")
    if sc.get("scan_lift"):
        s = sc["scan_lift"] if isinstance(sc["scan_lift"], dict) else {"to": sc["scan_lift"]}
        if s.get("to"):
            f = str((base / s["to"]).resolve()) if not Path(s["to"]).is_absolute() else s["to"]
            s["to"] = f
            sc["scan_lift"] = s
            if not Path(f).exists():
                out.append(f"{n}: scan_lift: {f} not found")
    if sc.get("alive"):
        a = sc["alive"]
        names = [a] if isinstance(a, str) else list(a)
        bad = [x for x in names if x not in ALIVE]
        if bad:
            out.append(f"{n}: alive: {', '.join(map(str, bad))}: choose from {', '.join(ALIVE)}")
    return out
