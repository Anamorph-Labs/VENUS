"""Finishing touches laid over the cut: cutaway shots (B-roll), a music bed
that dips under the voice, an opening title and an end card.

The cut is made first; this pass adds the layers on top, then burns the
captions last so they stay above any cutaway."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .cut import Clip, subtitle_filter
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
    t = 0.0
    for c in clips:
        a, _ = spans.get(c.line, (t, t))
        spans[c.line] = (a, t + c.length)
        t += c.length
    return spans


def _ass_text(s: str) -> str:
    return s.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", "\\N")


def _ass_time(t: float) -> str:
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def write_titles(path: Path, w: int, h: int, title: str | None, end_card: str | None,
                 cut_len: float, card_len: float) -> None:
    """An ASS file: the title sits in the upper third over the opening (so
    the hook still starts at once); the end card text sits centred on a
    plain frame after the last line."""
    big = round(0.075 * min(w, h))
    rows = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {w}", f"PlayResY: {h}", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV",
        f"Style: Title,DejaVu Sans,{big},&H00FFFFFF,&H64000000,&H00000000,1,0,1,{max(2, big // 16)},0,8,40,40,{round(0.12 * h)}",
        f"Style: Card,DejaVu Sans,{big},&H00FFFFFF,&H00000000,&H00000000,1,0,1,0,0,5,40,40,0",
        "", "[Events]", "Format: Layer, Start, End, Style, Text",
    ]
    if title:
        end = min(3.0, max(1.5, cut_len - 0.5))
        rows.append(f"Dialogue: 0,{_ass_time(0.15)},{_ass_time(end)},Title,{{\\fad(300,400)}}{_ass_text(title)}")
    if end_card:
        rows.append(f"Dialogue: 0,{_ass_time(cut_len + 0.2)},{_ass_time(cut_len + card_len)},Card,{{\\fad(400,300)}}{_ass_text(end_card)}")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def finish(
    base: Path, out: Path, size: str, fps: float, spans: dict[int, tuple[float, float]],
    cutaways: list[Cutaway] = (), music: Path | None = None, music_lufs: float = -22.0,
    title: str | None = None, end_card: str | None = None, card_len: float = 2.5,
    srt: Path | None = None,
) -> list[str]:
    """Returns plain notes on anything it had to adjust."""
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

    if card:
        parts.append(f"[{v}]tpad=stop_mode=add:stop_duration={card:.3f}:color=0x15171c[pad]")
        v = "pad"
    if srt is not None:
        parts.append(f"[{v}]{subtitle_filter(srt, w, h)}[cap]")
        v = "cap"
    if title or end_card:
        ass = out.with_suffix(".titles.ass")
        write_titles(ass, w, h, title, end_card, cut_len, card)
        esc = str(ass).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")
        parts.append(f"[{v}]subtitles='{esc}'[tt]")
        v = "tt"
    parts.append(f"[{v}]format=yuv420p[vo]")

    a = "0:a"
    if card:
        parts.append(f"[{a}]apad=pad_dur={card:.3f}[ap]")
        a = "ap"
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
            "[key]aformat=channel_layouts=stereo[keyst]",
            "[mus][keyst]sidechaincompress=threshold=0.03:ratio=4:attack=20:release=900:makeup=1[duck]",
            "[voice]aformat=sample_rates=48000:channel_layouts=stereo[vst]",
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
    return notes
