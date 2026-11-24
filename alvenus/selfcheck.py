"""Self-review: Venus watches its own video before anyone else does.

It checks what a careful editor would on a last pass:
- text on screen long enough to read, and readable against what is behind it
- no stretch of black picture left in by mistake
- no rapid flashing (more than three flashes in a second can harm people
  with photosensitive epilepsy, so broadcasters screen for it)
- sound and picture the same length and starting together, and no dead silence
- pace: no lone shot too quick to see, and a video cut to the beat stays on it

Everything runs locally with FFmpeg and numpy."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import numpy as np

from .media import run

SMALL = (64, 36)
CAPTION_STYLES = {"Cap", "CapBox"}  # captions follow the voice, so they are read as they are heard


class Finding(str):
    """A plain-language problem that also says what kind it is and when, so
    Venus can fix it: kind is reading, contrast, black, flash, sync, silence or pace."""

    def __new__(cls, text: str, kind: str, times=(), **extra):
        f = super().__new__(cls, text)
        f.kind, f.times, f.extra = kind, list(times), extra
        return f


def _probe(video: Path) -> dict:
    out = run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,start_time,duration,width,height,r_frame_rate",
               "-show_entries", "format=duration", "-of", "json", str(video)]).stdout
    return json.loads(out)


def _secs(t: str) -> float:
    h, m, s = t.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def text_events(ass: Path) -> list[tuple[float, float, str, str]]:
    """(start, end, style, plain text) for every event that shows words."""
    out = []
    for row in ass.read_text(encoding="utf-8").splitlines():
        if not row.startswith("Dialogue:"):
            continue
        parts = row[len("Dialogue:"):].split(",", 9)
        if len(parts) < 10:
            continue
        raw = parts[9]
        if "\\p1" in raw:  # a drawing (bar, block, chart shape), not words
            raw = re.sub(r"\\p1.*?(\\p0|$)", "", raw)
        if "\\alpha&HFF&" in raw and "\\t(" not in raw:  # an invisible spacer word
            continue
        text = re.sub(r"\{[^}]*\}", "", raw).replace("\\N", " ").replace("\\h", " ").strip()
        if text:
            out.append((_secs(parts[1].strip()), _secs(parts[2].strip()), parts[3].strip(), text))
    return out


def _norm(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def _reading(events, total: float, spoken=()) -> list[str]:
    """Each piece of silent text must stay up long enough to read: half a
    second to find it, then about 0.28 s a word (roughly 215 words a minute).
    Captions and anything that repeats a spoken line are heard as they are read."""
    said = [set(_norm(x)) for x in spoken]
    seen: dict[str, float] = {}
    first: dict[str, float] = {}
    for t0, t1, style, text in events:
        if t1 - t0 < 0.25:  # one frame of an animation (a counter ticking up), not text to read
            continue
        words = _norm(text)
        if style in CAPTION_STYLES or (words and any(sum(x in s for x in words) >= 0.8 * len(words) for s in said)):
            continue
        end = min(t1, total)
        seen[text] = max(seen.get(text, 0.0), end - t0)  # kinetic lines repeat the text per word
        first.setdefault(text, t0)
    notes = []
    for text, shown in seen.items():
        need = 0.5 + 0.28 * len(text.split())
        if shown < need:
            short = text if len(text) <= 40 else text[:37] + "..."
            notes.append(Finding(f"text \"{short}\" is on screen {shown:.1f}s; it needs about {need:.1f}s to read",
                                 "reading", [first[text]], need=need, shown=shown))
    return notes


def _gray(cmd: list[str], w: int, h: int) -> np.ndarray:
    proc = subprocess.run(cmd + ["-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True)
    if proc.returncode != 0 or not proc.stdout:
        return np.zeros((0, h, w), np.uint8)
    return np.frombuffer(proc.stdout, np.uint8).reshape(-1, h, w)


def _dilate(m: np.ndarray, r: int) -> np.ndarray:
    out = m.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dx * dx + dy * dy <= r * r:
                out |= np.roll(np.roll(m, dy, 0), dx, 1)
    return out


def _contrast(video: Path, ass: Path, events, w: int, h: int, total: float) -> list[str]:
    """Render the text layer alone, over black and over white, to find every
    pixel it touches (and whether any of it runs off the frame). In the finished frame, letters with their own light and
    dark (an outline, or words on a plate) read over anything; plain letters
    are compared with what is just around them."""
    from .style import FONTS, fonts_dir  # noqa: F401

    esc = lambda p: str(p).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")
    # letters only: shapes (chart fills, lines, dots, plates drawn as their own
    # events) are pictures, not text, and would be measured as if they were words
    import tempfile

    rows = ass.read_text(encoding="utf-8").splitlines()
    cam = next((r.split(": ", 1)[1] for r in rows if r.startswith("; venus-camera: ")), "")
    letters = Path(tempfile.mkdtemp()) / "letters.ass"
    letters.write_text("\n".join("Comment:" + r[9:] if r.startswith("Dialogue:") and "\\p1" in r else r for r in rows),
                       encoding="utf-8")
    ass = letters
    times = []
    for t0, t1, _, _ in sorted(events):
        t = t0 + min(0.9, (min(t1, total) - t0) / 2)
        if t < total - 0.05 and (not times or t - times[-1] > 0.6):
            times.append(t)
    if len(times) > 30:
        times = [times[round(i * (len(times) - 1) / 29)] for i in range(30)]
    sw, sh = w, h  # full size: thin outlines blur into the letters when shrunk
    r = max(2, round(min(sw, sh) * 0.006))
    bad, cut_off = [], []
    def layer(t: float, bg: str) -> np.ndarray:
        return _gray(["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i", f"color={bg}:s={w}x{h}:r=25:d=0.04",
                      "-vf", f"setpts=PTS+{t:.3f}/TB,subtitles='{esc(ass)}':fontsdir='{esc(fonts_dir())}',scale={sw}:{sh}"
                      + (f",perspective={cam.replace('(TIME)', f'({t:.3f})')}:interpolation=linear" if cam else ""),
                      "-frames:v", "1"], sw, sh)

    for t in times:
        on_black, on_white = layer(t, "black"), layer(t, "white")
        frame = _gray(["ffmpeg", "-nostdin", "-v", "error", "-ss", f"{t:.3f}", "-i", str(video), "-vf", f"scale={sw}:{sh}",
                       "-frames:v", "1"], sw, sh)
        if not len(on_black) or not len(on_white) or not len(frame):
            continue
        kb, kw = on_black[0].astype(np.int16), on_white[0].astype(np.int16)
        text = (kb > 24) | (kw < 231)  # every pixel the text layer touches, see-through or not
        if text.sum() < 40 or text.mean() > 0.4:  # nothing, or a full-screen card
            continue
        band = text[int(0.05 * sh):int(0.95 * sh)]  # the progress line along the bottom may touch the sides
        if band[:, :2].any() or band[:, -2:].any():
            cut_off.append(t)
        f = frame[0].astype(np.int16)
        lo, hi = np.percentile(f[text], [5, 95])
        if hi - lo > 90:  # letters against their own outline or plate: readable over anything
            continue
        ring = _dilate(text, r) & ~text
        if ring.sum() < 20:
            continue
        on, around = float(np.median(f[text])), float(np.median(f[ring]))
        if abs(on - around) < 55:
            bad.append((t, on, around))
    letters.unlink()
    letters.parent.rmdir()
    notes = []
    for t, on, around in bad[:6]:
        notes.append(Finding(f"text at {t:.1f}s is hard to read: it is {'about as bright as' if abs(on - around) < 25 else 'too close in brightness to'} "
                             f"what is behind it", "contrast", [t]))
    if cut_off:
        notes.append(Finding(f"text runs off the edge of the frame at {cut_off[0]:.1f}s"
                             + (f" (and {len(cut_off) - 1} more places)" if len(cut_off) > 1 else ""), "edge", cut_off))
    if len(bad) > 6:
        notes.append(Finding(f"...and {len(bad) - 6} more places with hard-to-read text", "contrast", [b[0] for b in bad[6:]]))
    return notes


def _picture(video: Path, fps: float, total: float) -> list[str]:
    w, h = SMALL
    frames = _gray(["ffmpeg", "-nostdin", "-v", "error", "-i", str(video), "-vf", f"scale={w}:{h}"], w, h)
    if not len(frames):
        return ["could not read the picture"]
    notes = []
    # Black: nearly every pixel at black level.
    black = (frames < 34).mean(axis=(1, 2)) > 0.98
    runs, start = [], None
    for i, b in enumerate(list(black) + [False]):
        if b and start is None:
            start = i
        elif not b and start is not None:
            runs.append((start / fps, i / fps))
            start = None
    for a, b in runs:
        long = b - a
        if a < 0.05 and long > 0.35:
            notes.append(Finding(f"the video opens on {long:.1f}s of black", "black", [a]))
        elif b > total - 0.1 and long < 2.5:
            continue  # a fade out at the end
        elif long > 1.2:
            notes.append(Finding(f"{long:.1f}s of black picture at {a:.1f}s", "black", [a]))
    # Flashing: big swings in overall brightness that reverse; count flashes per second.
    mean = frames.reshape(len(frames), -1).mean(axis=1)
    d = np.diff(mean)
    swings = [(i, np.sign(x)) for i, x in enumerate(d) if abs(x) > 28]
    flips = [i for (i, s), (_, s0) in zip(swings[1:], swings[:-1]) if s != s0]
    win = max(1, round(fps))
    worst, at = 0, 0.0
    for k, i in enumerate(flips):
        n = sum(1 for j in flips[k:] if j - i < win)
        if n > worst:
            worst, at = n, i / fps
    if worst / 2 > 3:
        notes.append(Finding(f"about {worst // 2} bright flashes in one second at {at:.1f}s; more than 3 a second can trigger seizures",
                             "flash", [at]))
    return notes


def _sound(video: Path, info: dict, total: float) -> list[str]:
    streams = info.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if not a:
        return ["no sound track"]
    notes = []
    vd, ad = float(v.get("duration") or total), float(a.get("duration") or total)
    vs, as_ = float(v.get("start_time") or 0), float(a.get("start_time") or 0)
    if abs(vd - ad) > 0.15:
        notes.append(Finding(f"sound and picture differ in length by {abs(vd - ad):.2f}s", "sync"))
    if abs(vs - as_) > 0.05:
        notes.append(Finding(f"sound starts {as_ - vs:+.2f}s from the picture", "sync"))
    from .media import load_audio

    y = load_audio(video, 8000)
    if len(y):
        hop = 800  # 0.1 s
        rms = np.sqrt(np.convolve(y ** 2, np.ones(hop) / hop, "valid")[::hop] + 1e-12)
        quiet = 20 * np.log10(rms) < -80  # digital silence, not a quiet room
        run_len = longest = 0
        where = 0.0
        for i, q in enumerate(quiet):
            run_len = run_len + 1 if q else 0
            if run_len > longest:
                longest, where = run_len, (i - run_len + 1) * 0.1
        if longest * 0.1 >= 1.0:
            notes.append(Finding(f"{longest * 0.1:.1f}s of dead silence at {where:.1f}s", "silence", [where]))
    return notes


def _pace(video: Path, total: float) -> list[str]:
    """Pace: a shot too quick to take in on its own, and stretches where a video
    cut to the beat drifts off it."""
    from .read import cuts_of, frames

    fr, fps = frames(video, width=96, fps_cap=25.0)
    if len(fr) < 10:
        return []
    cuts = [c / fps for c in cuts_of(fr)]
    edges = [0.0] + cuts + [total]
    lens = [b - a for a, b in zip(edges, edges[1:])]
    notes = []
    def plain(t0: float, t1: float) -> bool:  # a white flash or a dip to black is a transition, not a shot
        m = float(fr[int(t0 * fps): max(int(t0 * fps) + 1, int(t1 * fps))].mean())
        return m > 225 or m < 30
    blips = [edges[i] for i in range(1, len(lens) - 1) if lens[i] < 0.4 and lens[i - 1] >= 1.0 and lens[i + 1] >= 1.0
             and not plain(edges[i], edges[i + 1])]
    if blips:
        when = ", ".join(f"{t:.1f}s" for t in blips[:5])
        notes.append(Finding(f"{'a shot' if len(blips) == 1 else f'{len(blips)} shots'} too quick to take in ({when}): under 0.4 s "
                             "between longer shots, so the eye catches a flicker, not a picture. Hold it longer, or make it part of a run of quick cuts",
                             "pace", blips))
    notes += _repeats(fr, fps, edges, plain)
    if len(cuts) >= 8:
        try:
            from .beats import SR, beat_grid
            from .media import load_audio

            period, first, conf = beat_grid(load_audio(video, SR))
        except Exception:
            return notes
        if period > 0 and conf >= 0.25:
            grid = period / 2  # cuts on the beat or the half beat
            on = [abs(((c - first) / grid) - round((c - first) / grid)) * grid <= 0.07 for c in cuts]
            if sum(on) >= 0.6 * len(on):  # this video is cut to the music: hold it to that everywhere
                k = 0
                while k + 4 <= len(on):
                    if sum(on[k:k + 4]) <= 1:
                        j = k + 4
                        while j < len(on) and not on[j]:
                            j += 1
                        notes.append(Finding(f"the cuts drift off the beat from {cuts[k]:.1f}s to {cuts[j - 1]:.1f}s, while the rest land on it",
                                             "pace", [cuts[k]]))
                        k = j
                    else:
                        k += 1
    return notes


def _type(ass: Path, w: int, h: int) -> list:
    """Clean type: every caption card inside the safe area (clear of the frame's
    edges and, on tall videos, of the app's caption area and buttons), rows of
    even length, and no word left alone on a row of its own. Read from the
    caption layout itself, measured with the fonts on screen."""
    from .placement import safe_box
    from .style import text_width

    L, T, R, B = safe_box(w, h)
    cap = round((0.062 if h > w else 0.055) * min(w, h))
    out, seen = [], set()
    for row in ass.read_text(encoding="utf-8").splitlines():
        if not row.startswith("Dialogue:"):
            continue
        parts = row[len("Dialogue:"):].split(",", 9)
        if len(parts) < 10 or parts[3].strip() != "Cap":
            continue
        raw = parts[9]
        text = re.sub(r"\{[^}]*\}", "", raw)
        key = (parts[1], text)
        if key in seen or not text.strip():
            continue
        seen.add(key)
        t = _secs(parts[1].strip())
        rows = [r.strip() for r in text.split("\\N")]
        fs = float(m.group(1)) if (m := re.search(r"\\fs(\d+(?:\.\d+)?)", raw)) else cap
        font = "InstrumentSerif-Italic.ttf" if "Instrument Serif" in raw else "Inter-SemiBold.otf" if "Inter SemiBold" in raw else "Inter-ExtraBold.otf"
        widths = [text_width(r, fs, font) for r in rows]
        if len(rows) > 1 and len(rows[-1].split()) == 1 and len(rows[0].split()) >= 3:
            out.append(Finding(f"a caption at {t:.1f}s leaves one word alone on its last row (\"{rows[-1]}\")", "type", [t]))
        if len(rows) > 1 and min(widths) < 0.45 * max(widths):
            out.append(Finding(f"a caption at {t:.1f}s has rows of very different length", "type", [t]))
        pm = re.search(r"\\pos\((\d+),(\d+)\)", raw)
        am = re.search(r"\\an(\d)", raw)
        if pm:
            x, y, an = int(pm.group(1)), int(pm.group(2)), int(am.group(1)) if am else 2
            col, rowk = (an - 1) % 3, (an - 1) // 3
            bw, bh = max(widths), fs * 1.2 * len(rows)
            x0 = x if col == 0 else x - bw / 2 if col == 1 else x - bw
            y0 = y - bh if rowk == 0 else y - bh / 2 if rowk == 1 else y
            if x0 < L - 4 or x0 + bw > R + 4 or y0 < T - 4 or y0 + bh > B + 4:
                out.append(Finding(f"a caption at {t:.1f}s runs outside the safe area (\"{' '.join(rows)[:30]}\")", "type", [t]))
    return out[:5]


def _thumb(f: np.ndarray) -> np.ndarray:
    g = f.mean(axis=2) if f.ndim == 3 else f.astype(np.float64)
    h, w = g.shape
    g = g[: h // 4 * 4, : w // 4 * 4].reshape(h // 4, 4, w // 4, 4).mean(axis=(1, 3))
    return g


def _repeats(fr: np.ndarray, fps: float, edges: list[float], plain, near: float = 8.0, alike: float = 0.93) -> list:
    """The same shot (or one nearly the same) shown twice within `near`
    seconds: viewers read it as a mistake. Compared on the middle frame of
    each shot, by shape and by tone; plain frames (flat colour, text cards on
    one background) are left out."""
    mids = []
    for a, b in zip(edges, edges[1:]):
        if b - a < 0.3 or plain(a, b):
            mids.append(None)
            continue
        g = _thumb(fr[min(len(fr) - 1, int((a + b) / 2 * fps))].astype(np.float64))
        gy, gx = np.gradient(g)
        e = np.hypot(gx, gy)
        if g.std() < 14 or e.mean() < 3:
            mids.append(None)
            continue
        mids.append(((g - g.mean()) / g.std(), (e - e.mean()) / (e.std() or 1), a))
    out, seen = [], set()
    for i, x in enumerate(mids):
        if x is None:
            continue
        for j in range(i - 2, -1, -1):
            y = mids[j]
            if y is None:
                continue
            if x[2] - y[2] > near:
                break
            tone, shape = float((x[0] * y[0]).mean()), float((x[1] * y[1]).mean())
            if tone > alike and shape > alike - 0.1 and j not in seen:
                out.append(Finding(f"the shot at {x[2]:.1f}s looks the same as the one at {y[2]:.1f}s (measured likeness {min(tone, shape):.2f}); "
                                   "a repeat this close reads as a mistake. Swap one for an unused clip of the same look", "repeat", [x[2], y[2]]))
                seen.add(i)
                break
    return out


def review(video: Path, ass: Path | None = None, spoken=()) -> list[str]:
    """Plain-language problems found in a finished video ([] = all clear)."""
    video = Path(video)
    info = _probe(video)
    v = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    if not v:
        return ["no picture"]
    total = float(info.get("format", {}).get("duration") or 0)
    w, h = int(v["width"]), int(v["height"])
    num, _, den = v.get("r_frame_rate", "30/1").partition("/")
    fps = float(num) / float(den or 1) or 30.0
    notes = []
    if ass is None:
        ass = next((p for p in (video.with_suffix(".look.ass"), video.with_suffix(".montage.ass")) if p.exists()), None)
    if ass and Path(ass).exists():
        events = text_events(Path(ass))
        notes += _reading(events, total, spoken)
        notes += _contrast(video, Path(ass), events, w, h, total)
        try:
            notes += _type(Path(ass), w, h)
        except Exception:  # a check that can't run never stops the video
            pass
    notes += _picture(video, fps, total)
    notes += _sound(video, info, total)
    try:
        notes += _pace(video, total)
    except Exception:  # a check that can't run never stops the video
        pass
    return notes


def report(video: Path, ass: Path | None = None, spoken=()) -> str:
    notes = review(video, ass, spoken)
    if not notes:
        return "self-review: all clear (reading time, contrast, black frames, flashing, sound and picture)"
    return "self-review found:\n" + "\n".join(f"   - {n}" for n in notes)
