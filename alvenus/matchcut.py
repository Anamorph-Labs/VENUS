"""Match cuts: find shots that share a framing (an eye in the same place, a
figure on the same horizon, one object in the same spot) and cut them one
after another, lined up so the subject doesn't jump.

How it looks at a shot: one frame, small. The "subject" is where the picture
stands out most from its surroundings (contrast against a blurred copy, plus
edges); we keep its centre and size. The "layout" is the frame's light and
dark arrangement on a 16 x 9 grid. Two shots match when their layouts agree
and their subjects sit in the same place at a similar size.

Lining up: the later shot is pushed in a little (never out) and moved so its
subject lands where the earlier shot's subject was, the way an editor
reframes a match cut by hand.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

GW, GH = 96, 54
MATCH = 0.55  # a distance under this counts as a match cut


@dataclass
class Look:
    cx: float  # subject centre, 0..1 across
    cy: float  # 0..1 down
    size: float  # subject size, 0..1 of the frame's height
    layout: np.ndarray  # 16 x 9, normalised
    edges: np.ndarray  # 16 x 9 edge energy, normalised


def _frame(path: str | Path, at: float, aspect: float) -> np.ndarray:
    """One grey frame at `at` seconds, cropped to the output's shape, GW x GH."""
    h = GH if aspect >= 1 else GW
    w = round(h * aspect)
    raw = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-ss", f"{max(0.0, at):.3f}", "-i", str(path), "-frames:v", "1",
                          "-vf", f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}", "-f", "rawvideo",
                          "-pix_fmt", "gray", "-"], capture_output=True).stdout
    if len(raw) < w * h:
        return np.zeros((h, w), np.float32)
    return np.frombuffer(raw[: w * h], np.uint8).reshape(h, w).astype(np.float32)


def _blur(g: np.ndarray, r: int) -> np.ndarray:
    k = np.ones(2 * r + 1) / (2 * r + 1)
    g = np.apply_along_axis(lambda v: np.convolve(np.pad(v, r, mode="edge"), k, "valid"), 1, g)
    return np.apply_along_axis(lambda v: np.convolve(np.pad(v, r, mode="edge"), k, "valid"), 0, g)


def _grid(a: np.ndarray, gw: int = 16, gh: int = 9) -> np.ndarray:
    h, w = a.shape
    ys = np.linspace(0, h, gh + 1).astype(int)
    xs = np.linspace(0, w, gw + 1).astype(int)
    return np.array([[a[ys[j]:ys[j + 1], xs[i]:xs[i + 1]].mean() for i in range(gw)] for j in range(gh)], np.float32)


def look_at(g: np.ndarray) -> Look:
    h, w = g.shape
    gx = np.abs(np.diff(g, axis=1, prepend=g[:, :1]))
    gy = np.abs(np.diff(g, axis=0, prepend=g[:1]))
    edges = gx + gy
    sal = np.abs(g - _blur(g, max(3, w // 8))) + 0.5 * _blur(edges, 1)
    # the frame's border rarely holds the subject: fade it out a little
    yy, xx = np.mgrid[0:h, 0:w]
    sal *= 1 - 0.5 * (np.abs(xx / (w - 1) - 0.5) * 2) ** 3 - 0.5 * (np.abs(yy / (h - 1) - 0.5) * 2) ** 3
    top = sal >= np.percentile(sal, 85)
    wts = sal * top
    s = wts.sum() or 1.0
    cx, cy = float((wts * xx).sum() / s / (w - 1)), float((wts * yy).sum() / s / (h - 1))
    spread = float(np.sqrt((wts * ((xx / (w - 1) - cx) ** 2 * (w / h) ** 2 + (yy / (h - 1) - cy) ** 2)).sum() / s))
    norm = lambda a: (a - a.mean()) / (a.std() or 1.0)  # noqa: E731
    return Look(cx, cy, min(1.0, 2.5 * spread), norm(_grid(g)), norm(_grid(edges)))


def look(path: str | Path, at: float, aspect: float = 16 / 9) -> Look:
    return look_at(_frame(path, at, aspect))


def distance(a: Look, b: Look) -> float:
    """0 = the same framing; above ~1 = nothing alike."""
    lay = 1 - float((a.layout * b.layout).mean())  # 0..2
    edg = 1 - float((a.edges * b.edges).mean())
    place = float(np.hypot(a.cx - b.cx, a.cy - b.cy))
    size = abs(np.log(max(a.size, 0.02) / max(b.size, 0.02)))
    return 0.35 * lay + 0.25 * edg + 1.4 * place + 0.35 * size


def chain(looks: list[Look], first: int = 0) -> list[int]:
    """An order that keeps each next shot as close in framing to the last one
    as possible (nearest neighbour, from `first`)."""
    left = set(range(len(looks))) - {first}
    order = [first]
    while left:
        nxt = min(left, key=lambda j: distance(looks[order[-1]], looks[j]))
        order.append(nxt)
        left.remove(nxt)
    return order


def runs(looks: list[Look], order: list[int], limit: float = MATCH) -> list[list[int]]:
    """Split an order into runs of shots that match the one before them."""
    out: list[list[int]] = []
    for k, i in enumerate(order):
        if k and distance(looks[order[k - 1]], looks[i]) < limit:
            out[-1].append(i)
        else:
            out.append([i])
    return out


def line_up(target: Look, it: Look, max_zoom: float = 1.6) -> list[float] | None:
    """How to reframe `it` so its subject sits where `target`'s does:
    [zoom, x, y], x and y being the crop's top-left corner as a share of the
    output size. None when it already lines up."""
    z = float(np.clip(target.size / max(it.size, 0.02), 1.0, max_zoom))
    x0 = it.cx * z - target.cx
    y0 = it.cy * z - target.cy
    x0, y0 = float(np.clip(x0, 0, z - 1)), float(np.clip(y0, 0, z - 1))
    if z < 1.02 and x0 < 0.01 and y0 < 0.01:
        return None
    return [round(z, 3), round(x0, 4), round(y0, 4)]


def reframe_filter(frame: list[float], w: int, h: int) -> str:
    z, x0, y0 = frame
    zw, zh = round(w * z) // 2 * 2, round(h * z) // 2 * 2
    return f",scale={zw}:{zh},crop={w}:{h}:{min(zw - w, round(x0 * w))}:{min(zh - h, round(y0 * h))}"


def order_shots(shots, aspect: float) -> tuple[list, list[list[int]]]:
    """Reorder a montage's shot contents (which clip, from where) across its
    beat-timed slots so matching framings follow each other, and line each
    one up with the one before it in its run. Lengths and speeds stay with
    their slots, so the cut stays on the music."""
    import copy

    looks = [look(s.clip, s.start + s.source_length() / 2, aspect) for s in shots]
    order = chain(looks)
    groups = runs(looks, order)
    order = [i for g in groups for i in g]
    out = []
    from .media import duration

    lengths = {x.clip: duration(x.clip) for x in shots}
    for slot, i in zip(shots, order):
        s = copy.copy(slot)
        s.clip, s.gain = shots[i].clip, shots[i].gain
        # keep the moment the shot was chosen for, but stay inside the clip at this slot's length
        mid = shots[i].start + shots[i].source_length() / 2
        s.start = round(max(0.0, min(mid - s.source_length() / 2, lengths[s.clip] - s.source_length() - 0.05)), 3)
        s.frame = None
        out.append(s)
    k = 0
    for g in groups:
        for j in range(1, len(g)):
            out[k + j].frame = line_up(looks[g[0]], looks[g[j]])
            out[k + j].why = (out[k + j].why + "; " if out[k + j].why else "") + "match cut: framing lined up with the shot before"
        k += len(g)
    return out, groups
