"""Read a reference video shot by shot ("make it like this one, and this one").

`alvenus study` measures a reference as a few averages. That flattens most
creative edits: a reel that starts as a strobe of flashes, rides the beat and
then slows to one small light reads as "fast cuts". Reading goes through the
whole clip frame by frame and writes down what an editor would notice:

- every cut, to the frame, and every shot's length (one-frame flashes too);
- what each shot is: a white or black flash, a negative of the shot before, a
  subject on a plain colour, a line drawing or blueprint, black and white,
  a two-colour poster, a colour pop, a dot (halftone) picture, a light burst;
- what is in it, when the free CLIP model is there: a face, a hand, a clock,
  space, words on screen... and how close the framing is;
- how it moves: still, busy, a pan, a push in or a pull out;
- its light and colour;
- the music: the beat, how many cuts land on it, the loud hits, the silences;
- the parts of the clip (a frantic open, a steady middle, a slow ending), each
  in plain words, and the whole shape in one sentence;
- a picture of every shot with its number, time, length and what it is, plus a
  timeline of the cuts against the beat, so an AI that can see checks it.

Nothing is copied out of the reference: only these readings. `alvenus blend`
then takes parts of one or more readings and cuts your own clips to them."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np

from .media import duration, frame_rate, has_video, video_size

W = 192  # frames are read this wide: enough to see what a shot is, fast to go through
VERSION = 2

# What a shot can be, in the words used everywhere (reading, recipe, report).
KINDS = {
    "white": "white flash",
    "black": "black frame",
    "solid": "flat colour frame",
    "negative": "negative of the shot before",
    "plain": "subject on a plain background",
    "lines": "line drawing",
    "blueprint": "blueprint (light lines on blue)",
    "chalk": "chalk (light lines on dark)",
    "mono": "black and white",
    "poster": "two- or three-colour poster",
    "pop": "colour pop (grey with one colour)",
    "dots": "dot (halftone) picture",
    "burst": "light burst",
    "fade": "fade",
}

# What CLIP is asked about each shot. Short, concrete words that an editor uses.
SUBJECTS = [
    "a person's face", "a person", "a crowd of people", "a hand", "an eye", "a child", "an astronaut",
    "a silhouette of a person", "a running figure", "a dancer", "an animal", "a bird", "a flower", "a plant",
    "a tree", "a forest", "the ocean", "a wave", "a beach", "mountains", "a desert", "the sky with clouds",
    "a sunset", "stars in space", "a planet", "a black hole", "the moon", "a city at night", "a city street",
    "a building", "a room", "a doorway", "a car", "a road", "a train", "a spaceship", "a clock", "a watch",
    "a phone", "a computer screen", "a book", "food", "a product on a table", "fire", "smoke", "rain",
    "lightning", "light rays", "a light bulb", "text on screen", "a logo", "a map", "a chart", "abstract shapes",
    "a pattern", "a painting", "a statue", "a mirror", "water drops", "a road at night", "a window",
]
FRAMING = {
    "extreme close-up": "an extreme close-up",
    "close-up": "a close-up",
    "medium shot": "a medium shot of a person from the waist up",
    "wide shot": "a wide shot of a scene",
    "aerial": "an aerial view from above",
}
MEDIUM = {
    "photo": "a real photograph",
    "film still": "a still from a movie",
    "drawing": "a pencil drawing",
    "3D render": "a 3D render",
    "cartoon": "a cartoon illustration",
    "graphic": "a flat graphic design",
}


# --- 1. frames ----------------------------------------------------------------

def frames(path: Path, width: int = W, fps_cap: float = 30.0) -> tuple[np.ndarray, float]:
    """Every frame (up to fps_cap a second), width px wide, as N x H x W x 3 uint8."""
    w0, h0 = video_size(path) or (16, 9)
    h = max(2, int(round(width * h0 / max(w0, 1) / 2)) * 2)
    fps = min(frame_rate(path), fps_cap) or 25.0
    raw = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(path), "-an", "-vf",
                          f"fps={fps:g},scale={width}:{h}:flags=area,format=rgb24", "-f", "rawvideo", "-"],
                         capture_output=True).stdout
    n = len(raw) // (width * h * 3)
    return np.frombuffer(raw[: n * width * h * 3], np.uint8).reshape(n, h, width, 3), fps


def _hist(f: np.ndarray) -> np.ndarray:
    q = (f[::2, ::2] // 32).reshape(-1, 3).astype(np.int32)
    h = np.bincount(q[:, 0] * 64 + q[:, 1] * 8 + q[:, 2], minlength=512).astype(np.float32)
    return h / h.sum()


def cuts_of(fr: np.ndarray, soft: set | None = None) -> list[int]:
    """Frame numbers where a new shot starts (never 0). Catches one-frame flashes:
    a flash is a shot of its own, cut in and cut out."""
    if len(fr) < 2:
        return []
    g = fr.astype(np.float32).mean(axis=3)
    d = np.abs(np.diff(g, axis=0)).mean(axis=(1, 2))  # frame i+1 against frame i
    hs = [_hist(f) for f in fr]
    hd = np.array([0.5 * np.abs(a - b).sum() for a, b in zip(hs, hs[1:])])
    med = float(np.median(d)) if len(d) else 0.0
    out = []
    for i in range(len(d)):
        local = np.median(d[max(0, i - 8): i + 9])
        strong = d[i] > max(14.0, 3.0 * local, 2.5 * med) and hd[i] > 0.22
        lone = d[i] > max(30.0, 4.0 * float(np.median(np.r_[d[max(0, i - 4): i], d[i + 1: i + 5]])) if len(d) > 1 else 30.0)
        if strong or hd[i] > 0.5 or (d[i] > 60 and hd[i] > 0.12) or lone:  # a jump on its own, not steady fast movement
            out.append(i + 1)
    mixes = [i for i in soft_cuts(g) if all(abs(i - c) > 4 for c in out)]
    if soft is not None:
        soft.update(mixes)
    return sorted(out + mixes)


def soft_cuts(g: np.ndarray, k: int = 6) -> list[int]:
    """Dissolves and quick cross-fades: over a few frames the picture turns from
    one steady shot into another, each frame in between a mix of the two (a pan or
    a zoom is not a mix, so it doesn't count)."""
    n, h = len(g), k // 2
    found: list[tuple[float, int]] = []
    for i in range(k, n - k):
        a, b = g[i - h], g[i + h]
        D = float(np.abs(b - a).mean())
        if D < 18:
            continue
        if float(np.abs(a - g[i - k]).mean()) > 0.3 * D or float(np.abs(b - g[min(n - 1, i + k)]).mean()) > 0.3 * D:
            continue  # not steady on both sides: movement, not a transition
        m, diff = g[i] - b, a - b
        alpha = float(np.clip((m * diff).sum() / ((diff * diff).sum() + 1e-6), 0, 1))
        if 0.15 < alpha < 0.85 and float(np.abs(m - alpha * diff).mean()) < 0.3 * D:
            found.append((D, i))
    keep: list[int] = []
    for D, i in sorted(found, reverse=True):
        if all(abs(i - j) > k for j in keep):
            keep.append(i)
    return sorted(keep)


# --- 2. what a shot is --------------------------------------------------------

def _sat(f: np.ndarray) -> np.ndarray:
    x = f.astype(np.float32) / 255
    mx, mn = x.max(-1), x.min(-1)
    return np.where(mx > 0.06, (mx - mn) / np.maximum(mx, 1e-3), 0)


def _luma(f: np.ndarray) -> np.ndarray:
    x = f.astype(np.float32)
    return 0.2126 * x[..., 0] + 0.7152 * x[..., 1] + 0.0722 * x[..., 2]


def _edges(l: np.ndarray) -> np.ndarray:
    gx = np.abs(np.diff(l, axis=1, prepend=l[:, :1]))
    gy = np.abs(np.diff(l, axis=0, prepend=l[:1]))
    return np.maximum(gx, gy)


def _palette(f: np.ndarray, k: int = 3) -> list[tuple[str, float]]:
    px = f.reshape(-1, 3).astype(np.float32)[:: max(1, len(f.reshape(-1, 3)) // 2500)]
    order = np.argsort(px.sum(1))
    c = px[order[np.linspace(0, len(px) - 1, k).astype(int)]].copy()  # dark, middle, light to start
    for _ in range(8):
        lab = np.argmin(((px[:, None] - c[None]) ** 2).sum(-1), axis=1)
        for j in range(k):
            if (lab == j).any():
                c[j] = px[lab == j].mean(0)
    share = np.bincount(lab, minlength=k) / len(px)
    return [("#%02X%02X%02X" % tuple(int(v) for v in c[j]), round(float(share[j]), 2)) for j in np.argsort(-share)]


def colour_name(hex_rgb: str) -> str:
    import colorsys

    r, g, b = (int(hex_rgb[i:i + 2], 16) / 255 for i in (1, 3, 5))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    if l < 0.1:
        return "black"
    if l > 0.92:
        return "white"
    if s < 0.18:
        return "grey" if 0.25 < l < 0.75 else ("dark grey" if l <= 0.25 else "light grey")
    names = [(0.03, "red"), (0.09, "orange"), (0.15, "amber"), (0.19, "yellow"), (0.42, "green"), (0.53, "teal"),
             (0.58, "cyan"), (0.7, "blue"), (0.79, "purple"), (0.92, "magenta"), (1.01, "red")]
    name = next(n for lim, n in names if h < lim)
    return ("dark " if l < 0.3 else "pale " if l > 0.75 else "") + name


def _dotty(l: np.ndarray) -> float:
    """Share of the frame made of small separate bright or dark dots (halftone)."""
    if l.shape[0] < 8 or l.shape[1] < 8:
        return 0.0
    c = l[2:-2, 2:-2]
    nb = [l[2 + dy: l.shape[0] - 2 + dy, 2 + dx: l.shape[1] - 2 + dx] for dy in (-2, 0, 2) for dx in (-2, 0, 2) if dy or dx]
    ring = np.mean(nb, axis=0)
    peak = (c - ring > 45) & (c >= np.max([l[2 + dy: l.shape[0] - 2 + dy, 2 + dx: l.shape[1] - 2 + dx]
                                          for dy in (-1, 0, 1) for dx in (-1, 0, 1)], axis=0))
    pit = (ring - c > 45) & (c <= np.min([l[2 + dy: l.shape[0] - 2 + dy, 2 + dx: l.shape[1] - 2 + dx]
                                          for dy in (-1, 0, 1) for dx in (-1, 0, 1)], axis=0))
    return float(max(peak.mean(), pit.mean()))


def _shift(a: np.ndarray, b: np.ndarray) -> tuple[float, float, float]:
    """How the picture moved from a to b: (dx, dy as a share of the frame, how sure 0..1)."""
    fa, fb = np.fft.fft2(a - a.mean()), np.fft.fft2(b - b.mean())
    r = fa * np.conj(fb)
    r /= np.maximum(np.abs(r), 1e-6)
    c = np.abs(np.fft.ifft2(r))
    y, x = np.unravel_index(np.argmax(c), c.shape)
    h, w = a.shape
    dy, dx = (y if y <= h // 2 else y - h), (x if x <= w // 2 else x - w)
    return -dx / w, -dy / h, float(c.max() / (c.mean() * 20 + 1e-6))


def _zoom(a: np.ndarray, b: np.ndarray) -> float:
    """Scale from a to b (>1 pushes in), checked against a few candidates."""
    from PIL import Image

    h, w = a.shape
    best, err0 = 1.0, float(np.abs(a - b).mean())
    best_err = err0
    for s in (0.8, 0.88, 0.94, 1.06, 1.14, 1.25):
        im = Image.fromarray(a.astype(np.uint8)).resize((max(2, int(w * s)), max(2, int(h * s))), Image.BILINEAR)
        x = np.asarray(im, np.float32)
        if s >= 1:
            oy, ox = (x.shape[0] - h) // 2, (x.shape[1] - w) // 2
            x = x[oy: oy + h, ox: ox + w]
            e = float(np.abs(x - b).mean())
        else:
            oy, ox = (h - x.shape[0]) // 2, (w - x.shape[1]) // 2
            e = float(np.abs(x - b[oy: oy + x.shape[0], ox: ox + x.shape[1]]).mean())
        if e < best_err:
            best, best_err = s, e
    return best if best_err < 0.85 * err0 else 1.0


def _corr(a: np.ndarray, b: np.ndarray) -> float:
    a, b = a - a.mean(), b - b.mean()
    return float((a * b).sum() / (np.sqrt((a * a).sum() * (b * b).sum()) + 1e-6))


def kinds_of(fr: np.ndarray, prev_last: np.ndarray | None) -> tuple[list[str], dict]:
    """What a shot is, from its frames (and the last frame of the shot before)."""
    from .cutout import border_colour

    mid = fr[len(fr) // 2]
    l = _luma(mid)
    sat = _sat(mid)
    lum, spread = float(l.mean()), float(l.std())
    k: list[str] = []
    facts: dict = {}
    if lum > 200 and float((l < 170).mean()) < 0.002:  # nothing in it at all (a small figure on white is "plain")
        k.append("white")
    elif lum < 30 and float((l > 60).mean()) < 0.002:
        k.append("black")
    elif spread < 11:
        k.append("solid")
    if prev_last is not None and not k:
        a, b = _luma(prev_last), _luma(fr[0])
        if _corr(255 - a, b) > 0.55 and _corr(a, b) < 0.1:
            k.append("negative")
    if not k or k == ["negative"]:
        bg, even = border_colour(mid)
        edge = _edges(l)
        lines = float((edge > 40).mean())
        flat_sat = float(sat.mean())
        dark_share, light_share = float((l < 80).mean()), float((l > 175).mean())
        q = (mid[::2, ::2] // 43).reshape(-1, 3)
        _, counts = np.unique(q[:, 0] * 36 + q[:, 1] * 6 + q[:, 2], return_counts=True)
        top = np.sort(counts)[::-1]
        few = int(np.searchsorted(np.cumsum(top) / top.sum(), 0.9) + 1)
        r, g, b_ = (float(mid[..., i].mean()) for i in range(3))
        differs = np.abs(mid.astype(np.float32) - bg).sum(-1) > 60
        if even < 30 and 0.002 < float(differs.mean()) < 0.8:
            k.append("plain")
            facts["background"] = "#%02X%02X%02X" % tuple(int(v) for v in bg)
            rows = np.nonzero(differs.any(axis=1))[0]
            facts["subject_height"] = round(float((rows[-1] - rows[0] + 1) / differs.shape[0]), 2)  # how big the subject stands
        if flat_sat < 0.12 and light_share > 0.55 and lines > 0.04 and dark_share < 0.3:
            k.append("lines")
        elif b_ > r + 25 and b_ > g and lines > 0.04 and light_share < 0.35:
            k.append("blueprint")
        elif flat_sat < 0.14 and dark_share > 0.55 and lines > 0.04 and light_share < 0.25:
            k.append("chalk")
        if flat_sat < 0.07 and not {"lines", "chalk", "plain"} & set(k):
            k.append("mono")
        elif few <= 3 and flat_sat > 0.15 and spread > 30:
            k.append("poster")
        grey = float((sat < 0.12).mean())
        strong = float(((sat > 0.5) & (l > 60)).mean())
        if grey > 0.7 and 0.012 < strong < 0.25 and "poster" not in k:
            k.append("pop")
            facts["pop_colour"] = colour_name("#%02X%02X%02X" % tuple(int(v) for v in mid[(sat > 0.5) & (l > 60)].mean(0)))
        if _dotty(l) > 0.02:
            k.append("dots")
        h, w = l.shape
        centre = float(l[h // 3: 2 * h // 3, w // 3: 2 * w // 3].mean())
        edge_l = float(np.mean([l[: h // 6].mean(), l[-h // 6:].mean(), l[:, : w // 6].mean(), l[:, -w // 6:].mean()]))
        if centre > 170 and centre > 1.7 * edge_l + 20:
            k.append("burst")
    # a fade: the light runs steadily down to black (or up out of it) through the shot
    if len(fr) >= 6:
        lm = np.array([_luma(f[::4, ::4]).mean() for f in fr])
        if (lm[-1] < 18 and lm[0] > 45 and np.all(np.diff(lm) < 4)) or (lm[0] < 18 and lm[-1] > 45 and np.all(np.diff(lm) > -4)):
            k.append("fade")
    return k, facts


def motion_of(fr: np.ndarray, fps: float) -> dict:
    g = fr.astype(np.float32).mean(axis=3)
    n = len(g)
    busy = float(np.abs(np.diff(g, axis=0)).mean()) if n > 1 else 0.0
    out = {"busy": round(busy, 1)}
    if n < 4:
        out["camera"] = "too short to tell"
        return out
    a, b = g[0], g[-1]
    dx, dy, sure = _shift(a, b)
    secs = n / fps
    z = _zoom(a, b)
    if z != 1.0 and abs(dx) < 0.08 and abs(dy) < 0.08:
        out["camera"] = "push in" if z > 1 else "pull out"
    elif sure > 1.0 and max(abs(dx), abs(dy)) / secs > 0.04:
        out["camera"] = ("pan right" if dx > 0 else "pan left") if abs(dx) >= abs(dy) else ("tilt down" if dy > 0 else "tilt up")
    else:
        out["camera"] = "still" if busy < 3 else "moving inside the frame" if busy < 14 else "very busy"
    return out


# --- 3. what is in the shot (CLIP) ------------------------------------------

_TEXT: dict = {}
SURE = 0.5  # below this CLIP is guessing: the shot's content is reported as unclear, never filled in


def _ask(images: list[np.ndarray]) -> list[dict] | None:
    """CLIP's best words for each picture, or None when the model can't be had."""
    try:
        from . import footage
    except Exception:
        return None
    try:
        if not (footage.model_dir() / "vision_model_quantized.onnx").exists():
            footage.fetch()
        if not _TEXT:
            for name, words in (("subject", SUBJECTS), ("framing", list(FRAMING.values())), ("medium", list(MEDIUM.values()))):
                _TEXT[name] = footage.embed_text(words)
        from PIL import Image

        arr = np.stack([np.asarray(Image.fromarray(im).resize((224, 224), Image.BICUBIC)) for im in images])
        emb = footage.embed_frames(arr)
    except Exception:
        return None
    out = []
    for e in emb:
        row: dict = {}
        for name, words in (("subject", SUBJECTS), ("framing", list(FRAMING)), ("medium", list(MEDIUM))):
            s = _TEXT[name] @ e * 100
            p = np.exp(s - s.max())
            p /= p.sum()
            order = np.argsort(-p)
            if name == "subject":  # only what the model is fairly sure of; otherwise say so
                row[name] = [SUBJECTS[i] for i in order[:2] if p[i] >= SURE]
                row["subject_sure"] = round(float(p[order[0]]), 2)
            else:
                row[name] = words[order[0]] if p[order[0]] >= 0.5 else ""
        out.append(row)
    return out


# --- 4. the music -------------------------------------------------------------

def music_of(path: Path, cut_times: list[float], length: float) -> dict | None:
    from .beats import SR, beat_grid, onset_envelope, HOP
    from .media import load_audio

    try:
        y = load_audio(path, SR)
    except Exception:
        return None
    if len(y) < SR // 2 or float(np.abs(y).max()) < 1e-3:
        return None
    period, first, conf = beat_grid(y)
    out: dict = {}
    if period > 0 and conf >= 0.1:
        beats = [float(t) for t in np.arange(first, len(y) / SR, period)]
        out["bpm"] = round(60 / period, 1)
        out["beat_seconds"] = round(period, 3)
        out["beats"] = [round(b, 3) for b in beats]

        def near(t: float, grid: float) -> float:
            k = (t - first) / grid
            return abs(k - round(k)) * grid

        tol = min(0.07, period / 6)
        if cut_times:
            out["cuts_on_beat"] = round(sum(near(t, period) < tol for t in cut_times) / len(cut_times), 2)
            out["cuts_on_half_beat"] = round(sum(near(t, period / 2) < tol for t in cut_times) / len(cut_times), 2)
            out["cuts_on_quarter_beat"] = round(sum(near(t, period / 4) < tol * 0.8 for t in cut_times) / len(cut_times), 2)
    env = onset_envelope(y, kick=True)
    if len(env) > 4:
        thr = np.percentile(env, 97)
        peaks = [i for i in range(1, len(env) - 1) if env[i] >= thr and env[i] >= env[i - 1] and env[i] >= env[i + 1]]
        hits, last = [], -1.0
        for i in peaks:
            t = i * HOP / SR
            if t - last > 0.18:
                hits.append(round(t, 2))
                last = t
        out["hits"] = hits[:60]
        if cut_times and hits:
            h = np.array(hits)
            out["cuts_on_hits"] = round(sum(float(np.abs(h - t).min()) < 0.06 for t in cut_times) / len(cut_times), 2)
    step = 0.25
    rms = [float(np.sqrt(np.mean(y[int(t * SR): int((t + step) * SR)] ** 2) + 1e-12)) for t in np.arange(0, length, step)]
    db = 20 * np.log10(np.array(rms) + 1e-9)
    top = np.percentile(db, 95) if len(db) else 0
    out["loudness_curve"] = [round(float(np.clip((d - (top - 30)) / 30, 0, 1)), 2) for d in db]  # 0..1 every quarter second
    quiet, start = [], None
    for i, d in enumerate(db):
        if d < top - 30:
            start = i if start is None else start
        elif start is not None:
            if (i - start) * step >= 0.3:
                quiet.append([round(start * step, 2), round(i * step, 2)])
            start = None
    if start is not None and (len(db) - start) * step >= 0.3:
        quiet.append([round(start * step, 2), round(length, 2)])
    out["silences"] = quiet
    return out


# --- 5. parts of the clip ------------------------------------------------------

def pace_word(sec: float) -> str:
    return ("strobe" if sec < 0.13 else "frantic" if sec < 0.3 else "fast" if sec < 0.6 else
            "steady" if sec < 1.5 else "slow" if sec < 3.5 else "held")


def sections(shots: list[dict], penalty: float = 2.6, min_shots: int = 3) -> list[tuple[int, int]]:
    """Split the shots into parts of one pace: [a, b) index ranges. A part
    changes where shot lengths change for good (not for one shot), and at a
    black or silent stop."""
    n = len(shots)
    if n <= min_shots:
        return [(0, n)]
    x = np.log(np.array([max(s["seconds"], 1 / 60) for s in shots]))
    cs, cs2 = np.concatenate([[0], np.cumsum(x)]), np.concatenate([[0], np.cumsum(x * x)])

    def cost(a: int, b: int) -> float:
        m = b - a
        mu = (cs[b] - cs[a]) / m
        return float(cs2[b] - cs2[a] - m * mu * mu)

    best = [0.0] + [np.inf] * n
    prev = [0] * (n + 1)
    for b in range(1, n + 1):
        for a in range(0, b):
            if b - a < min_shots and not (a == 0 and b == n):
                continue
            c = best[a] + cost(a, b) + penalty
            if c < best[b]:
                best[b], prev[b] = c, a
    if not np.isfinite(best[n]):
        return [(0, n)]
    out, b = [], n
    while b > 0:
        out.append((prev[b], b))
        b = prev[b]
    return out[::-1]


def _trend(sec: list[float]) -> str:
    if len(sec) < 4:
        return ""
    third = max(1, len(sec) // 3)
    a, b = float(np.median(sec[:third])), float(np.median(sec[-third:]))
    if b > 1.7 * a:
        return "slowing down"
    if a > 1.7 * b:
        return "speeding up"
    return ""


def describe_part(shots: list[dict], t0: float, t1: float) -> dict:
    sec = [s["seconds"] for s in shots]
    med = float(np.median(sec))
    count: dict[str, int] = {}
    for s in shots:
        for k in s["kinds"]:
            count[k] = count.get(k, 0) + 1
    subj: dict[str, int] = {}
    for s in shots:
        for w in s.get("subject", [])[:1]:
            subj[w] = subj.get(w, 0) + 1
    lum = [s["light"] for s in shots]
    cams: dict[str, int] = {}
    for s in shots:
        c = s["motion"].get("camera", "")
        if c and c not in ("too short to tell",):
            cams[c] = cams.get(c, 0) + 1
    words = [f"{pace_word(med)}: {len(shots)} shot{'s' if len(shots) != 1 else ''}, usually {med:.2f} s"
             + (f" ({int(np.median([s['frames'] for s in shots]))} frames)" if med < 0.5 else "")]
    tr = _trend(sec)
    if tr:
        words.append(tr + f" (from about {np.median(sec[:max(1, len(sec) // 3)]):.2f} s to {np.median(sec[-max(1, len(sec) // 3):]):.2f} s a shot)")
    if count:
        words.append(", ".join(f"{v}x {KINDS[k]}" for k, v in sorted(count.items(), key=lambda kv: -kv[1])))
    mixes = sum(1 for s in shots[1:] if s.get("enters") == "dissolve")
    if mixes:
        words.append(f"{mixes} of the changes are dissolves, not cuts")
    if len(lum) > 2 and float(np.std(lum)) > 55:
        words.append("the light flickers hard from shot to shot")
    else:
        m = float(np.mean(lum))
        words.append("dark" if m < 70 else "bright" if m > 170 else "mid-tone")
    if subj:
        words.append("mostly " + ", ".join(k for k, _ in sorted(subj.items(), key=lambda kv: -kv[1])[:3]))
    if cams:
        words.append("camera: " + ", ".join(k for k, _ in sorted(cams.items(), key=lambda kv: -kv[1])[:2]))
    return {"from": round(t0, 2), "to": round(t1, 2), "shots": [shots[0]["n"], shots[-1]["n"]], "pace": pace_word(med),
            "usual_shot_seconds": round(med, 3), "trend": tr, "kinds": count, "words": "; ".join(words)}


# --- 6. the whole reading -----------------------------------------------------

def read(path: Path, out_dir: Path | None = None, see: bool = True, say=print) -> dict:
    path = Path(path)
    out_dir = Path(out_dir) if out_dir else path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    if not has_video(path):
        raise SystemExit(f"{path.name}: no picture to read")
    say(f"reading {path.name}: every frame")
    fr, fps = frames(path)
    n = len(fr)
    length = n / fps if n else duration(path)
    mixes: set = set()
    cut = cuts_of(fr, mixes)
    bounds = [0] + cut + [n]
    shots: list[dict] = []
    for k, (a, b) in enumerate(zip(bounds, bounds[1:])):
        seg = fr[a:b]
        kinds, facts = kinds_of(seg, fr[a - 1] if a > 0 else None)
        mid = seg[len(seg) // 2]
        pal = _palette(mid)
        shots.append({"n": k + 1, "start": round(a / fps, 3), "seconds": round((b - a) / fps, 3), "frames": b - a,
                      "kinds": kinds, **facts, "light": round(float(_luma(mid).mean()), 1),
                      "colours": [colour_name(h) for h, s in pal if s > 0.12], "palette": pal,
                      "motion": motion_of(seg, fps), "enters": "dissolve" if a in mixes else "cut"})
    if see:
        say(f"   looking at {len(shots)} shots with CLIP")
        pics = [fr[(bounds[k] + bounds[k + 1]) // 2] for k in range(len(shots))]
        seen = _ask(pics)
        if seen is None:
            say("   (CLIP isn't here; shots are read by their light and shape only)")
        else:
            for s, r in zip(shots, seen):
                if not ({"white", "black", "solid"} & set(s["kinds"])):
                    s.update(r)
    cut_times = [round(c / fps, 3) for c in cut]
    say("   listening")
    music = music_of(path, cut_times, length)
    parts = []
    for a, b in sections(shots):
        sub = shots[a:b]
        t0, t1 = sub[0]["start"], sub[-1]["start"] + sub[-1]["seconds"]
        parts.append(describe_part(sub, t0, t1))
    w0, h0 = video_size(path) or (0, 0)
    from .reference import _shape

    sec = [s["seconds"] for s in shots]
    reading = {
        "version": VERSION, "file": str(path.resolve()), "name": path.stem, "seconds": round(length, 2),
        "frame": {"size": f"{w0}x{h0}", "shape": _shape(w0, h0) if w0 else "", "fps": round(fps, 2)},
        "shots_count": len(shots), "usual_shot_seconds": round(float(np.median(sec)), 3) if sec else 0,
        "shortest_shot_seconds": round(min(sec), 3) if sec else 0, "longest_shot_seconds": round(max(sec), 3) if sec else 0,
        "cuts": cut_times, "parts": parts, "ending": ending(shots, music, length), "music": music, "shots": shots,
    }
    try:
        from .learnstyle import _colour

        reading["colour"] = _colour(path, length, size=(w0, h0))
    except Exception:
        reading["colour"] = {}
    reading["in_one_line"] = arc(reading)
    stem = out_dir / path.stem
    Path(f"{stem}.read.json").write_text(json.dumps(reading, indent=1), encoding="utf-8")
    sheet(reading, fr, bounds, Path(f"{stem}.shots.jpg"))
    Path(f"{stem}.read.md").write_text(report(reading), encoding="utf-8")
    reading["_files"] = [f"{stem}.read.json", f"{stem}.read.md", f"{stem}.shots.jpg"]
    return reading


def ending(shots: list[dict], music: dict | None, length: float) -> str:
    if not shots:
        return ""
    last = shots[-1]
    k = set(last["kinds"])
    bits = []
    if "black" in k:
        bits.append(f"cuts to black for the last {last['seconds']:.2f} s")
    elif "white" in k:
        bits.append("ends on a white-out")
    elif "fade" in k:
        bits.append("fades to black")
    else:
        bits.append(f"holds the last shot {last['seconds']:.2f} s")
    if len(shots) > 3:
        before = float(np.median([s["seconds"] for s in shots[-4:-1]]))
        if before > 1.6 * float(np.median([s["seconds"] for s in shots[: max(1, len(shots) // 2)]])):
            bits.insert(0, "the cutting slows before the end")
    if music and music.get("silences"):
        s0, s1 = music["silences"][-1]
        if s1 >= length - 0.3:
            bits.append(f"the sound stops at {s0:.1f} s")
    return "; ".join(bits)


def arc(r: dict) -> str:
    bits = [f"{p['from']:.1f}-{p['to']:.1f} s {p['pace']}{(' and ' + p['trend']) if p['trend'] else ''}"
            + (f" ({', '.join(KINDS[k] for k, _ in sorted(p['kinds'].items(), key=lambda kv: -kv[1])[:2])})" if p["kinds"] else "") for p in r["parts"]]
    m = r.get("music") or {}
    beat = ""
    if m.get("bpm"):
        on = max(m.get("cuts_on_beat", 0), m.get("cuts_on_half_beat", 0))
        beat = f"; {m['bpm']:.0f} bpm, {round(on * 100)}% of cuts on the beat or half-beat"
    return f"{r['frame']['shape']}, {r['seconds']:.1f} s, {r['shots_count']} shots: " + "; then ".join(bits) + f"; {r['ending']}{beat}."


# --- 7. what to look at -------------------------------------------------------

def _font(size: int):
    from PIL import ImageFont

    f = Path(__file__).parent / "fonts" / "Inter-SemiBold.otf"
    try:
        return ImageFont.truetype(str(f), size)
    except OSError:
        return ImageFont.load_default()


TAG = {"white": "FLASH", "black": "BLACK", "solid": "COLOUR", "negative": "NEG", "plain": "PLAIN BG", "lines": "LINES",
       "blueprint": "BLUEPRINT", "chalk": "CHALK", "mono": "B&W", "poster": "POSTER", "pop": "POP", "dots": "DOTS",
       "burst": "BURST", "fade": "FADE"}


def sheet(r: dict, fr: np.ndarray, bounds: list[int], out: Path, cols: int = 10) -> None:
    """One picture per shot (number, start, length, what it is) under a timeline
    of the cuts against the beat."""
    from PIL import Image, ImageDraw

    shots = r["shots"]
    th = fr.shape[1] * 150 // fr.shape[2]
    if th > 180:  # tall frames: keep the cells a sensible size
        tw, th = int(150 * 180 / th), 180
    else:
        tw = 150
    cell_h = th + 34
    rows = (len(shots) + cols - 1) // cols
    width = cols * (tw + 6) + 6
    top = 150
    im = Image.new("RGB", (width, top + rows * cell_h + 6), (18, 18, 20))
    d = ImageDraw.Draw(im)
    f11, f13 = _font(11), _font(14)
    words, line, y = f"{r['name']}  ·  {r['in_one_line']}".split(), "", 4
    for w_ in words:  # wrap the one-line description across the top
        if d.textlength(line + " " + w_, font=f11) > width - 16:
            d.text((8, y), line, fill=(235, 235, 235), font=f11)
            line, y = w_, y + 13
        else:
            line = (line + " " + w_).strip()
    d.text((8, y), line, fill=(235, 235, 235), font=f11)
    # timeline: each shot a box as long as it lasts, in its own main colour, height = its light
    x0, x1, y0, y1 = 8, width - 8, 44, 104
    span = max(r["seconds"], 1e-3)
    for s in shots:
        a = x0 + (x1 - x0) * s["start"] / span
        b = x0 + (x1 - x0) * (s["start"] + s["seconds"]) / span
        col = tuple(int(s["palette"][0][0][i:i + 2], 16) for i in (1, 3, 5))
        hgt = 10 + (y1 - y0 - 10) * s["light"] / 255
        d.rectangle([a, y1 - hgt, max(a + 1, b - 1), y1], fill=col, outline=(90, 90, 90))
    m = r.get("music") or {}
    for t in m.get("beats", []):
        x = x0 + (x1 - x0) * t / span
        d.line([x, y1 + 2, x, y1 + 10], fill=(255, 210, 63))
    curve = m.get("loudness_curve") or []
    if curve:
        pts = [(x0 + (x1 - x0) * (i * 0.25) / span, y1 + 36 - 22 * v) for i, v in enumerate(curve)]
        d.line(pts, fill=(120, 200, 255), width=2)
    for j, p in enumerate(r["parts"]):
        x = x0 + (x1 - x0) * p["from"] / span
        d.line([x, y0 - 2, x, y1 + 40], fill=(255, 255, 255), width=2)
        d.text((x + 3, y1 + 28 + 13 * (j % 2)), f"{p['pace']}{' · ' + p['trend'] if p['trend'] else ''}", fill=(255, 255, 255), font=f11)
    d.text((x0, y1 + 12), "beats", fill=(255, 210, 63), font=f11)
    d.text((x0 + 40, y1 + 12), "loudness", fill=(120, 200, 255), font=f11)
    for k, s in enumerate(shots):
        cx, cy = 6 + (k % cols) * (tw + 6), top + (k // cols) * cell_h
        a, b = bounds[k], bounds[k + 1]
        pic = Image.fromarray(fr[(a + b) // 2]).resize((tw, th), Image.BILINEAR)
        im.paste(pic, (cx, cy))
        d.text((cx + 3, cy + 2), str(s["n"]), fill=(255, 255, 255), font=f13, stroke_width=2, stroke_fill=(0, 0, 0))
        tag = " ".join(TAG[x] for x in s["kinds"][:2])
        d.text((cx, cy + th + 2), f"{s['start']:.2f}s  {s['seconds']:.2f}s ({s['frames']}f)", fill=(200, 200, 200), font=f11)
        label = (s.get("subject") or [""])[0]
        if tag:
            d.text((cx, cy + th + 16), tag, fill=(255, 210, 63), font=f11)
            label = label and " " + label
            room = tw - d.textlength(tag, font=f11)
        else:
            room = tw
        while label and d.textlength(label, font=f11) > room:
            label = label[:-1]
        d.text((cx + tw - room, cy + th + 16), label, fill=(150, 150, 150), font=f11)
    im.save(out, quality=88)


def report(r: dict) -> str:
    m = r.get("music") or {}
    lines = [f"# Reading of {r['name']}", "", r["in_one_line"], "",
             f"Frame: {r['frame']['shape']} ({r['frame']['size']}, {r['frame']['fps']} fps). "
             f"{r['shots_count']} shots; usually {r['usual_shot_seconds']:.2f} s, from {r['shortest_shot_seconds']:.2f} s to {r['longest_shot_seconds']:.2f} s.",
             f"Every shot, numbered: {Path(r['_files'][2]).name if r.get('_files') else r['name'] + '.shots.jpg'}", ""]
    if m:
        bits = []
        if m.get("bpm"):
            bits.append(f"{m['bpm']:.0f} beats a minute")
            bits.append(f"cuts on the beat {round(m.get('cuts_on_beat', 0) * 100)}%, on the half-beat {round(m.get('cuts_on_half_beat', 0) * 100)}%, "
                        f"on a quarter {round(m.get('cuts_on_quarter_beat', 0) * 100)}%")
        if "cuts_on_hits" in m:
            bits.append(f"{round(m['cuts_on_hits'] * 100)}% of cuts land on a loud hit")
        if m.get("silences"):
            bits.append("silent at " + ", ".join(f"{a:.1f}-{b:.1f} s" for a, b in m["silences"]))
        lines += ["Music: " + "; ".join(bits) + ".", ""]
    lines += ["## Parts", ""]
    for p in r["parts"]:
        lines.append(f"- **{p['from']:.2f}-{p['to']:.2f} s** (shots {p['shots'][0]}-{p['shots'][1]}): {p['words']}.")
    lines += ["", f"Ending: {r['ending']}.", ""]
    c = r.get("colour") or {}
    if c:
        from .learnstyle import describe_colour

        try:
            lines += [f"Colour: {describe_colour(c)}", ""]
        except Exception:
            pass
    lines += ["## Every shot", "",
              "Measured (exact): when each shot starts, its length, its light and colours. Seen (best guesses, check the "
              "picture): what kind of shot it is, what's in it (with how sure), the camera. \"unclear\" means Venus couldn't tell.", "",
              "| # | at | length | what it is (seen) | in it (seen, how sure) | light, colour | movement (seen) |", "|---|---|---|---|---|---|---|"]
    for s in r["shots"]:
        what = ", ".join(KINDS[k] for k in s["kinds"]) or "-"
        if s.get("background"):
            what += f" ({colour_name(s['background'])})"
        if s.get("pop_colour"):
            what += f" ({s['pop_colour']})"
        if "subject_sure" in s:
            inside = (", ".join(s.get("subject", [])) + f" ({round(s['subject_sure'] * 100)}%)") if s.get("subject") else "unclear"
        else:
            inside = ""
        inside += (f"; {s['framing']}" if s.get("framing") else "") + (f"; {s['medium']}" if s.get("medium") else "")
        lines.append(f"| {s['n']} | {s['start']:.2f} | {s['seconds']:.2f} s ({s['frames']}f) | {what} | {inside or '-'} | "
                     f"{int(s['light'])}, {', '.join(s['colours'])} | {s['motion'].get('camera', '')} |")
    lines.append("")
    return "\n".join(lines)


def compare(readings: list[dict]) -> str:
    """Several references side by side, and the parts each is best at."""
    lines = ["# References side by side", ""]
    for i, r in enumerate(readings):
        lines.append(f"**{chr(65 + i)} = {r['name']}**: {r['in_one_line']}")
        for p in r["parts"]:
            lines.append(f"  - {chr(65 + i)} {p['from']:.1f}-{p['to']:.1f} s: {p['words']}")
        lines.append("")
    lines += ["To combine them, write a recipe (see `alvenus blend --help`): which part of which reference, in what order, "
              "what to take from it (rhythm, effects, light) and whose colour to use. A starting recipe that keeps each "
              "reference's parts in order is beside this file.", ""]
    return "\n".join(lines)


def starter_recipe(readings: list[dict], paths: list[str]) -> dict:
    """A first recipe for an AI to change with the person: every part, in order,
    nothing chosen for them (no look, no length)."""
    refs = {chr(65 + i): p for i, p in enumerate(paths)}
    parts = []
    for i, r in enumerate(readings):
        for p in r["parts"]:
            parts.append({"ref": chr(65 + i), "from": p["from"], "to": p["to"], "take": ["rhythm", "effects", "light"],
                          "why": p["words"]})
    shapes = {r["frame"]["shape"] for r in readings}
    return {"_how_to_use": "A starting point only: every part of every reference, in order. Ask the person which parts they "
                           "want, in what order, and fill in what they say; don't guess. 'take' any of rhythm (the cut lengths), "
                           "effects (what each shot is: flashes, negatives, line drawings, dots...), light (bright and dark from "
                           "shot to shot), content (the same kind of thing in the shot). 'look' is whose colour to grade with "
                           "(empty until they choose). 'shape' is empty when the references differ. 'length' stretches or "
                           "squeezes the whole thing to that many seconds. Then: alvenus blend RECIPE --clips YOUR_CLIPS "
                           "--music SONG --out OUT.mp4",
            "refs": refs, "parts": parts, "look": None, "shape": shapes.pop() if len(shapes) == 1 else None,
            "length": None, "on_beat": True}
