"""Editable timeline export, so the cut can be finished in a normal editor.

CMX3600 EDL: the oldest, plainest timeline format. DaVinci Resolve
(File > Import > Timeline), Premiere Pro (File > Import) and Final Cut (via
tools) read it. Clips are named by file so the editor can relink the media.
"""

from __future__ import annotations

from pathlib import Path

from .cut import Clip


def _tc(seconds: float, fps: int) -> str:
    f = int(round(seconds * fps))
    hh, f = divmod(f, 3600 * fps)
    mm, f = divmod(f, 60 * fps)
    ss, ff = divmod(f, fps)
    return f"{hh:02d}:{mm:02d}:{ss:02d}:{ff:02d}"


def write_edl(path: Path, title: str, sources: list[Path], clips: list[Clip], script: list[str], fps: float) -> None:
    rate = int(round(fps))  # EDL counts whole frames (non-drop-frame)
    rows = [f"TITLE: {title}", "FCM: NON-DROP FRAME", ""]
    rec = 3600.0  # timelines conventionally start at 01:00:00:00
    for n, c in enumerate(clips, 1):
        name = sources[c.source].name
        reel = f"AX{c.source + 1:<6}"[:8]
        rows.append(
            f"{n:03d}  {reel:<8} AA/V  C        "
            f"{_tc(c.start, rate)} {_tc(c.end, rate)} {_tc(rec, rate)} {_tc(rec + c.length, rate)}"
        )
        rows.append(f"* FROM CLIP NAME: {name}")
        rows.append(f"* LINE {c.line + 1}: {script[c.line]}")
        rows.append("")
        rec += c.length
    path.write_text("\n".join(rows), encoding="utf-8")
