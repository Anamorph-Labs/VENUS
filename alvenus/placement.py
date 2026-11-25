"""Where each caption card sits, decided per shot from the picture under it.

Captions that always sit in one spot ignore the picture: they cover a face in
one shot and leave an empty sky unused in the next. For every caption card
Venus looks at the frame under it (one reading every half second, small) and
scores each place the card could go: how busy the picture is there (fine
detail, edges), how much skin tone is there (a face or hands: never covered),
and how far it is from the platform's own buttons and caption area (safe
zones). The quietest place wins, with three habits a good designer has:

  - the card stays put within a shot; it moves only when the picture changes;
  - bottom centre is the reading habit, so it gets a small head start;
  - when two places are nearly as good, the one the last shot didn't use wins,
    so the words don't sit in the same spot all video.

What it measures is detail and skin tone, not who is in the picture: it does
not recognise faces or objects. A scene can always say where its caption goes
("caption_place": "top", "bottom-left", ...), and that wins."""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

SW = 160  # analysis width in pixels
EVERY = 0.5  # seconds between readings

# name -> (ASS alignment, x as part of width, y as part of height) for the card's anchor
SLOTS_WIDE = {
    "bottom": (2, 0.5, 0.93), "top": (8, 0.5, 0.07),
    "bottom-left": (1, 0.07, 0.93), "bottom-right": (3, 0.93, 0.93),
    "top-left": (7, 0.07, 0.07), "top-right": (9, 0.93, 0.07),
}
# Tall videos: the bottom fifth (caption and account name) and the right edge
# (like, comment, share) belong to the app, so cards stay above and left of them.
SLOTS_TALL = {
    "bottom": (2, 0.5, 0.78), "middle": (5, 0.5, 0.52), "top": (8, 0.5, 0.14),
    "bottom-left": (1, 0.08, 0.78), "top-left": (7, 0.08, 0.14),
    "bottom-right": (3, 0.88, 0.78), "top-right": (9, 0.88, 0.14),  # right edge stops short of the app's buttons
}
NAMES = sorted(set(SLOTS_WIDE) | set(SLOTS_TALL))


def safe_box(w: int, h: int) -> tuple[int, int, int, int]:
    """(left, top, right, bottom) of where words may go: clear of the edges and,
    on tall videos, of the app's caption area (bottom 20%) and buttons (right 12%)."""
    if h > w:
        return round(0.06 * w), round(0.08 * h), round(0.88 * w), round(0.80 * h)
    return round(0.05 * w), round(0.05 * h), round(0.95 * w), round(0.95 * h)


def slots(w: int, h: int) -> dict:
    return SLOTS_TALL if h > w else SLOTS_WIDE


def box_of(name: str, bw: float, bh: float, w: int, h: int) -> tuple[float, float, float, float]:
    """The box a card of bw x bh pixels covers at a slot."""
    an, xf, yf = slots(w, h)[name]
    x, y = xf * w, yf * h
    col, row = (an - 1) % 3, (an - 1) // 3  # 0 left/bottom ... 2 right/top
    x0 = x if col == 0 else x - bw / 2 if col == 1 else x - bw
    y0 = y - bh if row == 0 else y - bh / 2 if row == 1 else y
    return x0, y0, x0 + bw, y0 + bh


def read_frames(video: Path, every: float = EVERY) -> tuple[np.ndarray, float]:
    """Small RGB frames every `every` seconds."""
    from .media import video_size

    w0, h0 = video_size(video) or (16, 9)
    sh = max(2, round(SW * h0 / max(1, w0) / 2) * 2)
    raw = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(video), "-an", "-vf",
                          f"fps={1 / every:g},scale={SW}:{sh}:flags=area,format=rgb24", "-f", "rawvideo", "-"],
                         capture_output=True).stdout
    n = len(raw) // (SW * sh * 3)
    return np.frombuffer(raw[: n * SW * sh * 3], np.uint8).reshape(n, sh, SW, 3), every


def cost_map(f: np.ndarray) -> np.ndarray:
    """Per pixel, how bad it is to put words here: fine detail plus skin tone."""
    x = f.astype(np.float32)
    g = x.mean(axis=2)
    gy, gx = np.gradient(g)
    edges = np.hypot(gx, gy)
    r, gg, b = x[..., 0], x[..., 1], x[..., 2]
    cr = 0.5 * r - 0.4187 * gg - 0.0813 * b + 128
    cb = -0.1687 * r - 0.3313 * gg + 0.5 * b + 128
    skin = ((cr > 135) & (cr < 172) & (cb > 80) & (cb < 125) & (g > 50)).astype(np.float32)
    return np.minimum(edges, 60) / 60 + 2.5 * skin


class Planner:
    """Decides a place for each caption card. place(t0, t1, bw, bh, line) -> slot name."""

    def __init__(self, video: Path | None, w: int, h: int, fixed: dict[int, str] | None = None, frames=None):
        self.w, self.h = w, h
        self.fixed = fixed or {}
        self.frames, self.every = frames if frames is not None else (read_frames(video) if video else (np.zeros((0, 1, 1, 3), np.uint8), EVERY))
        self.last: str | None = None
        self.last_shot: np.ndarray | None = None
        self.prev_shot_slot: str | None = None
        self.used: list[str] = []

    def _frame(self, t: float) -> np.ndarray | None:
        if not len(self.frames):
            return None
        return self.frames[min(len(self.frames) - 1, max(0, int(t / self.every)))]

    def _new_shot(self, f: np.ndarray) -> bool:
        if self.last_shot is None:
            return True
        a, b = f.astype(np.float32).mean(axis=2), self.last_shot.astype(np.float32).mean(axis=2)
        return float(np.abs(a - b).mean()) > 18

    def scores(self, f: np.ndarray, bw: float, bh: float) -> dict[str, float]:
        cm = cost_map(f)
        sh, sw = cm.shape
        sx, sy = sw / self.w, sh / self.h
        L, T, R, B = safe_box(self.w, self.h)
        out = {}
        for name in slots(self.w, self.h):
            x0, y0, x1, y1 = box_of(name, bw, bh, self.w, self.h)
            if x0 < L - 2 or x1 > R + 2 or y0 < T - 2 or y1 > B + 2:
                x0, x1 = max(x0, L), min(x1, R)
                y0, y1 = max(y0, T), min(y1, B)
            pad = 0.15 * bh
            a = cm[max(0, int((y0 - pad) * sy)): max(1, int((y1 + pad) * sy)), max(0, int(x0 * sx)): max(1, int(x1 * sx))]
            out[name] = float(a.mean()) if a.size else 9.0
            if name == "bottom":
                out[name] *= 0.85  # where people expect to read
        return out

    def place(self, t0: float, t1: float, bw: float, bh: float, line: int = -1) -> str:
        if line in self.fixed:
            self.last = self.fixed[line]
            return self.last
        f = self._frame((t0 + t1) / 2)
        if f is None:
            return self.last or "bottom"
        new = self._new_shot(f)
        if not new and self.last:
            return self.last
        sc = self.scores(f, bw, bh)
        order = sorted(sc, key=sc.get)
        best = order[0]
        if len(order) > 1 and best == self.prev_shot_slot and sc[order[1]] <= sc[best] * 1.12 + 0.01:
            best = order[1]  # nearly as good, and the words move with the new shot
        self.prev_shot_slot = self.last
        self.last, self.last_shot = best, f
        self.used.append(best)
        return best

    def anchor(self, name: str) -> tuple[int, int, int]:
        """(ASS alignment, x, y) for a slot, inside the safe box."""
        an, xf, yf = slots(self.w, self.h)[name]
        L, T, R, B = safe_box(self.w, self.h)
        return an, int(min(max(xf * self.w, L), R)), int(min(max(yf * self.h, T), B))


def parse_place(v) -> str | None:
    """A scene's "caption_place" ("top", "bottom left", "auto") as a slot name, or None for auto."""
    s = str(v or "").strip().lower().replace(" ", "-").replace("centre", "").replace("center", "").strip("-")
    if not s or s == "auto":
        return None
    return s if s in NAMES else None
