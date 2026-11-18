"""Fast drafts: the whole video at a third of the size with the quickest
encoder settings, plus a one-page sheet with a frame from every scene, so an
idea can be tried, looked at and changed in seconds instead of minutes."""

from __future__ import annotations

import tempfile
from pathlib import Path

from . import media

DRAFT_SCALE = 3


def enable(aspects: dict[str, str]) -> None:
    """Switch the whole run to draft quality (sizes in `aspects` shrink in place)."""
    media.DRAFT = True
    for k, v in aspects.items():
        w, h = (int(x) for x in v.split("x"))
        aspects[k] = f"{w // DRAFT_SCALE // 2 * 2}x{h // DRAFT_SCALE // 2 * 2}"


def fast_args(args: list[str]) -> list[str]:
    """The same ffmpeg command with the quickest x264 settings."""
    out = list(args)
    for flag, value in (("-preset", "ultrafast"), ("-crf", "26")):
        for i, a in enumerate(out[:-1]):
            if a == flag:
                out[i + 1] = value
    return out


def sheet(video: Path, marks: list[tuple[float, str]], out: Path, cols: int = 4) -> Path:
    """One image with a labelled frame from each mark (time, label)."""
    from .style import FONTS

    font = str(FONTS / "Inter-SemiBold.otf").replace("\\", "/").replace(":", r"\:")
    with tempfile.TemporaryDirectory() as d:
        for k, (t, label) in enumerate(marks):
            text = label.replace("\\", "").replace("'", "’").replace(":", r"\:").replace("%", r"\%")
            media.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", f"{max(0.0, t):.3f}", "-i", str(video), "-frames:v", "1",
                       "-vf", "scale='if(gt(iw,ih),480,-2)':'if(gt(iw,ih),-2,480)',"
                       f"drawbox=x=0:y=ih-34:w=iw:h=34:color=black@0.65:t=fill,"
                       f"drawtext=fontfile='{font}':text='{text}':x=10:y=h-26:fontsize=18:fontcolor=white",
                       str(Path(d) / f"f{k:03d}.png")])
        rows = (len(marks) + cols - 1) // cols
        media.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-framerate", "1", "-i", str(Path(d) / "f%03d.png"),
                   "-vf", f"tile={min(cols, len(marks))}x{rows}:padding=6:margin=6:color=white", "-frames:v", "1", str(out)])
    return out
