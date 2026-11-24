"""The creator's brand kit comes first.

A kit is a small JSON file: the brand's colours by name, and which one is the
background, the text and the accent (fonts too, if they have them):

    {"name": "My Studio",
     "colours": {"ivory": "#F4EFE6", "ink": "#151515", "deep blue": "#1F3A93"},
     "background": "ivory", "text": "ink", "accent": "deep blue",
     "fonts": {"heading": "fonts/Newsreader.ttf", "body": "fonts/HankenGrotesk.ttf"}}

Fonts are optional: a font file (best: it travels with the kit) or the name
of a font installed on this computer. The heading font is used for titles,
end cards and big words; the body font for captions, labels and charts.

Where Venus finds it: the storyboard's "brand" (a file path, or the kit
itself), else VENUS_HOME/brand.json (saved with `alvenus brand set`).

With a kit, Venus uses its accent wherever the video needs one, flags any
colour the storyboard asks for that isn't in the kit (the creator can say yes
to it once for this video), suggests a change only when the kit itself would
hurt the video (text that can't be read on its background), and after a
render looks for flat areas of colour (cards, backgrounds, type) that are
not the kit's colours or a blend of two of them."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import numpy as np

HEX = re.compile(r"^#?([0-9a-fA-F]{6})$")


def home_kit() -> Path:
    return Path(os.environ.get("VENUS_HOME") or Path.home() / ".venus") / "brand.json"


def hex_of(c: str) -> str | None:
    m = HEX.match(str(c).strip())
    return "#" + m.group(1).upper() if m else None


def load(ref=None, base: Path | None = None) -> dict | None:
    """The kit from a dict, a path, or the creator's saved one; None if there is none.
    ref=False means this video was asked to go without the kit."""
    if ref is False:
        return None
    kit = ref
    if isinstance(ref, (str, Path)):
        p = Path(ref)
        if not p.is_absolute() and base is not None:
            p = base / p
        kit = json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    elif ref is None:
        p = home_kit()
        kit = json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    if not isinstance(kit, dict) or not kit.get("colours"):
        return None
    cols = {str(k): hex_of(v) for k, v in kit["colours"].items()}
    kit["colours"] = {k: v for k, v in cols.items() if v}
    return kit if kit["colours"] else None


def role(kit: dict, name: str) -> str | None:
    """The hex colour for a role (background, text, accent), by its name in the kit or as a hex."""
    v = kit.get(name)
    if not v:
        return None
    return kit["colours"].get(str(v)) or hex_of(str(v))


# --- colour maths: sRGB -> Lab, so distances match what the eye sees -----------

def _lab(rgb: np.ndarray) -> np.ndarray:
    c = np.asarray(rgb, dtype=np.float64) / 255.0
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    m = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = c @ m.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], axis=-1)


def rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def distance_to_kit(pixels_rgb: np.ndarray, kit: dict) -> np.ndarray:
    """For each colour, how far (delta E) it is from the kit: from any kit colour,
    or any blend of two (soft edges, see-through layers and shadows are blends)."""
    labs = _lab(np.array([rgb(h) for h in kit["colours"].values()]))
    p = _lab(pixels_rgb).reshape(-1, 3)
    best = np.min(np.linalg.norm(p[:, None, :] - labs[None, :, :], axis=2), axis=1)
    for i in range(len(labs)):
        for j in range(i + 1, len(labs)):
            a, b = labs[i], labs[j]
            ab = b - a
            t = np.clip(((p - a) @ ab) / (ab @ ab or 1), 0, 1)
            best = np.minimum(best, np.linalg.norm(p - (a + t[:, None] * ab), axis=1))
    return best


def name_of(h: str) -> str:
    import colorsys

    from .read import colour_name

    hh, l, s_ = colorsys.rgb_to_hls(*(x / 255 for x in rgb(h)))
    if 0.02 < hh < 0.15 and s_ >= 0.18 and 0.1 <= l < 0.45:
        return "brown"
    return colour_name(h)


def contrast(a: str, b: str) -> float:
    def lum(h):
        c = np.array(rgb(h)) / 255.0
        c = np.where(c <= 0.03928, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def in_kit(h: str, kit: dict, tol: float = 10.0) -> bool:
    return float(distance_to_kit(np.array([rgb(h)]), kit)[0]) <= tol


# --- before anything is made ----------------------------------------------------

COLOUR_KEYS = ("accent", "colour", "color", "text_colour", "background_colour", "highlight")


def asked_colours(sb: dict) -> list[tuple[int, str, str]]:
    """(scene, key, hex) for every colour the storyboard asks for by hex (0 = whole video)."""
    out = []
    for i, d in enumerate([sb] + list(sb.get("scenes") or [])):
        for k in COLOUR_KEYS:
            if (h := hex_of(str(d.get(k) or ""))) is not None:
                out.append((i, k, h))
    return out


def board_findings(sb: dict, add, base: Path | None = None) -> dict | None:
    """Story-check notes about the brand. Returns the kit in use (or None)."""
    try:
        kit = load(sb.get("brand"), base)
    except (OSError, ValueError):
        add("brand-unreadable", "weak", 0, "the brand kit file can't be read", "fix the JSON, or take \"brand\" out")
        return None
    if not kit:
        return None
    ok = {hex_of(x) for x in sb.get("brand_exceptions") or [] if hex_of(x)}
    for i, k, h in asked_colours(sb):
        if h not in ok and not in_kit(h, kit):
            cols = ", ".join(f"{n} {v}" for n, v in kit["colours"].items())
            add("off-brand", "weak", i, f"{k} {h} ({name_of(h)}) is not in the brand kit",
                f"use a kit colour ({cols}); if the creator wants {h} for this video, add it to \"brand_exceptions\"")
    bg, tx = role(kit, "background"), role(kit, "text")
    if bg and tx and contrast(bg, tx) < 4.5:
        add("brand-contrast", "note", 0, f"the kit's text ({tx}) on its background ({bg}) is hard to read (contrast {contrast(bg, tx):.1f}:1)",
            "suggest to the creator a darker text or lighter background from their kit for this video; ask once, keep the kit otherwise")
    return kit


def apply(sb: dict, kit: dict | None, base: Path | None = None) -> None:
    """Fill what the storyboard leaves open with the kit (never overrides what it says)."""
    if not kit:
        return
    if not sb.get("accent") and (a := role(kit, "accent")):
        sb["accent"] = a
    sb["_branded"] = True
    if isinstance(kit.get("fonts"), dict) and not sb.get("fonts"):
        sb["fonts"] = {k: _abs(v, base) for k, v in kit["fonts"].items() if v}


def _abs(v, base: Path | None) -> str:
    p = Path(str(v)).expanduser()
    if p.suffix.lower() in (".ttf", ".otf") and not p.is_absolute() and base is not None:
        p = base / p
    return str(p) if p.suffix.lower() in (".ttf", ".otf") else str(v)


# which of Venus's own fonts each of the creator's replaces
FONT_ROLES = {"heading": ("Inter Display Black", "Instrument Serif"), "body": ("Inter ExtraBold", "Inter SemiBold")}


def font_family(path: Path) -> str | None:
    """The family name inside a font file (what the renderer looks it up by)."""
    try:
        from PIL import ImageFont

        return ImageFont.truetype(str(path), 20).getname()[0]
    except Exception:
        return None


def installed(name: str) -> bool:
    import shutil
    import subprocess

    from .style import FONT_FILES

    if name in FONT_FILES:
        return True
    if not shutil.which("fc-list"):
        return False
    out = subprocess.run(["fc-list", ":", "family"], capture_output=True, text=True).stdout
    return any(name.lower() == f.strip().lower() for line in out.splitlines() for f in line.split(","))


def font_setup(fonts: dict | None) -> list[str]:
    """Use the creator's fonts for everything on screen (style.FONT_MAP), or
    say plainly why one can't be used. Call reset_fonts() when done."""
    from . import style

    reset_fonts()
    notes = []
    for role_name, value in (fonts or {}).items():
        if role_name not in FONT_ROLES or not value:
            continue
        v = str(value)
        if v.lower().endswith((".ttf", ".otf")):
            p = Path(v).expanduser()
            fam = font_family(p) if p.exists() else None
            if not fam:
                notes.append(f"{role_name} font: {p.name} can't be read here, so Venus's own font is used instead")
                continue
            style.KIT_FILES[fam] = p
        else:
            fam = v
            if not installed(fam):
                notes.append(f"{role_name} font: \"{fam}\" isn't installed on this computer, so Venus's own font is used instead. "
                             "Put the font file's path in the brand kit, and it will travel with the kit")
                continue
        for ours in FONT_ROLES[role_name]:
            style.FONT_MAP[ours] = fam
        notes.append(f"{role_name} font: {fam} (from the brand kit)")
    return notes


def reset_fonts() -> None:
    from . import style

    style.FONT_MAP.clear()
    style.KIT_FILES.clear()


# --- after the render -------------------------------------------------------------

def check_video(video: Path, kit: dict, every: float = 1.0, tol: float = 14.0, share: float = 0.03) -> list[str]:
    """Flat areas of colour (cards, backgrounds, type) in the finished video that are not
    the kit's colours or a blend of them. Photos and footage have texture and are left out."""
    import subprocess

    from .media import duration

    total = duration(video)
    w, h = 160, 90
    raw = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(video), "-vf", f"fps={1 / every:g},scale={w}:{h}:flags=area",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    n = len(raw) // (w * h * 3)
    frames = np.frombuffer(raw[: n * w * h * 3], dtype=np.uint8).reshape(n, h, w, 3)
    found: dict[str, list[float]] = {}
    for k, f in enumerate(frames):
        lum = f.mean(axis=2)
        pad = np.pad(lum, 1, mode="edge")
        local = np.max([np.abs(pad[1 + dy: 1 + dy + h, 1 + dx: 1 + dx + w] - lum) for dy in (-1, 0, 1) for dx in (-1, 0, 1)], axis=0)
        flat = local < 3
        if flat.mean() < share:
            continue
        q = (f[flat] // 16).astype(np.int32)
        keys, counts = np.unique(q[:, 0] * 256 + q[:, 1] * 16 + q[:, 2], return_counts=True)
        for key, cnt in zip(keys, counts):
            if cnt < share * w * h:
                continue
            c = np.array([key // 256, (key // 16) % 16, key % 16]) * 16 + 8
            if float(distance_to_kit(c[None, :], kit)[0]) > tol:
                hx = "#%02X%02X%02X" % tuple(int(x) for x in c)
                found.setdefault(hx, []).append(round(min(total, k * every), 1))
    out = []
    for hx, ts in sorted(found.items(), key=lambda kv: -len(kv[1]))[:5]:
        when = ", ".join(f"{int(t // 60)}:{t % 60:04.1f}" for t in ts[:6]) + (" ..." if len(ts) > 6 else "")
        out.append(f"off-brand colour {hx} ({name_of(hx)}) fills part of the frame at {when}: not in the brand kit. "
                   f"If it is a graphic, change it to a kit colour; if it is footage, ignore this")
    return out
