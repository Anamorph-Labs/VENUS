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


def run(args: list[str]) -> subprocess.CompletedProcess:
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


def speech_regions(path: str | Path, noise_db: float = -35.0, min_silence: float = 0.35) -> list[tuple[float, float]]:
    """Find stretches of sound between silences using FFmpeg's silencedetect."""
    total = duration(path)
    err = run(
        ["ffmpeg", "-nostdin", "-i", str(path), "-vn", "-af", f"silencedetect=noise={noise_db}dB:d={min_silence}", "-f", "null", "-"]
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
    return regions
