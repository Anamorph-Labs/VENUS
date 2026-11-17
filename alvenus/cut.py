"""Build the cut: trim the chosen takes from the source and join them with FFmpeg."""

from __future__ import annotations

from pathlib import Path

from .media import has_video, run


def _srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def plan_clips(spans: list[tuple[float, float]], total: float, head: float = 0.12, tail: float = 0.25) -> list[tuple[float, float]]:
    """Add a little breathing room around each take without running into the next sound."""
    clips = []
    for s, e in spans:
        clips.append((max(0.0, s - head), min(total, e + tail)))
    return clips


def write_srt(path: Path, clips: list[tuple[float, float]], texts: list[str]) -> None:
    lines, t = [], 0.0
    for n, ((s, e), text) in enumerate(zip(clips, texts), 1):
        d = e - s
        lines += [str(n), f"{_srt_time(t)} --> {_srt_time(t + d)}", text, ""]
        t += d
    path.write_text("\n".join(lines), encoding="utf-8")


def render(source: Path, clips: list[tuple[float, float]], out: Path, srt: Path | None = None, size: str = "1280x720") -> None:
    video = has_video(source)
    fade = 0.02
    parts, labels = [], []
    for i, (s, e) in enumerate(clips):
        d = e - s
        a = (
            f"[0:a]atrim={s:.3f}:{e:.3f},asetpts=PTS-STARTPTS,"
            f"afade=t=in:d={fade},afade=t=out:st={max(0.0, d - fade):.3f}:d={fade}[a{i}]"
        )
        parts.append(a)
        if video:
            parts.append(f"[0:v]trim={s:.3f}:{e:.3f},setpts=PTS-STARTPTS[v{i}]")
            labels.append(f"[v{i}][a{i}]")
        else:
            labels.append(f"[a{i}]")
    n = len(clips)
    if video:
        parts.append(f"{''.join(labels)}concat=n={n}:v=1:a=1[vc][ac]")
        vlast = "vc"
    else:
        parts.append(f"{''.join(labels)}concat=n={n}:v=0:a=1[ac]")
        total = sum(e - s for s, e in clips)
        parts.append(f"color=c=0x15171c:s={size}:r=30:d={total:.3f}[vc]")
        vlast = "vc"
    if srt is not None:
        style = "FontName=DejaVu Sans,FontSize=22,Outline=1,Shadow=0,MarginV=40"
        esc = str(srt).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")
        parts.append(f"[{vlast}]subtitles='{esc}':force_style='{style}'[vs]")
        vlast = "vs"
    parts.append("[ac]loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[ao]")
    run([
        "ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(source),
        "-filter_complex", ";".join(parts),
        "-map", f"[{vlast}]", "-map", "[ao]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out),
    ])
