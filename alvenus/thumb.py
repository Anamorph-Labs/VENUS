"""A thumbnail for the cut: a strong frame of the speaker, a dark fade at the
bottom, and the title set big in the accent colour's company."""

from __future__ import annotations

from pathlib import Path

from .media import run
from .style import FONTS, _esc, ass_colour


def pick_moment(spans: dict[int, tuple[float, float]], covered: set[int], prefer: set[int]) -> float:
    """The middle of the line that best shows the speaker: one they lean in on
    (pushed or highlighted) if any, else the longest line not under a card or
    cutaway."""
    free = {n: s for n, s in spans.items() if n not in covered} or spans
    best = [n for n in free if n in prefer] or list(free)
    n = max(best, key=lambda k: free[k][1] - free[k][0])
    return (free[n][0] + free[n][1]) / 2


def _wrap(text: str, per_line: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        if cur and len(cur) + 1 + len(word) > per_line:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    return lines + ([cur] if cur else [])


def make(video: Path, at: float, out: Path, text: str, w: int, h: int, accent: str, look: str = "natural") -> None:
    from .style import LOOKS

    vertical = h > w
    size = round((0.14 if vertical else 0.11) * min(w, h))
    per_line = 11 if vertical else 18
    rows = _wrap(text, per_line)
    while len(rows) > 3 and per_line < 40:  # a long title gets smaller type, never cut off
        per_line += 2
        rows = _wrap(text, per_line)
    size = round(size * min(1.0, (11 if vertical else 18) / per_line))
    m = round(0.07 * w)
    y = round(h * (0.78 if vertical else 0.84))  # clear of the app buttons on phones
    hi = ass_colour(accent)
    bar_h = max(8, round(size * 0.12))
    ass = out.with_suffix(".thumb.ass")
    body = "\\N".join(_esc(r) for r in rows)
    lines_h = round(size * 1.05 * len(rows))
    ass.write_text("\n".join([
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {w}", f"PlayResY: {h}", "WrapStyle: 2", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: T,Inter Display Black,{size},&H00FFFFFF,&H00FFFFFF,&H00101010,&H80000000,0,0,0,0,100,100,0,0,1,0,{max(2, round(size * 0.05))},1,0,0,0,1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        f"Dialogue: 0,0:00:00.00,0:00:10.00,T,,0,0,0,,{{\\an1\\pos({m},{y})\\fsp-1}}{body}",
        f"Dialogue: 0,0:00:00.00,0:00:10.00,T,,0,0,0,,{{\\an1\\pos({m},{y - lines_h - round(size * 0.25)})\\p1\\bord0\\shad0\\1c{hi}}}"
        f"m 0 0 l {round(size * 1.4)} 0 {round(size * 1.4)} {bar_h} 0 {bar_h}{{\\p0}}",
    ]) + "\n", encoding="utf-8")
    esc = lambda p: str(p).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")
    shade = (f"split[a][b];[b]crop=iw:ih*0.55:0:ih*0.45,geq=lum='lum(X,Y)*(1-0.75*Y/H)':cb='cb(X,Y)':cr='cr(X,Y)'[s];"
             f"[a][s]overlay=0:H*0.45")
    run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", f"{max(0.0, at):.3f}", "-i", str(video),
         "-filter_complex", f"[0:v]scale={w}:{h},format=yuv420p,{LOOKS.get(look) + ',' if LOOKS.get(look) else ''}{shade},eq=contrast=1.06:saturation=1.1,"
         f"subtitles='{esc(ass)}':fontsdir='{esc(FONTS)}'",
         "-frames:v", "1", "-q:v", "2", str(out)])
    ass.unlink()
