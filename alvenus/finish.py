"""Finishing touches laid over the cut: cutaway shots (B-roll), a music bed
that dips under the voice, an opening title and an end card.

The cut is made first; this pass adds the layers on top, then burns the
captions last so they stay above any cutaway."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .cut import Clip, positions, subtitle_filter
from .style import LOOKS, ass_filter, write_ass
from .media import duration, has_video, load_audio, run


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
    more_events=(), camera=(), talk: dict | None = None, music_duck: float = 12.0, sfx_gain: float = 0.0, music_open=None, music_stop: float | None = None,
    caption_places: dict | bool | None = None, voice_gap: float = 10.0,
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

    from .learnstyle import matched

    grade_ = matched(look, base) or LOOKS.get(look)  # a learned look is matched to this very footage
    if grade_:
        parts.append(f"[{v}]{grade_}[graded]")
        v = "graded"
    talk_lines: set[int] = set()
    if talk:  # the produced-show layout: some lines open up into a set, speaker beside words or graphic
        from . import talk as talk_

        def graphic_rows(n: int, gw: int, gh: int) -> list[str]:
            from .graphics import chart_events, line_chart_events, quote_events, stat_events, timeline_events

            rows: list[str] = []
            for xs, fn in ((stats, stat_events), (charts, chart_events), (line_charts, line_chart_events),
                           (quotes, quote_events), (timelines, timeline_events)):
                for x in xs:
                    if x.line == n:
                        rows += fn(x, *spans[n], gw, gh, accent)
            return rows

        targs, tparts, tnotes = talk_.build(base, out, w, h, fps, spans, talk["kinds"], accent, all_words, graphic_rows,
                                            talk.get("emphasis", {}), talk.get("chapters", {}), talk.get("label", ""),
                                            talk.get("breaks", set()), talk.get("set", "dark"))
        if tparts:
            first = n_in
            args += targs
            n_in = first + targs.count("-i")
            fill = lambda m: str(first + int(m.group(1)))
            import re as _re

            for ln in tparts:
                parts.append(_re.sub(r"\{FIRST\+(\d+)\}", fill, ln).replace("[IN]", f"[{v}]"))
            v = "talk"
            talk_lines = {n for n, k in talk["kinds"].items() if k != "full" and n in spans}
            stats, charts, line_charts, quotes, timelines = ([x for x in xs if x.line not in talk_lines]
                                                              for xs in (stats, charts, line_charts, quotes, timelines))
            kinetic_lines = [(n, e) for n, e in kinetic_lines if n not in talk_lines]
            if sfx is not None:
                sfx = list(sfx) + [(spans[n][0], "pop") for n in talk_lines]
        notes += tnotes
    if card:
        # The end card sits on the last frame, held, blurred and darkened.
        parts.append(
            f"[{v}]tpad=stop_mode=clone:stop_duration={card:.3f},"
            f"boxblur=luma_radius=24:luma_power=2:chroma_radius=12:enable='gte(t,{cut_len:.3f})',"
            f"eq=brightness=-0.18:saturation=0.7:enable='gte(t,{cut_len:.3f})'[pad]"
        )
        v = "pad"
    from .genre import matte

    late_srt = srt is not None and matte(w, h) > 0  # captions in the cinema bar go on after the bars
    if srt is not None and not late_srt:
        parts.append(f"[{v}]{subtitle_filter(srt, w, h)}[cap]")
        v = "cap"
    from . import genre

    if genre.EXTRAS or words or title or end_card or lower_thirds or card_lines or stats or charts or line_charts or quotes or progress or maps or timelines or kinetic_lines or titles or split_labels or more_events:
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
        extra += list(more_events)  # ready-made graphics (lists, comparisons, callouts)
        for text, t0, t1 in titles:  # mid-video title cards
            extra += title_events(text, w, h, accent, t0 + 0.1, t1, centre=True, kind=title_style)
        lts = [(lt, spans[lt.line][0]) for lt in lower_thirds if lt.line in spans]
        cards = [([x for x in all_words if x.line == n], *spans[n], n) for n in card_lines if n in spans]
        notes += [f"lower third for line {lt.line + 1} skipped: that line is not in the cut" for lt in lower_thirds if lt.line not in spans]
        ass = out.with_suffix(".look.ass")
        from . import style as style_

        if words and style_.CAPTION_MODE in ("pop", "keyword", "stack") and caption_places is not False:
            from .placement import Planner

            # each caption card goes where the picture under it leaves room (placement.py)
            style_.PLACE = Planner(base, w, h, fixed=dict(caption_places or {}))
        try:
            write_ass(ass, w, h, accent, words, title, end_card, cut_len, card, lts, cards, extra, skip | talk_lines, title_style=title_style)
        finally:
            used, style_.PLACE = (style_.PLACE.used if style_.PLACE else []), None
        if used:
            from collections import Counter

            notes.append("captions: placed shot by shot where the picture leaves room ("
                         + ", ".join(f"{k} {n}" for k, n in Counter(used).most_common()) + ")")
        parts.append(f"[{v}]{ass_filter(ass)}[tt]")
        v = "tt"
    if late_srt:
        parts.append(f"[{v}]{subtitle_filter(srt, w, h)}[cap]")
        v = "cap"
    if camera:  # a slow drifting camera over graphic scenes, words and all, as if filmed
        # one continuous path (no jump between two graphic scenes in a row); it
        # eases in and out where a stretch of graphic scenes meets real footage
        runs: list[list[float]] = []
        for t0, t1 in sorted(camera):
            if runs and t0 - runs[-1][1] < 0.05:
                runs[-1][1] = t1
            else:
                runs.append([t0, t1])
        T = "(TIME)"  # filled in below; the self-review fills in its own moment to follow the same move
        ramp = lambda x: f"(clip({x},0,1)*clip({x},0,1)*(3-2*clip({x},0,1)))"
        A = "+".join(f"{ramp(f'({T}-{a:.3f})/0.8')}*{ramp(f'({b:.3f}-{T})/0.8')}" if a > 0.05 else ramp(f"({b:.3f}-{T})/0.8")
                     for a, b in runs)
        z = f"(1+({A})*(0.04+0.015*sin({T}*0.5)))"
        sx, sy = f"(({A})*0.010*W*sin({T}*0.37+1))", f"(({A})*0.007*H*sin({T}*0.29))"
        corners = [("W/2-W/2/", "H/2-H/2/"), ("W/2+W/2/", "H/2-H/2/"), ("W/2-W/2/", "H/2+H/2/"), ("W/2+W/2/", "H/2+H/2/")]
        persp = ":".join(f"x{i}='{a}{z}+{sx}':y{i}='{b}{z}+{sy}'" for i, (a, b) in enumerate(corners))
        look = out.with_suffix(".look.ass")
        if look.exists():  # so the self-review can measure the words where the camera put them
            look.write_text(look.read_text(encoding="utf-8").replace("[Script Info]\n", f"[Script Info]\n; venus-camera: {persp}\n", 1),
                            encoding="utf-8")
        parts.append(f"[{v}]perspective={persp.replace(T, f'(on/{fps:g})')}:interpolation=linear:eval=frame[cam]")
        v = "cam"
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
    # The sound: effects tidied (fewer, varied), the music made long enough by
    # repeating it on the bar, its level planned around the voice and then
    # measured line by line; effects lifted where they'd be lost. See mix.py.
    from . import listen, mix

    ev: list = []
    if sfx is not None:
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
        ev = [e for e in ev if 0 <= e[0] <= total]
    ev, dropped = mix.tidy(ev)
    fx_times = [t for t, _ in ev]
    try:
        voice = load_audio(base, listen.SR)
    except RuntimeError:  # a cut with no sound of its own
        voice = np.zeros(int(cut_len * listen.SR), np.float32)
    bed = np.zeros(int((total + 0.5) * listen.SR), np.float32)
    bed[: min(len(bed), len(voice))] += voice[: len(bed)]
    gaps, joins, jumps, lifted = [], [], [], []
    if music is not None:
        src, joins, jumps = listen.extend_music(Path(music), total + 0.5, out.with_suffix(".long.wav"))
        fade_out = min(2.5, total / 3)
        raw = out.with_suffix(".music.raw.wav")
        run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(src), "-vn", "-af",
             f"aformat=sample_rates=48000:channel_layouts=stereo,loudnorm=I={music_lufs:g}:TP=-3,"
             f"atrim=0:{total:.3f},asetpts=PTS-STARTPTS,afade=t=in:d=1,afade=t=out:st={total - fade_out:.3f}:d={fade_out:.3f},"
             f"apad=whole_dur={total + 0.5:.3f}", "-ar", "48000", "-ac", "2", str(raw)])
        if music_open:  # muffled, as if through a wall, then opening out fully at a chosen moment
            muffle(raw, *music_open)
        if music_stop is not None and 0 <= music_stop < total:  # the music cuts dead and stays silent
            stop(raw, music_stop)
        phrases = listen.phrases_of(listen.loudness(voice))
        keys = listen.duck_keys(phrases, total, music_duck)
        keys = listen.make_room(keys, fx_times, total)
        m16 = load_audio(raw, listen.SR)
        if music_duck > 0:
            keys, gaps = mix.fit_under_voice(voice, m16, keys, phrases, gap=voice_gap) if voice_gap > 0 else (keys, [])
        g16 = 10 ** (np.interp(np.arange(len(m16)) / listen.SR, [k[0] for k in keys], [k[1] for k in keys]) / 20)
        n = min(len(bed), len(m16))
        bed[:n] += (m16 * g16)[:n]
        m48 = listen._stereo(raw)
        g48 = 10 ** (np.interp(np.arange(len(m48)) / 48000, [k[0] for k in keys], [k[1] for k in keys]) / 20)
        listen._write_stereo(out.with_suffix(".music.wav"), m48 * g48[:, None].astype(np.float32))
        raw.unlink(missing_ok=True)
        if src != Path(music):
            src.unlink(missing_ok=True)
    if sfx is not None and ev:
        from .sfx import write_track

        lifted = mix.effect_gains(ev, bed)
        track = out.with_suffix(".sfx.wav")
        write_track(track, ev, total, sfx_gain, lifted)
    notes += mix.report(gaps, joins, jumps, dropped, lifted)
    ins = []
    if sfx is not None and ev:
        k, n_in = n_in, n_in + 1
        args += ["-i", str(out.with_suffix(".sfx.wav"))]
        parts.append(f"[{k}:a]aformat=sample_rates=48000:channel_layouts=stereo[fxa]")
        ins.append("[fxa]")
    if music is not None:
        k, n_in = n_in, n_in + 1
        args += ["-i", str(out.with_suffix(".music.wav"))]
        parts.append(f"[{k}:a]aformat=sample_rates=48000:channel_layouts=stereo[mus]")
        ins.append("[mus]")
    if ins:
        parts += [f"[{a}]aformat=sample_rates=48000:channel_layouts=stereo,apad=whole_dur={total + 0.5:.3f}[vst]",
                  f"[vst]{''.join(ins)}amix=inputs={1 + len(ins)}:normalize=0:duration=first,alimiter=limit=0.89:level=false[ao]"]
    else:
        parts.append(f"[{a}]apad[ao]")  # never let the sound end before the picture (-t trims both)

    args += [
        "-filter_complex", ";".join(parts), "-map", "[vo]", "-map", "[ao]", "-t", f"{total:.3f}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-maxrate", "14M", "-bufsize", "28M", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out),
    ]
    run(args)
    for x in (".sfx.wav", ".music.wav"):
        out.with_suffix(x).unlink(missing_ok=True)
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


def open_spec(v) -> tuple[float, float, float] | None:
    """`music_open`: seconds, or {"at", "over", "from"}: the music is muffled from
    `from` and opens out fully over `over` seconds at `at`."""
    if v in (None, False):
        return None
    if isinstance(v, dict):
        return float(v.get("from", 0.0)), float(v.get("at", 0.0)), max(0.05, float(v.get("over", 0.8)))
    return 0.0, float(v), 0.8


def stop(wav: Path, at: float) -> None:
    """Cut the music dead at `at` (a 15 ms edge, so it doesn't click) and keep it silent after."""
    tmp = wav.with_suffix(".stop.wav")
    run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(wav), "-af", f"afade=t=out:st={max(0.0, at - 0.015):.3f}:d=0.015",
         "-ar", "48000", "-ac", "2", str(tmp)])
    tmp.replace(wav)


def muffle(wav: Path, start: float, at: float, over: float) -> None:
    """Make the music sound far away (low-passed and softer) from `start`, then open it out."""
    tmp = wav.with_suffix(".open.wav")
    far = f"if(lt(t,{start:.3f}),0,if(lt(t,{at:.3f}),1,max(0,1-(t-{at:.3f})/{over:.3f})))"
    run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(wav), "-filter_complex",
         f"[0:a]asplit[a][b];[a]lowpass=f=420,lowpass=f=420,volume='0.7*{far}':eval=frame[m];"
         f"[b]volume='1-{far}':eval=frame[f];[m][f]amix=inputs=2:normalize=0[o]", "-map", "[o]", "-ar", "48000", "-ac", "2", str(tmp)])
    tmp.replace(wav)
