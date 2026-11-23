"""The creative-edit pass: dress a fast montage with silhouettes, light strobes
and looks, the way surreal "creative edit" reels are cut.

It looks at the first frame of every shot and decides:

- a shot on a plain background (a studio, an AI picture on one colour) gets
  the subject lifted onto a flipping colour, small and centred, held in the
  same spot from shot to shot, so a run of them reads as one thing changing
  (seed, sprout, plant). The last of such a run dashes off with speed lines.
- other shots take turns through a deck: glowing silhouettes with copies, a
  black silhouette on a rim of red light, the photo flickering with its
  sketch or blueprint, negative, x-ray, colour pop, two-colour poster,
  lightning, arrows, the picture repeated, squeezed into a strip. The
  cut-out tricks go to the longer shots, where they can be seen.
- drops and every few cuts start with a light burst, a star flash or a
  smear; the second-last shot burns to white; the last becomes dots (that
  gather into --shape) and ends on a black-and-white strobe.
- --words go behind the subject of the longest shot in the middle.

Every choice is written to the plan (.montage.json: "fx" and "fxo" per shot),
so a person or their AI can change any shot's effects and render again."""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

from .cutout import is_plain

DECK = [
    (["glow"], {"copies": 3}, 0.3),
    (["flick"], {"with": "sketch"}, 0.0),
    (["silhouette"], {}, 0.25),
    (["negative"], {}, 0.0),
    (["pop"], {}, 0.3),
    (["flick"], {"with": "blueprint"}, 0.0),
    (["xray"], {}, 0.0),
    (["lightning"], {}, 0.3),
    (["poster"], {}, 0.0),
    (["arrows"], {"count": 5}, 0.3),
    (["repeat"], {}, 0.0),
    (["strobe-light"], {}, 0.0),
    (["strip"], {}, 0.0),
    (["flick"], {"with": "chalk"}, 0.0),
]
ENTRY = ["starburst", "smear", "burst", "pixel"]


def first_frame(clip: str, at: float, size: int = 160) -> np.ndarray | None:
    raw = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-ss", f"{max(0.0, at):.3f}", "-i", clip, "-frames:v", "1",
                          "-vf", f"scale={size}:{size}:force_original_aspect_ratio=decrease,pad={size}:{size}:-1:-1:color=0x808080@0",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    if len(raw) < size * size * 3:
        return None
    return np.frombuffer(raw[: size * size * 3], np.uint8).reshape(size, size, 3)


def _look_at(clip: str, at: float) -> tuple[bool, bool]:
    """(on a plain background, dark)."""
    from .montage import IMAGES

    f = first_frame(clip, 0.0 if Path(clip).suffix.lower() in IMAGES else at + 0.05)
    if f is None:
        return False, False
    # The pad above is grey; look only at the picture itself.
    rows = np.where(np.abs(f.astype(int) - 128).sum(axis=(1, 2)) > 0)[0]
    cols = np.where(np.abs(f.astype(int) - 128).sum(axis=(0, 2)) > 0)[0]
    if len(rows) and len(cols):
        f = f[rows.min():rows.max() + 1, cols.min():cols.max() + 1]
    return is_plain(f), float(f.mean()) < 70


def dress(shots: list, words: str | None = None, shape: str | None = None, seed: int = 0) -> list:
    """Give every shot its creative effects (in place) and return the shots."""
    if not shots:
        return shots
    rng = np.random.default_rng(seed)
    # The ending needs room: dots take a second and a half to gather into a shape.
    want = 1.5 if shape else 0.6
    while len(shots) > 2 and shots[-1].length < want:
        end = shots.pop()
        prev = shots[-1]
        prev.length = round(prev.length + end.length, 3)
        prev.speed_end, prev.pulse = None, 0.0
        from .montage import IMAGES

        if Path(prev.clip).suffix.lower() not in IMAGES:
            from .media import duration

            room = duration(prev.clip) - prev.start - 0.05
            if prev.length * prev.speed > room:
                prev.speed = round(max(0.2, room / prev.length), 3)
        prev.why = "the ending: held longer for the last effect"
    looks = [_look_at(s.clip, s.start) for s in shots]
    deck_i = int(rng.integers(0, len(DECK)))
    n = len(shots)
    for k, (sh, (plain, dark)) in enumerate(zip(shots, looks)):
        sh.fx, sh.fxo = [], {}
        if plain:
            sh.fx, sh.fxo = ["solid"], {"size": 0.24, "cutout": "plain"}
            nxt_plain = k + 1 < n and looks[k + 1][0]
            if not nxt_plain and sh.length >= 0.35:
                sh.fx.append("speedlines")
        elif k % 6 != 5:  # one shot in six stays clean, so the eye can rest
            for _ in range(len(DECK)):
                fx, o, need = DECK[deck_i % len(DECK)]
                deck_i += 1
                if sh.length >= need:
                    sh.fx, sh.fxo = list(fx), dict(o)
                    break
        if sh.flash:  # a drop: a light burst instead of a plain white flash
            sh.flash = False
            sh.fx.insert(0, "burst")
        elif k and k % 3 == 0:
            sh.fx.insert(0, ENTRY[(k // 3) % len(ENTRY)])
    if words:
        mid = [k for k in range(n // 4, max(n // 4 + 1, 3 * n // 4)) if not looks[k][0]] or list(range(n))
        k = max(mid, key=lambda i: shots[i].length)
        shots[k].fx = [x for x in shots[k].fx if x not in ("glow", "silhouette", "pop", "repeat", "strip")] + ["words"]
        shots[k].fxo["words"] = words
    if n >= 3:
        shots[-2].fx = [x for x in shots[-2].fx if x != "speedlines"] + ["burn"]
    last = shots[-1]
    last.fx = ["dots", "endstrobe"] if (shape or looks[-1][1]) else last.fx + ["endstrobe"]
    last.fxo["endstrobe.frames"] = 4
    if shape:
        last.fxo["shape"] = shape
    return shots
