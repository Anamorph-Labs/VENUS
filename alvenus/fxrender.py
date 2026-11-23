"""Reading a shot into frames, running creative effects on them, and writing it
back. Used by `alvenus fx`, `alvenus cutout` and creative montages."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np

IMAGES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


def is_image(p: str | Path) -> bool:
    return Path(p).suffix.lower() in IMAGES


def probe_fps(p: str | Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=avg_frame_rate,width,height",
                          "-of", "json", str(p)], capture_output=True, text=True).stdout
    try:
        st = json.loads(out)["streams"][0]
        a, b = st["avg_frame_rate"].split("/")
        return float(a) / float(b) if float(b) else 30.0
    except (KeyError, IndexError, ValueError, ZeroDivisionError):
        return 30.0


def read_frames(p: str | Path, size: tuple[int, int] | None = None, fps: float | None = None,
                seconds: float = 2.0) -> tuple[np.ndarray, float]:
    """All frames as N x H x W x 3 uint8. A picture becomes `seconds` of still frames."""
    from .media import video_size

    fps = fps or (30.0 if is_image(p) else probe_fps(p))
    w, h = size or video_size(p) or (1280, 720)
    w, h = w // 2 * 2, h // 2 * 2
    pre = ["-loop", "1", "-framerate", f"{fps:g}", "-t", f"{seconds:.3f}"] if is_image(p) else []
    vf = f"fps={fps:g},scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1"
    raw = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", *pre, "-i", str(p), "-an", "-vf", vf,
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    n = len(raw) // (w * h * 3)
    if n == 0:
        raise SystemExit(f"could not read any frames from {p}")
    return np.frombuffer(raw[: n * w * h * 3], np.uint8).reshape(n, h, w, 3).copy(), fps


def write_frames(frames: np.ndarray, fps: float, out: str | Path, crf: int = 14) -> None:
    n, h, w, _ = frames.shape
    p = subprocess.Popen(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
                          "-r", f"{fps:g}", "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf),
                          "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE)
    for f in frames:
        p.stdin.write(np.ascontiguousarray(f).tobytes())
    p.stdin.close()
    if p.wait():
        raise RuntimeError(f"ffmpeg could not write {out}")


def apply_file(src: str | Path, out: str | Path, effects: list[str], opts: dict | None = None, seed: int = 0,
               size: tuple[int, int] | None = None, seconds: float = 2.0) -> int:
    """Run effects over a whole clip (or picture) and write the result. Returns the frame count."""
    from .fx import apply

    frames, fps = read_frames(src, size, seconds=seconds)
    res = apply(frames, fps, effects, opts, seed)
    write_frames(res, fps, out)
    return len(res)


def parse_opts(items: list[str] | None) -> dict:
    d: dict = {}
    for it in items or []:
        k, sep, v = it.partition("=")
        if not sep:
            raise SystemExit(f"--opt {it!r}: use NAME=VALUE, e.g. --opt copies=3")
        d[k.strip()] = v.strip()
    return d
