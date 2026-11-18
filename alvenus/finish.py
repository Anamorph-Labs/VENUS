"""Finishing touches laid over the cut: cutaway shots (B-roll), a music bed
that dips under the voice, an opening title and an end card.

The cut is made first; this pass adds the layers on top, then burns the
captions last so they stay above any cutaway."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .cut import Clip, positions, subtitle_filter
from .style import LOOKS, ass_filter, write_ass
from .media import duration, has_video, run


@dataclass
class Cutaway:
    line: int  # 0-based script line it covers
    path: Path
    offset: float = 0.0  # where to start inside the B-roll file


def parse_broll(items: list[str], n_lines: int) -> list[Cutaway]:
    """LINE=FILE or LINE=FILE@SECONDS, e.g. 3=market.mp4@4.5"""
    out = []
    for it in items:
        line, _, rest = it.partition("=")
        path, _, off = rest.partition("@")
        if not line.strip().isdigit() or not path:
            raise SystemExit(f"--broll {it!r}: use LINE=FILE or LINE=FILE@SECONDS")
        n = int(line) - 1
        if not 0 <= n < n_lines:
            raise SystemExit(f"--broll {it!r}: the script has lines 1 to {n_lines}")
        p = Path(path)
        if not p.exists() or not has_video(p):
            raise SystemExit(f"--broll {it!r}: {p} is not a video file")
        out.append(Cutaway(n, p, float(off or 0.0)))
    return out


def line_spans(clips: list[Clip]) -> dict[int, tuple[float, float]]:
    """Where each script line sits on the finished timeline."""
    spans: dict[int, tuple[float, float]] = {}
    for c, t in zip(clips, positions(clips)):
        a, _ = spans.get(c.line, (t, t))
        spans[c.line] = (a, t + c.length)
    return spans


def finish(
    base: Path, out: Path, size: str, fps: float, spans: dict[int, tuple[float, float]],
    cutaways: list[Cutaway] = (), music: Path | None = None, music_lufs: float = -22.0,
    title: str | None = None, end_card: str | None = None, card_len: float = 2.5,
    srt: Path | None = None, words=None, look: str = "natural", accent: str = "#FFD23F",
    lower_thirds=(), card_lines=(), all_words=None, stats=(), charts=(), sfx: list | None = None,
    line_charts=(), quotes=(), progress: bool = False, scene_marks=(),
    maps=(), timelines=(), kinetic_lines=(), titles=(), split_labels=(), title_style: str = "track",
) -> list[str]:
    """srt: classic one-line captions; words: timed words for animated captions;
    sfx: None for no sound effects, else [(time, kind)] for the cut's own
    transitions (graphics add theirs here). Returns plain notes on anything it
    had to adjust."""
    w, h = (int(x) for x in size.split("x"))
    cut_len = duration(base)
    card = card_len if end_card else 0.0
    total = cut_len + card
    notes: list[str] = []
    args = ["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(base)]
    parts: list[str] = []
    n_in = 1  # ffmpeg input numbers: 0 is the cut
    v = "0:v"

    for j, cw in enumerate(cutaways):
        if cw.line not in spans:
            notes.append(f"B-roll for line {cw.line + 1} skipped: that line is not in the cut")
            continue
        t0, t1 = spans[cw.line]
        have = duration(cw.path) - cw.offset
        if have < 0.5:
            notes.append(f"B-roll for line {cw.line + 1} skipped: {cw.path.name} has nothing after {cw.offset:g}s")
            continue
        if have < t1 - t0:
            notes.append(f"B-roll {cw.path.name} is shorter than line {cw.line + 1}; it covers the first {have:.1f}s, then back to the speaker")
            t1 = t0 + have
        k, n_in = n_in, n_in + 1
        args += ["-i", str(cw.path)]
        parts.append(
            f"[{k}:v]trim={cw.offset:.3f}:{cw.offset + t1 - t0:.3f},setpts=PTS-STARTPTS,fps={fps:g},"
            f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,format=yuv420p,"
            f"setpts=PTS+{t0:.3f}/TB[b{j}]"
        )
        parts.append(f"[{v}][b{j}]overlay=eof_action=pass:enable='between(t,{t0:.3f},{t1:.3f})'[o{j}]")
        v = f"o{j}"

    for j, mc in enumerate(maps):
        if mc.line not in spans:
            notes.append(f"map for line {mc.line + 1} skipped: that line is not in the cut")
            continue
        t0, t1 = spans[mc.line]
        k, n_in = n_in, n_in + 1
        args += ["-loop", "1", "-t", f"{t1 - t0 + 0.5:.3f}", "-i", mc.image]
        parts.append(
            f"[{k}:v]fps={fps:g},scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,"
            # The map holds still so the pins stay on their places; the pins
            # and the route are the movement.
            f"format=yuva420p,"
            f"fade=t=in:d=0.25:alpha=1,setpts=PTS+{t0:.3f}/TB[m{j}]")
        parts.append(f"[{v}][m{j}]overlay=eof_action=pass:enable='between(t,{t0:.3f},{t1:.3f})'[om{j}]")
        v = f"om{j}"

    if LOOKS.get(look):
        parts.append(f"[{v}]{LOOKS[look]}[graded]")
        v = "graded"
    if card:
        # The end card sits on the last frame, held, blurred and darkened.
        parts.append(
            f"[{v}]tpad=stop_mode=clone:stop_duration={card:.3f},"
            f"boxblur=luma_radius=24:luma_power=2:chroma_radius=12:enable='gte(t,{cut_len:.3f})',"
            f"eq=brightness=-0.18:saturation=0.7:enable='gte(t,{cut_len:.3f})'[pad]"
        )
        v = "pad"
    if srt is not None:
        parts.append(f"[{v}]{subtitle_filter(srt, w, h)}[cap]")
        v = "cap"
    if words or title or end_card or lower_thirds or card_lines or stats or charts or line_charts or quotes or progress or maps or timelines or kinetic_lines or titles or split_labels:
        from .graphics import (chart_events, kinetic_events, line_chart_events, map_events, progress_events, quote_events,
                               stat_events, timeline_events)

        extra, skip = [], set()
        for st in stats:
            if st.line in spans:
                extra += stat_events(st, *spans[st.line], w, h, accent)
                skip.add(st.line)
        for ch in charts:
            if ch.line in spans:
                extra += chart_events(ch, *spans[ch.line], w, h, accent)
                skip.add(ch.line)
        for ch in line_charts:
            if ch.line in spans:
                extra += line_chart_events(ch, *spans[ch.line], w, h, accent)
                skip.add(ch.line)
        for q in quotes:
            if q.line in spans:
                extra += quote_events(q, *spans[q.line], w, h, accent)
                skip.add(q.line)
        for mc in maps:
            if mc.line in spans:
                extra += map_events(mc, *spans[mc.line], w, h, accent)
        for tl in timelines:
            if tl.line in spans:
                extra += timeline_events(tl, *spans[tl.line], w, h, accent)
                skip.add(tl.line)
        for n, emph in kinetic_lines:
            if n in spans and all_words:
                extra += kinetic_events([x for x in all_words if x.line == n], *spans[n], w, h, accent, emph)
                skip.add(n)
        if progress:
            extra += progress_events(cut_len, w, h, accent, list(scene_marks))
        from .style import title_events

        from .graphics import split_label_events

        for (t0, t1), side, label in split_labels:
            extra += split_label_events(label, side, t0, t1, w, h, accent)
        for text, t0, t1 in titles:  # mid-video title cards
            extra += title_events(text, w, h, accent, t0 + 0.1, t1, centre=True, kind=title_style)
        lts = [(lt, spans[lt.line][0]) for lt in lower_thirds if lt.line in spans]
        cards = [([x for x in all_words if x.line == n], *spans[n], n) for n in card_lines if n in spans]
        notes += [f"lower third for line {lt.line + 1} skipped: that line is not in the cut" for lt in lower_thirds if lt.line not in spans]
        ass = out.with_suffix(".look.ass")
        write_ass(ass, w, h, accent, words, title, end_card, cut_len, card, lts, cards, extra, skip, title_style=title_style)
        parts.append(f"[{v}]{ass_filter(ass)}[tt]")
        v = "tt"
    parts.append(f"[{v}]format=yuv420p[vo]")

    a = "0:a"
    if card:
        # Under the end card: a faint room hiss instead of digital silence,
        # which sounds like the sound cut out.
        parts += [f"[{a}]aformat=sample_rates=48000:channel_layouts=stereo,apad=pad_dur={card:.3f}[ap0]",
                  f"anoisesrc=c=pink:a=0.0012:r=48000:d={card + 0.2:.3f},aformat=sample_rates=48000:channel_layouts=stereo,"
                  f"afade=t=in:d=0.3,adelay={round(cut_len * 1000)}:all=1[hiss]",
                  "[ap0][hiss]amix=inputs=2:normalize=0:duration=first[ap]"]
        a = "ap"
    if sfx is not None:
        from .sfx import write_track

        ev = list(sfx)
        ev += [(spans[lt.line][0] + 0.05, "pop") for lt in lower_thirds if lt.line in spans]
        ev += [(spans[n][0], "pop") for n in card_lines if n in spans]
        ev += [(spans[x.line][0], "pop") for x in list(stats) + list(charts) + list(line_charts) + list(quotes) + list(timelines) if x.line in spans]
        for mc in maps:  # a pop as each pin lands
            if mc.line in spans:
                t0, t1 = spans[mc.line]
                gap = min(0.8, max(0.35, (t1 - t0 - 0.8) / max(1, len(mc.pins))))
                ev += [(t0 + 0.3 + gap * i, "pop") for i in range(len(mc.pins)) if t0 + 0.3 + gap * i < t1]
        if title:
            ev.append((0.15, "hit"))
        ev += [(t0 + 0.1, "hit") for _, t0, _ in titles]
        if end_card:
            ev += [(cut_len, "whoosh"), (cut_len + 0.2, "hit")]
        if ev:
            track = out.with_suffix(".sfx.wav")
            write_track(track, ev, total)
            k, n_in = n_in, n_in + 1
            args += ["-i", str(track)]
            parts += [f"[{a}]aformat=sample_rates=48000:channel_layouts=stereo[vfx]",
                      f"[vfx][{k}:a]amix=inputs=2:normalize=0:duration=first[withfx]"]
            a = "withfx"
    if music is not None:
        k, n_in = n_in, n_in + 1
        args += ["-stream_loop", "-1", "-i", str(music)]
        fade_out = min(2.5, total / 3)
        parts += [
            f"[{a}]asplit[voice][key]",
            f"[{k}:a]aformat=sample_rates=48000:channel_layouts=stereo,loudnorm=I={music_lufs:g}:TP=-3,"
            f"atrim=0:{total:.3f},asetpts=PTS-STARTPTS,afade=t=in:d=1,afade=t=out:st={total - fade_out:.3f}:d={fade_out:.3f}[mus]",
            # The voice drives a compressor on the music: whenever someone
            # speaks, the music dips about 10 dB; a slow release keeps it from
            # pumping up in the short gaps between lines.
            f"[key]aformat=channel_layouts=stereo,apad=whole_dur={total + 0.5:.3f}[keyst]",
            "[mus][keyst]sidechaincompress=threshold=0.03:ratio=4:attack=20:release=900:makeup=1[duck]",
            f"[voice]aformat=sample_rates=48000:channel_layouts=stereo,apad=whole_dur={total + 0.5:.3f}[vst]",
            # The limiter holds back a moment and ends early: give it a little
            # more voice than needed, so sound and picture finish together
            # (-t trims both to length).
            "[vst][duck]amix=inputs=2:normalize=0:duration=first,alimiter=limit=0.89:level=false[ao]",
        ]
    else:
        parts.append(f"[{a}]anull[ao]")

    args += [
        "-filter_complex", ";".join(parts), "-map", "[vo]", "-map", "[ao]", "-t", f"{total:.3f}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out),
    ]
    run(args)
    out.with_suffix(".sfx.wav").unlink(missing_ok=True)
    return notes


_STOP = set("a an and are as at be but by for from has have he her his i in is it its me my of on or our she so that the their them they this to was we were what when with you your".split())


def _stem(w: str) -> str:
    w = w.lower()
    for end in ("ing", "es", "s"):
        if len(w) > len(end) + 2 and w.endswith(end):
            return w[: -len(end)]
    return w


def _tokens(text: str) -> set[str]:
    import re
    return {_stem(t) for t in re.findall(r"[a-zA-Z]+", text.replace("_", " ")) if t.lower() not in _STOP and len(t) > 2}


def auto_broll(script: list[str], folder: Path, taken: set[int], used: set[Path], near: set[int] = frozenset()) -> tuple[list[Cutaway], list[str]]:
    """Match cutaway clips in `folder` to script lines by their names, plus any
    "tags" written into the folder's broll.json (from `alvenus scan`). The
    first and last lines stay on the speaker, as do lines in `taken` (cards,
    stats, charts, explicit B-roll). Each clip is used once, and at most one
    line in two gets a cutaway (counting the `near` lines that already have one)
    so the speaker stays the anchor."""
    import json

    from .scan import VIDEO

    if not folder.is_dir():
        raise SystemExit(f"--broll-dir {folder}: not a folder")
    tags: dict[str, str] = {}
    info = folder / "broll.json"
    if info.exists():
        try:
            for c in json.loads(info.read_text(encoding="utf-8")).get("clips", []):
                t = c.get("tags") or ""
                tags[Path(c["file"]).name] = " ".join(t) if isinstance(t, list) else str(t)
        except (ValueError, KeyError, TypeError):
            pass
    clips = [f for f in sorted(folder.iterdir()) if f.suffix.lower() in VIDEO and f.resolve() not in used and has_video(f)]
    words = {f: _tokens(f.stem + " " + tags.get(f.name, "")) for f in clips}
    scored = []
    for n, line in enumerate(script):
        if n in taken or n == 0 or n == len(script) - 1:
            continue
        lw = _tokens(line)
        for f in clips:
            hit = len(lw & words[f])
            if hit:
                scored.append((hit, -n, n, f))
    out, lines, notes = [], set(near), []
    for hit, _, n, f in sorted(scored, key=lambda s: (-s[0], -s[1])):
        if n in lines or n - 1 in lines or n + 1 in lines or any(c.path == f for c in out):
            continue
        out.append(Cutaway(n, f))
        lines.add(n)
        notes.append(f"B-roll {f.name} over line {n + 1} (matched: {', '.join(sorted(_tokens(script[n]) & words[f]))})")
    return sorted(out, key=lambda c: c.line), notes
