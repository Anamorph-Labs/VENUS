"""Look through a folder of cutaway shots (B-roll) so the AI editor can choose.

For each clip: length, frame shape, whether it has its own sound, where its
own cuts are, and five frames with their times printed on them. All the
strips go on one overview sheet, so a model that can see images can pick
"market.mp4 from 4.5 s" for a line about the market."""

from __future__ import annotations

import json
from pathlib import Path

from .media import duration, frame_rate, has_video, run, video_size
from .reference import _cuts, _shape

VIDEO = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".mts"}


def _strip(path: Path, out: Path, times: list[float]) -> None:
    """Five frames side by side, each labelled with the file name and time."""
    args = ["ffmpeg", "-nostdin", "-y", "-v", "error"]
    for t in times:
        args += ["-ss", f"{t:.3f}", "-i", str(path)]
    label = path.name.replace("\\", "/").replace(":", r"\:").replace("'", "")
    parts = [
        f"[{i}:v]trim=end_frame=1,scale=256:144:force_original_aspect_ratio=decrease,"
        f"pad=256:144:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,"
        f"drawtext=text='{label} @ {t:.1f}s':x=4:y=h-th-4:fontsize=13:fontcolor=white:box=1:boxcolor=black@0.6[f{i}]"
        for i, t in enumerate(times)
    ]
    parts.append("".join(f"[f{i}]" for i in range(len(times))) + f"hstack=inputs={len(times)}[s]")
    run(args + ["-filter_complex", ";".join(parts), "-map", "[s]", "-frames:v", "1", str(out)])


def scan(items: list[str], out_dir: Path | None = None) -> dict:
    files: list[Path] = []
    for it in items:
        p = Path(it)
        files += sorted(f for f in p.iterdir() if f.suffix.lower() in VIDEO) if p.is_dir() else [p]
    files = [f for f in files if f.exists() and has_video(f)]
    if not files:
        raise SystemExit("no video clips found to scan")
    out_dir = out_dir or (Path(items[0]) if Path(items[0]).is_dir() else Path(items[0]).parent)
    out_dir.mkdir(parents=True, exist_ok=True)

    clips, strips = [], []
    for f in files:
        length = duration(f)
        w, h = video_size(f) or (0, 0)
        times = [round(length * k, 2) for k in (0.1, 0.3, 0.5, 0.7, 0.9)]
        strip = out_dir / f".{f.stem}.strip.png"
        _strip(f, strip, times)
        strips.append(strip)
        audio = bool(run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
                          "-of", "csv=p=0", str(f)]).stdout.strip())
        clips.append({
            "file": str(f.resolve()), "seconds": round(length, 2), "size": f"{w}x{h}",
            "shape": _shape(w, h) if w and h else None, "fps": round(frame_rate(f), 2),
            "own_sound": audio, "cuts_inside_at": [round(c, 2) for c in _cuts(f)],
            "frames_shown_at": times,
        })

    sheets = []
    for n in range(0, len(strips), 12):  # 12 clips per sheet keeps it readable
        sheet = out_dir / f"broll.sheet{n // 12 + 1}.png"
        group = strips[n : n + 12]
        args = ["ffmpeg", "-nostdin", "-y", "-v", "error"]
        for s in group:
            args += ["-i", str(s)]
        stack = "".join(f"[{i}:v]" for i in range(len(group))) + f"vstack=inputs={len(group)}" if len(group) > 1 else "null"
        run(args + ["-filter_complex", stack, "-frames:v", "1", str(sheet)])
        sheets.append(str(sheet))
    for s in strips:
        s.unlink()

    report = {"clips": clips, "contact_sheets": sheets,
              "how_to_use": "lay a clip over a script line with --broll LINE=FILE@SECONDS, or add it to the plan's broll list"}
    (out_dir / "broll.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
