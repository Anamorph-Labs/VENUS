"""A camera for screen recordings: it follows what is happening.

A screen recording shown whole and still reads flat: the viewer hunts for the
cursor and the words are too small to read. For a scene marked "screen"
(every clip in a how-to, unless it says "screen": false), Venus finds where
the screen changes from moment to moment (the cursor moving, text being
typed, a menu opening), and moves a virtual camera there: it pushes in on a
small change so it can be read, eases back out when the whole page changes,
and holds still when nothing happens. Every move is eased; nothing jumps.

Measured from the recording itself (frame differences), not guessed: it does
not read what is on the screen."""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

AW = 320  # analysis width
STEP = 0.2  # seconds between readings


def _gray(path: Path, w: int, fps: float) -> tuple[np.ndarray, int]:
    from .media import video_size

    w0, h0 = video_size(path) or (16, 9)
    h = max(2, round(w * h0 / max(1, w0) / 2) * 2)
    raw = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(path), "-an", "-vf",
                          f"fps={fps:g},scale={w}:{h}:flags=area,format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
    n = len(raw) // (w * h)
    return np.frombuffer(raw[: n * w * h], np.uint8).reshape(n, h, w), h


def path_of(frames: np.ndarray, most: float = 1.8, step: float = STEP) -> list[tuple[float, float, float, float]]:
    """(time, zoom, centre x, centre y) every `step` s; x, y as parts of the frame."""
    n, h, w = frames.shape
    keys = []
    z, cx, cy = 1.0, 0.5, 0.5
    tz, tx, ty = 1.0, 0.5, 0.5  # where the camera is heading; it stays there until something new happens
    idle = 0.0
    for i in range(n):
        if i:
            d = np.abs(frames[i].astype(np.int16) - frames[i - 1].astype(np.int16)) > 12
            share = float(d.mean())
            if share > 0.2:  # the whole page changed: step back and show it
                tz, tx, ty, idle = 1.0, 0.5, 0.5, 0.0
            elif share > 0.0004:
                ys, xs = np.nonzero(d)
                x0, x1 = np.percentile(xs, [2, 98]) / w
                y0, y1 = np.percentile(ys, [2, 98]) / h
                ext = max(x1 - x0, (y1 - y0), 0.08)
                tz = float(np.clip(0.55 / ext, 1.0, most))  # the change fills about half the frame, with room around it
                tx, ty = float((x0 + x1) / 2), float((y0 + y1) / 2)
                idle = 0.0
            else:
                idle += step
                if idle > 3.0:  # nothing happening for a while: drift gently back out
                    tz = max(1.0, tz - 0.15 * step)
        a = 1 - np.exp(-step / 0.7)  # eased: about 0.7 s to settle on a new spot
        z += (tz - z) * a
        cx += (tx - cx) * a
        cy += (ty - cy) * a
        half = 0.5 / z  # keep the crop inside the picture
        keys.append((round(i * step, 3), round(z, 3), round(float(np.clip(cx, half, 1 - half)), 4),
                     round(float(np.clip(cy, half, 1 - half)), 4)))
    return keys


def apply(video: Path, w: int, h: int, fps: float, most: float = 1.8) -> int:
    """Rewrite a scene's video with the camera following the activity.
    Returns how many moves it made (0: nothing happened, left as it was)."""
    frames, _ = _gray(video, AW, 1 / STEP)
    if len(frames) < 3:
        return 0
    keys = path_of(frames, most)
    if max(k[1] for k in keys) < 1.05:
        return 0
    t = np.array([k[0] for k in keys])
    Z, X, Y = (np.array([k[i] for k in keys]) for i in (1, 2, 3))
    raw = video.with_name(video.stem + ".flat.mp4")
    video.rename(raw)
    dec = subprocess.Popen(["ffmpeg", "-nostdin", "-v", "error", "-i", str(raw), "-an", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                           stdout=subprocess.PIPE)
    enc = subprocess.Popen(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
                            "-r", f"{fps:g}", "-i", "-", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "14",
                            "-pix_fmt", "yuv420p", str(video)], stdin=subprocess.PIPE)
    from PIL import Image

    size = w * h * 3
    k = 0
    moves = 0
    last = 1.0
    try:
        while True:
            buf = dec.stdout.read(size)
            if len(buf) < size:
                break
            tt = k / fps
            z, cx, cy = float(np.interp(tt, t, Z)), float(np.interp(tt, t, X)), float(np.interp(tt, t, Y))
            if abs(z - last) > 0.02:
                moves += 1
                last = z
            im = Image.frombuffer("RGB", (w, h), buf)
            cw, ch = w / z, h / z
            x0 = min(max(0.0, cx * w - cw / 2), w - cw)  # never past the picture's edge (rounding included)
            y0 = min(max(0.0, cy * h - ch / 2), h - ch)
            im = im.resize((w, h), Image.BICUBIC, box=(x0, y0, x0 + cw, y0 + ch))
            enc.stdin.write(im.tobytes())
            k += 1
    finally:
        enc.stdin.close()
        enc.wait()
        dec.stdout.close()
        dec.wait()
    raw.unlink(missing_ok=True)
    return moves
