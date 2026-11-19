"""Thin helpers around FFmpeg, which the user installs and we run as a separate program."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import numpy as np


def need_ffmpeg() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise SystemExit(f"{tool} not found. Please install FFmpeg (https://ffmpeg.org/download.html).")


DRAFT = False  # set by draft.enable(): every encode at the quickest settings


def run(args: list[str]) -> subprocess.CompletedProcess:
    if DRAFT and args and args[0] == "ffmpeg":
        from .draft import fast_args

        args = fast_args(args)
    proc = subprocess.run(args, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-15:])
        raise RuntimeError(f"command failed: {' '.join(args[:6])} ...\n{tail}")
    return proc


def load_audio(path: str | Path, sr: int = 16000) -> np.ndarray:
    """Decode any audio/video file to mono float32 at `sr` Hz."""
    proc = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode(errors="replace")[-800:])
    return np.frombuffer(proc.stdout, dtype=np.float32).copy()


def duration(path: str | Path) -> float:
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)]).stdout
    return float(out.strip())


def has_video(path: str | Path) -> bool:
    out = run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=index", "-of", "csv=p=0", str(path)]).stdout
    return bool(out.strip())


def video_size(path: str | Path) -> tuple[int, int] | None:
    """The picture's size as it is shown: phones store upright video sideways
    with a note to turn it, so a turned picture swaps width and height."""
    import json

    out = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
               "stream=width,height:stream_side_data=rotation:stream_tags=rotate", "-of", "json", str(path)]).stdout
    try:
        st = json.loads(out)["streams"][0]
    except (ValueError, KeyError, IndexError):
        return None
    w, h = int(st["width"]), int(st["height"])
    turn = st.get("tags", {}).get("rotate")
    for sd in st.get("side_data_list", []) or []:
        if "rotation" in sd:
            turn = sd["rotation"]
    if turn is not None and round(abs(float(turn))) % 180 == 90:
        w, h = h, w
    return w, h


def frame_rate(path: str | Path, default: float = 30.0) -> float:
    out = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0", str(path)]).stdout.strip()
    out = out.split(",")[0].split()[0] if out else out  # some phone files add an empty field
    if not out or "/" not in out:
        return default
    n, d = out.split("/")[:2]
    return float(n) / float(d) if float(d) else default


def speech_regions(
    path: str | Path, noise_db: float = -35.0, min_silence: float = 0.35, start: float | None = None, end: float | None = None
) -> list[tuple[float, float]]:
    """Find stretches of sound between silences using FFmpeg's silencedetect.
    With start/end, only that part of the file is read; times stay absolute."""
    rng = []
    if start is not None:
        rng += ["-ss", f"{start:.3f}"]
    if end is not None:
        rng += ["-to", f"{end:.3f}"]
    total = (end if end is not None else duration(path)) - (start or 0.0)
    err = run(
        ["ffmpeg", "-nostdin", *rng, "-i", str(path), "-vn", "-af", f"silencedetect=noise={noise_db}dB:d={min_silence}", "-f", "null", "-"]
    ).stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", err)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", err)]
    regions: list[tuple[float, float]] = []
    cursor = 0.0
    for i, s in enumerate(starts):
        if s - cursor > 0.05:
            regions.append((cursor, s))
        cursor = ends[i] if i < len(ends) else total
    if total - cursor > 0.05:
        regions.append((cursor, total))
    off = start or 0.0
    return [(a + off, b + off) for a, b in regions]
