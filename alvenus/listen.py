"""Listening closely: what is in a voice track and in a song, to the hundredth
of a second, so the music never moves on a word and no cut splits words that
were spoken together.

voice_map  where each spoken phrase starts and ends, and the quiet gaps between
           them. Words that run into each other with no quiet are one phrase.
music_map  tempo, beats, bars, the song's sections (quiet, building, loud),
           its hits and the moments it stops dead.
duck_keys  how loud the music is at each moment under a voice: it dips before
           a phrase starts and comes back after it ends, the slow change always
           inside a gap, never on a word. A gap too short for that stays down.
quiet_point  the quietest spot near a planned cut, or None when the voice
           never drops there (two words joined: don't cut).

Everything is measured from the sound itself; nothing is guessed."""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SR = 16000
HOP = 0.01  # one loudness reading every 10 ms


def loudness(y: np.ndarray, sr: int = SR, hop: float = HOP) -> np.ndarray:
    """Loudness in dB every `hop` seconds (20 ms windows)."""
    n = int(hop * sr)
    if len(y) < n:
        return np.full(1, -120.0)
    k = len(y) // n
    frames = y[: k * n].reshape(k, n).astype(np.float64)
    rms = np.sqrt((frames ** 2).mean(axis=1))
    rms = np.sqrt(np.convolve(rms ** 2, [0.5, 0.5], "same"))
    return 20 * np.log10(np.maximum(rms, 1e-6))


def _voiced(db: np.ndarray) -> tuple[np.ndarray, float]:
    floor = float(np.percentile(db, 10))
    loud = float(np.percentile(db, 95))
    thr = max(floor + 0.35 * (loud - floor), loud - 30, -55.0)
    return db > thr, thr


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    out, start = [], None
    for i, m in enumerate(mask):
        if m and start is None:
            start = i
        elif not m and start is not None:
            out.append((start, i))
            start = None
    if start is not None:
        out.append((start, len(mask)))
    return out


def phrases_of(db: np.ndarray, join: float = 0.25, shortest: float = 0.06) -> list[tuple[float, float]]:
    """Spoken stretches: sound runs closer than `join` seconds are one phrase
    (the small dips between words are not places to cut or move the music)."""
    mask, _ = _voiced(db)
    runs = [(a * HOP, b * HOP) for a, b in _runs(mask) if (b - a) * HOP >= shortest]
    out: list[list[float]] = []
    for a, b in runs:
        if out and a - out[-1][1] < join:
            out[-1][1] = b
        else:
            out.append([a, b])
    return [(round(a, 2), round(b, 2)) for a, b in out]


def voice_map(path: Path, join: float = 0.25) -> dict:
    from .media import load_audio

    y = load_audio(path, SR)
    db = loudness(y)
    ph = phrases_of(db, join)
    total = round(len(y) / SR, 2)
    gaps = [(round(a[1], 2), round(b[0], 2)) for a, b in zip(ph, ph[1:])]
    return {"length": total, "phrases": ph, "gaps": gaps}


def quiet_point(db: np.ndarray, t: float, search: float = 0.12, margin_db: float = 6.0) -> float | None:
    """The quietest moment within `search` s of t, if it is really quiet
    (within margin_db of the quiet threshold); None means the voice never drops
    there: the words are joined, so a cut would split them."""
    i0, i1 = max(0, int((t - search) / HOP)), min(len(db), int((t + search) / HOP) + 1)
    if i1 <= i0:
        return t
    seg = db[i0:i1]
    k = int(np.argmin(seg))
    _, thr = _voiced(db)
    if seg[k] > thr - margin_db:
        return None
    return round((i0 + k) * HOP, 3)


def duck_keys(phrases, total: float, depth_db: float = 12.0, ramp: float = 0.5, lead: float = 0.12,
              tail: float = 0.2, up_hold: float = 0.4) -> list[tuple[float, float]]:
    """(time, gain dB) points for the music under a voice. Each dip finishes
    `lead` s before a phrase and the rise starts `tail` s after it, so every
    change sits in quiet. Gaps that can't fit a dip, a held moment up and a
    rise stay down: the music never bobs on a short breath."""
    need = 2 * ramp + lead + tail + up_hold
    groups: list[list[float]] = []
    for a, b in phrases:
        if groups and a - groups[-1][1] < need:
            groups[-1][1] = b
        else:
            groups.append([a, b])
    keys: list[tuple[float, float]] = [(0.0, 0.0)]
    for a, b in groups:
        down_end = a - lead
        down_start = down_end - ramp
        if down_start < 0.05:  # speech right at the start: the music begins already down
            keys = [(0.0, -depth_db)]
        else:
            keys += [(round(down_start, 3), 0.0), (round(down_end, 3), -depth_db)]
        up_start = b + tail
        keys += [(round(up_start, 3), -depth_db), (round(min(total, up_start + ramp), 3), 0.0)]
    if keys[-1][0] < total:
        keys.append((round(total, 3), keys[-1][1]))
    return keys


def gain_at(keys, t: float) -> float:
    for (t0, g0), (t1, g1) in zip(keys, keys[1:]):
        if t0 <= t <= t1:
            return g0 if t1 == t0 else g0 + (g1 - g0) * (t - t0) / (t1 - t0)
    return keys[-1][1]


def moves_on_words(keys, phrases) -> list[float]:
    """Times where the music level changes while someone is speaking (should be none)."""
    bad = []
    for (t0, g0), (t1, g1) in zip(keys, keys[1:]):
        if g0 == g1:
            continue
        for a, b in phrases:
            if t0 < b and t1 > a:
                bad.append(round(max(t0, a), 2))
    return bad


def make_room(keys, events, total: float, dip_db: float = 3.0, before: float = 0.08, after: float = 0.35, ramp: float = 0.06):
    """Lower the music a little around each sound effect, so the effect sits just
    above it. Under a voice the music is already down: left as it is."""
    if not events:
        return keys
    out = []
    grid = sorted({k[0] for k in keys} | {max(0.0, min(total, t + d)) for t in events
                                          for d in (-before - ramp, -before, after, after + ramp)})

    def near_fx(t):
        e = 0.0
        for x in events:
            a, b = x - before, x + after
            if a <= t <= b:
                e = max(e, 1.0)
            elif a - ramp < t < a:
                e = max(e, (t - (a - ramp)) / ramp)
            elif b < t < b + ramp:
                e = max(e, 1 - (t - b) / ramp)
        return e

    for t in grid:
        g = gain_at(keys, t)
        if g > -dip_db:
            g = min(g, g - dip_db * near_fx(t))
        out.append((round(t, 3), round(g, 2)))
    return out


def write_gain(path: Path, keys, total: float, sr: int = 48000) -> None:
    """The music's level over time as a stereo track of gains (0..1), to multiply the music by."""
    t = np.arange(int(total * sr) + 1) / sr
    xs = np.array([k[0] for k in keys])
    ys = np.array([k[1] for k in keys])
    g = 10 ** (np.interp(t, xs, ys) / 20)
    pcm = (np.clip(g, 0, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(np.repeat(pcm, 2).tobytes())


# --- the song ------------------------------------------------------------------

def music_map(path: Path) -> dict:
    """Tempo, beats, bars, sections, hits and stops of a song, all measured."""
    from .beats import SR as BSR, beat_grid
    from .media import load_audio

    y = load_audio(path, SR)
    length = len(y) / SR
    period, first, conf = beat_grid(load_audio(path, BSR), BSR)
    sure = period > 0 and conf >= 0.15
    beats = [round(float(t), 3) for t in np.arange(first, length, period)] if sure else []
    db = loudness(y)
    out: dict = {"length": round(length, 2), "tempo": round(60 / period, 1) if sure else None,
                 "beat_sure": round(float(conf), 2), "beats": beats}
    if beats:
        strength = [float(np.mean(db[int(b / HOP): int(b / HOP) + 5])) for b in beats]
        down = int(np.argmax([np.mean(strength[k::4]) if len(strength) > k else -999 for k in range(4)]))
        out["bars"] = beats[down::4]
    else:
        out["bars"] = []
    # sections: loudness over 2-second steps, split where it changes for good
    step = int(2 / HOP)
    lv = [float(np.mean(db[i: i + step])) for i in range(0, len(db), step)] or [-120.0]
    lo, hi = np.percentile(lv, 10), np.percentile(lv, 95)
    steady = hi - lo < 4.0  # the level hardly changes: one section, not noise read as drama
    word = lambda v: "steady" if steady else "quiet" if v < lo + (hi - lo) * 0.35 else "loud" if v > lo + (hi - lo) * 0.75 else "medium"  # noqa: E731
    sections: list[dict] = []
    for i, v in enumerate(lv):
        w = word(v)
        if sections and (sections[-1]["feel"] == w or (i + 1 < len(lv) and word(lv[i + 1]) == sections[-1]["feel"])):
            sections[-1]["end"] = round(min(length, (i + 1) * 2.0), 2)
            continue
        sections.append({"start": round(i * 2.0, 2), "end": round(min(length, (i + 1) * 2.0), 2), "feel": w})
    for k, s in enumerate(sections):
        prev = sections[k - 1]["feel"] if k else None
        if prev == "quiet" and s["feel"] != "quiet" or prev == "medium" and s["feel"] == "loud":
            s["feel"] += " (it lifts here)"
        elif prev and prev.startswith("loud") and s["feel"] != "loud":
            s["feel"] += " (it drops here)"
    out["sections"] = sections
    # hits: accents that stand out from the song's usual attacks (not every beat)
    cand = []
    for i in range(5, len(db) - 3):
        if db[i] - np.max(db[i - 5:i]) > 9 and (not cand or i * HOP - cand[-1][0] > 0.25):
            cand.append((i * HOP, float(np.max(db[i:i + 3]))))
    usual = float(np.median([c[1] for c in cand])) if cand else 0.0
    out["hits"] = [round(t, 2) for t, v in cand if v >= usual + 6]
    # stops: the song itself goes near silent for a moment (a dead stop, a break)
    quiet = db < min(lo - 20, -45.0)
    stops = [(round(a * HOP, 2), round(b * HOP, 2)) for a, b in _runs(quiet) if (b - a) * HOP >= 0.15 and a * HOP > 0.5
             and b * HOP < length - 0.5]
    out["stops"] = stops
    return out


def clock(t: float) -> str:
    return f"{int(t // 60)}:{t % 60:05.2f}"


def report(music: dict | None = None, voice: dict | None = None) -> str:
    lines = []
    if music:
        if music["tempo"]:
            lines.append(f"Song: {music['length']:.1f} s at {music['tempo']:g} BPM (beat every {60 / music['tempo']:.2f} s, "
                         f"{len(music['bars'])} bars; beat certainty {music['beat_sure']:.2f})")
        else:
            lines.append(f"Song: {music['length']:.1f} s, no steady beat found (free time): cut on its sections and hits, not a grid")
        for s in music["sections"]:
            lines.append(f"  {clock(s['start'])}-{clock(s['end'])}  {s['feel']}")
        if music["hits"]:
            lines.append("  hits at " + ", ".join(clock(t) for t in music["hits"][:24]) + (" ..." if len(music["hits"]) > 24 else ""))
        if music["stops"]:
            lines.append("  stops dead at " + ", ".join(f"{clock(a)} ({b - a:.2f} s)" for a, b in music["stops"]))
    if voice:
        ph, gaps = voice["phrases"], voice["gaps"]
        lines.append(f"Voice: {len(ph)} phrases over {voice['length']:.1f} s. Words inside a phrase run together: never cut there.")
        for (a, b), g in zip(ph, gaps + [None]):
            gap = f"   gap {g[1] - g[0]:.2f} s" if g else ""
            lines.append(f"  {clock(a)}-{clock(b)} speaking{gap}")
        fit = [g for g in gaps if g[1] - g[0] >= 1.6]
        lines.append(f"  the music can lift in {len(fit)} of the {len(gaps)} gaps (1.6 s or longer); in the others it stays down")
    return "\n".join(lines)


# --- music that has to run longer than the song ----------------------------------

def _stereo(path: Path, sr: int = 48000) -> np.ndarray:
    import subprocess

    raw = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(path), "-vn", "-ac", "2", "-ar", str(sr), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).reshape(-1, 2).copy()


def _write_stereo(path: Path, y: np.ndarray, sr: int = 48000) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(y, -1, 1) * 32767).astype("<i2").tobytes())


def loop_points(y: np.ndarray, sr: int, bars: list[float], beat: float | None) -> tuple[float, float, float]:
    """(start, end, blend) of the stretch to repeat. On a song with a beat both
    ends are bar lines, so the repeat lands on the downbeat; the start is the
    bar whose loudness best matches the end, so the level doesn't jump."""
    length = len(y) / sr
    db = loudness(y.mean(axis=1) if y.ndim == 2 else y, sr)

    def level(t: float) -> float:
        i = int(t / HOP)
        return float(np.mean(db[max(0, i - 50): i + 50])) if len(db) else -120.0

    if len(bars) >= 4:
        ends = [b for b in bars if b <= length - 0.6]
        end = ends[-1] if ends else length - 0.6
        starts = [b for b in bars if 0.5 <= b <= end - 4.0] or [bars[0]]
        start = min(starts, key=lambda b: abs(level(b) - level(end)) + 0.02 * b)
        return start, end, round(min(0.5, (beat or 0.5)), 3)
    end = max(1.0, length - 1.2)
    starts = [t for t in np.arange(0.5, max(0.6, end / 3), 0.25)]
    start = min(starts, key=lambda t: abs(level(t) - level(end)))
    return round(float(start), 3), round(end, 3), 1.5


def extend_music(path: Path, need: float, out: Path) -> tuple[Path, list[float], list[float]]:
    """The song made at least `need` seconds long by repeating a stretch of it,
    joined on the bar with a short equal-power blend instead of jumping back to
    the top. Returns (file to use, where each join sits, level change at each
    join in dB). A song already long enough comes back as it is."""
    sr = 48000
    y = _stereo(path, sr)
    length = len(y) / sr
    if length >= need or length < 3.0:
        return path, [], []
    m = music_map(path)
    beat = 60 / m["tempo"] if m.get("tempo") else None
    start, end, xf = loop_points(y, sr, m.get("bars") or [], beat)
    s, e, n = int(start * sr), int(end * sr), int(xf * sr)
    fade = np.linspace(0, np.pi / 2, n, dtype=np.float32)
    fin, fout = np.sin(fade)[:, None], np.cos(fade)[:, None]
    body = y[s:e]
    out_y = y[:e].copy()
    joins = []
    while len(out_y) / sr < need + 0.5:
        tail = y[e: e + n]
        if len(tail) < n:
            tail = np.vstack([tail, np.zeros((n - len(tail), 2), np.float32)])
        head = y[s: s + n]
        joins.append(round(len(out_y) / sr, 2))
        rest = y[s:] if (len(out_y) + len(y) - s) / sr >= need + 0.5 else body
        out_y = np.vstack([out_y, tail * fout + head * fin, rest[n:]])
    db = loudness(out_y.mean(axis=1), sr)
    jumps = []
    for t in joins:
        i = int(t / HOP)
        a, b = db[max(0, i - 100): i - 10], db[i + 10: i + 100]
        jumps.append(round(abs(float(np.mean(b)) - float(np.mean(a))), 1) if len(a) and len(b) else 0.0)
    _write_stereo(out, out_y, sr)
    return out, joins, jumps
