"""Sound design: the small sounds an editor lays under motion so it feels
physical. A soft whoosh as one scene moves into the next, a light pop when a
graphic lands, a low "hit" under a title.

Every sound is made here from numbers (filtered noise and tuned tones), so
there is nothing to download and nothing to license. They sit well under the
voice: felt more than heard."""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SR = 48000


def _env(n: int, attack: float, peak_at: float = None) -> np.ndarray:
    t = np.linspace(0, 1, n)
    p = peak_at if peak_at is not None else attack
    rise = np.clip(t / max(p, 1e-3), 0, 1) ** 2
    fall = np.clip((1 - t) / max(1 - p, 1e-3), 0, 1) ** 1.6
    return rise * fall


def whoosh(seconds: float = 0.55, seed: int = 1) -> np.ndarray:
    """Air moving past: noise through a filter that opens and closes, peaking
    a little after the middle, with slight stereo movement."""
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    noise = rng.standard_normal((n, 2))
    t = np.linspace(0, 1, n)
    # One-pole low-pass whose cutoff sweeps 300 Hz -> 4 kHz -> 600 Hz.
    cutoff = 300 + 3700 * np.sin(np.pi * np.clip(t / 0.62, 0, 1) ** 0.8) ** 2 * (t < 0.62) + \
        (t >= 0.62) * (600 + 3400 * (1 - (t - 0.62) / 0.38) ** 2)
    a = np.exp(-2 * np.pi * cutoff / SR)
    y = np.zeros_like(noise)
    s = np.zeros(2)
    for i in range(n):  # short sounds, a plain loop is fine
        s = (1 - a[i]) * noise[i] + a[i] * s
        y[i] = s
    pan = 0.5 + 0.35 * np.sin(np.pi * (t - 0.5))
    y[:, 0] *= 1.2 - pan * 0.4
    y[:, 1] *= 0.8 + pan * 0.4
    return y * _env(n, 0.6)[:, None]


def pop(seconds: float = 0.12) -> np.ndarray:
    """A light, rounded pop: a tone falling from 900 to 300 Hz in a blink."""
    n = int(seconds * SR)
    t = np.arange(n) / SR
    f = 300 + 600 * np.exp(-t / 0.018)
    ph = 2 * np.pi * np.cumsum(f) / SR
    y = np.sin(ph) * np.exp(-t / 0.03)
    y[: int(0.002 * SR)] *= np.linspace(0, 1, int(0.002 * SR))
    return np.stack([y, y], 1)


def hit(seconds: float = 0.9) -> np.ndarray:
    """A soft low impact under a title: a sub tone dropping in pitch with a
    puff of filtered noise on top."""
    n = int(seconds * SR)
    t = np.arange(n) / SR
    f = 45 + 70 * np.exp(-t / 0.06)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.28)
    rng = np.random.default_rng(7)
    puff = np.convolve(rng.standard_normal(n), np.ones(24) / 24, "same") * np.exp(-t / 0.05) * 0.6
    y = body + puff
    y[: int(0.003 * SR)] *= np.linspace(0, 1, int(0.003 * SR))
    return np.stack([y, y * 0.96], 1)


# kind -> (sound, level in dBFS at its peak, where its peak sits in seconds)
KINDS = {
    "whoosh": (whoosh, -17.0, 0.34),
    "pop": (pop, -24.0, 0.0),
    "hit": (hit, -19.0, 0.0),
}


def write_track(path: Path, events: list[tuple[float, str]], total: float) -> None:
    """All the sound effects on one stereo track, each placed so its peak lands
    on its moment."""
    out = np.zeros((int(total * SR) + 1, 2))
    cache: dict[str, np.ndarray] = {}
    for i, (t, kind) in enumerate(sorted(events)):
        make, level, peak = KINDS[kind]
        if kind not in cache:
            y = make()
            cache[kind] = y / (np.abs(y).max() or 1) * 10 ** (level / 20)
        y = cache[kind]
        if kind == "whoosh":  # vary each whoosh a little so a run of them does not sound looped
            y = whoosh(seed=i + 1)
            y = y / (np.abs(y).max() or 1) * 10 ** (level / 20)
        s = int(max(0.0, t - peak) * SR)
        e = min(len(out), s + len(y))
        if e > s:
            out[s:e] += y[: e - s]
    pcm = (np.clip(out, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
