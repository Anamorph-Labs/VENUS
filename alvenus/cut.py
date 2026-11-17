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
    zoom: float = 1.0  # punch-in: >1 crops in to hide a jump cut
    hold: float = 0.0  # seconds to hold the last frame (and room tone) after the clip

    @property
    def length(self) -> float:
        return self.end - self.start + self.hold


PUNCH_IN = 1.12  # how far to push in on alternate shots from the same camera


def hide_jump_cuts(clips: list[Clip]) -> None:
    """When two clips in a row come from the same file (same camera, same
    framing), the cut between them jumps. Editors hide that by alternating
    between the normal framing and a slightly closer one."""
    for prev, c in zip(clips, clips[1:]):
        if c.source == prev.source:
            c.zoom = 1.0 if prev.zoom > 1.0 else PUNCH_IN


def _srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def take_clips(
    path: Path, source: int, line: int, start: float, end: float, file_len: float,
    head: float = 0.12, tail: float = 0.25, max_pause: float | None = 0.6, keep_pause: float = 0.3,
    room: tuple[float, float] | None = None, hold_short: bool = False,
) -> list[Clip]:
    """Clips for one chosen take. With max_pause set, any pause inside the take
    longer than max_pause is shortened to keep_pause (a small jump cut).

    `room` is the quiet before and after the take in its file (end of the
    previous sound, start of the next), so the breathing room never catches
    a word of a neighbouring take. With hold_short, a tail the footage can't
    give is made up by holding the last frame over room tone."""
    lo, hi = (room if room else (0.0, file_len))
    s = min(start, max(0.0, lo + 0.05, start - head))
    want = end + tail
    e = max(end, min(file_len, hi - 0.05, want))
    hold = round(want - e, 3) if hold_short and want - e > 0.04 else 0.0
    if max_pause is None:
        return [Clip(source, s, e, line, hold=hold)]
    sounds = speech_regions(path, min_silence=max_pause, start=start, end=end)
    if len(sounds) <= 1:
        return [Clip(source, s, e, line, hold=hold)]
    clips, cur = [], s
    half = keep_pause / 2
    for (a0, a1), (b0, _) in zip(sounds, sounds[1:]):
        clips.append(Clip(source, cur, a1 + half, line))
        cur = b0 - half
    clips.append(Clip(source, cur, e, line, hold=hold))
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


def subtitle_filter(srt: Path, w: int, h: int) -> str:
    # Subtitle sizes are in units of 1/288 of the frame height; keep the
    # text about 6% of the frame's short side so vertical video isn't huge.
    fs = round(0.06 * min(w, h) * 288 / h, 1)
    style = f"FontName=DejaVu Sans,FontSize={fs},Outline=2,Shadow=1,MarginV=40,MarginL=20,MarginR=20"
    esc = str(srt).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")
    return f"subtitles='{esc}':force_style='{style}'"


def render(
    sources: list[Path], clips: list[Clip], out: Path, srt: Path | None = None, size: str = "1280x720",
    fps: float = 30.0, room_tone: tuple[int, float, float] | None = None,
) -> None:
    """room_tone: (source, start, end) of a quiet stretch of the recording. It is
    looped quietly under the whole cut so the room never drops to dead silence
    at a cut, a fade or a held frame."""
    used = sorted({c.source for c in clips})
    inp = {src: k for k, src in enumerate(used)}  # source index -> ffmpeg input number
    video = all(has_video(sources[s]) for s in used)
    w, h = (int(x) for x in size.split("x"))
    sizes = {s: video_size(sources[s]) for s in used} if video else {}
    if room_tone is not None and room_tone[0] not in inp:
        inp[room_tone[0]] = len(used)
        used.append(room_tone[0])
    fade_in, fade_out = 0.03, 0.06  # long enough to never click, short enough to keep every word
    parts, labels = [], []
    for i, c in enumerate(clips):
        k = inp[c.source]
        d = c.end - c.start
        hold = f",apad=pad_dur={c.hold:.3f}" if c.hold else ""
        parts.append(
            f"[{k}:a]atrim={c.start:.3f}:{c.end:.3f},asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=mono,"
            f"afade=t=in:d={fade_in},afade=t=out:st={max(0.0, d - fade_out):.3f}:d={fade_out}{hold}[a{i}]"
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
            post = []
            if c.zoom > 1.0:
                zw, zh = (2 * round(w * c.zoom / 2), 2 * round(h * c.zoom / 2))
                post.append(f"scale={zw}:{zh},crop={w}:{h}")
            if c.hold:
                post.append(f"tpad=stop_mode=clone:stop_duration={c.hold:.3f}")
            if post:
                parts[-1] = parts[-1][: -len(f"[v{i}]")] + "[vp" + str(i) + "]"
                parts.append(f"[vp{i}]{','.join(post)},setsar=1[v{i}]")
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
    if room_tone is not None:
        k, r0, r1 = room_tone
        total = sum(c.length for c in clips)
        n_samples = max(1, int((r1 - r0) * 48000))
        j = next(i for i, x in enumerate(parts) if "concat=" in x)
        parts[j] = parts[j].replace("[ac]", "[speech]")
        parts.append(
            f"[{k}:a]atrim={r0:.3f}:{r1:.3f},asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=mono,"
            f"aloop=loop=-1:size={n_samples},atrim=0:{total:.3f},asetpts=PTS-STARTPTS[room]"
        )
        parts.append("[speech][room]amix=inputs=2:normalize=0:duration=first[ac]")
    vlast = "vc"
    if srt is not None:
        parts.append(f"[{vlast}]{subtitle_filter(srt, w, h)}[vs]")
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
