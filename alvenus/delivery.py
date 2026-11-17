"""Delivery: how a take was said, not only what was said.

Measured straight from the sound, so it is objective and cheap:
  - level: how loud the voice is while speaking (a mumbled take is quieter)
  - pace: words per second (rushed or dragging, compared with the rest)
  - liveliness: how much the pitch moves (a flat, bored read moves little)
  - ending: whether the voice fades away on the last words
  - distortion: whether the recording clipped

These are signals, not taste. The tool uses them to break ties between takes
with the same words and to flag weak takes; the person or their AI decides
what the moment needs (a quiet, flat read can be exactly right).
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

import numpy as np

SR = 16000
FRAME = 640  # 40 ms
HOP = 160  # 10 ms


@dataclass
class Delivery:
    level_db: float
    pitch_range: float  # spread of the voice's pitch, in semitones
    end_drop_db: float  # how much quieter the last part is than the rest
    clipped: float  # share of samples at full scale
    words_per_sec: float = 0.0
    issues: list[str] = field(default_factory=list)


def _frames(x: np.ndarray) -> np.ndarray:
    if len(x) < FRAME:
        x = np.pad(x, (0, FRAME - len(x)))
    n = 1 + (len(x) - FRAME) // HOP
    return x[np.arange(FRAME)[None, :] + HOP * np.arange(n)[:, None]]


def _pitch(frames: np.ndarray) -> np.ndarray:
    """Rough pitch per frame (Hz) by autocorrelation; 0 where unvoiced."""
    lo, hi = SR // 400, SR // 70  # 70-400 Hz covers speaking voices
    w = frames * np.hanning(FRAME)
    spec = np.fft.rfft(w, 2 * FRAME, axis=1)
    ac = np.fft.irfft(np.abs(spec) ** 2, axis=1)[:, : hi + 1]
    ac = ac / np.maximum(ac[:, :1], 1e-12)
    lag = lo + np.argmax(ac[:, lo : hi + 1], axis=1)
    strength = ac[np.arange(len(ac)), lag]
    return np.where(strength > 0.5, SR / lag, 0.0)


def measure(audio: np.ndarray, start: float, end: float) -> Delivery:
    x = audio[int(start * SR) : int(end * SR)].astype(np.float64)
    fr = _frames(x)
    rms = np.sqrt(np.mean(fr**2, axis=1)) + 1e-9
    db = 20 * np.log10(rms)
    speaking = db > db.max() - 30  # frames with voice, not the gaps
    level = float(np.mean(db[speaking]))
    f0 = _pitch(fr)
    voiced = f0[(f0 > 0) & speaking]
    pitch_range = float(np.std(12 * np.log2(voiced / np.median(voiced)))) if len(voiced) > 10 else 0.0
    idx = np.flatnonzero(speaking)
    cut = idx[int(len(idx) * 0.7)] if len(idx) > 10 else len(db)
    head, tail = db[: cut][speaking[:cut]], db[cut:][speaking[cut:]]
    end_drop = float(np.mean(head) - np.mean(tail)) if len(head) and len(tail) else 0.0
    clipped = float(np.mean(np.abs(x) > 0.985)) if len(x) else 0.0
    return Delivery(round(level, 1), round(pitch_range, 2), round(end_drop, 1), round(clipped, 4))


def judge(takes) -> None:
    """Flag delivery problems, comparing each take with the others in the
    same shoot (people differ; what matters is a take being off for them)."""
    measured = [t for t in takes if t.delivery is not None and t.line is not None]
    if len(measured) < 2:
        return
    clean = [t for t in measured if t.delivery.clipped <= 0.001]
    level_med = statistics.median(t.delivery.level_db for t in clean or measured)
    pitch_med = statistics.median(t.delivery.pitch_range for t in measured)
    for t in measured:
        d = t.delivery
        # The same line's other takes are the fairest comparison: same words,
        # same speaker, same spot. Distorted takes are no guide to level.
        same = [o for o in clean if o.line == t.line and o is not t]
        ref_level = max(o.delivery.level_db for o in same) if same else level_med
        if d.level_db < ref_level - 6:
            d.issues.append("quiet, low energy")
        # Pace only means something against a take of the same line.
        peers = [o.delivery.words_per_sec for o in same if abs(o.score - t.score) < 0.1]
        if peers and d.words_per_sec > statistics.median(peers) * 1.2:
            d.issues.append("rushed")
        if pitch_med and d.pitch_range < pitch_med * 0.5:
            d.issues.append("flat read")
        if d.end_drop_db > 8:
            d.issues.append("trails off at the end")
        if d.clipped > 0.001:
            d.issues.append("distorted (too loud for the mic)")
        if d.issues:
            t.notes.append("delivery: " + ", ".join(d.issues))
