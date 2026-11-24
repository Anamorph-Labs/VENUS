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


def _lowpass(x: np.ndarray, cutoff) -> np.ndarray:
    """One-pole low-pass over a (n, 2) signal; cutoff in Hz (number or per-sample array)."""
    n = len(x)
    c = np.broadcast_to(np.asarray(cutoff, float), (n,))
    a = np.exp(-2 * np.pi * c / SR)
    y = np.zeros_like(x)
    s = np.zeros(x.shape[1])
    for i in range(n):
        s = (1 - a[i]) * x[i] + a[i] * s
        y[i] = s
    return y


def riser(seconds: float = 2.4) -> np.ndarray:
    """Tension before a slam: noise whose filter opens and a tone gliding up,
    growing until it stops dead at its peak (the end of the sound)."""
    n = int(seconds * SR)
    t = np.linspace(0, 1, n)
    rng = np.random.default_rng(11)
    air = _lowpass(rng.standard_normal((n, 2)), 200 + 7000 * t ** 2.2)
    f = 110 * 2 ** (t * 2.0)
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR) + 0.5 * np.sin(4 * np.pi * np.cumsum(f * 1.01) / SR)
    y = air * 0.9 + np.stack([tone, tone], 1) * 0.25
    return y * (t ** 2.4)[:, None]


def boom(seconds: float = 2.2) -> np.ndarray:
    """The trailer impact: a deep sub drop with a hard crack on top and a long
    dark tail, for a word slamming onto the screen."""
    n = int(seconds * SR)
    t = np.arange(n) / SR
    f = 32 + 90 * np.exp(-t / 0.05)
    sub = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.7)
    rng = np.random.default_rng(5)
    crack = rng.standard_normal((n, 2)) * np.exp(-t / 0.025)[:, None] * 0.8
    tail = _lowpass(rng.standard_normal((n, 2)), 380) * np.exp(-t / 0.9)[:, None] * 2.2
    y = np.stack([sub, sub], 1) + crack + tail
    y[: int(0.002 * SR)] *= np.linspace(0, 1, int(0.002 * SR))[:, None]
    return y


def braam(seconds: float = 2.6) -> np.ndarray:
    """A low brassy blast (many detuned saw tones through a closing filter),
    the big dark note under a title card."""
    n = int(seconds * SR)
    t = np.arange(n) / SR
    y = np.zeros((n, 2))
    for k, det in enumerate((-0.6, -0.25, 0.0, 0.3, 0.7)):
        for base in (55.0, 82.4, 110.0):
            ph = (base + det) * t + 0.13 * k
            saw = 2 * (ph - np.floor(ph + 0.5))
            y[:, k % 2] += saw
    y = _lowpass(y, 2400 * np.exp(-t / 0.5) + 180)
    env = np.minimum(1, t / 0.03) * np.exp(-t / 1.1)
    return y * env[:, None]


def snap(seconds: float = 0.18) -> np.ndarray:
    """A bright flash-frame snap: a click and a short burst of high noise."""
    n = int(seconds * SR)
    t = np.arange(n) / SR
    rng = np.random.default_rng(3)
    x = rng.standard_normal((n, 2))
    hi = x - _lowpass(x, 2500)
    return hi * np.exp(-t / 0.02)[:, None]


def glitch(seconds: float = 0.32, seed: int = 4) -> np.ndarray:
    """Digital stutter for scrambled letters: chopped buzz and bit-crushed
    noise in short random slices."""
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    t = np.arange(n) / SR
    buzz = np.sign(np.sin(2 * np.pi * 180 * t)) * 0.5 + np.round(rng.standard_normal(n) * 3) / 6
    gate = np.repeat(rng.random(n // 600 + 1) > 0.35, 600)[:n]
    y = buzz * gate * np.exp(-t / 0.2)
    return np.stack([y, np.roll(y, 90)], 1)


def tick(seconds: float = 0.05) -> np.ndarray:
    """A tiny mechanical click, for letters typing on or a line drawing."""
    n = int(seconds * SR)
    t = np.arange(n) / SR
    rng = np.random.default_rng(9)
    y = (rng.standard_normal(n) * 0.6 + np.sin(2 * np.pi * 2200 * t)) * np.exp(-t / 0.006)
    return np.stack([y, y], 1)


def swell(seconds: float = 1.4) -> np.ndarray:
    """A reversed cymbal: shimmer that grows into the next moment and cuts off."""
    n = int(seconds * SR)
    t = np.linspace(0, 1, n)
    rng = np.random.default_rng(13)
    x = rng.standard_normal((n, 2))
    shimmer = x - _lowpass(x, 3500)
    return shimmer * (t ** 3)[:, None]


def shutter(seconds: float = 0.16) -> np.ndarray:
    """A camera shutter: two quick clicks, for a photo landing."""
    a = tick()
    y = np.zeros((int(seconds * SR), 2))
    y[: len(a)] += a
    k = int(0.07 * SR)
    y[k: k + len(a)] += a * 0.7
    return y


# kind -> (sound, level in dBFS at its peak, where its peak sits in seconds)
KINDS = {
    "whoosh": (whoosh, -17.0, 0.34),
    "pop": (pop, -24.0, 0.0),
    "hit": (hit, -19.0, 0.0),
    "riser": (riser, -20.0, 2.4),   # (peaks at its very end: the moment it leads into)
    "boom": (boom, -15.0, 0.0),
    "braam": (braam, -18.0, 0.03),
    "snap": (snap, -22.0, 0.0),
    "glitch": (glitch, -24.0, 0.0),
    "tick": (tick, -30.0, 0.0),
    "swell": (swell, -24.0, 1.4),
    "shutter": (shutter, -26.0, 0.0),
}


def export_pack(folder: Path) -> list[Path]:
    """Write every sound as its own WAV file (free to use: made here from
    numbers), so a person can drop them into any editor."""
    folder.mkdir(parents=True, exist_ok=True)
    out = []
    for name, (make, level, _) in KINDS.items():
        y = make()
        y = y / (np.abs(y).max() or 1) * 10 ** (max(level, -12.0) / 20)
        pcm = (np.clip(y, -1, 1) * 32767).astype("<i2")
        p = folder / f"{name}.wav"
        with wave.open(str(p), "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes(pcm.tobytes())
        out.append(p)
    return out


def _variant(y: np.ndarray, n: int) -> np.ndarray:
    """The n-th use of a sound, slightly retuned, so a run of them never sounds copied."""
    if n == 0:
        return y
    f = (1.0, 1.045, 0.962, 1.025, 0.978, 1.06)[n % 6]
    src = np.arange(0, len(y) - 1, f)
    if y.ndim == 2:
        return np.stack([np.interp(src, np.arange(len(y)), y[:, c]) for c in range(y.shape[1])], axis=1)
    return np.interp(src, np.arange(len(y)), y)


def write_track(path: Path, events: list[tuple[float, str]], total: float, gain_db: float = 0.0,
                event_gains: list[float] | None = None) -> None:
    """All the sound effects on one stereo track, each placed so its peak lands
    on its moment. event_gains: dB to add to each event (same order as events)."""
    out = np.zeros((int(total * SR) + 1, 2))
    cache: dict[str, np.ndarray] = {}
    used: dict[str, int] = {}
    order = sorted(range(len(events)), key=lambda j: events[j])
    for i, j in enumerate(order):
        t, kind = events[j]
        make, level, peak = KINDS[kind]
        if kind not in cache:
            y = make()
            cache[kind] = y / (np.abs(y).max() or 1) * 10 ** (level / 20)
        y = cache[kind]
        if kind == "whoosh":  # vary each whoosh a little so a run of them does not sound looped
            y = whoosh(seed=i + 1)
            y = y / (np.abs(y).max() or 1) * 10 ** (level / 20)
        else:
            y = _variant(y, used.get(kind, 0))
        used[kind] = used.get(kind, 0) + 1
        if y.ndim == 1:
            y = np.stack([y, y], axis=1)
        if event_gains is not None:
            y = y * 10 ** (event_gains[j] / 20)
        s = int(max(0.0, t - peak) * SR)
        e = min(len(out), s + len(y))
        if e > s:
            out[s:e] += y[: e - s]
    out *= 10 ** (gain_db / 20)
    pcm = (np.clip(out, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
