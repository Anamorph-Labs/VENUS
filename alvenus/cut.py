"""Build the cut: trim the chosen takes from the sources and join them with FFmpeg."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .media import has_video, run, speech_regions, video_size


@dataclass
class Clip:
    source: int  # index into the list of input files
    start: float
    end: float
    line: int  # script line this clip belongs to

    @property
    def length(self) -> float:
        return self.end - self.start


def _srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def take_clips(
    path: Path, source: int, line: int, start: float, end: float, file_len: float,
    head: float = 0.12, tail: float = 0.25, max_pause: float | None = 0.6, keep_pause: float = 0.3,
) -> list[Clip]:
    """Clips for one chosen take. With max_pause set, any pause inside the take
    longer than max_pause is shortened to keep_pause (a small jump cut)."""
    s, e = max(0.0, start - head), min(file_len, end + tail)
    if max_pause is None:
        return [Clip(source, s, e, line)]
    sounds = speech_regions(path, min_silence=max_pause, start=start, end=end)
    if len(sounds) <= 1:
        return [Clip(source, s, e, line)]
    clips, cur = [], s
    half = keep_pause / 2
    for (a0, a1), (b0, _) in zip(sounds, sounds[1:]):
        clips.append(Clip(source, cur, a1 + half, line))
        cur = b0 - half
    clips.append(Clip(source, cur, e, line))
    return clips


def write_srt(path: Path, clips: list[Clip], script: list[str]) -> None:
    """One caption per script line, spanning all of that line's clips."""
    rows, t, n = [], 0.0, 0
    i = 0
    while i < len(clips):
        line = clips[i].line
        d = 0.0
        while i < len(clips) and clips[i].line == line:
            d += clips[i].length
            i += 1
        n += 1
        rows += [str(n), f"{_srt_time(t)} --> {_srt_time(t + d)}", script[line], ""]
        t += d
    path.write_text("\n".join(rows), encoding="utf-8")


def render(sources: list[Path], clips: list[Clip], out: Path, srt: Path | None = None, size: str = "1280x720", fps: float = 30.0) -> None:
    used = sorted({c.source for c in clips})
    inp = {src: k for k, src in enumerate(used)}  # source index -> ffmpeg input number
    video = all(has_video(sources[s]) for s in used)
    w, h = (int(x) for x in size.split("x"))
    sizes = {s: video_size(sources[s]) for s in used} if video else {}
    fade = 0.02
    parts, labels = [], []
    for i, c in enumerate(clips):
        k = inp[c.source]
        d = c.length
        parts.append(
            f"[{k}:a]atrim={c.start:.3f}:{c.end:.3f},asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=mono,"
            f"afade=t=in:d={fade},afade=t=out:st={max(0.0, d - fade):.3f}:d={fade}[a{i}]"
        )
        if video:
            # Scale/pad every clip to one size and rate so files from different
            # cameras or phone settings can sit on one timeline.
            trim = f"[{k}:v]trim={c.start:.3f}:{c.end:.3f},setpts=PTS-STARTPTS,fps={fps:g}"
            sw, sh = sizes[c.source] or (w, h)
            if abs(sw / sh - w / h) < 0.01:
                parts.append(f"{trim},scale={w}:{h},setsar=1,format=yuv420p[v{i}]")
            else:
                # A clip of another shape (say a vertical phone clip) sits on a
                # blurred, darkened, enlarged copy of itself instead of black bars.
                parts.append(
                    f"{trim},split[f{i}][b{i}];"
                    f"[b{i}]scale={w // 4}:{h // 4}:force_original_aspect_ratio=increase,crop={w // 4}:{h // 4},"
                    f"boxblur=10:2,eq=brightness=-0.12:saturation=0.8,scale={w}:{h}[bb{i}];"
                    f"[f{i}]scale={w}:{h}:force_original_aspect_ratio=decrease[ff{i}];"
                    f"[bb{i}][ff{i}]overlay=(W-w)/2:(H-h)/2,setsar=1,format=yuv420p[v{i}]"
                )
            labels.append(f"[v{i}][a{i}]")
        else:
            labels.append(f"[a{i}]")
    n = len(clips)
    if video:
        parts.append(f"{''.join(labels)}concat=n={n}:v=1:a=1[vc][ac]")
    else:
        parts.append(f"{''.join(labels)}concat=n={n}:v=0:a=1[ac]")
        total = sum(c.length for c in clips)
        parts.append(f"color=c=0x15171c:s={size}:r={fps:g}:d={total:.3f}[vc]")
    vlast = "vc"
    if srt is not None:
        style = "FontName=DejaVu Sans,FontSize=22,Outline=1,Shadow=0,MarginV=40"
        esc = str(srt).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")
        parts.append(f"[{vlast}]subtitles='{esc}':force_style='{style}'[vs]")
        vlast = "vs"
    parts.append("[ac]loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[ao]")
    args = ["ffmpeg", "-nostdin", "-y", "-v", "error"]
    for s in used:
        args += ["-i", str(sources[s])]
    args += [
        "-filter_complex", ";".join(parts),
        "-map", f"[{vlast}]", "-map", "[ao]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out),
    ]
    run(args)
