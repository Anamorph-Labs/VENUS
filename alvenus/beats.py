"""Cutting to the music: find the beat of the music bed, then let each scene
change land on a beat, the way an editor slips a cut a few frames to sit on
the rhythm. Only the quiet breath before a new scene is lengthened; speech is
never moved or cut."""

from __future__ import annotations

from pathlib import Path

import numpy as np

SR = 22050
HOP = 512
NFFT = 1024


def onset_envelope(y: np.ndarray, kick: bool = False) -> np.ndarray:
    """How much new sound starts in each ~23 ms step (spectral flux)."""
    n_fft = NFFT
    if len(y) < n_fft:
        return np.zeros(1)
    frames = np.lib.stride_tricks.sliding_window_view(y, n_fft)[::HOP] * np.hanning(n_fft)
    mag = np.log1p(np.abs(np.fft.rfft(frames, axis=1)) * 10)
    rise = np.maximum(np.diff(mag, axis=0, prepend=mag[:1]), 0)
    low = int(250 / (SR / n_fft))
    if kick:  # the kick drum marks where the beat falls; hi-hats on the off-beat must not pull it
        flux = rise[:, low:].mean(axis=1) + 2 * rise[:, 1:low].mean(axis=1)
    else:  # every kind of attack, for the tempo
        flux = rise.sum(axis=1)
    flux -= np.convolve(flux, np.ones(16) / 16, "same")  # keep the peaks, drop the slow swell
    return np.maximum(flux, 0)


def beat_grid(y: np.ndarray, sr: int = SR) -> tuple[float, float, float]:
    """(seconds per beat, time of the first beat, confidence 0..1)."""
    env = onset_envelope(y)
    fps = sr / HOP
    if env.max() <= 0 or len(env) < fps * 4:
        return 0.0, 0.0, 0.0
    env = env / env.max()
    ac = np.correlate(env, env, "full")[len(env) - 1 :]
    lags = np.arange(len(ac))
    lo, hi = int(fps * 60 / 180), int(fps * 60 / 70)  # 70 to 180 BPM
    # A gentle preference for ~110 BPM breaks ties between a tempo and its double.
    weight = np.exp(-0.5 * (np.log2(np.maximum(lags[lo:hi], 1) / (fps * 60 / 110)) / 0.9) ** 2)
    score = ac[lo:hi] * weight
    lag = lo + int(np.argmax(score))
    conf = float(ac[lag] / (ac[0] or 1))
    # Parabolic refinement for a period between frames.
    if lo < lag < hi - 1:
        a, b, c = ac[lag - 1], ac[lag], ac[lag + 1]
        lag = lag + 0.5 * (a - c) / ((a - 2 * b + c) or 1)
    period = lag / fps
    env = onset_envelope(y, kick=True)
    env = env / (env.max() or 1)
    phases = np.linspace(0, period, 48, endpoint=False)
    t_env = np.arange(len(env)) / fps
    best = max(phases, key=lambda p: env[np.clip(np.round((np.arange(p, t_env[-1], period)) * fps).astype(int), 0, len(env) - 1)].sum())
    return float(period), float(best + NFFT / 2 / sr) % float(period), conf  # frame time -> its centre


def beats_of(music: Path, total: float) -> list[float]:
    """Beat times over the finished cut (the music bed starts at 0 and loops)."""
    from .media import duration, load_audio

    y = load_audio(music, SR)
    period, first, conf = beat_grid(y)
    if period <= 0 or conf < 0.15:
        return []
    length = duration(music)
    out, start = [], 0.0
    while start < total:
        out += [start + t for t in np.arange(first, length, period) if start + t <= total]
        start += length
    return out


def sync(clips, beats: list[float], scene_starts: set[int], room_end: dict[int, float],
         reach: float = 0.4) -> list[str]:
    """Delay each scene start (clip index in `scene_starts`) to the next beat
    within `reach` seconds by lengthening the clip before it: first with more
    of its own quiet footage (up to `room_end`, where the next sound in that
    file begins), then by holding its last frame. Returns plain notes."""
    from .cut import positions

    if not beats:
        return []
    b = np.array(beats)
    moved = []
    for i in sorted(scene_starts):
        if i == 0 or i >= len(clips):
            continue
        p = positions(clips)[i] + clips[i].tdur / 2  # a transition's middle is its "cut"
        ahead = b[(b >= p - 0.02) & (b <= p + reach)]
        if not len(ahead):
            continue
        d = float(ahead[0] - p)
        if d < 0.02:
            continue
        prev = clips[i - 1]
        room = room_end.get(i - 1, prev.end) - 0.05
        more = max(0.0, min(d, room - prev.end)) if not prev.hold else 0.0
        prev.end += more
        prev.hold = round(prev.hold + d - more, 3)
        moved.append(d)
    if not moved:
        return []
    return [f"{len(moved)} scene change(s) moved onto the music's beat (by {min(moved):.2f}-{max(moved):.2f}s)"]
