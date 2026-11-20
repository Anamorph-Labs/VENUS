"""Designed looks for storyboards, learned from the person's own reference
board: "mono" (a greyscale editorial reel: grey paper, fine grid, print
furniture, black-and-white photos, one accent colour, words that arrive one
at a time in mixed type) and "paper" (a Vox-style paper collage: crumpled
cream paper, photo prints with torn edges and tape, flat colour shapes and
paint behind them, heavy captions with a highlighter, hand-drawn marks).

Each scene is built in layers so it moves like a filmed table-top: the paper
drifts one way, the print drops in and drifts the other, light (leaf shadow)
sways over everything, and a new graphic beat lands about once a second
(a word, a highlight, a label, a mark), which is the pace of the references.

Pictures are made with Pillow; words and marks are drawn by libass over the
finished cut, like every other Venus graphic.

Mark up words in a scene's "text" or "caption" for the type to change:
  *word*    elegant serif italic        _word_   small light word
  ==word==  highlighted (accent box)    "big_words": [...] the huge ones
"""

from __future__ import annotations

import math
import random
import re
from pathlib import Path

DESIGNS = {
    "mono": "greyscale editorial: grey grid paper, print furniture, black-and-white photos, one accent colour, words one at a time in mixed type",
    "paper": "Vox-style paper collage: crumpled paper, torn photo prints with tape, colour shapes and paint, heavy captions with a highlighter",
}
VERSION = 4  # bump when the drawing changes, so cached scenes are redrawn

INK = (17, 17, 17)
CREAM = (238, 229, 210)
TEAL = (47, 143, 139)
RED = (200, 65, 47)
MARK_RED = "&H002F41D0&"  # hand-drawn red, as an ASS colour (BGR)


def _rgb(hex_rgb: str) -> tuple[int, int, int]:
    s = hex_rgb.lstrip("#")
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


def _ass(rgb: tuple[int, int, int], alpha: int = 0) -> str:
    r, g, b = rgb
    return f"&H{alpha:02X}{b:02X}{g:02X}{r:02X}&"


# ---------------------------------------------------------------- textures


def _noise(w: int, h: int, scale: int, rng) -> "np.ndarray":
    import numpy as np
    from PIL import Image

    sw, sh = max(2, w // scale), max(2, h // scale)
    small = Image.fromarray((rng.random((sh, sw)) * 255).astype("uint8"))
    return np.asarray(small.resize((w, h), Image.BICUBIC)).astype("float32") / 255.0


def paper_base(design: str, w: int, h: int, dark: bool = False, seed: int = 7):
    """The paper itself (no furniture), as a Pillow RGB image (kept on disk:
    a crumpled sheet takes a few seconds to fold)."""
    from PIL import Image

    import os

    base = Path(os.environ.get("ALVENUS_MODELS") or Path.home() / ".cache" / "al-venus")
    f = base / "paper" / f"{design}-{w}x{h}-{int(dark)}-{seed}-v{VERSION}.png"
    if f.exists():
        try:
            return Image.open(f).convert("RGB")
        except OSError:
            pass
    img = _paper(design, w, h, dark, seed)
    f.parent.mkdir(parents=True, exist_ok=True)
    img.save(f)
    return img


def _paper(design: str, w: int, h: int, dark: bool, seed: int):
    import numpy as np
    from PIL import Image, ImageFilter

    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w].astype("float32")
    r = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h * 0.45) / (h / 2)) ** 2)
    if design == "mono":
        if dark:
            base = 16 + 26 * np.clip(1 - r * 0.8, 0, 1) ** 2
            rgb = np.stack([base, base, base * 1.02], -1)
        else:
            # light falls on the centre of the sheet; the edges sink into grey
            base = 247 - 52 * np.clip(r * 0.78, 0, 1) ** 1.6
            rgb = np.stack([base, base * 0.997, base * 0.99], -1)
        fine = _noise(w, h, 3, rng) - 0.5
        rgb += fine[..., None] * (5 if not dark else 4)
    else:
        # crumpled paper: many random creases (tent-shaped folds) give flat
        # facets with sharp edges between them, lit from the top left
        height = np.zeros((h, w), "float32")
        sc = max(w, h)
        for _ in range(140):
            a = rng.uniform(0, np.pi)
            nx, ny = np.cos(a), np.sin(a)
            cx, cy = rng.uniform(0, w), rng.uniform(0, h)
            across = (xx - cx) * nx + (yy - cy) * ny
            along = -(xx - cx) * ny + (yy - cy) * nx
            reach = rng.uniform(0.03, 0.12) * sc
            length = rng.uniform(0.08, 0.3) * sc
            env = np.exp(-(along / length) ** 2)
            height += rng.choice((-1, 1)) * np.clip(1 - np.abs(across) / reach, 0, 1) * reach * env * rng.uniform(0.02, 0.05)
        height += _noise(w, h, max(4, sc // 50), rng) * sc * 0.0012
        gy, gx = np.gradient(height)
        light = np.clip((-gx * 0.75 - gy * 0.6) * 9, -1, 1)
        col = np.array((52, 50, 47) if dark else CREAM, dtype="float32")
        rgb = col[None, None, :] * (1 + 0.06 * light[..., None])
        rgb *= (1 - 0.22 * np.clip(r - 0.55, 0, 1) ** 1.5)[..., None]  # darker edges
        fibre = _noise(w, h, 2, rng) - 0.5
        rgb += fibre[..., None] * 9
        specks = rng.random((h, w)) > 0.9993
        rgb[specks] *= 0.7
    img = Image.fromarray(np.clip(rgb, 0, 255).astype("uint8"), "RGB")
    return img.filter(ImageFilter.GaussianBlur(0.4))


def _barcode(draw, x: int, y: int, bw: int, bh: int, rng, ink) -> None:
    cx = x
    while cx < x + bw:
        t = rng.choice((1, 1, 2, 3))
        draw.rectangle([cx, y, cx + t - 1, y + bh], fill=ink)
        cx += t + rng.choice((1, 2, 2, 3))


def _font(name: str, size: int):
    from PIL import ImageFont

    from .style import FONTS

    return ImageFont.truetype(str(FONTS / name), max(6, size))


def background(design: str, w: int, h: int, k: int, total: int, label: str, dark: bool = False, words_text: str = ""):
    """Paper plus its printed furniture: for "mono" a fine grid, crop marks,
    a header with the scene number, a barcode and tiny columns of real words;
    for "paper" a torn dark strip along one edge. Drawn 6% larger than the
    frame, so it can drift."""
    from PIL import Image, ImageDraw

    W, H = round(w * 1.06) // 2 * 2, round(h * 1.06) // 2 * 2
    img = paper_base(design, W, H, dark, seed=11 + (k % 3))
    d = ImageDraw.Draw(img, "RGBA")
    rng = random.Random(100 + k)
    ox, oy = (W - w) // 2, (H - h) // 2  # the visible frame inside the larger sheet
    u = min(w, h)
    ink = (235, 235, 235, 255) if dark else (20, 20, 20, 255)
    faint = (255, 255, 255, 22) if dark else (0, 0, 0, 20)
    if design == "mono":
        step = round(u / (11 if h > w else 14))
        for x in range(ox % step, W, step):
            d.line([(x, 0), (x, H)], fill=faint, width=1)
        for y in range(oy % step, H, step):
            d.line([(0, y), (W, y)], fill=faint, width=1)
        m = round(u * 0.06)
        small = _font("DMMono-Regular.ttf", round(u * 0.018))
        tiny = _font("DMMono-Regular.ttf", round(u * 0.0135))
        head = (label or "VENUS").upper()[:28]
        d.text((ox + m, oy + m), head, font=small, fill=ink)
        num = f"{k + 1:05d}"
        d.text((ox + w - m - d.textlength(num, font=small), oy + m), num, font=small, fill=ink)
        mid = f"{k + 1:02d} / {total:02d}"
        d.text((ox + w // 2 - d.textlength(mid, font=tiny) // 2, oy + m + 2), mid, font=tiny, fill=ink[:3] + (150,))
        y_rule = oy + m + round(u * 0.032)
        d.line([(ox + m, y_rule), (ox + w - m, y_rule)], fill=ink[:3] + (90,), width=1)
        # crop marks
        c = round(u * 0.012)
        for cx, cy in ((ox + m, oy + round(h * 0.2)), (ox + w - m, oy + round(h * 0.2)),
                       (ox + m, oy + h - round(h * 0.2)), (ox + w - m, oy + h - round(h * 0.2))):
            d.line([(cx - c, cy), (cx + c, cy)], fill=ink[:3] + (140,), width=1)
            d.line([(cx, cy - c), (cx, cy + c)], fill=ink[:3] + (140,), width=1)
        # footer: barcode, and two tiny columns made of the video's own words
        bh = round(u * 0.035)
        _barcode(d, ox + w - m - round(u * 0.16), oy + h - m - bh, round(u * 0.16), bh, rng, ink)
        words = (words_text or label or "venus edition").lower().split()
        words = (words * (1 + 40 // max(1, len(words))))
        col_w = round(u * 0.2)
        for ci in range(2):
            x0 = ox + m + ci * (col_w + round(u * 0.03))
            yb = oy + h - m - round(u * 0.105)
            lines, cur = [], ""
            for wd in words[ci * 23 + k * 7:]:
                if d.textlength(cur + " " + wd, font=tiny) > col_w:
                    lines.append(cur)
                    cur = wd
                else:
                    cur = (cur + " " + wd).strip()
                if len(lines) == 4:
                    break
            for li, txt in enumerate(lines):
                d.text((x0, yb + li * round(u * 0.017)), txt, font=tiny, fill=ink[:3] + (120,))
        d.text((ox + m, oy + h - m - round(u * 0.014)), "EST. 2026 — EDITION " + num[-2:], font=tiny, fill=ink[:3] + (150,))
    else:
        # a torn dark strip across the bottom (or the right side, on wide frames)
        pts, n = [], 60
        if h > w:
            y0 = oy + h - round(h * 0.045)
            pts = [(0, H)] + [(i * W / n, y0 + rng.uniform(-1, 1) * u * 0.012) for i in range(n + 1)] + [(W, H)]
        else:
            y0 = oy + h - round(h * 0.06)
            pts = [(0, H)] + [(i * W / n, y0 + rng.uniform(-1, 1) * u * 0.014) for i in range(n + 1)] + [(W, H)]
        d.polygon(pts, fill=(28, 26, 24, 255) if not dark else (225, 216, 196, 255))
    return img


def leaf_shadow(w: int, h: int, seed: int = 3):
    """Soft shadows of leaves falling across the sheet from a window: a few
    blurred dark shapes at the edges, drawn wide so they can sway."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter

    W, H = round(w * 1.3), h
    lay = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(lay)
    rng = random.Random(seed)
    u = min(w, h)
    for _ in range(7):
        side = rng.choice((0, 1))
        cx = rng.uniform(0, W * 0.16) if side == 0 else rng.uniform(W * 0.84, W)
        cy = rng.uniform(-0.05, 1.05) * H
        L, Wd, ang = u * rng.uniform(0.25, 0.45), u * rng.uniform(0.06, 0.11), rng.uniform(0, math.pi)
        pts = []
        for i in range(24):
            t = i / 23 * 2 * math.pi
            px, py = L / 2 * math.cos(t), Wd / 2 * math.sin(t) * (1 + 0.3 * math.cos(t))
            pts.append((cx + px * math.cos(ang) - py * math.sin(ang), cy + px * math.sin(ang) + py * math.cos(ang)))
        d.polygon(pts, fill=255)
        d.line([pts[0], pts[12]], fill=255, width=max(2, round(u * 0.008)))  # the stem
    lay = lay.filter(ImageFilter.GaussianBlur(u * 0.026))
    a = (np.asarray(lay).astype("float32") * 0.11).astype("uint8")
    out = Image.new("RGBA", (W, H), (30, 30, 34, 0))
    out.putalpha(Image.fromarray(a))
    return out


# ------------------------------------------------------------------ prints


def layout(w: int, h: int, has_text: bool, src_aspect: float) -> tuple[int, int, int, int]:
    """Where the print sits: (x, y, width, height) of the picture inside it."""
    vertical = h > w
    a = min(1.45, max(0.72, src_aspect))
    if vertical:
        pw = round(w * (0.76 if has_text else 0.84))
        ph = round(pw / a)
        ph = min(ph, round(h * (0.5 if has_text else 0.66)))
        pw = min(pw, round(ph * a))
        cx, cy = w / 2, h * (0.63 if has_text else 0.5)
    else:
        ph = round(h * (0.56 if has_text else 0.7))
        pw = round(ph * a)
        pw = min(pw, round(w * (0.5 if has_text else 0.62)))
        ph = min(ph, round(pw / a))
        cx, cy = (w * (0.72 if has_text else 0.5)), h * 0.5
    pw, ph = pw // 2 * 2, ph // 2 * 2
    return round(cx - pw / 2), round(cy - ph / 2), pw, ph


def _treat(img, design: str):
    from PIL import ImageEnhance, ImageOps

    img = img.convert("RGB")
    if design == "mono":
        g = ImageOps.autocontrast(ImageOps.grayscale(img), cutoff=1)
        g = ImageEnhance.Contrast(g).enhance(1.12)
        return g.convert("RGB")
    img = ImageEnhance.Color(img).enhance(0.55)
    r, g, b = img.split()
    from PIL import Image

    warm = Image.merge("RGB", (r.point(lambda v: min(255, v * 1.04 + 6)), g, b.point(lambda v: v * 0.9)))
    return ImageEnhance.Contrast(warm).enhance(1.06)


def _blob(size: int, rng, fill):
    """An organic paint blob: a wobbly circle, softened then cut sharp."""
    from PIL import Image, ImageDraw, ImageFilter

    lay = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(lay)
    n = 40
    ph = [rng.uniform(0, 6.28) for _ in range(3)]
    pts = []
    for i in range(n):
        t = i / n * 2 * math.pi
        rr = size * 0.36 * (1 + 0.12 * math.sin(3 * t + ph[0]) + 0.07 * math.sin(5 * t + ph[1]) + 0.05 * math.sin(9 * t + ph[2]))
        pts.append((size / 2 + rr * math.cos(t), size / 2 + rr * math.sin(t)))
    d.polygon(pts, fill=255)
    for _ in range(7):  # splatter
        t = rng.uniform(0, 6.28)
        rr = size * rng.uniform(0.4, 0.48)
        s = size * rng.uniform(0.01, 0.03)
        x, y = size / 2 + rr * math.cos(t), size / 2 + rr * math.sin(t)
        d.ellipse([x - s, y - s, x + s, y + s], fill=255)
    lay = lay.filter(ImageFilter.GaussianBlur(size * 0.008)).point(lambda v: 255 if v > 120 else 0)
    out = Image.new("RGBA", (size, size), fill + (0,))
    out.putalpha(lay)
    return out


def print_plate(design: str, w: int, h: int, k: int, rect: tuple[int, int, int, int], accent: str,
                picture=None, dark: bool = False):
    """The print and what lies under it, as one transparent layer the size of
    the frame: the accent shape or paint, the shadow, the border, the photo
    (when it is a still; a moving clip is laid into the window later) and,
    for "paper", the tape. Returns (plate, window), window = picture rect."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter

    x, y, pw, ph = rect
    u = min(w, h)
    rng = random.Random(500 + k)
    under = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    plate = under  # the shape is drawn on its own layer, so it can land on its own beat
    acc = _rgb(accent)
    # what sits behind the print
    if design == "mono":
        if k % 2 == 0:
            r = round(max(pw, ph) * 0.42)
            cx, cy = x + pw * (0.22 if k % 4 == 0 else 0.8), y + ph * 0.3
            ImageDraw.Draw(plate).ellipse([cx - r, cy - r, cx + r, cy + r], fill=acc + (255,))
        else:
            bx = x - round(pw * 0.08) if k % 4 == 1 else x + round(pw * 0.62)
            ImageDraw.Draw(plate).rectangle([bx, y - round(ph * 0.12), bx + round(pw * 0.46), y + round(ph * 0.7)], fill=acc + (255,))
    else:
        shape = (k + 2) % 3
        if shape == 0:
            b = _blob(round(max(pw, ph) * 0.95), rng, acc)
            plate.alpha_composite(b, (round(x - pw * 0.08 - b.width / 2 + b.width * 0.25), round(y + ph * 0.18 - b.height / 2)))
        else:
            col = TEAL if shape == 1 else RED
            r = round(max(pw, ph) * 0.36)
            cx, cy = x + (pw * 0.12 if shape == 1 else pw * 0.9), y + ph * (0.2 if shape == 1 else 0.75)
            ImageDraw.Draw(plate).ellipse([cx - r, cy - r, cx + r, cy + r], fill=col + (255,))
    plate = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    # the print: border and (for paper) a torn bottom edge
    border = round(u * (0.012 if design == "mono" else 0.02))
    sheet = Image.new("L", (pw + 2 * border, ph + 2 * border), 255)
    if design == "paper":
        ds = ImageDraw.Draw(sheet)
        n = 50
        pts = [(0, sheet.height)] + [(i * sheet.width / n, sheet.height - border * 0.4 - rng.uniform(0, 1) * border * 1.6) for i in range(n + 1)] + [(sheet.width, sheet.height)]
        ds.polygon(pts, fill=0)
    face = Image.new("RGBA", sheet.size, (250, 248, 242, 255) if design == "paper" else (252, 252, 252, 255))
    if picture is not None:
        from PIL import ImageOps

        pic = ImageOps.fit(_treat(picture, design), (pw, ph), Image.LANCZOS, centering=(0.5, 0.4))
        face.paste(pic, (border, border))
    else:  # the window where the clip will play
        ImageDraw.Draw(face).rectangle([border, border, border + pw - 1, border + ph - 1], fill=(0, 0, 0, 0))
    face.putalpha(Image.fromarray(np.minimum(np.asarray(sheet), np.asarray(face.getchannel("A")))))
    angle = 0.0
    if design == "paper" and picture is not None:
        angle = rng.choice((-1, 1)) * rng.uniform(1.2, 2.6)
    rot = face.rotate(angle, resample=Image.BICUBIC, expand=True) if angle else face
    px, py = x - border - (rot.width - face.width) // 2, y - border - (rot.height - face.height) // 2
    # soft shadow under the print
    sh = Image.new("RGBA", rot.size, (0, 0, 0, 0))
    sh.putalpha(rot.getchannel("A").point(lambda v: v * 0.42 if not dark else v * 0.7))
    sh = sh.filter(ImageFilter.GaussianBlur(u * 0.012))
    plate.alpha_composite(sh, (px + round(u * 0.006), py + round(u * 0.014)))
    if picture is None:
        # leave the window clear of the shadow too
        hole = Image.new("L", (w, h), 255)
        ImageDraw.Draw(hole).rectangle([x, y, x + pw - 1, y + ph - 1], fill=0)
        plate.putalpha(Image.fromarray(np.minimum(np.asarray(plate.getchannel("A")), np.asarray(hole))))
    plate.alpha_composite(rot, (px, py))
    if design == "paper":
        # a strip of tape across the top edge
        tw, th = round(pw * 0.32), round(u * 0.045)
        tape = Image.new("RGBA", (tw, th), (236, 224, 190, 200))
        td = ImageDraw.Draw(tape)
        for i in range(0, th, max(2, th // 6)):  # zigzag torn ends
            td.polygon([(0, i), (th * 0.12, i + th / 12), (0, i + th / 6)], fill=(0, 0, 0, 0))
            td.polygon([(tw, i), (tw - th * 0.12, i + th / 12), (tw, i + th / 6)], fill=(0, 0, 0, 0))
        tape = tape.rotate(rng.uniform(-6, 6), resample=Image.BICUBIC, expand=True)
        plate.alpha_composite(tape, (round(x + pw / 2 - tape.width / 2), round(y - border - tape.height * 0.45)))
    return plate, under, (x, y, pw, ph)


# ------------------------------------------------------------------- scenes


def _first_frame(path: str):
    import subprocess

    from PIL import Image

    from .story import _still

    if _still(path):
        return Image.open(path)
    import io

    raw = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", path, "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"],
                         capture_output=True, check=True).stdout
    return Image.open(io.BytesIO(raw))


def has_print(sc: dict) -> bool:
    return bool(sc.get("file")) and sc["type"] in ("clip", "image", "title", "text")


def has_words(sc: dict) -> bool:
    return bool(sc.get("text") or sc.get("caption"))


def scene_video(sc: dict, d: float, w: int, h: int, fps: float, out: Path, k: int, total: int) -> None:
    """One scene of a designed storyboard: paper, furniture, print, light."""
    import tempfile

    from .media import run
    from .story import _still

    design = sc["_design"]
    dark = bool(sc.get("dark")) or sc["type"] not in ("clip", "image", "title", "text")
    accent = sc.get("_accent", "#D4F01E")
    tmp = Path(tempfile.mkdtemp(prefix="venus-p-", dir=out.parent))
    try:
        bg = background(design, w, h, k, total, sc.get("_label", ""), dark, sc.get("_words", ""))
        bg_p = tmp / "bg.png"
        bg.save(bg_p)
        D = max(d, 0.1)
        dirx = -1 if k % 2 else 1
        inputs = ["-loop", "1", "-t", f"{d:.3f}", "-i", str(bg_p)]
        g = [f"[0:v]fps={fps:g},crop={w}:{h}:x='(iw-ow)/2*(1+{dirx}*0.8*min(t/{D:.3f},1))':y='(ih-oh)/2*(1-0.4*min(t/{D:.3f},1))',setsar=1[b0]"]
        last, n = "b0", 1
        media = sc.get("file") if has_print(sc) else None
        if media:
            pic = _first_frame(media)
            rect = layout(w, h, has_words(sc), pic.width / max(1, pic.height))
            still = _still(media)
            plate, under, (x, y, pw, ph) = print_plate(design, w, h, k, rect, accent, pic if still else None, dark)
            pl_p, un_p = tmp / "plate.png", tmp / "under.png"
            plate.save(pl_p)
            under.save(un_p)
            # the colour shape lands just after the print, behind it: a beat of its own
            inputs += ["-loop", "1", "-t", f"{d:.3f}", "-i", str(un_p)]
            g.append(f"[{n}:v]format=rgba,fade=t=in:st=0.55:d=0.12:alpha=1[un]")
            g.append(f"[{last}][un]overlay=x='{dirx}*{w * 0.02:.1f}*min(t/{D:.3f},1)':y=0:eval=frame[b0u]")
            last, n = "b0u", n + 1
            inputs += ["-loop", "1", "-t", f"{d:.3f}", "-i", str(pl_p)]
            # the print drops in (slides up out of a fade), then drifts against the paper
            ease = "pow(1-min(t/0.35,1),3)"
            dx = f"{-dirx}*{w * 0.012:.1f}*min(t/{D:.3f},1)"
            g.append(f"[{n}:v]format=rgba,fade=t=in:st=0:d=0.18:alpha=1[pl]")
            g.append(f"[{last}][pl]overlay=x='{dx}':y='{h * 0.035:.1f}*{ease}':eval=frame[b1]")
            last, n = "b1", n + 1
            if not still:
                look = "hue=s=0,eq=contrast=1.12" if design == "mono" else "eq=saturation=0.55:contrast=1.05,colorbalance=rs=0.04:bs=-0.05"
                inputs += ["-ss", f"{float(sc.get('from', 0)):.3f}", "-t", f"{d + 0.2:.3f}", "-i", media]
                g.append(f"[{n}:v]fps={fps:g},scale={pw}:{ph}:force_original_aspect_ratio=increase,crop={pw}:{ph},{look},"
                         f"format=rgba,fade=t=in:st=0:d=0.18:alpha=1[clip]")
                g.append(f"[{last}][clip]overlay=x='{x}+{dx}':y='{y}+{h * 0.035:.1f}*{ease}':eval=frame:shortest=0[b2]")
                last, n = "b2", n + 1
        if design == "mono" and not dark:
            lf = tmp / "leaf.png"
            leaf_shadow(w, h, seed=k).save(lf)
            inputs += ["-loop", "1", "-t", f"{d:.3f}", "-i", str(lf)]
            g.append(f"[{last}][{n}:v]overlay=x='-{w * 0.15:.1f}+{w * 0.025:.1f}*sin(t*0.7+{k})':y=0[b3]")
            last, n = "b3", n + 1
        g.append(f"[{last}]noise=alls={5 if design == 'mono' else 7}:allf=t,format=yuv420p[v]")
        run(["ffmpeg", "-nostdin", "-y", "-v", "error"] + inputs + ["-filter_complex", ";".join(g), "-map", "[v]",
             "-t", f"{d:.3f}", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "14", "-pix_fmt", "yuv420p",
             "-r", f"{fps:g}", str(out)])
    finally:
        for f in tmp.glob("*"):
            f.unlink()
        tmp.rmdir()


# ------------------------------------------------------------------- words

FONT_FILES = {  # ASS family -> file, for measuring
    ("Inter Display", "Black"): "InterDisplay-Black.otf",
    ("Inter", "ExtraBold"): "Inter-ExtraBold.otf",
    ("Inter", "SemiBold"): "Inter-SemiBold.otf",
    ("Instrument Serif", "Italic"): "InstrumentSerif-Italic.ttf",
    ("Big Shoulders", "Bold"): "BigShoulders-Bold.ttf",
    ("DM Mono", "Regular"): "DMMono-Regular.ttf",
    ("Libre Baskerville", "Regular"): "LibreBaskerville-Regular.ttf",
    ("Nothing You Could Do", "Regular"): "NothingYouCouldDo-Regular.ttf",
}
_METRICS: dict[str, tuple[float, float]] = {}


def _measure(text: str, size: float, face: tuple[str, str]) -> tuple[float, float]:
    """(width, descent) libass gives `text` at `size` in this face."""
    from .style import FONTS

    f = FONT_FILES[face]
    try:
        from PIL import ImageFont

        if f not in _METRICS:
            fo = ImageFont.truetype(str(FONTS / f), 200)
            asc, desc = fo.getmetrics()
            _METRICS[f] = (asc, desc)
        asc, desc = _METRICS[f]
        fo = ImageFont.truetype(str(FONTS / f), 200)
        return fo.getlength(text) * size / (asc + desc), size * desc / (asc + desc)
    except Exception:
        return len(text) * size * 0.55, size * 0.2


def parse(text: str, big: set[str]) -> list[tuple[str, str]]:
    """Words with their role: big, serif, light, mark (highlighted) or plain."""
    out = []
    for tok in re.findall(r"==[^=]+==|\*[^*]+\*|_[^_]+_|\S+", text):
        role = "plain"
        if tok.startswith("==") and tok.endswith("==") and len(tok) > 4:
            role, tok = "mark", tok[2:-2]
        elif tok.startswith("*") and tok.endswith("*") and len(tok) > 2:
            role, tok = "serif", tok[1:-1]
        elif tok.startswith("_") and tok.endswith("_") and len(tok) > 2:
            role, tok = "light", tok[1:-1]
        for i, wd in enumerate(tok.split()):
            r = role
            if r == "plain" and re.sub(r"[^\w']", "", wd.lower()) in big:
                r = "big"
            out.append((wd, r))
    return out


def plain(text: str) -> str:
    """Text without the markup (for captions files and self-review)."""
    return " ".join(w for w, _ in parse(text, set()))


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("{", "(").replace("}", ")")


def _t(x: float) -> str:
    from .style import _t as t

    return t(x)


def word_events(text: str, big: set[str], t0: float, t1: float, w: int, h: int, design: str, accent: str,
                box: tuple[int, int, int, int], dark: bool, align: str = "left", caps: bool = False, layer: int = 20) -> tuple[list[str], list[float]]:
    """Words set into `box` (x, y, width, height), each arriving on its own
    beat: it fades up out of a blur and settles. Mixed type on one baseline.
    Returns the events and the time each word lands."""
    bx, by, bw, bh = box
    u = min(w, h)
    base = u * (0.115 if h > w else 0.11)
    if design == "paper":
        base *= 0.92
    faces = {
        "plain": (("Inter Display", "Black") if design == "paper" else ("Inter", "ExtraBold"), 1.0),
        "big": (("Inter Display", "Black"), 1.9),
        "serif": (("Instrument Serif", "Italic"), 1.3),
        "light": (("Inter", "SemiBold"), 0.6),
        "mark": (("Inter Display", "Black") if design == "paper" else ("Inter", "ExtraBold"), 1.0),
    }
    ink = (240, 240, 240) if dark else INK
    grey = (150, 150, 150) if dark else (110, 110, 110)
    words = parse(text, big)
    if caps:
        words = [(wd.upper() if r != "serif" else wd, r) for wd, r in words]
    if not words:
        return [], []
    # shrink until the words fit the box
    for shrink in (1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.42):
        lines, cur, cw = [], [], 0.0
        space = base * shrink * 0.28
        for wd, r in words:
            (fam, sz) = faces[r]
            size = base * shrink * sz
            wid, desc = _measure(wd, size, fam)
            need = wid + (space if cur else 0)
            if cur and cw + need > bw:
                lines.append(cur)
                cur, cw = [], 0.0
                need = wid
            cur.append((wd, r, size, wid, desc, fam))
            cw += need
        if cur:
            lines.append(cur)
        heights = [max(x[2] for x in ln) * 1.02 for ln in lines]
        if sum(heights) <= bh and all(sum(x[3] for x in ln) + space * (len(ln) - 1) <= bw * 1.001 for ln in lines):
            break
    total_h = sum(heights)
    y = by + (bh - total_h) / 2
    n = len(words)
    span = max(0.6, (t1 - t0) * 0.72)
    step = min(0.42, span / max(1, n))
    ev, lands = [], []
    i = 0
    for ln, lh in zip(lines, heights):
        y += lh
        lw = sum(x[3] for x in ln) + space * (len(ln) - 1)
        x = bx if align == "left" else bx + (bw - lw) / 2
        for wd, r, size, wid, desc, fam in ln:
            ta = t0 + 0.25 + i * step
            lands.append(ta)
            col = grey if r == "light" else ink
            fn, style = fam
            bold = "\\b1" if style in ("Black", "ExtraBold", "Bold") else "\\b0"
            ital = "\\i1" if style == "Italic" else "\\i0"
            ybot = y - size * 0.02
            rise = size * 0.18
            if r == "mark":
                pad = size * 0.12
                hx0, hy0 = round(x - pad), round(ybot - size * 0.86)
                hx1, hy1 = round(x + wid + pad), round(ybot - size * 0.08)
                hl = _rgb(accent)
                ev.append(f"Dialogue: {layer - 1},{_t(ta)},{_t(t1)},Card,,0,0,0,,{{\\an7\\pos(0,0)\\bord0\\shad0\\1c{_ass(hl)}"
                          f"\\clip({hx0},{hy0},{hx0 + 1},{hy1})\\t(0,260,\\clip({hx0},{hy0},{hx1},{hy1}))\\fad(0,150)\\p1}}"
                          f"m {hx0} {hy0} l {hx1} {hy0 + 2} l {hx1 - 2} {hy1} l {hx0 + 1} {hy1 - 1}{{\\p0}}")
            ev.append(f"Dialogue: {layer},{_t(ta)},{_t(t1)},Card,,0,0,0,,{{\\an1\\move({x:.0f},{ybot + rise:.0f},{x:.0f},{ybot:.0f},0,200)"
                      f"\\fn{fn}{bold}{ital}\\fs{size:.0f}\\fsp0\\bord0\\shad0\\1c{_ass(col)}"
                      f"\\alpha&HFF&\\blur6\\t(0,140,\\alpha&H00&\\blur0)\\fad(0,160)}}{_esc(wd)}")
            x += wid + space
            i += 1
    return ev, lands


def title_events(text: str, sub: str, t0: float, t1: float, w: int, h: int, design: str, accent: str, dark: bool) -> list[str]:
    """A title card: for "mono" a huge condensed name with a spaced-out label
    above it; for "paper" big condensed caps with a small underlined serif line."""
    u = min(w, h)
    m = round(u * 0.08)
    ink = (240, 240, 240) if dark else INK
    ev = []
    words = text.upper()
    size = u * 0.2
    wid, _ = _measure(words, size, ("Big Shoulders", "Bold"))
    # the name fills the width of the page, as on a poster (but never towers over it)
    size = min(size * (w - 2 * m) / max(1.0, wid), u * (0.42 if h > w else 0.3))
    wid, _ = _measure(words, size, ("Big Shoulders", "Bold"))
    col = ink if design == "mono" else (TEAL if not dark else (120, 200, 196))
    if design == "mono":
        x, yb = m, h - round(h * 0.16)
        al, ax = "\\an1", x
    else:  # centred: the letters close in on the middle
        x, yb = (w - wid) / 2, h * 0.5 + size * 0.35
        al, ax = "\\an2", w / 2
    # letters close in from wide spacing as they rise
    ev.append(f"Dialogue: 20,{_t(t0 + 0.15)},{_t(t1)},Card,,0,0,0,,{{{al}\\move({ax:.0f},{yb + size * 0.12:.0f},{ax:.0f},{yb:.0f},0,450)"
              f"\\fnBig Shoulders\\b1\\fs{size:.0f}\\bord0\\shad0\\1c{_ass(col)}\\fsp{size * 0.12:.0f}\\alpha&HFF&\\blur8"
              f"\\t(0,450,\\fsp0\\alpha&H00&\\blur0)\\fad(0,200)}}{_esc(words)}")
    if sub:
        if design == "mono":
            s = round(u * 0.024)
            ev.append(f"Dialogue: 20,{_t(t0 + 0.7)},{_t(t1)},Card,,0,0,0,,{{\\an1\\pos({x:.0f},{yb - size * 1.02:.0f})\\fnDM Mono\\b0\\fs{s}"
                      f"\\fsp{s * 0.9:.0f}\\bord0\\shad0\\1c{_ass(ink)}\\alpha&HFF&\\t(0,300,\\alpha&H00&)\\fad(0,200)}}{_esc(sub.upper())}")
        else:
            s = round(size * 0.24)
            sw, _ = _measure(sub, s, ("Libre Baskerville", "Regular"))
            sx, sy = (w - sw) / 2, yb + s * 1.6
            ev.append(f"Dialogue: 20,{_t(t0 + 0.8)},{_t(t1)},Card,,0,0,0,,{{\\an1\\pos({sx:.0f},{sy:.0f})\\fnLibre Baskerville\\b0\\fs{s}"
                      f"\\bord0\\shad0\\1c{_ass(ink)}\\alpha&HFF&\\t(0,300,\\alpha&H00&)\\fad(0,200)}}{_esc(sub)}")
            ly = round(sy + s * 0.25)
            ev.append(f"Dialogue: 19,{_t(t0 + 1.1)},{_t(t1)},Card,,0,0,0,,{{\\an7\\pos(0,0)\\bord0\\shad0\\1c{_ass(ink)}"
                      f"\\clip({sx:.0f},{ly - 5},{sx + 1:.0f},{ly + 5})\\t(0,350,\\clip({sx:.0f},{ly - 5},{sx + sw:.0f},{ly + 5}))\\fad(0,200)\\p1}}"
                      f"m {sx:.0f} {ly} l {sx + sw:.0f} {ly} l {sx + sw:.0f} {ly + 3} l {sx:.0f} {ly + 3}{{\\p0}}")
    acc = _rgb(accent)
    if design == "mono":  # a short accent bar draws out under the name
        bl = round(u * 0.18)
        by = round(yb + u * 0.02)
        ev.append(f"Dialogue: 19,{_t(t0 + 0.5)},{_t(t1)},Card,,0,0,0,,{{\\an7\\pos(0,0)\\bord0\\shad0\\1c{_ass(acc)}"
                  f"\\clip({x:.0f},{by},{x + 1:.0f},{by + 12})\\t(0,350,\\clip({x:.0f},{by},{x + bl:.0f},{by + 12}))\\fad(0,200)\\p1}}"
                  f"m {x:.0f} {by} l {x + bl:.0f} {by} l {x + bl:.0f} {by + 10} l {x:.0f} {by + 10}{{\\p0}}")
    return ev


def _wobble_ellipse(cx: float, cy: float, rx: float, ry: float, rng) -> str:
    """A hand-drawn loop: an ellipse that doesn't quite close, slightly lumpy."""
    pts = []
    turns = 1.12
    for i in range(41):
        t = i / 40 * turns * 2 * math.pi - 0.6
        k = 1 + 0.05 * math.sin(3 * t + rng.uniform(0, 1)) + 0.04 * (i / 40)
        pts.append((cx + rx * k * math.cos(t), cy + ry * k * math.sin(t)))
    return "m " + " l ".join(f"{x:.0f} {y:.0f}" for x, y in pts)


def mark_events(design: str, kind: str, px: float, py: float, label: str, t0: float, t1: float, w: int, h: int,
                accent: str, dark: bool, seed: int) -> list[str]:
    """A note on the picture. "paper": a red hand-drawn loop around the spot,
    a line out to a yellow tag. "mono": a dot, a hairline, a small mono label."""
    u = min(w, h)
    rng = random.Random(seed)
    ev = []
    right = px < w * 0.6
    lx = px + (u * 0.2 if right else -u * 0.2)
    ly = py - u * 0.12
    lx = min(max(lx, u * 0.06), w - u * 0.06)
    if design == "paper":
        if kind == "loop":
            r = u * 0.075
            path = _wobble_ellipse(px, py, r * 1.25, r, rng)
            ev.append(f"Dialogue: 22,{_t(t0)},{_t(t1)},Card,,0,0,0,,{{\\an7\\pos(0,0)\\1a&HFF&\\3c{MARK_RED}\\bord{u * 0.006:.1f}\\shad0"
                      f"\\clip(0,0,{px - r * 1.4:.0f},{h})\\t(0,420,\\clip(0,0,{w},{h}))\\fad(0,200)\\p1}}{path}{{\\p0}}")
        s = round(u * 0.032)
        tw, _ = _measure(label.upper(), s, ("Inter", "ExtraBold"))
        pad = s * 0.45
        x0 = lx if right else lx - tw - 2 * pad
        y0 = ly - s
        x1, y1 = x0 + tw + 2 * pad, ly + s * 0.3
        hl = _ass(_rgb(accent))
        ax = x0 if right else x1
        ev.append(f"Dialogue: 21,{_t(t0 + 0.25)},{_t(t1)},Card,,0,0,0,,{{\\an7\\pos(0,0)\\1a&HFF&\\3c&H00111111&\\bord{max(1.5, u * 0.0022):.1f}\\shad0"
                  f"\\alpha&HFF&\\t(0,200,\\alpha&H00&)\\fad(0,200)\\p1}}m {px:.0f} {py:.0f} l {ax:.0f} {(y0 + y1) / 2:.0f}{{\\p0}}")
        ev.append(f"Dialogue: 23,{_t(t0 + 0.35)},{_t(t1)},Card,,0,0,0,,{{\\an7\\pos(0,0)\\1c{hl}\\bord0\\shad0"
                  f"\\frz{rng.uniform(-3, 3):.1f}\\org({(x0 + x1) / 2:.0f},{(y0 + y1) / 2:.0f})\\fscx0\\fscy0\\t(0,180,\\fscx106\\fscy106)\\t(180,260,\\fscx100\\fscy100)\\fad(0,200)\\p1}}"
                  f"m {x0:.0f} {y0:.0f} l {x1:.0f} {y0:.0f} l {x1:.0f} {y1:.0f} l {x0:.0f} {y1:.0f}{{\\p0}}")
        ev.append(f"Dialogue: 24,{_t(t0 + 0.45)},{_t(t1)},Card,,0,0,0,,{{\\an1\\pos({x0 + pad:.0f},{y1 - s * 0.18:.0f})\\fnInter\\b1\\fs{s}"
                  f"\\bord0\\shad0\\1c&H00111111&\\alpha&HFF&\\t(0,160,\\alpha&H00&)\\fad(0,200)}}{_esc(label.upper())}")
    else:
        ink = "&H00EEEEEE&" if dark else "&H00111111&"
        s = round(u * 0.028)
        r = u * 0.009
        ev.append(f"Dialogue: 22,{_t(t0)},{_t(t1)},Card,,0,0,0,,{{\\an7\\pos(0,0)\\1c{ink}\\bord0\\shad0\\fad(150,200)\\p1}}"
                  f"m {px - r:.0f} {py:.0f} b {px - r:.0f} {py - r * 1.33:.0f} {px + r:.0f} {py - r * 1.33:.0f} {px + r:.0f} {py:.0f} "
                  f"b {px + r:.0f} {py + r * 1.33:.0f} {px - r:.0f} {py + r * 1.33:.0f} {px - r:.0f} {py:.0f}{{\\p0}}")
        ev.append(f"Dialogue: 21,{_t(t0 + 0.1)},{_t(t1)},Card,,0,0,0,,{{\\an7\\pos(0,0)\\1a&HFF&\\3c{ink}\\bord1.2\\shad0"
                  f"\\clip({min(px, lx) - 2:.0f},0,{min(px, lx) - 1:.0f},{h})\\t(0,300,\\clip(0,0,{w},{h}))\\fad(0,200)\\p1}}"
                  f"m {px:.0f} {py:.0f} l {lx:.0f} {ly:.0f}{{\\p0}}")
        tw, _ = _measure(label.upper(), s, ("DM Mono", "Regular"))
        tx = lx + u * 0.012 if right else lx - tw - u * 0.012
        tx = min(max(tx, u * 0.04), w - tw - u * 0.04)
        ev.append(f"Dialogue: 23,{_t(t0 + 0.3)},{_t(t1)},Card,,0,0,0,,{{\\an4\\pos({tx:.0f},{ly:.0f})\\fnDM Mono\\b0\\fs{s}"
                  f"\\bord0\\shad0\\1c{ink}\\alpha&HFF&\\t(0,200,\\alpha&H00&)\\fad(0,200)}}{_esc(label.upper())}")
    return ev


def scene_events(sc: dict, k: int, t0: float, t1: float, w: int, h: int, total: int) -> tuple[list[str], list[float]]:
    """Everything drawn over one designed scene, and the times its beats land."""
    from .story import _still

    design, accent = sc["_design"], sc.get("_accent", "#D4F01E")
    dark = bool(sc.get("dark"))
    u = min(w, h)
    vertical = h > w
    ev, beats = [], [t0]
    big = {re.sub(r"[^\w']", "", x.lower()) for p in sc.get("big_words") or [] for x in str(p).split()} - {""}
    words = sc.get("text") if sc["type"] in ("text", "title") else sc.get("caption")
    rect = None
    if has_print(sc):
        try:
            pic = _first_frame(sc["file"])
            rect = layout(w, h, bool(words), pic.width / max(1, pic.height))
        except Exception:
            rect = None
    if sc["type"] == "title" and not sc.get("file"):
        ev += title_events(sc.get("text", ""), sc.get("subtitle", ""), t0, t1, w, h, design, accent, dark)
        beats += [t0 + 0.15, t0 + 0.75]
    elif words:
        m = round(u * (0.085 if vertical else 0.07))
        if rect:
            x, y, pw, ph = rect
            if vertical:
                box = (m, round(h * 0.12), w - 2 * m, max(round(u * 0.2), y - round(h * 0.12) - round(u * 0.06)))
            else:
                box = (m, round(h * 0.18), x - 2 * m, round(h * 0.64))
        elif design == "paper" and sc["type"] != "text":
            box = (m, round(h * 0.62), w - 2 * m, round(h * 0.26))
        else:
            box = (m, round(h * 0.22), w - 2 * m, round(h * 0.56))
        align = "centre" if (design == "paper" and not (rect and not vertical)) else "left"
        e, lands = word_events(words, big, t0, t1, w, h, design, accent, box, dark, align=align, caps=design == "paper")
        ev += e
        beats += lands
    if rect:
        x, y, pw, ph = rect
        c = sc.get("callout")
        if c:
            ta = t0 + min(1.2, (t1 - t0) * 0.45)
            ev += mark_events(design, "loop", x + float(c["x"]) * pw, y + float(c["y"]) * ph, str(c["label"]), ta, t1, w, h, accent, dark, k)
            beats.append(ta)
        elif design == "mono":
            # a figure label under the print, the small print of a magazine page
            ta = t0 + min(1.4, (t1 - t0) * 0.5)
            s = round(u * 0.02)
            lab = f"FIG. {k + 1:02d}" + (f" — {sc['label']}" if sc.get("label") else "")
            ev.append(f"Dialogue: 18,{_t(ta)},{_t(t1)},Card,,0,0,0,,{{\\an7\\pos({x},{y + ph + round(u * 0.022)})\\fnDM Mono\\b0\\fs{s}"
                      f"\\bord0\\shad0\\1c&H00111111&\\alpha&HFF&\\t(0,250,\\alpha&H00&)\\fad(0,200)}}{_esc(lab.upper())}")
            beats.append(ta)
        else:
            # a hand-drawn arrow pointing in at the print
            ta = t0 + min(1.4, (t1 - t0) * 0.5)
            rng = random.Random(900 + k)
            side = 1 if k % 2 == 0 else -1
            ax = x + pw + u * 0.17 if side > 0 else x - u * 0.17
            ay = y + ph * 0.75
            tipx, tipy = (x + pw + u * 0.015, y + ph * 0.6) if side > 0 else (x - u * 0.015, y + ph * 0.6)
            mx, my = (ax + tipx) / 2 + rng.uniform(-1, 1) * u * 0.02, (ay + tipy) / 2 + u * 0.03
            hd = u * 0.04
            path = (f"m {ax:.0f} {ay:.0f} b {mx:.0f} {my:.0f} {mx:.0f} {my:.0f} {tipx:.0f} {tipy:.0f} "
                    f"m {tipx + side * hd:.0f} {tipy - hd * 0.3:.0f} l {tipx:.0f} {tipy:.0f} l {tipx + side * hd * 0.6:.0f} {tipy + hd:.0f}")
            ev.append(f"Dialogue: 22,{_t(ta)},{_t(t1)},Card,,0,0,0,,{{\\an7\\pos(0,0)\\1a&HFF&\\3c{MARK_RED}\\bord{u * 0.007:.1f}\\shad0"
                      f"\\alpha&HFF&\\t(0,200,\\alpha&H00&)\\fad(0,200)\\p1}}{path}{{\\p0}}")
            if sc.get("note"):
                s = round(u * 0.04)
                nw, _ = _measure(sc["note"], s, ("Nothing You Could Do", "Regular"))
                nx = ax + (u * 0.01 if side > 0 else -u * 0.01)
                if side > 0 and nx + nw > w - u * 0.03:
                    nx = w - u * 0.03 - nw
                if side < 0 and nx - nw < u * 0.03:
                    nx = u * 0.03 + nw
                ev.append(f"Dialogue: 22,{_t(ta + 0.2)},{_t(t1)},Card,,0,0,0,,{{\\an{7 if side > 0 else 9}\\pos({nx:.0f},{ay + u * 0.02:.0f})"
                          f"\\fnNothing You Could Do\\b0\\fs{s}\\bord0\\shad0\\1c{MARK_RED}\\alpha&HFF&\\t(0,250,\\alpha&H00&)\\fad(0,200)}}{_esc(sc['note'])}")
            beats.append(ta)
    return ev, beats
