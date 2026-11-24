"""A clean mix, measured: the voice always clear over the music, every sound
effect heard, nothing stacked or repeated by rote.

All of it is measured on the actual sound (10 ms loudness readings), before
the final mix is written, and fixed there:

fit_under_voice  for every spoken phrase, how far the voice sits over the
                 music; where it is less than `gap` dB, the music goes further
                 down for that stretch (still easing only in the gaps).
tidy             fewer, varied effects: never two within half a second (the
                 stronger one stays), never more than two small ones (pops,
                 ticks, snaps) in two seconds.
effect_gains     how much to lift each effect so it is heard over what plays
                 under it (never lowered here; sfx_volume does that)."""

from __future__ import annotations

import numpy as np

from . import listen

GAP_DB = 10.0  # the voice sits at least this far over the music on every phrase
SMALL = {"pop", "tick", "snap", "shutter", "glitch"}
RANK = {"boom": 6, "braam": 6, "hit": 5, "riser": 5, "swell": 4, "whoosh": 3, "glitch": 2, "shutter": 2, "snap": 2, "pop": 1, "tick": 0}


def _db(y: np.ndarray) -> float:
    return float(10 * np.log10(np.mean(np.asarray(y, np.float64) ** 2) + 1e-12))


def phrase_gaps(voice: np.ndarray, music: np.ndarray, phrases, sr: int = listen.SR) -> list[tuple[float, float, float]]:
    """(start, end, dB the voice sits over the music) for each phrase."""
    out = []
    for a, b in phrases:
        i, j = int(a * sr), int(b * sr)
        v, m = voice[i:j], music[i:j]
        if len(v) < sr * 0.05 or len(m) == 0:
            continue
        out.append((a, b, round(_db(v) - _db(m), 1)))
    return out


def fit_under_voice(voice: np.ndarray, music: np.ndarray, keys, phrases, gap: float = GAP_DB, floor_db: float = -36.0):
    """Lower the music further wherever a phrase has less than `gap` dB of room.
    `music` is the music before the gain keys. Returns (keys, gaps after)."""
    sr = listen.SR
    keys = [list(k) for k in keys]
    for _ in range(3):
        g = 10 ** (np.interp(np.arange(len(music)) / sr, [k[0] for k in keys], [k[1] for k in keys]) / 20)
        gaps = phrase_gaps(voice, music * g, phrases, sr)
        short = [(a, b, gap - d) for a, b, d in gaps if d < gap - 0.3]
        if not short:
            return [tuple(k) for k in keys], gaps
        for a, b, need in short:
            for k in keys:  # deepen every key that holds the music down over this phrase
                if k[1] < -0.5 and a - 1.0 <= k[0] <= b + 1.0:
                    k[1] = max(floor_db, k[1] - need - 0.5)
            if not any(k[1] < -0.5 and a - 1.0 <= k[0] <= b + 1.0 for k in keys):  # no dip here yet: add one
                keys += [[max(0.0, a - 0.62), 0.0], [max(0.0, a - 0.12), -need - 1.0], [b + 0.2, -need - 1.0], [b + 0.7, 0.0]]
                keys.sort(key=lambda k: k[0])
    g = 10 ** (np.interp(np.arange(len(music)) / sr, [k[0] for k in keys], [k[1] for k in keys]) / 20)
    return [tuple(k) for k in keys], phrase_gaps(voice, music * g, phrases, sr)


def tidy(events, near: float = 0.45, window: float = 2.0, most_small: int = 2):
    """(kept events, how many were dropped). Events are (time, kind)."""
    kept: list[tuple[float, str]] = []
    for t, k in sorted(events):
        clash = [e for e in kept if abs(e[0] - t) < near]
        if clash:
            if all(RANK.get(k, 1) > RANK.get(c[1], 1) for c in clash):
                for c in clash:
                    kept.remove(c)
                kept.append((t, k))
            continue
        if k in SMALL and sum(1 for e in kept if e[1] in SMALL and t - e[0] < window) >= most_small:
            continue
        kept.append((t, k))
    kept.sort()
    return kept, len(list(events)) - len(kept)


def effect_gains(events, bed: np.ndarray, sr: int = listen.SR, above: float = 3.0, most: float = 9.0) -> list[float]:
    """dB to add to each effect so its first 150 ms sit `above` dB over the
    sound under it (voice and music together). Only lifts, at most `most` dB."""
    from .sfx import KINDS

    out = []
    for t, kind in events:
        make, level, peak = KINDS[kind]
        y = make()
        y = y / (np.abs(y).max() or 1) * 10 ** (level / 20)
        y = y.mean(axis=1) if y.ndim == 2 else y
        p = int(peak * 48000)
        fx = _db(y[p: p + int(0.15 * 48000)] if p < len(y) else y)
        i = int(t * sr)
        under = _db(bed[max(0, i - int(0.05 * sr)): i + int(0.15 * sr)]) if i < len(bed) else -90.0
        out.append(round(float(np.clip(under + above - fx, 0.0, most)), 1))
    return out


def report(gaps, joins=(), jumps=(), dropped: int = 0, lifted=()) -> list[str]:
    """Plain notes on the mix, for the creator and their AI."""
    notes = []
    if gaps:
        low = min(gaps, key=lambda g: g[2])
        notes.append(f"mix: the voice sits at least {low[2]:.0f} dB over the music on every line "
                     f"(closest at {listen.clock(low[0])}); measured, not assumed")
    for t, j in zip(joins, jumps):
        notes.append(f"music: the song repeats at {listen.clock(t)}, joined on the bar with a short blend"
                     + (f" (level changes {j:.1f} dB there: listen to it)" if j > 3 else ""))
    if dropped:
        notes.append(f"sound effects: {dropped} left out because they were stacked or too many in a row")
    n = sum(1 for x in lifted if x > 0.5)
    if n:
        notes.append(f"sound effects: {n} lifted so they're heard over the music and voice")
    return notes
