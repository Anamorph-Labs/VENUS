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
    lower_thirds=(), card_lines=(), all_words=None,
) -> list[str]:
    """srt: classic one-line captions; words: timed words for animated captions."""
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
    if words or title or end_card or lower_thirds or card_lines:
        lts = [(lt, spans[lt.line][0]) for lt in lower_thirds if lt.line in spans]
        cards = [([x for x in all_words if x.line == n], *spans[n], n) for n in card_lines if n in spans]
        notes += [f"lower third for line {lt.line + 1} skipped: that line is not in the cut" for lt in lower_thirds if lt.line not in spans]
        ass = out.with_suffix(".look.ass")
        write_ass(ass, w, h, accent, words, title, end_card, cut_len, card, lts, cards)
        parts.append(f"[{v}]{ass_filter(ass)}[tt]")
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
