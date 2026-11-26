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


def _words_layer(sc: dict, spec: dict, box: tuple[int, int, int, int], size: int, w: int, h: int):
    """The words as one image per line (so they can arrive one after another), and where each sits."""
    text = str(spec.get("text") or sc.get("text") or "")
    up, it = _fonts(sc, size)
    accent = _rgb(sc.get("_accent"), DEEP_BLUE)
    if sum(accent) > 600:  # an accent too pale for an ivory page: the deep blue instead
        accent = DEEP_BLUE
    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    lines = _lay(probe, _runs(text), up, it, box[2])
    lh = int(size * 1.22)
    top = box[1] + max(0, (box[3] - lh * len(lines)) // 2)
    out = []
    for k, line in enumerate(lines):
        img = Image.new("RGBA", (box[2] + size * 2, int(size * 1.6)), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        for word, stress, x in line:
            # the italic is a little larger, so the stressed words sit level with the upright ones
            d.text((x, int(size * 0.2) - (size * 0.12 if stress else 0)), word, font=it if stress else up,
                   fill=(accent if stress else INK) + (255,))
        out.append((img, (box[0], top + k * lh)))
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


def page_scene(sc: dict, d: float, w: int, h: int, fps: float, out: Path) -> None:
    spec = sc["page"] if isinstance(sc.get("page"), dict) else {}
    vertical = h > w
    m = min(w, h)
    has_pic = bool(sc.get("file")) and sc.get("type") in ("clip", "image", "title", "text")
    side = spec.get("side", "right")
    back = paper(w, h, 3 + int(sc.get("_k", 0) or 0))
    scale = float(spec.get("size", 1.0))
    # where the words go, and how big
    if not has_pic:
        size = int(m * 0.085 * scale) if not vertical else int(w * 0.085 * scale)
        box = (int(w * 0.08), int(h * 0.18), int(w * (0.72 if not vertical else 0.84)), int(h * 0.6))
    elif vertical:
        size = int(w * 0.07 * scale)
        box = (int(w * 0.08), int(h * 0.58), int(w * 0.84), int(h * 0.3))
    else:
        size = int(m * 0.075 * scale)
        x0 = 0.07 if side == "right" else 0.59
        box = (int(w * x0), int(h * 0.2), int(w * (0.36 if side == "right" else 0.34)), int(h * 0.6))
    lines, bottom, accent = _words_layer(sc, spec, box, size, w, h)
    label = str(spec.get("label") or "").upper()
    if label:
        lf = ImageFont.truetype(str(FONTS / "Inter-SemiBold.otf"), max(8, int(m * 0.02)))
        limg = Image.new("RGBA", (w, int(m * 0.05)), (0, 0, 0, 0))
        ImageDraw.Draw(limg).text((0, 0), "  ".join(label), font=lf, fill=MUTED + (255,))  # spaced capitals
        lpos = (int(w * (0.045 if side == "right" or not has_pic else 0.59)), int(h * 0.075))
    note = str(spec.get("note") or "")
    if note:
        nimg, nline = _note(sc, note, box[0], bottom + int(size * 0.35), int(size * 0.62), accent)
        npos = (box[0], bottom + int(size * 0.35))
    # the picture as a card
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
        src = frames_of(sc["file"], cw, chh, fps, float(sc.get("from", 0)), d)
        angle = float(spec.get("angle", 0.0))
        r = max(2, int(m * 0.008))
    wr = Writer(out, w, h, fps)
    try:
        for i in range(max(1, round(d * fps))):
            t = i / fps
            frame = back
            if has_pic:
                q = _ease_out(t / 0.6)
                pic = _rounded(Image.fromarray(next(src)), r)
                if angle:
                    pic = pic.rotate(angle, resample=Image.BICUBIC, expand=True)
                pic, pad = _shadowed(pic, max(2, int(m * 0.018)), int(m * 0.012), 0.32)
                if q < 1:
                    a = np.asarray(pic).copy()
                    a[..., 3] = (a[..., 3] * q).astype(np.uint8)
                    pic = Image.fromarray(a)
                frame = _paste(frame, pic, (round(cx - pic.width / 2), round(cy - pic.height / 2 + m * 0.03 * (1 - q))))
            if label:
                frame = _paste(frame, limg, lpos)
            for k, (img, (x, y)) in enumerate(lines):  # each line rises in after the one before
                q = _ease((t - 0.2 - 0.14 * k) / 0.45)
                if q <= 0:
                    continue
                if q < 1:
                    a = np.asarray(img).copy()
                    a[..., 3] = (a[..., 3] * q).astype(np.uint8)
                    img = Image.fromarray(a)
                frame = _paste(frame, img, (x, round(y + size * 0.25 * (1 - q))))
            if note:
                q = _ease((t - 0.5 - 0.14 * len(lines)) / 0.4)
                if q > 0:
                    a = np.asarray(nimg).copy()
                    a[..., 3] = (a[..., 3] * min(1.0, q)).astype(np.uint8)
                    frame = _paste(frame, Image.fromarray(a), npos)
                    u = _ease((t - 0.75 - 0.14 * len(lines)) / 0.5)
                    if u > 0:
                        from .motion import _partial

                        lay = Layer(w, h)
                        _stroke(lay.draw, [(px * 2, py * 2) for px, py in _partial(nline, u)], max(2, int(size * 0.05)) * 2, accent + (255,))
                        frame = _paste(frame, lay.done(), (0, 0))
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
