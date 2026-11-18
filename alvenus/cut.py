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
    transition: str = ""  # how this clip comes in, if not a straight cut (see TRANSITIONS)
    tdur: float = 0.0  # length of that transition; it overlaps the end of the previous clip
    reframe: list | None = None  # [(t, centre)] subject track, to crop wide footage into a taller frame

    @property
    def length(self) -> float:
        return self.end - self.start + self.hold


# Scene-break transitions, by name, as FFmpeg xfade effects.
TRANSITIONS = {
    "cut": "", "crossfade": "fade", "dip": "fadeblack", "flash": "fadewhite",
    "zoom": "zoomin", "whip": "smoothleft", "slide": "slideleft", "blur": "hblur",
}


def positions(clips: list[Clip]) -> list[float]:
    """Where each clip starts on the finished timeline (transitions overlap)."""
    out, t = [], 0.0
    for c in clips:
        t -= c.tdur if out else 0.0
        out.append(t)
        t += c.length
    return out


def total_length(clips: list[Clip]) -> float:
    return positions(clips)[-1] + clips[-1].length if clips else 0.0


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
    remove: list[tuple[float, float]] = (),
) -> list[Clip]:
    """Clips for one chosen take. With max_pause set, any pause inside the take
    longer than max_pause is shortened to keep_pause (a small jump cut).
    `remove` lists stretches to cut out (filler sounds such as "um"); each is
    replaced by a short natural pause.

    `room` is the quiet before and after the take in its file (end of the
    previous sound, start of the next), so the breathing room never catches
    a word of a neighbouring take. With hold_short, a tail the footage can't
    give is made up by holding the last frame over room tone."""
    lo, hi = (room if room else (0.0, file_len))
    s = min(start, max(0.0, lo + 0.05, start - head))
    want = end + tail
    e = max(end, min(file_len, hi - 0.05, want))
    hold = round(want - e, 3) if hold_short and want - e > 0.04 else 0.0
    if max_pause is None and not remove:
        return [Clip(source, s, e, line, hold=hold)]
    sounds = speech_regions(path, min_silence=max_pause, start=start, end=end) if max_pause is not None else [(start, end)]
    for r0, r1 in remove:
        cut = []
        for a, b in sounds:
            if r1 <= a or r0 >= b:
                cut.append((a, b))
                continue
            if r0 - a > 0.05:
                cut.append((a, r0))
            if b - r1 > 0.05:
                cut.append((r1, b))
        sounds = cut
    if len(sounds) <= 1:
        return [Clip(source, s, e, line, hold=hold)]
    clips, cur = [], s
    half = keep_pause / 2
    for (a0, a1), (b0, _) in zip(sounds, sounds[1:]):
        filler = any(abs(a1 - r0) < 0.01 and abs(b0 - r1) < 0.01 for r0, r1 in remove)
        if not filler and b0 - a1 <= keep_pause + 0.02:  # already a short pause: leave it
            continue
        pad = 0.04 if filler else half  # where a filler was, just a breath
        clips.append(Clip(source, cur, min(a1 + pad, b0), line))
        cur = max(b0 - pad, a1)
    clips.append(Clip(source, cur, e, line, hold=hold))
    return clips


def write_srt(path: Path, clips: list[Clip], script: list[str]) -> None:
    """One caption per script line, spanning all of that line's clips."""
    rows, n, i = [], 0, 0
    pos = positions(clips)
    while i < len(clips):
        line, t = clips[i].line, pos[i]
        while i < len(clips) and clips[i].line == line:
            end = pos[i] + clips[i].length
            i += 1
        if i < len(clips):
            end = min(end, pos[i])  # during a transition the next line takes over
        n += 1
        rows += [str(n), f"{_srt_time(t)} --> {_srt_time(end)}", script[line], ""]
    path.write_text("\n".join(rows), encoding="utf-8")


def subtitle_filter(srt: Path, w: int, h: int) -> str:
    # Subtitle sizes are in units of 1/288 of the frame height; keep the
    # text about 6% of the frame's short side so vertical video isn't huge.
    fs = round(0.06 * min(w, h) * 288 / h, 1)
    from .style import FONTS

    style = f"FontName=Inter SemiBold,FontSize={fs},Outline=1.6,Shadow=1,MarginV=40,MarginL=20,MarginR=20"
    esc = lambda p: str(p).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")
    return f"subtitles='{esc(srt)}':fontsdir='{esc(FONTS)}':force_style='{style}'"


def _clip_filters(c: Clip, sw_sh, w: int, h: int, fps: float, video: bool) -> tuple[str, str]:
    """Video and audio filters for one clip, read from a file already cut to it."""
    fade_in, fade_out = 0.03, 0.06  # long enough to never click, short enough to keep every word
    d = c.end - c.start
    hold = f",apad=pad_dur={c.hold:.3f}" if c.hold else ""
    af = (f"aformat=sample_rates=48000:channel_layouts=mono,atrim=0:{d:.3f},asetpts=PTS-STARTPTS,"
          f"afade=t=in:d={fade_in},afade=t=out:st={max(0.0, d - fade_out):.3f}:d={fade_out}{hold}")
    if not video:
        return "", af
    head = f"trim=0:{d:.3f},setpts=PTS-STARTPTS,fps={fps:g}"
    sw, sh = sw_sh or (w, h)
    if abs(sw / sh - w / h) < 0.01:
        vf = f"[0:v]{head},scale={w}:{h},setsar=1,format=yuv420p"
    elif c.reframe and sw / sh > w / h:
        # Wide footage into a taller frame: crop around the subject as it moves.
        from .reframe import crop_x

        cw = 2 * round(sh * w / h / 2)
        vf = f"[0:v]{head},crop={cw}:{sh}:x='{crop_x(c.reframe, sw, cw)}':y=0,scale={w}:{h},setsar=1,format=yuv420p"
    else:
        # A clip of another shape (say a vertical phone clip) sits on a
        # blurred, darkened, enlarged copy of itself instead of black bars.
        vf = (
            f"[0:v]{head},split[f][b];"
            f"[b]scale={w // 4}:{h // 4}:force_original_aspect_ratio=increase,crop={w // 4}:{h // 4},"
            f"boxblur=10:2,eq=brightness=-0.12:saturation=0.8,scale={w}:{h}[bb];"
            f"[f]scale={w}:{h}:force_original_aspect_ratio=decrease[ff];"
            f"[bb][ff]overlay=(W-w)/2:(H-h)/2,setsar=1,format=yuv420p"
        )
    if c.zoom > 1.0:
        zw, zh = (2 * round(w * c.zoom / 2), 2 * round(h * c.zoom / 2))
        vf += f",scale={zw}:{zh},crop={w}:{h},setsar=1"
    if c.hold:
        vf += f",tpad=stop_mode=clone:stop_duration={c.hold:.3f}"
    return vf, af


def _render_clip(src: Path, c: Clip, path: Path, sw_sh, w: int, h: int, fps: float, video: bool) -> None:
    vf, af = _clip_filters(c, sw_sh, w, h, fps, video)
    graph = (f"{vf}[v];" if video else "") + f"[0:a]{af}[a]"
    args = ["ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", f"{c.start:.3f}", "-t", f"{c.end - c.start + 0.1:.3f}",
            "-i", str(src), "-filter_complex", graph]
    if video:
        args += ["-map", "[v]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "12", "-pix_fmt", "yuv420p"]
    args += ["-map", "[a]", "-c:a", "pcm_s16le", str(path)]
    run(args)


def render(
    sources: list[Path], clips: list[Clip], out: Path, srt: Path | None = None, size: str = "1280x720",
    fps: float = 30.0, room_tone: tuple[int, float, float] | None = None, crf: int = 20,
) -> None:
    """Each clip is cut and conformed to one size and rate on its own (a few
    at a time), then the pieces are joined. Working clip by clip keeps memory
    flat however long the shoot is.

    room_tone: (source, start, end) of a quiet stretch of the recording. It is
    looped quietly under the whole cut so the room never drops to dead silence
    at a cut, a fade or a held frame."""
    import os
    import tempfile
    from concurrent.futures import ThreadPoolExecutor

    used = sorted({c.source for c in clips})
    video = all(has_video(sources[s]) for s in used)
    w, h = (int(x) for x in size.split("x"))
    sizes = {s: video_size(sources[s]) for s in used} if video else {}
    tmp = Path(tempfile.mkdtemp(prefix="alvenus-", dir=out.parent))
    try:
        files = [tmp / f"c{i:04d}.mkv" for i in range(len(clips))]
        workers = max(1, min(3, (os.cpu_count() or 2) - 1))
        with ThreadPoolExecutor(workers) as pool:
            list(pool.map(lambda i: _render_clip(sources[clips[i].source], clips[i], files[i], sizes.get(clips[i].source),
                                                 w, h, fps, video), range(len(clips))))
        _join(files, clips, sources, out, srt, size, w, h, fps, video, room_tone, crf, tmp)
    finally:
        for f in tmp.glob("*"):
            f.unlink()
        tmp.rmdir()


def _join(files, clips, sources, out, srt, size, w, h, fps, video, room_tone, crf, tmp) -> None:
    parts: list[str] = []
    args = ["ffmpeg", "-nostdin", "-y", "-v", "error"]
    # Straight cuts are joined with concat; at a transition the next scene
    # is laid over the end of the previous one with xfade / acrossfade.
    segs: list[list[int]] = []
    for i, c in enumerate(clips):
        if not segs or (c.transition and TRANSITIONS.get(c.transition)):
            segs.append([])
        segs[-1].append(i)
    # Each scene is joined first with the concat demuxer (cheap, one input
    # per scene), so the final graph stays small however many clips there are.
    for g, seg in enumerate(segs):
        lst = tmp / f"scene{g}.txt"
        lst.write_text("".join(f"file '{files[i].name}'\n" for i in seg), encoding="utf-8")
        args += ["-f", "concat", "-safe", "0", "-i", str(lst)]
    total = total_length(clips)
    if len(segs) == 1:
        parts.append(("[0:v]null[vc];" if video else "") + "[0:a]anull[ac]")
    else:
        seg_len = [sum(clips[i].length for i in seg) for seg in segs]
        v_prev, a_prev, t = "0:v", "0:a", seg_len[0]
        for g in range(1, len(segs)):
            c = clips[segs[g][0]]
            d = min(c.tdur, seg_len[g] / 2, t / 2)
            last = g == len(segs) - 1
            vo, ao = ("vc", "ac") if last else (f"vx{g}", f"ax{g}")
            if video:
                parts.append(f"[{v_prev}][{g}:v]xfade=transition={TRANSITIONS[c.transition]}:duration={d:.3f}:offset={t - d:.3f}[{vo}]")
            parts.append(f"[{a_prev}][{g}:a]acrossfade=d={d:.3f}:c1=tri:c2=tri[{ao}]")
            v_prev, a_prev, t = vo, ao, t - d + seg_len[g]
    if not video:
        parts.append(f"color=c=0x15171c:s={size}:r={fps:g}:d={total:.3f}[vc]")
    if room_tone is not None:
        k, r0, r1 = room_tone
        n_samples = max(1, int((r1 - r0) * 48000))
        j = next(i for i, x in enumerate(parts) if x.endswith("[ac]"))
        parts[j] = parts[j][: -len("[ac]")] + "[speech]"
        args += ["-ss", f"{r0:.3f}", "-t", f"{r1 - r0:.3f}", "-i", str(sources[k])]
        parts.append(
            f"[{len(segs)}:a]aformat=sample_rates=48000:channel_layouts=mono,asetpts=PTS-STARTPTS,"
            f"aloop=loop=-1:size={n_samples},atrim=0:{total:.3f},asetpts=PTS-STARTPTS[room]"
        )
        parts.append("[speech][room]amix=inputs=2:normalize=0:duration=first[ac]")
    vlast = "vc"
    if srt is not None:
        parts.append(f"[{vlast}]{subtitle_filter(srt, w, h)}[vs]")
        vlast = "vs"
    parts.append("[ac]loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[ao]")
    args += [
        "-filter_complex", ";".join(parts),
        "-map", f"[{vlast}]", "-map", "[ao]",
        "-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out),
    ]
    run(args)
