"""The light editorial page, and prints that drop onto it.

A page scene (`"page": {...}` on a clip, image, title or text scene) is an
ivory sheet: the words on one side in a serif, with the words marked *like
this* in italic and in the video's accent colour, a small spaced label at the
top ("MAC", "STEP 2"), an optional note under the words with a hand-drawn
underline, and the picture (still or moving) as a card with a soft shadow on
the other side. A words-only page sets the words larger. Colours come from the
video: the accent marks the stressed words; the page is ivory and the type ink.

A drop (`"drop": true` on an image or clip scene) lays the picture as a print
with a white border onto the page: it falls in at the scene's start (so it
lands on the beat when scene changes follow the music) with a small settle,
and the prints of the drop scenes just before it stay where they landed, so
they pile up."""

from __future__ import annotations

import math
import re
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .motion import (DEEP_BLUE, INK, IVORY, Layer, Writer, _ease, _ease_out, _paste, _rgb, _rounded, _shadowed,
                     _stroke, _wobble, cover, frames_of)
from .style import FONTS

MUTED = (118, 114, 106)


def paper(w: int, h: int, seed: int = 3) -> np.ndarray:
    """A flat warm ivory sheet with the faintest grain."""
    rng = np.random.default_rng(seed)
    base = np.full((h, w, 3), (246, 242, 234), np.float32)
    small = rng.normal(0, 1, (max(2, h // 60), max(2, w // 60))).astype(np.float32)
    blot = np.asarray(Image.fromarray(((small - small.min()) / (np.ptp(small) + 1e-6) * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC), np.float32)
    base -= (blot[..., None] / 255 - 0.5) * 2
    base += rng.normal(0, 1.0, (h, w, 1)).astype(np.float32)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    edge = ((xx / w - 0.5) ** 2 + (yy / h - 0.5) ** 2) * 2
    base *= (1 - 0.02 * edge)[..., None]
    return np.clip(base, 0, 255).astype(np.uint8)


def _fonts(sc: dict, size: int):
    """(upright serif, italic serif, label, hand) for this scene: the brand heading first."""
    fonts = sc.get("_fonts") or {}

    def load(*names):
        for f in names:
            if f and Path(f).exists():
                try:
                    return ImageFont.truetype(str(f), max(6, int(size)))
                except OSError:
                    continue
        return ImageFont.load_default()

    up = load(fonts.get("heading") if str(fonts.get("heading", "")).lower().endswith((".ttf", ".otf")) else None,
              FONTS / "LibreBaskerville-Regular.ttf")
    it = load(FONTS / "InstrumentSerif-Italic.ttf")
    return up, it


def _runs(text: str) -> list[tuple[str, bool]]:
    """Words, each with whether it is stressed (*marked*)."""
    out, on = [], False
    for tok in re.findall(r"\*|[^\s*]+|\s+", text):
        if tok == "*":
            on = not on
        elif not tok.isspace():
            out.append((tok, on))
    return out


def _lay(draw, runs, up, it, width: int) -> list[list[tuple[str, bool, float]]]:
    """Break the words into lines no wider than `width`; each word with its x."""
    lines, cur, x = [], [], 0.0
    sp = draw.textlength(" ", font=up)
    for word, stress in runs:
        f = it if stress else up
        wl = draw.textlength(word, font=f)
        if cur and x + sp + wl > width:
            lines.append(cur)
            cur, x = [], 0.0
        if cur:
            x += sp
        cur.append((word, stress, x))
        x += wl
    return lines + ([cur] if cur else [])


LAND = 0.3  # seconds a word takes to land
EXIT = 0.38  # seconds the words take to leave before a page cuts to the next page
HOLD = 0.9  # every word is on the page at least this long before the scene ends


def is_page(sc: dict) -> bool:
    return isinstance(sc.get("page"), dict) and sc.get("type") in ("clip", "image", "title", "text")


def is_full(sc: dict) -> bool:
    """A page title over full-screen footage (the page's serif on the picture itself)."""
    return is_page(sc) and bool(sc["page"].get("full")) and bool(sc.get("file"))


def words_of(sc: dict) -> list[str]:
    spec = sc["page"] if isinstance(sc.get("page"), dict) else {}
    return [w for w, _ in _runs(str(spec.get("text") or sc.get("text") or ""))]


def land_times(n: int, length: float, heard: list[float] | None = None) -> list[float]:
    """When each word lands, in seconds from the scene's start: on the voice where it
    was heard, else quickly one after another; always all down with time to read."""
    if n <= 0:
        return []
    if heard and len(heard) == n:
        ts = [max(0.05, float(x)) for x in heard]
    else:
        ts = [0.12 + 0.085 * k for k in range(n)]
    last = max(0.15, length - HOLD - LAND)
    if ts[-1] > last:  # squeeze them in so the last word still sits long enough to be read
        a = min(ts[0], last * 0.4)
        span = max(1e-3, ts[-1] - ts[0])
        ts = [a + (t - ts[0]) * (last - a) / span for t in ts]
    return [round(t, 3) for t in ts]


def plan(scenes: list[dict], sb: dict) -> list[str]:
    """How pages meet. Two page scenes in a row never dissolve (their words would
    overlap): the words leave, then the next ones land, joined by a plain cut; the
    same picture on the same side stays put; a full-screen page title shrinks into
    the next page's card, and a card grows to full screen before a full title.
    A title over footage in a video of pages takes the page's serif too."""
    notes = []
    if any(is_page(s) for s in scenes) and sb.get("page_titles", True):
        for i, sc in enumerate(scenes):
            if sc["type"] == "title" and sc.get("file") and "page" not in sc and sc.get("text"):
                sc["page"] = {"full": True}
                notes.append(f"scene {i + 1}: the title is set in the page's serif over its footage (\"page_titles\": false keeps the bold title)")
    for k in range(len(scenes) - 1):
        a, b = scenes[k], scenes[k + 1]
        if not (is_page(a) and is_page(b)) or b.get("transition") not in (None, "cut"):
            continue
        b["transition"] = "cut"
        a["_exit"] = True
        pa, pb = a["page"], b["page"]
        if is_full(a) and b.get("file") and not is_full(b):
            b["_from_full"] = True
        elif is_full(b) and a.get("file") and not is_full(a):
            a["_to_full"] = True
        elif a.get("file") and a.get("file") == b.get("file") and pa.get("side", "right") == pb.get("side", "right") \
                and not is_full(a):
            a["_keep_card"], b["_card_stays"] = True, True
    return notes


PAGE = (246, 242, 234)  # the page: a flat warm ivory
CARD = (255, 254, 251)  # cards: a whiter ivory


def _font(path: Path, size: float, axes: list | None = None):
    try:
        f = ImageFont.truetype(str(path), max(6, int(size)))
        if axes:
            try:
                f.set_variation_by_axes(axes)
            except (OSError, ValueError):
                pass
        return f
    except OSError:
        return None


def _faces(sc: dict, size: float):
    """(upright, italic) serif for the page: the brand heading font first, else Newsreader, else Libre Baskerville."""
    from .style import FONTS as F

    studio = Path(__file__).parent / "studio_fonts"
    fonts = sc.get("_fonts") or {}
    head = fonts.get("heading") if str(fonts.get("heading", "")).lower().endswith((".ttf", ".otf")) else None
    up = (_font(Path(head), size) if head and Path(head).exists() else None) or \
        _font(studio / "Newsreader-normal.woff2", size, [400, 72]) or _font(F / "LibreBaskerville-Regular.ttf", size)
    it = _font(studio / "Newsreader-italic.woff2", size, [72]) or _font(F / "InstrumentSerif-Italic.ttf", size * 1.1)
    return up or ImageFont.load_default(), it or up or ImageFont.load_default()


def _sans(size: float):
    studio = Path(__file__).parent / "studio_fonts"
    return _font(studio / "HankenGrotesk-normal.woff2", size, [500]) or _font(FONTS / "Inter-SemiBold.otf", size) \
        or ImageFont.load_default()


def _lines(draw, text: str, up, it, width: float) -> list[list[tuple[str, bool, float]]]:
    """Lines of (word, stressed, x): a line break where the text has one ("\n"), a new line after a
    sentence once the line is a good length, else wrapped at `width`."""
    out = []
    on = False
    for para in text.split("\n"):
        if on:  # a *stress* left open runs on into the next line
            para = "*" + para
        runs = _runs(para)
        on = para.count("*") % 2 == 1
        out += _para(draw, runs, up, it, width)
    return out


def _para(draw, runs, up, it, width: float) -> list[list[tuple[str, bool, float]]]:
    sp = draw.textlength(" ", font=up)
    lines, cur, x = [], [], 0.0
    for k, (word, stress) in enumerate(runs):
        f = it if stress else up
        wl = draw.textlength(word, font=f)
        if cur and x + sp + wl > width:
            lines.append(cur)
            cur, x = [], 0.0
        if cur:
            x += sp
        cur.append((word, stress, x))
        x += wl
        if re.search(r"[.?!…:]$", word) and k + 1 < len(runs) and x > width * 0.4:  # a sentence ends: the next starts a line
            lines.append(cur)
            cur, x = [], 0.0
    return [ln for ln in lines + [cur] if ln]


def _words_layer(sc: dict, text: str, x0: float, y0: float, size: float, width: float, ink, accent, lead: float = 1.08):
    """Every word as its own image (so each can land on its own), where each sits, and the block's bottom."""
    up, it = _faces(sc, size)
    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    out = []
    lh = size * lead
    lines = _lines(probe, text, up, it, width)
    for k, line in enumerate(lines):
        for word, stress, x in line:
            f = it if stress else up
            img = Image.new("RGBA", (int(probe.textlength(word, font=f) + size * 0.4), int(size * 1.5)), (0, 0, 0, 0))
            ImageDraw.Draw(img).text((int(size * 0.1), int(size * 0.15)), word, font=f, fill=(accent if stress else ink) + (255,))
            out.append((img, (int(x0 + x - size * 0.1), int(y0 + k * lh - size * 0.15))))
    return out, y0 + len(lines) * lh


def _note(sc, text: str, x: float, y: float, size: float, accent) -> tuple[Image.Image, list, float]:
    _, it = _faces(sc, size)
    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    tw = probe.textlength(text, font=it)
    img = Image.new("RGBA", (int(tw + size), int(size * 1.6)), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((0, int(size * 0.15)), text, font=it, fill=accent + (255,))
    rng = np.random.default_rng(len(text))
    base = y + size * 1.45
    line = _wobble([(x - size * 0.05, base), (x + tw * 0.55, base - size * 0.1), (x + tw + size * 0.25, base + size * 0.02)],
                   size * 0.04, rng, 10)
    return img, line, tw


def _fade(img: Image.Image, q: float) -> Image.Image:
    if q >= 1:
        return img
    a = np.asarray(img).copy()
    a[..., 3] = (a[..., 3] * max(0.0, q)).astype(np.uint8)
    return Image.fromarray(a)


def _back(x: float) -> float:
    """Ease out with a small overshoot: the word lands with a little weight."""
    x = min(1.0, max(0.0, x))
    c = 1.4
    return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2


def _camera(frame: np.ndarray, z: float, fx: float, fy: float, keep: tuple[float, float, float, float] | None = None) -> np.ndarray:
    """Look closer (z > 1) toward the point fx, fy (0 to 1 of the frame), never
    losing the `keep` box (the words and their label), in pixels."""
    h, w = frame.shape[:2]
    if keep:
        z = min(z, w / max(1.0, keep[2] - keep[0]), h / max(1.0, keep[3] - keep[1]))
    if z <= 1.0005:
        return frame
    cw, ch = w / z, h / z
    x0 = min(max(0.0, fx * w - cw / 2), w - cw)
    y0 = min(max(0.0, fy * h - ch / 2), h - ch)
    if keep:  # slide the view so the words stay whole
        x0 = min(max(x0, keep[2] - cw), keep[0])
        y0 = min(max(y0, keep[3] - ch), keep[1])
        x0, y0 = min(max(0.0, x0), w - cw), min(max(0.0, y0), h - ch)
    return np.asarray(Image.fromarray(frame).resize((w, h), Image.BICUBIC, box=(x0, y0, x0 + cw, y0 + ch)))


def _overlays(sc: dict):
    from .motion import _notes_layer, _stamp_at, _strike_layer

    specs = []
    for s in (sc["stamp"] if isinstance(sc.get("stamp"), list) else [sc.get("stamp")] if sc.get("stamp") else []):
        specs.append((_stamp_at, {"text": s} if isinstance(s, str) else s))
    if sc.get("strike"):
        specs.append((_strike_layer, sc["strike"]))
    if sc.get("notes"):
        specs.append((_notes_layer, list(sc["notes"])))
    return specs


def _focus(sc: dict) -> list[tuple[float, float, float]]:
    """Where the camera looks, and from when: what is circled, pointed at or stamped, as it appears."""
    out = []
    for n in sc.get("notes") or []:
        if isinstance(n, dict):
            x, y = float(n.get("x", 0.5)), float(n.get("y", 0.5))
            if n.get("kind") == "arrow" and isinstance(n.get("to"), (list, tuple)) and len(n["to"]) == 2:
                x, y = float(n["to"][0]), float(n["to"][1])
            out.append((float(n.get("at", 0.5)), x, y))
    st = sc.get("stamp")
    for s in (st if isinstance(st, list) else [st] if isinstance(st, dict) else []):
        if isinstance(s, dict):
            out.append((float(s.get("at", 0.4)), float(s.get("x", 0.5)), float(s.get("y", 0.5))))
    out.sort()
    return out


def screenish(img: np.ndarray) -> bool:
    """A screen (a page, a window, a terminal) rather than a photo: large areas of exactly one colour.
    A measurement, not a recognition: set "screen" on the scene when it guesses wrong."""
    small = np.asarray(Image.fromarray(img).resize((96, 54), Image.NEAREST)) // 12
    keys = small[..., 0].astype(np.int32) * 10000 + small[..., 1].astype(np.int32) * 100 + small[..., 2]
    _, counts = np.unique(keys, return_counts=True)
    return counts.max() / keys.size > 0.22


def tone(img: np.ndarray) -> np.ndarray:
    """A photo toned to the page: warm sepia, lifted a little, so it sits on ivory like a print."""
    f = img.astype(np.float32) / 255
    y = (0.299 * f[..., 0] + 0.587 * f[..., 1] + 0.114 * f[..., 2])[..., None]
    y = 0.1 + 0.85 * y
    lo, hi = np.array([46, 38, 30], np.float32) / 255, np.array([245, 238, 224], np.float32) / 255
    sep = lo + (hi - lo) * y
    out = sep * 0.88 + f * 0.12
    return (np.clip(out, 0, 1) * 255).astype(np.uint8)


def _card_image(pic: np.ndarray, cw: int, ch: int, r: int, toned: bool) -> Image.Image:
    pic = cover(pic, cw, ch) if pic.shape[1] != cw or pic.shape[0] != ch else pic
    if toned:
        pic = tone(pic)
    return _rounded(Image.fromarray(pic), r)


def _chip(text: str, size: float) -> Image.Image:
    f = _sans(size)
    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    tw = probe.textlength(text, font=f)
    pw, ph = int(tw + size * 2), int(size * 2.2)
    img = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, pw - 1, ph - 1], radius=ph // 2, fill=CARD + (255,))
    d.text((size, size * 0.55), text, font=f, fill=INK + (255,))
    sh, _ = _shadowed(img, max(2, int(size * 0.5)), int(size * 0.25), 0.16)
    return sh


def _doodle(name: str, size: float, colour) -> Image.Image:
    from .pictures import draw_icon

    img = Image.new("RGBA", (int(size * 1.3), int(size * 1.3)), (0, 0, 0, 0))
    draw_icon(img, name, img.width / 2, img.height / 2, size, colour + (255,), width=1.7, rough=True, seed=len(name))
    return img


def _wipe(img: Image.Image, q: float) -> Image.Image:
    """Drawn on from the left, like a pen."""
    if q >= 1:
        return img
    a = np.asarray(img).copy()
    a[:, int(a.shape[1] * max(0.0, q)):, 3] = 0
    return Image.fromarray(a)


def _arrow(x0: float, y0: float, x1: float, y1: float, s: float, rng) -> list:
    """A loose hand-drawn arrow from (x0, y0) to (x1, y1), with its head, as one stroke."""
    mx, my = (x0 + x1) / 2, max(y0, y1) + s * 0.4
    pts = []
    for k in range(25):
        t = k / 24
        pts.append(((1 - t) ** 2 * x0 + 2 * (1 - t) * t * mx + t * t * x1, (1 - t) ** 2 * y0 + 2 * (1 - t) * t * my + t * t * y1))
    ang = math.atan2(y1 - pts[-3][1], x1 - pts[-3][0])
    hl = s * 0.45
    head = [(x1 + hl * math.cos(ang + 2.6), y1 + hl * math.sin(ang + 2.6)), (x1, y1),
            (x1 + hl * math.cos(ang - 2.6), y1 + hl * math.sin(ang - 2.6))]
    return _wobble(pts, s * 0.03, rng, 2) + head


def page_scene(sc: dict, d: float, w: int, h: int, fps: float, out: Path) -> None:
    from .motion import _partial

    spec = sc["page"] if isinstance(sc.get("page"), dict) else {}
    vertical = h > w
    u = (w if vertical else h) / 1080  # one unit of the 1920 x 1080 page this was designed on
    m = min(w, h)
    full = is_full(sc)
    has_pic = bool(sc.get("file")) and sc.get("type") in ("clip", "image", "title", "text") and not full
    cards = [str(c) for c in (spec.get("cards") or [])][:3]
    if cards:
        has_pic = False
    side = spec.get("side", "right")
    left = side == "right" or vertical  # the words on the left, the picture on the right
    scale = float(spec.get("size", 1.0))
    L = float(sc.get("_len") or d)
    accent = _rgb(sc.get("_accent"), DEEP_BLUE)
    if sum(accent) > 600:  # an accent too pale for an ivory page: the deep blue instead
        accent = DEEP_BLUE
    back = np.full((h, w, 3), PAGE, np.uint8)
    back = (back.astype(np.float32) + np.random.default_rng(3).normal(0, 1.0, (h, w, 1))).clip(0, 255).astype(np.uint8)
    text = str(spec.get("text") if (cards or "text" in spec) else sc.get("text") or "")
    src = None
    first = None
    if has_pic or full:
        src = frames_of(sc["file"], w, h, fps, float(sc.get("from", 0)), d)
        first = next(src)
    # a photo is toned to the page and tilted a touch; a screen stays as it is
    if first is not None:
        scr = sc.get("screen")
        if scr is None:
            scr = (sc.get("type") == "clip" and sc.get("_howto")) or screenish(first)
        toned = spec.get("tone", "none" if scr else "page") == "page"
        angle = float(spec["angle"]) if "angle" in spec else (0.0 if scr else (1.5 if (sc.get("_k", 0) or 0) % 2 == 0 else -1.5))
    else:
        scr, toned, angle = True, False, 0.0
    # ---- where everything sits
    ink = INK
    if full:
        size = 96 * u * scale
        wx, wy, ww = 110 * u, 110 * u, (900 if not vertical else 860) * u
        probe_frame = tone(first) if toned else first
        lum = probe_frame[: int(h * 0.4), : int(w * 0.5)].mean() / 255
        light_words = lum < 0.5
        if light_words:
            ink, accent = IVORY, (accent if sum(accent) > 450 else IVORY)
        veil_col = (20, 18, 16) if light_words else (250, 246, 238)
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        veil = np.exp(-(((xx - w * 0.22) / (w * 0.42)) ** 2 + ((yy - h * 0.2) / (h * 0.42)) ** 2))[..., None] * 0.55
    elif cards:
        size = 64 * u * scale
        wx, wy, ww = 120 * u, 300 * u, 600 * u
    elif has_pic:
        size = 86 * u * scale
        wx = 120 * u if left else w - 120 * u - 600 * u
        wy, ww = (300 * u, 640 * u) if not vertical else (200 * u, 900 * u)
    else:
        size = 104 * u * scale
        wx, wy, ww = 120 * u, 300 * u, (1500 if not vertical else 860) * u
    words, bottom = ([], wy) if (cards and not text) else _words_layer(sc, text, wx, wy, size, ww, ink, accent,
                                                                       1.1 if full else 1.08)
    times = sc.get("_page_times")
    times = times if isinstance(times, list) and len(times) == len(words) else land_times(len(words), L)
    last_word = (times[-1] + LAND) if times else 0.3
    label = str(spec.get("label") or "").upper() if not full else ""
    if label:
        lf = _sans(22 * u)
        probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
        sp = 22 * u * 0.22
        lw = sum(probe.textlength(c, font=lf) + sp for c in label)
        limg = Image.new("RGBA", (int(lw + 10), int(40 * u)), (0, 0, 0, 0))
        dl, x = ImageDraw.Draw(limg), 0.0
        mute = tuple(int(PAGE[i] * 0.45 + INK[i] * 0.55) for i in range(3))
        for c in label:  # spaced capitals
            dl.text((x, 0), c, font=lf, fill=mute + (255,))
            x += probe.textlength(c, font=lf) + sp
        lpos = (int(120 * u if left or not has_pic else w - 120 * u - 600 * u), int(90 * u))
    note = str(spec.get("note") or "") if not full else ""
    # ---- the picture as a card
    card = None
    if has_pic:
        if vertical:
            cw = int(900 * u)
            cx0 = 90 * u
        else:
            cw = int(1040 * u)
            cx0 = 760 * u if left else w - 760 * u - cw
        ar = first.shape[1] / first.shape[0]
        from .media import video_size

        try:
            if str(sc["file"]).lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")):
                with Image.open(sc["file"]) as im:
                    ar = im.width / im.height
            elif (vs := video_size(sc["file"])):
                ar = vs[0] / vs[1]
        except OSError:
            pass
        ch = int(min(cw / ar, (720 if not vertical else 1000) * u))
        cw = int(min(cw, ch * ar)) // 2 * 2
        ch = ch // 2 * 2
        cy = (492 * u) if not vertical else (bottom + 120 * u + ch / 2)
        if vertical:
            cx = w / 2
        elif left:  # the card's near edge stays where the words end
            cx = 760 * u + cw / 2
        else:
            cx = w - 760 * u - cw / 2
        card = (cx, cy, cw, ch)
        r = max(2, int(14 * u))
        away = 1 if left else -1
        # the full frames, for a card that grows to (or shrinks from) the whole frame
        src = _chain(first, src)
    elif full:
        src = _chain(first, src)
    # ---- the extras
    if note:
        nsize = 54 * u * (0.8 if cards else 1.0)
        if cards:
            nx = (1060 + 50) * u if len(cards) == 2 else w / 2 - 200 * u
            ny = 760 * u
        else:
            nx, ny = wx + 6 * u, bottom + 0.35 * size
        nimg, nline, ntw = _note(sc, note, nx, ny, nsize, accent)
    t_note = last_word + 0.15 if not cards else 0.3 + 0.35 * len(cards) + 0.2
    doodle = None
    if spec.get("doodle"):
        ds = 130 * u
        try:
            doodle = _doodle(str(spec["doodle"]), ds, accent)
        except SystemExit:
            doodle = None
        if doodle is not None:
            if note:
                dpos = (int(nx + ntw + 40 * u), int(ny + nsize * 0.8 - doodle.height / 2))
            else:
                dpos = (int(wx + ww * 0.6), int(bottom + 10 * u))
    big = None
    bspec = spec.get("big")
    if bspec:
        bspec = bspec if isinstance(bspec, dict) else {"text": str(bspec)}
        _, bit = _faces(sc, 200 * u)
        probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
        bw = probe.textlength(str(bspec["text"]), font=bit)
        big = Image.new("RGBA", (int(bw + 80 * u), int(260 * u)), (0, 0, 0, 0))
        ImageDraw.Draw(big).text((20 * u, 10 * u), str(bspec["text"]), font=bit, fill=accent + (255,))
        bpos = (int(wx + ww * 0.62), int(bottom + 20 * u))
        t_big = float(bspec.get("at", last_word + 0.25))
    pill = None
    pspec = spec.get("pill")
    if pspec and card:
        pspec = pspec if isinstance(pspec, dict) else {"text": str(pspec)}
        pill = _chip(str(pspec["text"]), 28 * u)
        t_pill = float(pspec.get("at", 0.9))
    also = None
    aspec = spec.get("also")
    if aspec and card:
        aspec = aspec if isinstance(aspec, dict) else {"file": str(aspec)}
        aw = int(card[2] * 0.44) // 2 * 2
        try:
            aimg = frames_of(str(aspec["file"]), aw, int(aw * 9 / 16) // 2 * 2, fps, float(aspec.get("from", 0)), d)
            also = aimg
        except (OSError, KeyError):
            also = None
        t_also = float(aspec.get("at", t_note + 0.4))
        acx = card[0] + card[2] / 2 - aw / 2 + 30 * u * (1 if left else -1)
        acy = card[1] + card[3] / 2 - (aw * 9 / 16) / 2 + 60 * u
        atext = str(aspec.get("note") or "")
        if atext:
            aimg_note, _, atw = _note(sc, atext, 0, 0, 44 * u, accent)
            anx = acx - aw / 2 - atw - 220 * u
            any_ = acy + (aw * 9 / 16) / 2 - 40 * u
            arrow = _arrow(anx + atw + 20 * u, any_ + 40 * u, acx - aw / 2 - 20 * u, any_ + 10 * u, 60 * u,
                           np.random.default_rng(5))
    card_imgs = []
    if cards:
        n = len(cards)
        cw2, ch2 = int(620 * u if n == 2 else 520 * u), int(420 * u if n == 2 else 360 * u)
        gap = 200 * u if n == 2 else 110 * u
        total = n * cw2 + (n - 1) * gap
        x = (w - total) / 2
        up, _ = _faces(sc, 64 * u)
        plus_f, _ = _faces(sc, 90 * u)
        for k, c in enumerate(cards):
            img = Image.new("RGBA", (cw2, ch2), (0, 0, 0, 0))
            dc = ImageDraw.Draw(img)
            dc.rounded_rectangle([0, 0, cw2 - 1, ch2 - 1], radius=int(14 * u), fill=CARD + (255,))
            tw = dc.textlength(c, font=up)
            dc.text(((cw2 - tw) / 2, ch2 / 2 - 64 * u * 0.62), c, font=up, fill=INK + (255,))
            img, pad = _shadowed(img, max(2, int(36 * u)), int(24 * u), 0.2)
            card_imgs.append((img, (int(x - pad), int(300 * u - pad))))
            x += cw2 + gap
        join = str(spec.get("join", "+"))
        pimg = Image.new("RGBA", (int(160 * u), int(160 * u)), (0, 0, 0, 0))
        pw = ImageDraw.Draw(pimg).textlength(join, font=plus_f)
        ImageDraw.Draw(pimg).text(((pimg.width - pw) / 2, 10 * u), join, font=plus_f, fill=INK + (255,))
        joins = [(pimg, (int(card_imgs[k][1][0] + card_imgs[k][0].width - (card_imgs[k][0].width - cw2) / 2 + gap / 2 - pimg.width / 2),
                         int(300 * u + ch2 / 2 - 70 * u))) for k in range(n - 1)]
    # what the camera must never lose: the words, their label and their note
    kx0, ky0, kx1, ky1 = wx - 30 * u, wy - 30 * u, wx + ww + 30 * u, bottom + (110 * u if note else 30 * u)
    if label:
        kx0, ky0 = min(kx0, lpos[0] - 30 * u), min(ky0, lpos[1] - 20 * u)
    if cards:
        kx0, kx1, ky1 = min(kx0, card_imgs[0][1][0]), max(kx1, card_imgs[-1][1][0] + card_imgs[-1][0].width), 880 * u
    keep = (kx0, ky0, kx1, ky1)
    specs = _overlays(sc)
    caches = [dict() for _ in specs]
    held: list = [None] * len(specs)
    focus = _focus(sc)
    exit_at = L - EXIT if sc.get("_exit") else None
    moving = sc.get("camera", True) is not False
    wr = Writer(out, w, h, fps)
    try:
        for i in range(max(1, round(d * fps))):
            t = i / fps
            ex = _ease((t - exit_at) / EXIT) if exit_at is not None else 0.0  # 0 until the words leave, then 1
            slide = -60 * u * ex
            if full:
                f0 = next(src)
                if toned:
                    f0 = tone(f0)
                k = min(1.0, t / 0.4) * (1 - ex)
                frame = (f0.astype(np.float32) * (1 - veil * k) + np.array(veil_col, np.float32) * veil * k).astype(np.uint8)
                frame = _camera(frame, 1.0 + 0.04 * min(1.0, t / max(1.0, L)) * (1 - ex), 0.5, 0.5)
            else:
                frame = back
            if card:
                cx, cy, cw, ch = card
                raw = next(src)
                g = 0.0  # how much of the whole frame the card fills (1 = all of it)
                if sc.get("_from_full"):
                    g = 1 - _ease(t / 0.75)
                elif sc.get("_to_full") and exit_at is not None:
                    g = _ease((t - (L - 0.6)) / 0.6)
                tw_, th_ = round(cw + (w - cw) * g), round(ch + (h - ch) * g)
                pic = _card_image(raw, tw_, th_, round(r * (1 - g)), toned)
                rot = angle * (1 - g)
                if sc.get("_card_stays") or g > 0:
                    q, dx = 1.0, 0.0
                else:  # the card slides in from its side, turning and growing a touch as it settles
                    q = _ease_out(t / 0.7)
                    dx = 140 * u * away * (1 - q)
                    rot = angle * q
                    if q < 1:
                        pic = pic.resize((max(2, round(pic.width * (0.94 + 0.06 * q))), max(2, round(pic.height * (0.94 + 0.06 * q)))),
                                         Image.BICUBIC)
                leaving = ex and not sc.get("_keep_card") and not sc.get("_to_full")
                if leaving:
                    dx += 140 * u * away * ex
                if rot:
                    pic = pic.rotate(rot, resample=Image.BICUBIC, expand=True)
                pic, pad = _shadowed(pic, max(2, int(40 * u * (1 - g))) or 1, int(30 * u * (1 - g)), 0.22 * (1 - g))
                op = min(1.0, t / 0.25) if not (sc.get("_card_stays") or g > 0) else 1.0
                if leaving:
                    op *= 1 - ex
                ccx, ccy = cx + (w / 2 - cx) * g, cy + (h / 2 - cy) * g
                frame = _paste(frame, _fade(pic, op), (round(ccx + dx - pic.width / 2), round(ccy - pic.height / 2)))
                if also is not None:
                    araw = next(also)
                    qa = _ease_out((t - t_also) / 0.5)
                    if qa > 0:
                        ap = _card_image(araw, araw.shape[1], araw.shape[0], r, False)
                        ap, apad = _shadowed(ap, max(2, int(30 * u)), int(22 * u), 0.24)
                        frame = _paste(frame, _fade(ap, min(1.0, qa * 1.5) * (1 - (ex if leaving else 0))),
                                       (round(acx - ap.width / 2 + dx), round(acy - ap.height / 2 + 50 * u * (1 - qa))))
                        if atext:
                            frame = _paste(frame, _fade(aimg_note, min(1.0, qa * 1.5) * (1 - ex)), (round(anx + slide), round(any_)))
                            ua = _ease((t - t_also - 0.3) / 0.5)
                            if ua > 0:
                                lay = Layer(w, h)
                                _stroke(lay.draw, [(px * 2, py * 2) for px, py in _partial(arrow, ua)], max(2, int(5 * u)) * 2,
                                        accent + (255,))
                                frame = _paste(frame, _fade(lay.done(), 1 - ex), (0, 0))
                if pill is not None:
                    qp = _back((t - t_pill) / 0.35)
                    if t >= t_pill:
                        pim = pill if qp >= 0.999 else pill.resize((max(2, int(pill.width * (0.9 + 0.1 * qp))), max(2, int(pill.height * (0.9 + 0.1 * qp)))), Image.BICUBIC)
                        px_ = cx + cw / 2 - 40 * u - pim.width + dx
                        py_ = cy + ch / 2 - pim.height * 0.55
                        frame = _paste(frame, _fade(pim, min(1.0, (t - t_pill) / 0.2) * (1 - (ex if leaving else 0))), (round(px_), round(py_)))
            for k, (img, (x, y)) in enumerate(card_imgs):  # words on white cards, one after another, joined by "+"
                q = _ease_out((t - 0.15 - 0.35 * k) / 0.5)
                if q > 0:
                    frame = _paste(frame, _fade(img, min(1.0, q * 1.6) * (1 - ex)), (round(x + slide), round(y + 40 * u * (1 - q))))
                if k < len(card_imgs) - 1:
                    qj = _back((t - 0.35 - 0.35 * k) / 0.3)
                    if qj > 0:
                        pimg_, (jx, jy) = joins[k]
                        frame = _paste(frame, _fade(pimg_, min(1.0, qj) * (1 - ex)), (round(jx + slide), round(jy + 20 * u * (1 - qj))))
            if label:
                frame = _paste(frame, _fade(limg, min(1.0, t / 0.3) * (1 - ex)), (lpos[0] + round(slide), lpos[1]))
            for (img, (x, y)), tw in zip(words, times):  # each word lands when it is said
                q = (t - tw) / LAND
                if q <= 0:
                    continue
                frame = _paste(frame, _fade(img, min(1.0, q * 1.8) * (1 - ex)),
                               (round(x + (slide if not full else 0)), round(y + size * 0.3 * (1 - _back(q)) + (slide * 0.5 if full else 0))))
            if note:
                q = _ease((t - t_note) / 0.3)
                if q > 0:
                    frame = _paste(frame, _fade(nimg, min(1.0, q) * (1 - ex)), (round(nx + slide), round(ny)))
                    un = _ease((t - t_note - 0.2) / 0.45)
                    if un > 0 and ex < 1:
                        lay = Layer(w, h)
                        _stroke(lay.draw, [(px * 2 + slide * 2, py * 2) for px, py in _partial(nline, un)],
                                max(2, int(5 * u)) * 2, accent + (255,))
                        frame = _paste(frame, _fade(lay.done(), 1 - ex), (0, 0))
            if doodle is not None:
                qd = (t - t_note - 0.35) / 0.6
                if qd > 0:
                    frame = _paste(frame, _fade(_wipe(doodle, qd), 1 - ex), (round(dpos[0] + slide), dpos[1]))
            if big is not None and t >= t_big:  # the big italic lands like a stamp
                qb = _ease_out((t - t_big) / 0.3)
                sz = 1.6 - 0.6 * qb
                bi = big.resize((max(2, int(big.width * sz)), max(2, int(big.height * sz))), Image.BICUBIC)
                frame = _paste(frame, _fade(bi, min(1.0, (t - t_big) / 0.12) * (1 - ex)),
                               (round(bpos[0] + big.width / 2 - bi.width / 2 + slide), round(bpos[1] + big.height / 2 - bi.height / 2)))
            for j, (fn, sp) in enumerate(specs):  # stamps, strikes and notes, before the camera so they move with the page
                got = held[j] if held[j] is not None else fn(sc, sp, t, w, h, frame, caches[j])
                if got is not None and got[2]:
                    held[j] = got
                if got is not None:
                    frame = _paste(frame, _fade(got[0], 1 - ex) if ex else got[0], got[1])
            if moving and not full:
                # a gentle camera: a slow drift toward the card (closer on a screen), then over to whatever is
                # circled, pointed at or stamped as it appears; back out as the page leaves
                fx, fy = (card[0] / w, card[1] / h) if card else (0.5, 0.5)
                z = 1.0 + (0.06 if (card and scr) else 0.025) * _ease(t / max(1.0, L))
                for at, nx_, ny_ in focus:
                    p = _ease((t - at + 0.25) / 0.6)
                    if p > 0:
                        fx, fy = fx + (nx_ - fx) * p, fy + (ny_ - fy) * p
                        z = max(z, 1.0 + 0.08 * p)
                z = 1 + (z - 1) * (1 - ex)
                fx, fy = 0.5 + (fx - 0.5) * (1 - ex), 0.5 + (fy - 0.5) * (1 - ex)
                frame = _camera(frame, z, fx, fy, keep)
            wr.put(frame)
    finally:
        wr.close()


def _chain(first, rest):
    yield first
    yield from rest


# ---------------------------------------------------------------- prints that drop and pile up


def drop_spec(sc: dict, n: int) -> dict:
    """Where the n-th print of a run lands: given, or a loose pile around the middle."""
    v = sc.get("drop") if isinstance(sc.get("drop"), dict) else {}
    rng = np.random.default_rng(11 + 7 * n)
    return {"x": float(v.get("x", 0.5 + rng.uniform(-0.13, 0.13))), "y": float(v.get("y", 0.5 + rng.uniform(-0.08, 0.08))),
            "angle": float(v.get("angle", rng.uniform(-7, 7))), "size": float(v.get("size", 0.62)),
            "at": float(v.get("at", 0.0)), "border": float(v.get("border", 0.045))}


def _print(img: np.ndarray, border: float) -> Image.Image:
    """A photograph as a print: a white border round it."""
    h, w = img.shape[:2]
    b = max(2, int(min(w, h) * border))
    canvas = Image.new("RGB", (w + 2 * b, h + 2 * b), (252, 251, 247))
    canvas.paste(Image.fromarray(img), (b, b))
    return canvas.convert("RGBA")


def _print_size(f: str, w: int, h: int, size: float) -> tuple[int, int]:
    try:
        im = Image.open(f)
        ar = im.width / im.height
    except OSError:
        ar = 16 / 9
    ph = int(min(w, h) * size)
    pw = int(ph * ar)
    if pw > w * 0.8:
        pw = int(w * 0.8)
        ph = int(pw / ar)
    return pw // 2 * 2, ph // 2 * 2


def _placed(pr: Image.Image, spec: dict, w: int, h: int, m: int, lift: float = 0.0):
    """The print turned, shadowed (higher = softer and wider), and its top-left corner."""
    sc = 1 + 0.22 * lift
    img = pr.resize((max(2, int(pr.width * sc)), max(2, int(pr.height * sc))), Image.BICUBIC) if lift else pr
    img = img.rotate(spec["angle"] + 5 * lift, resample=Image.BICUBIC, expand=True)
    img, _ = _shadowed(img, max(2, int(m * (0.01 + 0.03 * lift))), int(m * (0.008 + 0.04 * lift)), 0.42 - 0.15 * lift)
    x = spec["x"] * w - img.width / 2
    y = spec["y"] * h - img.height / 2 - m * 0.05 * lift
    return img, (round(x), round(y))


def drop_scene(sc: dict, d: float, w: int, h: int, fps: float, out: Path) -> None:
    m = min(w, h)
    back = paper(w, h, 5)
    for n, (f, start, spec) in enumerate(sc.get("_pile") or []):  # the prints already there
        pw, ph = _print_size(f, w, h, spec["size"])
        still = next(frames_of(f, pw, ph, fps, start, 0.05))
        img, xy = _placed(_print(still, spec["border"]), spec, w, h, m)
        back = _paste(back, img, xy)
    spec = sc["_drop"]
    pw, ph = _print_size(sc["file"], w, h, spec["size"])
    src = frames_of(sc["file"], pw, ph, fps, float(sc.get("from", 0)), d)
    fall = 0.28
    wr = Writer(out, w, h, fps)
    try:
        for i in range(max(1, round(d * fps))):
            t = i / fps - spec["at"]
            fr = next(src)
            if t < 0:
                wr.put(back)
                continue
            p = min(1.0, t / fall)
            lift = (1 - _ease_out(p)) if p < 1 else max(0.0, 0.03 * math.sin((t - fall) * 30) * math.exp(-(t - fall) * 12))
            img, xy = _placed(_print(fr, spec["border"]), spec, w, h, m, lift)
            if p < 1:
                a = np.asarray(img).copy()
                a[..., 3] = (a[..., 3] * min(1.0, p * 3)).astype(np.uint8)
                img = Image.fromarray(a)
            wr.put(_paste(back, img, xy))
    finally:
        wr.close()


def piles(scenes: list[dict]) -> None:
    """Give each drop scene the prints of the drop scenes just before it, and a plain cut between them."""
    run: list = []
    for sc in scenes:
        if sc.get("drop") and sc.get("file") and sc.get("type") in ("image", "clip"):
            sc["_drop"] = drop_spec(sc, len(run))
            sc["_pile"] = [list(x) for x in run]
            if run and "transition" not in sc:
                sc["transition"] = "cut"
            run.append((sc["file"], float(sc.get("from", 0)) + 0.0, sc["_drop"]))
        else:
            run = []


def problems(sc: dict, i: int) -> list[str]:
    out = []
    pg = sc.get("page")
    if pg is not None:
        if not isinstance(pg, dict):
            out.append(f"scene {i + 1}: page is {{\"text\", \"label\", \"note\", \"side\"}}")
        elif sc.get("type") not in ("clip", "image", "title", "text"):
            out.append(f"scene {i + 1}: page works on a clip, image, title or text scene")
        elif pg.get("cards") is not None and not (isinstance(pg["cards"], list) and 1 <= len(pg["cards"]) <= 3):
            out.append(f"scene {i + 1}: page cards is a list of 1 to 3 short texts")
        elif not (pg.get("text") or sc.get("text") or pg.get("cards")):
            out.append(f"scene {i + 1}: page needs \"text\" (the words on the page; *word* for the stressed one)")
        elif pg.get("side") not in (None, "left", "right"):
            out.append(f"scene {i + 1}: page side is left or right (where the picture sits)")
    dr = sc.get("drop")
    if dr:
        if sc.get("type") not in ("clip", "image") or not sc.get("file"):
            out.append(f"scene {i + 1}: drop works on an image or clip scene with a file")
        elif not isinstance(dr, (bool, dict)):
            out.append(f"scene {i + 1}: drop is true, or {{\"x\", \"y\", \"angle\", \"size\", \"at\"}}")
    return out
