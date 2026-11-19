"""Learn a style from reference clips: "make mine feel like these".

Give Venus a folder of videos you love (about five of one kind: your Vox-style
explainers, your favourite trailers). It measures what they have in common
and saves it as a style pack of your own, used like the built-in ones
(`cut --preset NAME`, `montage --style NAME`, `make --style NAME`):

- frame shape;
- pace: how long shots last, and from that how tight pauses and scene gaps are;
- how scenes change: hard cuts, dissolves or dips through black;
- colour: saturation, contrast, warmth, lifted or deep blacks, vignette,
  turned into a grade of its own;
- the accent colour that keeps coming back (titles, shapes, light);
- and a background and title animation that suit all of it.

It never copies anything out of the references: only these measurements.
Packs live in ~/.config/al-venus/packs (or $ALVENUS_PACKS)."""

from __future__ import annotations

import colorsys
import json
import os
import re
import statistics
import subprocess
from pathlib import Path

import numpy as np

from .media import duration, has_video, run, video_size
from .reference import _shape

VIDEO = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".mts"}
# What ordinary, ungraded footage measures (phone video of everyday scenes);
# a reference is graded by how far it sits from this.
NEUTRAL = {"saturation": 0.32, "spread": 0.78, "warmth": 0.0, "black": 0.03}


def packs_dir() -> Path:
    return Path(os.environ.get("ALVENUS_PACKS") or Path.home() / ".config" / "al-venus" / "packs")


def _thumbs(path: Path, fps: float = 25.0) -> np.ndarray:
    """Tiny grey frames (32x18), fps a second: enough to see shots change."""
    proc = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(path), "-an", "-vf",
                           f"fps={fps:g},scale=32:18:flags=area,format=gray", "-f", "rawvideo", "-"], capture_output=True)
    a = np.frombuffer(proc.stdout, np.uint8)
    return a[: len(a) // 576 * 576].reshape(-1, 18, 32).astype(np.float32) / 255


def _edits(path: Path, length: float, fps: float = 25.0) -> dict:
    """Where the picture changes to a new shot, and how: in one frame (a cut)
    or blended over several (a dissolve), or through black (a dip)."""
    f = _thumbs(path, fps)
    if len(f) < int(fps):
        return {"shots": 1, "hard": 0, "soft": 0, "dips": 0, "soft_seconds": 0.0}
    step = np.abs(np.diff(f, axis=0)).mean(axis=(1, 2))  # frame to frame
    half = int(fps * 0.5)
    wide = np.array([np.abs(f[min(len(f) - 1, k + half)] - f[max(0, k - half)]).mean() for k in range(len(f))])
    calm = float(np.median(step)) + 1e-4
    floor = max(0.05, 3 * float(np.percentile(wide, 20)))  # well above the quiet stretches inside shots
    events, k = [], 0
    while k < len(wide):  # each peak of change across a second is one change of shot
        if wide[k] > floor:
            j = k
            while j + 1 < len(wide) and wide[j + 1] > floor:
                j += 1
            peak = k + int(np.argmax(wide[k:j + 1]))
            if not events or peak - events[-1][0] > fps * 0.6:
                events.append((peak, k, j))
            k = j + 1
        else:
            k += 1
    hard = soft = dips = 0
    lens = []
    blacks = _black_moments(path, length)
    for peak, k, j in events:
        lo, hi = max(0, peak - half), min(len(step), peak + half)
        win = step[lo:hi]
        if any(abs(b - peak / fps) < 0.8 for b in blacks):
            dips += 1
        elif win.max() > 6 * calm and win.max() > 0.5 * win.sum() * 0.6:
            hard += 1  # nearly all the change happened between two frames
        else:
            soft += 1
            busy = win > max(2 * calm, 0.25 * win.max())
            lens.append(busy.sum() / fps)
    return {"shots": len(events) + 1, "hard": hard, "soft": soft, "dips": dips,
            "soft_seconds": round(float(statistics.median(lens)), 2) if lens else 0.0}


def _black_moments(path: Path, length: float) -> list[float]:
    err = run(["ffmpeg", "-nostdin", "-i", str(path), "-an", "-vf", "scale=160:-2,blackdetect=d=0.05:pix_th=0.12", "-f", "null", "-"]).stderr
    starts = [float(x) for x in re.findall(r"black_start:([\d.]+)", err)]
    return [x for x in starts if 0.3 < x < length - 0.3]


def _colour(path: Path, length: float, n: int = 12, size: tuple[int, int] | None = None, look: str = "") -> dict:
    """Colour facts over n frames across the clip, the whole frame (titles and
    shapes often sit near the edges)."""
    w, h = (90, 160) if size and size[1] > size[0] else (160, 90)
    step = max(length / n, 0.1)
    proc = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(path), "-vf",
                           f"fps=1/{step:.3f},scale={w * 2}:{h * 2}{',' + look if look else ''},scale={w}:{h}:flags=area,format=rgb24",
                           "-f", "rawvideo", "-"], capture_output=True)
    arr = np.frombuffer(proc.stdout, np.uint8)
    arr = arr[: len(arr) // (w * h * 3) * w * h * 3].reshape(-1, h, w, 3).astype(np.float32) / 255
    if not len(arr):
        return {}
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    mx, mn = arr.max(-1), arr.min(-1)
    sat = np.where(mx > 0.05, (mx - mn) / np.maximum(mx, 1e-3), 0)
    luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
    lo, hi = np.percentile(luma, 2), np.percentile(luma, 98)
    lit = luma > 0.15
    warmth = float(np.mean((r - b)[lit])) if lit.any() else 0.0
    shadows = luma < np.percentile(luma, 25)
    tint = (float(np.mean((r - b)[shadows])) if shadows.any() else 0.0)  # teal shadows read negative
    lights = luma > np.percentile(luma, 75)
    glow = float(np.mean((r - b)[lights])) if lights.any() else 0.0  # orange highlights read positive
    cy, cx = h // 2, w // 2
    centre = float(luma[:, cy - h // 4: cy + h // 4, cx - w // 4: cx + w // 4].mean())
    corner = float(np.mean([luma[:, :h // 5, :w // 6].mean(), luma[:, :h // 5, -w // 6:].mean(),
                            luma[:, -h // 5:, :w // 6].mean(), luma[:, -h // 5:, -w // 6:].mean()]))
    # the accent: a strong colour that keeps coming back
    flat = np.zeros(sat.shape, bool)  # strong colour in flat areas: graphics and titles, not busy detail
    flat[:, 1:-1, 1:-1] = (np.abs(arr[:, 1:-1, 1:-1] - arr[:, 1:-1, 2:]).max(-1) < 0.03) & \
                          (np.abs(arr[:, 1:-1, 1:-1] - arr[:, 2:, 1:-1]).max(-1) < 0.03)
    strong = (sat > 0.55) & (mx > 0.55) & flat
    # graphics are drawn in one exact colour, again and again; footage never is
    q = (arr[strong] * 15.99).astype(int)
    keys, counts = np.unique(q[:, 0] * 256 + q[:, 1] * 16 + q[:, 2], return_counts=True) if len(q) else (np.array([]), np.array([]))
    total = arr.shape[0] * h * w
    colours = [("#%02X%02X%02X" % (((k >> 8) & 15) * 17, ((k >> 4) & 15) * 17, (k & 15) * 17), int(c) / total)
               for k, c in sorted(zip(keys, counts), key=lambda x: -x[1])[:3] if c / total > 0.003]
    return {"saturation": float(np.mean(sat)), "spread": float(hi - lo), "black": float(lo), "white": float(hi),
            "warmth": warmth, "shadow_tint": tint, "highlight_tint": glow, "vignette": max(0.0, (centre - corner) / max(centre, 1e-3)),
            "colours": colours}


def measure(path: Path) -> dict:
    length = duration(path)
    w, h = video_size(path) or (0, 0)
    ed = _edits(path, length)
    return {"file": path.name, "seconds": round(length, 2), "shape": _shape(w, h) if w and h else None,
            "average_shot_seconds": round(length / max(1, ed["shots"]), 2), **ed, **_colour(path, length, size=(w, h))}


def _med(rows: list[dict], key: str, default: float = 0.0) -> float:
    vals = [r[key] for r in rows if isinstance(r.get(key), (int, float))]
    return float(statistics.median(vals)) if vals else default


def _lift(hex_rgb: str) -> str:
    """The measured colour, brought up to full strength for type and shapes."""
    r, g, b = (int(hex_rgb[i:i + 2], 16) / 255 for i in (1, 3, 5))
    hh, ss, vv = colorsys.rgb_to_hsv(r, g, b)
    return "#%02X%02X%02X" % tuple(round(x * 255) for x in colorsys.hsv_to_rgb(hh, max(ss, 0.7), max(vv, 0.92)))


def _settings(c: dict, base: dict | None = None) -> dict:
    """First guess at the grade, from how far `c` sits from `base` (what this
    footage measures; ordinary ungraded footage when unknown)."""
    b = {**NEUTRAL, "shadow_tint": 0.0, "highlight_tint": 0.0, "white": 0.97, **(base or {})}
    lift = c["black"] - b["black"]
    roll = b.get("white", 0.97) - c.get("white", 1.0)
    return {"sat": c["saturation"] / max(0.05, b["saturation"]),
            "con": c["spread"] / max(0.2, b["spread"]) / max(0.6, 1 - max(0, lift) - max(0, roll)),
            "warm": (c["warmth"] - b["warmth"]) * 0.6, "tint": (c.get("shadow_tint", 0.0) - b["shadow_tint"]) * 0.5,
            "glow": (c.get("highlight_tint", c["warmth"]) - b["highlight_tint"]) * 0.5, "lift": lift, "roll": roll,
            "vignette": c.get("vignette", 0) > 0.18 and (base or {}).get("vignette", 0) < 0.12}


_LIMITS = {"sat": (0.5, 1.7), "con": (0.7, 1.5), "warm": (-0.2, 0.2), "tint": (-0.35, 0.35), "glow": (-0.35, 0.35),
           "lift": (0.0, 0.14), "roll": (0.0, 0.12)}


def _filter(p: dict) -> str:
    p = {k: (max(_LIMITS[k][0], min(_LIMITS[k][1], v)) if k in _LIMITS else v) for k, v in p.items()}
    parts = []
    if max(abs(p["warm"]), abs(p["tint"]), abs(p["glow"])) > 0.01:
        parts.append(f"colorbalance=rs={p['tint']:.3f}:bs={-p['tint']:.3f}:rm={p['warm']:.3f}:bm={-p['warm']:.3f}"
                     f":rh={p['glow']:.3f}:bh={-p['glow']:.3f}")
    parts.append(f"eq=contrast={p['con']:.3f}:saturation={p['sat']:.3f}")
    if p["lift"] > 0.01 or p["roll"] > 0.01:
        parts.append(f"curves=all='0/{p['lift']:.3f} 0.5/{0.5 + p['lift'] / 2 - p['roll'] / 2:.3f} 1/{1 - p['roll']:.3f}'")
    if p["vignette"]:
        parts.append("vignette=PI/5")
    return ",".join(parts)


def grade(c: dict, base: dict | None = None) -> str:
    """An FFmpeg grade that moves footage toward the measured colour."""
    return _filter(_settings(c, base))


def fit(c: dict, footage: Path, rounds: int = 3) -> str:
    """A grade for this footage, checked by trying it: grade a few frames,
    measure them, correct what is still off, and again (a colourist's loop)."""
    length, size = duration(footage), video_size(footage)
    here = _colour(footage, length, size=size)
    if not here:
        return grade(c)
    p = _settings(c, here)
    for _ in range(rounds):
        got = _colour(footage, length, size=size, look=_filter(p))
        if not got:
            break
        p["sat"] *= c["saturation"] / max(0.03, got["saturation"])
        p["con"] *= c["spread"] / max(0.1, got["spread"])
        p["warm"] += (c["warmth"] - got["warmth"]) * 0.7
        p["tint"] += (c.get("shadow_tint", 0.0) - got["shadow_tint"]) * 0.6
        p["glow"] += (c.get("highlight_tint", c["warmth"]) - got["highlight_tint"]) * 0.6
        p["lift"] += (c["black"] - got["black"]) * 0.8
        p = {k: (max(_LIMITS[k][0], min(_LIMITS[k][1], v)) if k in _LIMITS else v) for k, v in p.items()}
    return _filter(p)


MATCH: dict[str, dict] = {}  # learned look name -> the references' colour, to match each piece of footage to


def matched(look: str, footage: Path | str) -> str | None:
    """For a learned look: a grade made for this footage, so it lands on the
    references' colour whatever it started as (None for other looks)."""
    if look not in MATCH:
        return None
    key = (look, str(footage))
    if key not in _seen:
        try:
            _seen[key] = fit(MATCH[look], Path(footage))
        except Exception:
            _seen[key] = grade(MATCH[look])
    return _seen[key]


_seen: dict[tuple[str, str], str] = {}


def learn(items: list[str], name: str, say=print) -> tuple[dict, Path, str]:
    files: list[Path] = []
    for it in items:
        p = Path(it)
        files += sorted(f for f in p.rglob("*") if f.suffix.lower() in VIDEO) if p.is_dir() else [p]
    files = [f for f in files if f.exists() and has_video(f)]
    if not files:
        raise SystemExit("no reference videos found")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,30}", name):
        raise SystemExit("--as NAME: lower-case letters, digits and dashes, e.g. my-vox")
    rows = []
    for f in files:
        say(f"   studying {f.name}")
        rows.append(measure(f))
    shapes = [r["shape"] for r in rows if r["shape"]]
    aspect = max(set(shapes), key=shapes.count) if shapes else "16:9"
    shot = _med(rows, "average_shot_seconds", 3.0)
    soft = sum(r["soft"] for r in rows) / max(1, sum(r["soft"] + r["hard"] for r in rows))
    dips = sum(r["dips"] for r in rows) / max(1, sum(r["shots"] - 1 for r in rows))
    soft_len = _med([r for r in rows if r["soft_seconds"]], "soft_seconds", 0.6)
    colour = {k: _med(rows, k) for k in ("saturation", "spread", "black", "white", "warmth", "shadow_tint", "highlight_tint", "vignette")}
    seen: dict[str, list[float]] = {}  # a colour that turns up in most of the references, in flat shapes
    for r in rows:
        for c, share in r.get("colours", []):
            seen.setdefault(c, []).append(share)
    common = [c for c, v in seen.items() if len(v) >= max(2, round(0.6 * len(rows)))]
    accent = (_lift(max(common, key=lambda c: (len(seen[c]), sum(seen[c])))) if common
              else ("#FFB35C" if colour["warmth"] > 0.04 else "#8FD3FF"))

    if dips > 0.3:
        transition, tsec = "dip", max(0.4, min(1.2, soft_len or 0.8))
    elif soft > 0.35:
        transition, tsec = "crossfade", max(0.3, min(1.2, soft_len))
    elif shot < 1.6:
        transition, tsec = "cut", 0.0
    else:
        transition, tsec = "cut", 0.0
    look = f"learned-{name}"
    if colour["saturation"] > NEUTRAL["saturation"] * 1.2:
        background = "orbs"
    elif colour["warmth"] > 0.05:
        background = "ink"
    elif colour["warmth"] < -0.03:
        background = "aurora"
    else:
        background = "spotlight" if colour["vignette"] > 0.18 else "dark"
    fast = shot < 2.0
    pack = {
        "about": f"Learned from {len(rows)} reference video(s): {aspect}, a shot every {shot:.1f} s, "
                 f"{'dissolves' if transition == 'crossfade' else 'dips to black' if transition == 'dip' else 'hard cuts'}, "
                 f"{describe_colour(colour)}.",
        "aspect": aspect, "captions": True, "caption_style": "pop" if fast else "classic",
        "max_pause": round(max(0.25, min(1.0, 0.12 * shot + 0.15)), 2), "beat": round(max(0.08, min(0.5, 0.05 * shot)), 2),
        "scene_beat": round(max(0.3, min(1.6, 0.25 * shot + 0.15)), 2), "look": look, "transition": transition,
        "music_lufs": -20.0 if fast else -24.0, "background": background,
        "title_style": "stamp" if shot < 1.3 else "block" if shot < 3.0 else "reveal", "accent": accent,
        "grade": grade(colour), "colour": {k: round(v, 4) for k, v in colour.items()}, "learned_from": [r["file"] for r in rows],
    }
    if tsec:
        pack["transition_seconds"] = round(tsec, 2)
    out = packs_dir() / f"{name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(pack, indent=2), encoding="utf-8")
    report = report_md(name, pack, rows, colour, shot, soft, dips)
    return pack, out, report


def describe_colour(c: dict) -> str:
    bits = []
    s = c["saturation"] / NEUTRAL["saturation"]
    bits.append("rich colour" if s > 1.2 else "muted colour" if s < 0.8 else "natural colour")
    if c["warmth"] > 0.05:
        bits.append("warm")
    elif c["warmth"] < -0.03:
        bits.append("cool")
    if c.get("shadow_tint", 0) < -0.03 and c["warmth"] > 0:
        bits.append("teal shadows")
    if c["black"] > 0.08:
        bits.append("soft, lifted blacks")
    elif c["spread"] > 0.88:
        bits.append("deep contrast")
    if c.get("vignette", 0) > 0.18:
        bits.append("darker edges")
    return ", ".join(bits)


def report_md(name: str, pack: dict, rows: list[dict], colour: dict, shot: float, soft: float, dips: float) -> str:
    lines = [f"# Style pack: {name}", "", pack["about"], "",
             f"Use it: `alvenus cut ... --preset {name}`, `alvenus montage ... --style {name}`, `alvenus make sb.json --style {name}`.", "",
             "## What Venus measured", "",
             "| video | shape | shot every | changes | colour | flat colours |", "|---|---|---|---|---|---|"]
    for r in rows:
        kind = f"{r['hard']} cut(s), {r['soft']} dissolve(s), {r['dips']} dip(s)"
        lines.append(f"| {r['file']} | {r['shape']} | {r['average_shot_seconds']} s | {kind} | "
                     f"{describe_colour({**NEUTRAL, **{k: r.get(k, 0) for k in ('saturation', 'spread', 'black', 'warmth', 'shadow_tint', 'vignette')}})} | "
                     f"{', '.join(c for c, _ in r.get('colours', [])) or '-'} |")
    lines += ["", "## What the pack sets", "",
              f"- Pace: pauses kept under {pack['max_pause']} s, {pack['scene_beat']} s between scenes (shots last about {shot:.1f} s).",
              f"- Scene changes: {pack['transition']}" + (f" ({pack.get('transition_seconds')} s)" if pack.get("transition_seconds") else "")
              + f" ({soft:.0%} of changes were soft, {dips:.0%} went through black).",
              f"- Colour grade: `{pack['grade']}`.",
              f"- Accent colour {pack['accent']}, {pack['background']} background, {pack['title_style']} titles, {pack['caption_style']} captions.",
              "", "Everything can be overridden as usual; the references themselves are never copied into your video."]
    return "\n".join(lines) + "\n"


def load_user_packs(presets: dict, looks: dict) -> None:
    """Make every learned pack usable by name, with its grade as a look."""
    d = packs_dir()
    if not d.is_dir():
        return
    for f in sorted(d.glob("*.json")):
        try:
            p = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        name = f.stem
        if name in presets and not presets[name].get("learned_from"):
            continue  # never shadow a built-in pack
        if p.get("grade") is not None:
            looks[f"learned-{name}"] = p["grade"]
        if isinstance(p.get("colour"), dict):
            MATCH[f"learned-{name}"] = p["colour"]
        presets[name] = {k: v for k, v in p.items() if k not in ("grade", "learned_from", "colour")} | {"learned_from": p.get("learned_from", [])}
