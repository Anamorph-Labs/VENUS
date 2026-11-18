"""Auto-reframe: turn wide footage into a taller frame (9:16, 4:5, 1:1) by
following the person, the way a camera operator would, instead of cropping
the dead centre.

No face-detection library is needed: a speaking person is where the picture
moves (mouth, head, hands) and where skin tones are. We sample a few frames
per second, find the horizontal centre of that, smooth it heavily and only
re-aim when the subject has clearly moved, then ease to the new framing."""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

SW, SH = 160, 90  # analysis size


def _frames(path: Path, start: float, end: float, fps: float) -> np.ndarray:
    raw = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{max(0.1, end - start):.3f}",
         "-i", str(path), "-an", "-vf", f"fps={fps:g},scale={SW}:{SH}:flags=area", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True,
    ).stdout
    n = len(raw) // (SW * SH * 3)
    return np.frombuffer(raw[: n * SW * SH * 3], np.uint8).reshape(n, SH, SW, 3).astype(np.float32)


def _skin(f: np.ndarray) -> np.ndarray:
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    cb = 128 - 0.169 * r - 0.331 * g + 0.5 * b
    cr = 128 + 0.5 * r - 0.419 * g - 0.081 * b
    y = 0.299 * r + 0.587 * g + 0.114 * b
    return ((cb > 77) & (cb < 127) & (cr > 135) & (cr < 175) & (y > 40)).astype(np.float32)


def _blur(m: np.ndarray, k: int = 9) -> np.ndarray:
    ker = np.ones(k) / k
    m = np.apply_along_axis(lambda r: np.convolve(r, ker, mode="same"), 1, m)
    return np.apply_along_axis(lambda c: np.convolve(c, ker, mode="same"), 0, m)


def track(path: Path, start: float, end: float, fps: float = 4.0) -> list[tuple[float, float]]:
    """(seconds from `start`, subject centre as a fraction of the width)."""
    fr = _frames(path, start, end, fps)
    if len(fr) == 0:
        return [(0.0, 0.5)]
    # Motion between samples, blurred in space and averaged over ~2 s, finds
    # the speaker; skin tones count only near that motion (wood and walls can
    # be skin-coloured too).
    diff = np.abs(np.diff(fr, axis=0, prepend=fr[:1])).mean(axis=3)
    diff = np.maximum(diff - 3.0, 0)  # ignore compression shimmer
    win = max(1, int(2 * fps))
    centres = []
    for i, f in enumerate(fr):
        m = diff[max(0, i - win // 2) : i + win // 2 + 1].mean(axis=0)  # centred: we know the future
        m = _blur(m)
        if m.max() < 0.5:
            centres.append(np.nan)
            continue
        m = m / m.max()
        weight = m + 0.3 * _skin(f) * (m > 0.15)
        col = weight.sum(axis=0)
        keep = col >= 0.5 * col.max()  # the strongest region, so two blobs don't average to empty space
        xs = np.arange(SW)
        centres.append(float((xs[keep] * col[keep]).sum() / col[keep].sum() / (SW - 1)))
    c = np.array(centres)
    if np.isnan(c).all():
        return [(0.0, 0.5)]
    # Gaps (no motion) keep the last known framing; leading gaps take the first.
    first = c[~np.isnan(c)][0]
    for i in range(len(c)):
        if np.isnan(c[i]):
            c[i] = c[i - 1] if i else first
    # Median filter: ignore a passing hand or a single noisy frame.
    k = 5
    padded = np.pad(c, k // 2, mode="edge")
    c = np.array([np.median(padded[i : i + k]) for i in range(len(c))])
    # Hold the framing until the subject clearly moves, then ease over ~0.4 s.
    out, aim, moving = [], float(c[0]), False
    for i, x in enumerate(c):
        if abs(x - aim) > 0.05:
            moving = True
        if moving:
            aim += (x - aim) * min(1.0, 1.0 / (0.4 * fps))
            aim = min(max(aim, x - 0.06), x + 0.06)  # never let the subject slip out of frame
            moving = abs(x - aim) > 0.01
        out.append((i / fps, round(float(aim), 3)))
    # Thin to the keyframes that matter (drop points on a straight run).
    kept = [out[0]]
    for a, b in zip(out[1:], out[2:] + [out[-1]]):
        if abs(a[1] - kept[-1][1]) > 0.005 or a is out[-1]:
            kept.append(a)
    if len(kept) > 40:  # keep the expression short: spread 40 keyframes evenly
        idx = np.linspace(0, len(kept) - 1, 40).round().astype(int)
        kept = [kept[i] for i in idx]
    return kept


def crop_x(keys: list[tuple[float, float]], src_w: int, crop_w: int) -> str:
    """FFmpeg expression for the crop's left edge over time t (clip-relative);
    use it quoted: crop=...:x='EXPR'."""
    def x_of(c: float) -> float:
        return float(min(max(c * src_w - crop_w / 2, 0), src_w - crop_w))
    if len(keys) == 1:
        return f"{x_of(keys[0][1]):.1f}"
    expr = f"{x_of(keys[-1][1]):.1f}"
    for (t0, c0), (t1, c1) in reversed(list(zip(keys, keys[1:]))):
        x0, x1 = x_of(c0), x_of(c1)
        seg = f"{x0:.1f}+({x1 - x0:.1f})*(t-{t0:.2f})/{max(t1 - t0, 0.01):.2f}"
        expr = f"if(lt(t,{t1:.2f}),{seg},{expr})"
    return expr
