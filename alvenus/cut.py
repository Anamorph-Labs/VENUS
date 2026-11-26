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
    push: tuple[float, float] | None = None  # slow push-in: zoom at the clip's first and last frame

    @property
    def length(self) -> float:
        return self.end - self.start + self.hold


# Scene-break transitions, by name, as FFmpeg xfade effects.
TRANSITIONS = {
    "cut": "", "crossfade": "fade", "dip": "fadeblack", "flash": "fadewhite",
    "zoom": "zoomin", "whip": "smoothleft", "slide": "slideleft", "blur": "hblur",
    "circle": "circleopen", "ink": "custom", "leak": "custom", "glitch": "custom",
    "bloom": "custom", "cloud": "custom", "tear": "custom", "tiles": "custom", "trail": "custom",
}

# Hand-made transitions. FFmpeg's per-pixel expressions are far too slow at
# full size (about 50 s of work per second of 1080p), so each one draws only a
# small black-and-white mask (where the new shot shows through) and the two
# full-size shots are blended through it: about as quick as a dissolve.
# In each mask q = T/D runs 0 -> 1 across the transition.
_MASK = {
    # A ragged, ink-like edge bleeds across the frame from left to right.
    "ink": ("192x108", "255*clip((T/{D}*0.75-0.06-0.5*X/W-0.07*(sin(X/W*9+Y/H*4.3)+sin(Y/H*11-X/W*3.1)+0.6*sin(X/W*17+Y/H*13)+0.4*sin(Y/H*27+X/W*21)))*7,0,1)"),
    # A soft wipe under a warm wash of light that blooms at the midpoint (glow mask below).
    "leak": ("160x90", "255*clip((T/{D})*1.6-0.3-0.3*X/W,0,1)"),
    # Bands of the frame flick between the two shots for a few frames, then settle.
    "glitch": ("8x36", "255*abs(gte(T/{D},0.5)-gt(sin(PI*T/{D}),0.25)*gt(mod(abs(sin(floor(Y)*12.99+floor(T/{D}*9)*78.23))*43758.5,1),0.55))"),
    # Ink blots spread from a few places at once and run together (sepia film openers).
    "bloom": ("192x108", "255*clip((T/{D}*0.62-min(min(hypot(X/W-0.22,(Y/H-0.35)*0.56),hypot(X/W-0.74,(Y/H-0.62)*0.56)),"
              "min(hypot(X/W-0.55,(Y/H-0.12)*0.56),hypot(X/W-0.1,(Y/H-0.85)*0.56)))"
              "-0.035*(sin(X/W*23+Y/H*7)+sin(Y/H*29-X/W*11)+0.7*sin(X/W*53+Y/H*41)))*10,0,1)"),
    # Billows of cloud roll in and part on the new shot; a white mist peaks halfway (mist mask below).
    "cloud": ("160x90", "255*clip((T/{D}*1.1-0.05-0.55*abs(X/W-0.5)-0.25*abs(Y/H-0.5)"
              "-0.08*(sin(X/W*7+Y/H*3)+sin(Y/H*9-X/W*5)+0.6*sin(X/W*15+Y/H*11)))*3.2,0,1)"),
    # A torn paper edge crosses the frame; a pale strip of torn paper rides on it (edge mask below).
    "tear": ("384x216", "255*lt(X/W,T/{D}*1.3-0.15+0.025*sin(Y/H*31)+0.012*sin(Y/H*97+2)+0.006*sin(Y/H*233))"),
    # The frame breaks into squares that flip to the new shot in a scattered order.
    "tiles": ("16x9", "255*gt(T/{D}*1.25-0.12,mod(abs(sin(X*12.99+Y*78.23))*43758.5,1))"),
}
_MASK["trail"] = (  # the new shot follows a streak of light flying across the frame
    "384x216", "255*clip((pow(T/{D},0.8)*1.35-0.2-(X/W+0.35*(Y/H-0.5)))*10,0,1)")
# A streak of light: a long tail behind a bright head, along a slightly tilted line,
# riding the edge of the wipe. The halo takes the video's colour; the core is white.
_TRAIL_AT = "(pow(T/{D},0.8)*1.35-0.2-0.35*(Y/H-0.5))"
_TRAIL_HALO = ("250*sin(PI*T/{D})*(exp(-pow((X/W-" + _TRAIL_AT + ")/0.05,2))*0.8+exp(-pow((Y/H-0.46+0.1*X/W)/0.035,2))"
               "*exp(-max(0," + _TRAIL_AT + "-X/W)/0.3)*gt(" + _TRAIL_AT + "+0.02,X/W))")
_TRAIL_CORE = ("255*sin(PI*T/{D})*(exp(-pow((X/W-" + _TRAIL_AT + ")/0.008,2))*0.9+exp(-pow((Y/H-0.46+0.1*X/W)/0.006,2))"
               "*exp(-max(0," + _TRAIL_AT + "-X/W)/0.18)*gt(" + _TRAIL_AT + "+0.005,X/W))")
TRAIL_COLOUR = "0x2B4A78"

# Light laid over the blend for the transitions that need it: (mask, colour).
_OVER = {
    "cloud": ("160x90", "235*pow(sin(PI*T/{D}),1.5)*clip(0.55+0.3*sin(X/W*6+Y/H*4+T/{D}*2)+0.25*sin(Y/H*9-X/W*3),0,1)", "0xF4F2EE"),
    "tear": ("384x216", "250*lt(abs(X/W-(T/{D}*1.3-0.15+0.025*sin(Y/H*31)+0.012*sin(Y/H*97+2)+0.006*sin(Y/H*233))"
             "-0.009-0.004*sin(Y/H*151)),0.009+0.003*sin(Y/H*71))*lt(0.001,T/{D})*lt(T/{D},0.999)", "0xEDE6D8"),
}
_GLOW = "230*pow(sin(PI*T/{D}),2)*exp(-pow(X/W-(0.15+0.7*T/{D}),2)/0.09)"
_WARM = "0xFFC98A"


def join_pair(a: str, b: str, out: str, name: str, d: float, offset: float, size: str, fps: float, k, colour: str | None = None) -> str:
    """Filter-graph text that lays stream b over the end of stream a with the
    named transition (b starts at `offset`), like xfade."""
    t = TRANSITIONS[name]
    if t != "custom":
        return f"[{a}][{b}]xfade={xfade(name)}:duration={d:.3f}:offset={offset:.3f}[{out}]"
    w, h = size.split("x")
    res, expr = _MASK[name]
    e = expr.format(D=f"{d:.4f}")
    mask = (f"nullsrc=s={res}:r={fps:g}:d={d:.4f},geq=lum='{e}':cb='{e}':cr='{e}',"
            f"scale={w}:{h}:flags={'neighbor' if name in ('glitch', 'tiles') else 'bicubic'},format=yuv420p[m{k}]")
    p = [mask,
         f"[{a}]split[a{k}1][a{k}2]", f"[{b}]split[b{k}1][b{k}2]",
         f"[a{k}1]trim=end={offset:.4f},setpts=PTS-STARTPTS[h{k}]",
         f"[a{k}2]trim=start={offset:.4f}:end={offset + d:.4f},setpts=PTS-STARTPTS,format=yuv420p[x{k}]",
         f"[b{k}1]trim=end={d:.4f},setpts=PTS-STARTPTS,format=yuv420p[y{k}]",
         f"[b{k}2]trim=start={d:.4f},setpts=PTS-STARTPTS[t{k}]",
         f"[x{k}][y{k}][m{k}]maskedmerge[mid{k}]"]
    mid = f"mid{k}"
    if name == "leak":
        g = _GLOW.format(D=f"{d:.4f}")
        p += [f"nullsrc=s=160x90:r={fps:g}:d={d:.4f},geq=lum='{g}':cb='{g}':cr='{g}',scale={w}:{h},format=yuv420p[gm{k}]",
              f"color=c={_WARM}:s={size}:r={fps:g}:d={d:.4f},format=yuv420p[warm{k}]",
              f"[{mid}][warm{k}][gm{k}]maskedmerge[lit{k}]"]
        mid = f"lit{k}"
    elif name == "trail":
        c = "0x" + (colour or TRAIL_COLOUR).lstrip("#").replace("0x", "")
        for tag, expr, col in (("th", _TRAIL_HALO, c), ("tc", _TRAIL_CORE, "0xFFFFFF")):
            g = expr.format(D=f"{d:.4f}")
            p += [f"nullsrc=s=384x216:r={fps:g}:d={d:.4f},geq=lum='{g}':cb='{g}':cr='{g}',scale={w}:{h}:flags=bicubic,format=yuv420p[{tag}m{k}]",
                  f"color=c={col}:s={size}:r={fps:g}:d={d:.4f},format=yuv420p[{tag}c{k}]",
                  f"[{mid}][{tag}c{k}][{tag}m{k}]maskedmerge[{tag}{k}]"]
            mid = f"{tag}{k}"
    elif name in _OVER:
        ores, oexpr, colour = _OVER[name]
        g = oexpr.format(D=f"{d:.4f}")
        p += [f"nullsrc=s={ores}:r={fps:g}:d={d:.4f},geq=lum='{g}':cb='{g}':cr='{g}',scale={w}:{h}:flags=bicubic,format=yuv420p[om{k}]",
              f"color=c={colour}:s={size}:r={fps:g}:d={d:.4f},format=yuv420p[oc{k}]",
              f"[{mid}][oc{k}][om{k}]maskedmerge[ov{k}]"]
        mid = f"ov{k}"
    elif name == "glitch":
        p += [f"[{mid}]chromashift=cbh={max(4, int(w) // 120)}:crh=-{max(4, int(w) // 120)}[gl{k}]"]
        mid = f"gl{k}"
    p.append(f"[h{k}]setsar=1[hh{k}];[{mid}]setsar=1[mm{k}];[t{k}]setsar=1[tt{k}];[hh{k}][mm{k}][tt{k}]concat=n=3:v=1:a=0[{out}]")
    return ";".join(p)


def xfade(name: str) -> str:
    """The xfade options for a transition by name."""
    t = TRANSITIONS[name]
    if t == "custom":
        raise ValueError(f"{name} is drawn by join_pair, not xfade")
    return f"transition={t}"


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
    return keep_joined_words(path, clips) if path is not None else clips


def keep_joined_words(path: Path, clips: list[Clip]) -> list[Clip]:
    """Every cut inside a take must sit in real quiet. Where the voice never
    drops (one word slurred into the next), the cut is taken back and the
    words stay together as spoken; a cut a little off the quiet is moved onto it."""
    from . import listen
    from .media import load_audio

    if len(clips) < 2:
        return clips
    t0, t1 = clips[0].start, clips[-1].end
    try:
        db = listen.loudness(load_audio(path, listen.SR, t0, t1))
    except Exception:
        return clips
    out = [clips[0]]
    for c in clips[1:]:
        p = out[-1]
        a, b = listen.quiet_point(db, p.end - t0, 0.06), listen.quiet_point(db, c.start - t0, 0.06)
        if a is None or b is None:
            out[-1] = Clip(p.source, p.start, c.end, p.line, hold=c.hold)
            continue
        p.end, c.start = min(c.end, t0 + a), max(t0 + a, t0 + b)
        out.append(c)
    return out


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

    from .genre import matte

    mv, bar = 40, matte(w, h)
    if bar:  # in the cinema bar, like subtitles in a cinema
        fs = round(fs * 0.78, 1)
        mv = max(4, round((bar - 0.06 * min(w, h) * 0.78) / 2 * 288 / h))
    style = f"FontName=Inter SemiBold,FontSize={fs},Outline=1.6,Shadow=1,MarginV={mv},MarginL=20,MarginR=20"
    esc = lambda p: str(p).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")
    return f"subtitles='{esc(srt)}':fontsdir='{esc(FONTS)}':force_style='{style}'"


def _clip_filters(c: Clip, sw_sh, w: int, h: int, fps: float, video: bool) -> tuple[str, str]:
    """Video and audio filters for one clip, read from a file already cut to it."""
    fade_in, fade_out = 0.03, 0.06  # long enough to never click, short enough to keep every word
    if c.start < 0.02:
        # The clip opens on the first instant of its file: on a phone, talking
        # often starts before recording does, and even 30 ms of fade there
        # swallows a short first word ("and"). Just enough to avoid a click.
        fade_in = 0.002
    d = c.end - c.start
    hold = f",apad=pad_dur={c.hold:.3f}" if c.hold else ""
    # apad first: a clip that runs to the very end of its file may have a
    # little less sound than picture, and the two must stay the same length.
    af = (f"aformat=sample_rates=48000:channel_layouts=mono,apad=whole_dur={d:.3f},atrim=0:{d:.3f},asetpts=PTS-STARTPTS,"
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
    if c.push:
        # Sub-pixel smooth zoom (a resize would step a whole pixel at a time
        # and shimmer): move the four corners in, frame by frame.
        z0, z1 = c.push
        n = max(1, round(d * fps))
        z = f"({z0:.4f}+{z1 - z0:.4f}*min(on/{n},1))"
        corners = [("W/2-W/2/", "H/2-H/2/"), ("W/2+W/2/", "H/2-H/2/"), ("W/2-W/2/", "H/2+H/2/"), ("W/2+W/2/", "H/2+H/2/")]
        pts = ":".join(f"x{i}='{a}{z}':y{i}='{b}{z}'" for i, (a, b) in enumerate(corners))
        vf += f",perspective={pts}:interpolation=cubic:eval=frame"
    if c.hold:
        vf += f",tpad=stop_mode=clone:stop_duration={c.hold:.3f}"
    return vf, af


def push_in(clips: list[Clip], lines: set[int], amount: float = 0.07) -> int:
    """A slow push-in across each line in `lines`, the way a camera operator
    leans in on the line that matters. Spread over all of the line's clips so
    it reads as one move. Returns how many lines got one."""
    done = 0
    for line in lines:
        idx = [i for i, c in enumerate(clips) if c.line == line]
        if not idx:
            continue
        total = sum(clips[i].end - clips[i].start for i in idx) or 1.0
        t = 0.0
        for i in idx:
            d = clips[i].end - clips[i].start
            clips[i].push = (1 + amount * t / total, 1 + amount * (t + d) / total)
            t += d
        done += 1
    return done


def _render_clip(src: Path, c: Clip, path: Path, sw_sh, w: int, h: int, fps: float, video: bool) -> None:
    vf, af = _clip_filters(c, sw_sh, w, h, fps, video)
    graph = (f"{vf}[v];" if video else "") + f"[0:a]{af}[a]"
    args = ["ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", f"{c.start:.3f}", "-t", f"{c.end - c.start + 0.1:.3f}",
            "-i", str(src), "-filter_complex", graph]
    if video:
        args += ["-map", "[v]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "12", "-pix_fmt", "yuv420p"]
    args += ["-map", "[a]", "-c:a", "pcm_s16le", str(path)]
    run(args)


# Voice treatment, the way a dialogue mixer would: roll off rumble, lift the
# room noise out (its level measured from the quiet stretch of the shoot),
# tame harsh "s" sounds; "studio" adds a little warmth and presence and a
# gentle compressor so quiet and loud words sit closer together.
VOICE = {
    "off": "",
    "clean": "highpass=f=80,afftdn=nr={nr}:nf={nf},deesser=i=0.35",
    "studio": "highpass=f=80,afftdn=nr={nr}:nf={nf},deesser=i=0.35,"
              "equalizer=f=180:t=q:w=1:g=1.5,equalizer=f=3500:t=q:w=1.2:g=2,"
              "acompressor=threshold=-22dB:ratio=2.5:attack=8:release=180:makeup=1.5",
}


def noise_floor(path: Path, start: float, end: float) -> float:
    """RMS level (dBFS) of a quiet stretch: what the denoiser should remove."""
    r = run(["ffmpeg", "-nostdin", "-v", "info", "-ss", f"{start:.3f}", "-t", f"{max(0.2, end - start):.3f}", "-i", str(path),
             "-af", "astats=measure_overall=RMS_level:measure_perchannel=0", "-f", "null", "-"])
    import re
    m = re.findall(r"RMS level dB: (-?[\d.]+|-inf)", r.stderr)
    try:
        return max(-80.0, min(-20.0, float(m[-1])))
    except (IndexError, ValueError):
        return -50.0


def voice_chain(voice: str, sources: list[Path], room_tone) -> str:
    chain = VOICE.get(voice or "off", "")
    if not chain:
        return ""
    nf = noise_floor(sources[room_tone[0]], room_tone[1], room_tone[2]) if room_tone else -50.0
    # The denoiser's floor sits a little above the measured hiss (set at the
    # hiss itself it leaves most of it behind), and it only takes the room
    # down to a natural quiet, about -72 dBFS, never to dead silence.
    nr = max(0.0, min(20.0, nf + 72))
    if nr < 3:
        chain = chain.replace("afftdn=nr={nr}:nf={nf},", "")
    return chain.format(nr=f"{nr:.0f}", nf=f"{min(-20.0, nf + 8):.0f}") + ","


def render(
    sources: list[Path], clips: list[Clip], out: Path, srt: Path | None = None, size: str = "1280x720",
    fps: float = 30.0, room_tone: tuple[int, float, float] | None = None, crf: int = 20, voice: str = "off",
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
        _join(files, clips, sources, out, srt, size, w, h, fps, video, room_tone, crf, tmp, voice_chain(voice, sources, room_tone))
    finally:
        for f in tmp.glob("*"):
            f.unlink()
        tmp.rmdir()


def _join(files, clips, sources, out, srt, size, w, h, fps, video, room_tone, crf, tmp, voice: str = "") -> None:
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
                parts.append(join_pair(v_prev, f"{g}:v", vo, c.transition, d, t - d, size, fps, g))
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
    parts.append(f"[ac]{voice}loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[ao]")
    args += [
        "-filter_complex", ";".join(parts),
        "-map", f"[{vlast}]", "-map", "[ao]",
        "-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out),
    ]
    run(args)
