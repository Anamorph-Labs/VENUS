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
    """An ivory sheet: fine grain, a slow unevenness and a soft edge."""
    rng = np.random.default_rng(seed)
    base = np.full((h, w, 3), IVORY, np.float32)
    small = rng.normal(0, 1, (max(2, h // 60), max(2, w // 60))).astype(np.float32)
    blot = np.asarray(Image.fromarray(((small - small.min()) / (np.ptp(small) + 1e-6) * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC), np.float32)
    base -= (blot[..., None] / 255 - 0.5) * 6
    base += rng.normal(0, 2.2, (h, w, 1)).astype(np.float32)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    edge = ((xx / w - 0.5) ** 2 + (yy / h - 0.5) ** 2) * 2
    base *= (1 - 0.07 * edge)[..., None]
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


def _words_layer(sc: dict, spec: dict, box: tuple[int, int, int, int], size: int, w: int, h: int, centre: bool = False,
                 light: bool = False):
    """Every word as its own image (so each can land on its own), and where each sits."""
    text = str(spec.get("text") or sc.get("text") or "")
    up, it = _fonts(sc, size)
    accent = _rgb(sc.get("_accent"), DEEP_BLUE)
    if light:  # on footage: ivory words, the stressed ones in the accent only where it is light enough to read
        ink, accent = IVORY, (accent if sum(accent) > 450 else IVORY)
    else:
        ink = INK
        if sum(accent) > 600:  # an accent too pale for an ivory page: the deep blue instead
            accent = DEEP_BLUE
    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    lines = _lay(probe, _runs(text), up, it, box[2])
    lh = int(size * 1.22)
    top = box[1] + max(0, (box[3] - lh * len(lines)) // 2)
    out = []
    for k, line in enumerate(lines):
        if not line:
            continue
        last = line[-1]
        lw = last[2] + probe.textlength(last[0], font=it if last[1] else up)
        dx = (box[2] - lw) / 2 if centre else 0
        for word, stress, x in line:
            f = it if stress else up
            img = Image.new("RGBA", (int(probe.textlength(word, font=f) + size), int(size * 1.6)), (0, 0, 0, 0))
            # the italic is a little larger, so the stressed words sit level with the upright ones
            ImageDraw.Draw(img).text((int(size * 0.1), int(size * 0.2) - (size * 0.12 if stress else 0)), word, font=f,
                                     fill=(accent if stress else ink) + (255,))
            out.append((img, (int(box[0] + dx + x - size * 0.1), top + k * lh)))
    return out, top + len(lines) * lh, accent


def _note(sc, text: str, x: int, y: int, size: int, accent) -> tuple[Image.Image, list]:
    _, it = _fonts(sc, size)
    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    tw = probe.textlength(text, font=it)
    img = Image.new("RGBA", (int(tw + size), int(size * 1.6)), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((0, int(size * 0.15)), text, font=it, fill=accent + (255,))
    rng = np.random.default_rng(len(text))
    base = y + size * 1.4
    line = _wobble([(x - size * 0.1, base), (x + tw * 0.55, base + size * 0.08), (x + tw + size * 0.3, base - size * 0.05)],
                   size * 0.05, rng, 10)
    return img, line


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


def _focus(sc: dict, card: tuple[float, float] | None, words: tuple[float, float]) -> list[tuple[float, float, float]]:
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


def page_scene(sc: dict, d: float, w: int, h: int, fps: float, out: Path) -> None:
    spec = sc["page"] if isinstance(sc.get("page"), dict) else {}
    vertical = h > w
    m = min(w, h)
    full = is_full(sc)
    has_pic = bool(sc.get("file")) and sc.get("type") in ("clip", "image", "title", "text") and not full
    side = spec.get("side", "right")
    back = paper(w, h, 3)  # one sheet for every page, so a cut from page to page keeps the paper still
    scale = float(spec.get("size", 1.0))
    L = float(sc.get("_len") or d)  # the scene's own length (the picture runs on under a transition)
    # where the words go, and how big
    if full:
        size = int(m * (0.075 if not vertical else 0.085) * scale)
        box = (int(w * 0.12), int(h * 0.3), int(w * 0.76), int(h * 0.4))
    elif not has_pic:
        size = int(m * 0.085 * scale) if not vertical else int(w * 0.085 * scale)
        box = (int(w * 0.08), int(h * 0.18), int(w * (0.72 if not vertical else 0.84)), int(h * 0.6))
    elif vertical:
        size = int(w * 0.07 * scale)
        box = (int(w * 0.08), int(h * 0.58), int(w * 0.84), int(h * 0.3))
    else:
        size = int(m * 0.075 * scale)
        x0 = 0.07 if side == "right" else 0.59
        box = (int(w * x0), int(h * 0.2), int(w * (0.36 if side == "right" else 0.34)), int(h * 0.6))
    words, bottom, accent = _words_layer(sc, spec, box, size, w, h, centre=full, light=full)
    times = sc.get("_page_times")
    times = times if isinstance(times, list) and len(times) == len(words) else land_times(len(words), L)
    label = str(spec.get("label") or "").upper() if not full else ""
    if label:
        lf = ImageFont.truetype(str(FONTS / "Inter-SemiBold.otf"), max(8, int(m * 0.02)))
        limg = Image.new("RGBA", (w, int(m * 0.05)), (0, 0, 0, 0))
        ImageDraw.Draw(limg).text((0, 0), "  ".join(label), font=lf, fill=MUTED + (255,))  # spaced capitals
        lpos = (int(w * (0.045 if side == "right" or not has_pic else 0.59)), int(h * 0.075))
    note = str(spec.get("note") or "") if not full else ""
    t_note = (times[-1] + LAND * 0.6) if times else 0.3
    if note:
        nimg, nline = _note(sc, note, box[0], bottom + int(size * 0.35), int(size * 0.62), accent)
        npos = (box[0], bottom + int(size * 0.35))
    # the picture as a card (or, on a full page, the whole frame)
    card_at = None
    if has_pic:
        if vertical:
            cw, chh = int(w * 0.84), int(h * 0.4)
            cx, cy = w / 2, h * 0.31
        else:
            cw, chh = int(w * 0.5), int(h * 0.62)
            cx, cy = w * (0.71 if side == "right" else 0.29), h * 0.5
        from .media import video_size

        ar = None
        try:
            if str(sc["file"]).lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")):
                with Image.open(sc["file"]) as im:
                    ar = im.width / im.height
            elif (vs := video_size(sc["file"])):
                ar = vs[0] / vs[1]
        except OSError:
            ar = None
        ar = ar or w / h
        if cw / chh > ar:
            cw = int(chh * ar)
        else:
            chh = int(cw / ar)
        cw, chh = cw // 2 * 2, chh // 2 * 2
        grow = sc.get("_from_full") or sc.get("_to_full")
        # a card that grows to (or shrinks from) the whole frame is drawn from frames big enough for it
        fw, fh = (w, h) if grow else (cw, chh)
        src = frames_of(sc["file"], fw, fh, fps, float(sc.get("from", 0)), d)
        angle = float(spec.get("angle", 0.0))
        r = max(2, int(m * 0.008))
        card_at = (cx / w, cy / h)
        away = 1 if (vertical or side == "right") else -1  # the card comes in from (and leaves to) its own side
    elif full:
        src = frames_of(sc["file"], w, h, fps, float(sc.get("from", 0)), d)
        yy = np.linspace(-1, 1, h, dtype=np.float32)[:, None]
        shade = (1 - 0.42 * np.exp(-(yy / 0.55) ** 2))[..., None]  # a soft band of shade behind the words
    # what the camera must never lose: the words, their label and their note
    kx0, ky0 = box[0] - m * 0.03, box[1] - m * 0.03
    kx1, ky1 = box[0] + box[2] + m * 0.03, max(box[1] + box[3], bottom + (int(size * 1.4) if note else 0)) + m * 0.03
    if label:
        kx0, ky0 = min(kx0, lpos[0] - m * 0.03), min(ky0, lpos[1] - m * 0.02)
    keep = (kx0, ky0, kx1, ky1)
    specs = _overlays(sc)
    caches = [dict() for _ in specs]
    held: list = [None] * len(specs)
    focus = _focus(sc, card_at, (box[0] / w, box[1] / h))
    screen = bool(sc.get("screen")) or (sc.get("type") == "clip" and has_pic and sc.get("_howto"))
    exit_at = L - EXIT if sc.get("_exit") else None
    moving = sc.get("camera", True) is not False
    wr = Writer(out, w, h, fps)
    try:
        for i in range(max(1, round(d * fps))):
            t = i / fps
            ex = _ease((t - exit_at) / EXIT) if exit_at is not None else 0.0  # 0 until the words leave, then 1
            if full:
                k = min(1.0, t / 0.4) * (1 - ex)  # the shade comes in, and goes as the words leave
                frame = (next(src).astype(np.float32) * (1 - (1 - shade) * k)).astype(np.uint8)
                z0 = 1.0 + 0.04 * min(1.0, t / max(1.0, L)) * (1 - ex)  # a slow push into the footage
                frame = _camera(frame, z0, 0.5, 0.5)
            else:
                frame = back
            if has_pic:
                pic = Image.fromarray(next(src))
                g = 0.0  # how much of the whole frame the card fills (1 = all of it)
                if sc.get("_from_full"):
                    g = 1 - _ease(t / 0.75)
                elif sc.get("_to_full") and exit_at is not None:
                    g = _ease((t - (L - 0.6)) / 0.6)
                if g > 0:
                    tw_, th_ = round(cw + (w - cw) * g), round(chh + (h - chh) * g)
                    pic = Image.fromarray(cover(np.asarray(pic), tw_, th_)) if (fw, fh) != (tw_, th_) else pic
                elif (fw, fh) != (cw, chh):
                    pic = Image.fromarray(cover(np.asarray(pic), cw, chh))
                pic = _rounded(pic, round(r * (1 - g)))
                rot = angle * (1 - g)
                if sc.get("_card_stays") or g > 0:
                    q, dx = 1.0, 0.0
                else:  # the card slides in from its side, turning and growing a touch as it settles
                    q = _ease_out(t / 0.7)
                    dx = m * 0.13 * away * (1 - q)
                    rot = angle * q
                    if q < 1:
                        pic = pic.resize((max(2, round(pic.width * (0.94 + 0.06 * q))), max(2, round(pic.height * (0.94 + 0.06 * q)))),
                                         Image.BICUBIC)
                if ex and not sc.get("_keep_card") and not sc.get("_to_full"):
                    dx += m * 0.13 * away * ex  # and leaves the same way
                if rot:
                    pic = pic.rotate(rot, resample=Image.BICUBIC, expand=True)
                pic, pad = _shadowed(pic, max(2, int(m * 0.018 * (1 - g))) or 1, int(m * 0.012 * (1 - g)), 0.32 * (1 - g))
                op = min(1.0, t / 0.25) if not (sc.get("_card_stays") or g > 0) else 1.0
                if ex and not sc.get("_keep_card") and not sc.get("_to_full"):
                    op *= 1 - ex
                ccx = cx + (w / 2 - cx) * g
                ccy = cy + (h / 2 - cy) * g
                frame = _paste(frame, _fade(pic, op), (round(ccx + dx - pic.width / 2), round(ccy - pic.height / 2)))
            if label:
                frame = _paste(frame, _fade(limg, 1 - ex), (lpos[0] - round(m * 0.06 * ex), lpos[1]))
            lift = -m * 0.06 * ex  # leaving: the words slide away and fade
            for (img, (x, y)), tw in zip(words, times):  # each word lands when it is said
                u = (t - tw) / LAND
                if u <= 0:
                    continue
                q = _back(u)
                frame = _paste(frame, _fade(img, min(1.0, u * 1.8) * (1 - ex)),
                               (round(x + (lift if not full else 0)), round(y + size * 0.3 * (1 - q) + (lift * 0.5 if full else 0))))
            if note:
                q = _ease((t - t_note) / 0.3)
                if q > 0:
                    frame = _paste(frame, _fade(nimg, min(1.0, q) * (1 - ex)), (npos[0] + round(lift), npos[1]))
                    u = _ease((t - t_note - 0.2) / 0.45)
                    if u > 0 and ex < 1:
                        from .motion import _partial

                        lay = Layer(w, h)
                        _stroke(lay.draw, [(px * 2 + lift * 2, py * 2) for px, py in _partial(nline, u)],
                                max(2, int(size * 0.05)) * 2, accent + (255,))
                        frame = _paste(frame, _fade(lay.done(), 1 - ex), (0, 0))
            for j, (fn, sp) in enumerate(specs):  # stamps, strikes and notes, before the camera so they move with the page
                got = held[j] if held[j] is not None else fn(sc, sp, t, w, h, frame, caches[j])
                if got is not None and got[2]:
                    held[j] = got
                if got is not None:
                    frame = _paste(frame, _fade(got[0], 1 - ex) if ex else got[0], got[1])
            if moving and not full:
                # a gentle camera: a slow drift toward the card (closer on a screen recording), then over to
                # whatever is circled, pointed at or stamped as it appears; back out as the page leaves
                fx, fy = card_at if card_at else (0.5, 0.5)
                z = 1.0 + (0.07 if screen else 0.025) * _ease(t / max(1.0, L))
                for at, nx, ny in focus:
                    p = _ease((t - at + 0.25) / 0.6)
                    if p > 0:
                        fx, fy = fx + (nx - fx) * p, fy + (ny - fy) * p
                        z = max(z, 1.0 + 0.08 * p)
                z = 1 + (z - 1) * (1 - ex)
                fx, fy = 0.5 + (fx - 0.5) * (1 - ex), 0.5 + (fy - 0.5) * (1 - ex)
                frame = _camera(frame, z, fx, fy, keep)
            wr.put(frame)
    finally:
        wr.close()


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
        elif not (pg.get("text") or sc.get("text")):
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
