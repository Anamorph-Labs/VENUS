"""Explainer graphics drawn over the cut: lower thirds, kinetic text cards and
highlighted words. All of it is ASS (libass) so it renders inside FFmpeg with
no extra software; every piece is timed to the words as they are spoken."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .match import words as norm
from .style import _esc, _t, ass_colour


@dataclass
class LowerThird:
    line: int
    name: str
    role: str = ""


def parse_lower_thirds(items: list[str], n_lines: int) -> list[LowerThird]:
    out = []
    for it in items:
        line, _, rest = it.partition("=")
        name, _, role = rest.partition("|")
        if not line.strip().isdigit() or not name.strip() or not 0 < int(line) <= n_lines:
            raise SystemExit(f"--lower-third {it!r}: use LINE=Name|Role, e.g. 1=Mara Ilić|Night baker")
        out.append(LowerThird(int(line) - 1, name.strip(), role.strip()))
    return out


def parse_lines(items: list[str], n_lines: int, flag: str) -> list[int]:
    out = []
    for it in items:
        if not str(it).strip().isdigit() or not 0 < int(it) <= n_lines:
            raise SystemExit(f"{flag} {it!r}: give a script line number from 1 to {n_lines}")
        if int(it) - 1 not in out:
            out.append(int(it) - 1)
    return out


def parse_highlights(items: list[str], script: list[str]) -> list[tuple[int, list[str]]]:
    out = []
    for it in items:
        line, _, phrase = it.partition("=")
        if not line.strip().isdigit() or not 0 < int(line) <= len(script) or not phrase.strip():
            raise SystemExit(f"--highlight {it!r}: use LINE=words, e.g. 3=broken clocks")
        n = int(line) - 1
        want = norm(phrase)
        have = norm(script[n])
        if not any(have[i : i + len(want)] == want for i in range(len(have))):
            raise SystemExit(f"--highlight {it!r}: line {n + 1} doesn't contain {phrase.strip()!r}")
        out.append((n, want))
    return out


def mark(words, highlights: list[tuple[int, list[str]]]) -> None:
    """Flag the words of each highlighted phrase."""
    for line, want in highlights:
        ws = [w for w in words if w.line == line]
        normed = [norm(w.text) for w in ws]
        flat = [(i, x) for i, n in enumerate(normed) for x in n]
        for s in range(len(flat) - len(want) + 1):
            if [x for _, x in flat[s : s + len(want)]] == want:
                for i, _ in flat[s : s + len(want)]:
                    ws[i].mark = True


def lower_third_events(lt: LowerThird, start: float, w: int, h: int, accent: str, length: float = 3.8) -> list[str]:
    """An accent bar draws down, then the name wipes out from behind it and
    the role follows; it all fades away after a few seconds."""
    vertical = h > w
    size = round((0.052 if vertical else 0.05) * min(w, h))
    small = round(size * 0.62)
    x = round(0.07 * w)
    base = round((0.62 if vertical else 0.76) * h)  # name baseline; clear of the captions
    bar_w, bar_h = max(6, round(size * 0.14)), round(size * 1.05 + (small * 1.2 if lt.role else 0))
    top = base - size
    hi = ass_colour(accent)
    end = start + length
    rows = [
        f"Dialogue: 4,{_t(start)},{_t(end)},LT,,0,0,0,,{{\\an7\\pos({x},{top})\\p1\\bord0\\shad0\\1c{hi}"
        f"\\fscy0\\t(0,280,0.5,\\fscy100)\\fad(0,300)}}m 0 0 l {bar_w} 0 {bar_w} {bar_h} 0 {bar_h}{{\\p0}}",
    ]
    tx = x + bar_w + round(size * 0.4)
    rows.append(
        f"Dialogue: 4,{_t(start + 0.15)},{_t(end)},LT,,0,0,0,,{{\\an1\\pos({tx},{base})\\clip({tx},0,{tx},{h})"
        f"\\t(0,420,0.6,\\clip({tx},0,{w},{h}))\\fad(0,300)}}{_esc(lt.name)}"
    )
    if lt.role:
        rows.append(
            f"Dialogue: 4,{_t(start + 0.35)},{_t(end)},LTRole,,0,0,0,,{{\\an7\\pos({tx},{base + round(small * 0.35)})"
            f"\\clip({tx},0,{tx},{h})\\t(0,420,0.6,\\clip({tx},0,{w},{h}))\\fad(0,300)}}{_esc(lt.role)}"
        )
    return rows


def card_events(words, start: float, end: float, w: int, h: int, accent: str) -> list[str]:
    """Kinetic text card: the line fills the screen on a dark panel, each word
    rising in as it is said; highlighted words land in the accent colour."""
    hi = ass_colour(accent)
    rows = [
        f"Dialogue: 5,{_t(start)},{_t(end)},Card,,0,0,0,,{{\\an7\\pos(0,0)\\p1\\bord0\\shad0\\1c&H00171311&"
        f"\\fad(150,200)}}m 0 0 l {w} 0 {w} {h} 0 {h}{{\\p0}}",
        f"Dialogue: 6,{_t(start + 0.1)},{_t(end)},Card,,0,0,0,,{{\\an7\\pos({round(0.08 * w)},{round(0.16 * h)})\\p1\\bord0\\shad0"
        f"\\1c{hi}\\fscx0\\t(0,350,0.5,\\fscx100)\\fad(0,200)}}m 0 0 l {round(0.08 * min(w, h))} 0 "
        f"{round(0.08 * min(w, h))} {max(6, round(0.012 * min(w, h)))} 0 {max(6, round(0.012 * min(w, h)))}{{\\p0}}",
    ]
    for i, wd in enumerate(words):
        s = max(start, wd.start)
        e = words[i + 1].start if i + 1 < len(words) else end
        if i == len(words) - 1:
            e = end
        if e - s < 0.02:
            continue
        parts = []
        for j, x in enumerate(words):
            col = f"\\1c{hi}" if x.mark else ""
            if j < i:
                parts.append(f"{{{col}}}{_esc(x.text)}{{\\r}}" if col else _esc(x.text))
            elif j == i:
                parts.append(f"{{{col}\\alpha&HFF&\\t(0,160,\\alpha&H00&)}}{_esc(x.text)}{{\\r}}")
            else:
                parts.append(f"{{\\alpha&HFF&}}{_esc(x.text)}{{\\r}}")
        fade = f"\\fad(0,200)" if i == len(words) - 1 else ""
        rows.append(f"Dialogue: 7,{_t(s)},{_t(e)},CardText,,0,0,0,,{{{fade}}}{' '.join(parts)}")
    return rows


def styles(w: int, h: int) -> list[str]:
    vertical = h > w
    lt = round((0.052 if vertical else 0.05) * min(w, h))
    card = round((0.1 if vertical else 0.095) * min(w, h))
    m = round(0.08 * w)
    return [
        f"Style: LT,Inter ExtraBold,{lt},&H00FFFFFF,&H00FFFFFF,&H00101010,&H80000000,0,0,0,0,100,100,0,0,1,"
        f"{max(1, round(lt * 0.05))},{max(1, round(lt * 0.06))},1,0,0,0,1",
        f"Style: LTRole,Inter SemiBold,{round(lt * 0.62)},&H00E6E6E6,&H00FFFFFF,&H00101010,&H80000000,0,0,0,0,100,100,0,0,1,"
        f"{max(1, round(lt * 0.04))},{max(1, round(lt * 0.05))},7,0,0,0,1",
        "Style: Card,Inter ExtraBold,10,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1",
        f"Style: CardText,Inter Display Black,{card},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,"
        f"4,{m},{m},0,1",
    ]


# --- Data graphics: big-number stats and bar charts -------------------------

@dataclass
class Stat:
    line: int
    value: str  # as it should end up on screen: "73%", "1,200", "$4.5M"
    label: str = ""


@dataclass
class Chart:
    line: int
    bars: list  # [(label, value)]
    title: str = ""


def parse_stats(items: list[str], n_lines: int) -> list[Stat]:
    out = []
    for it in items:
        line, _, rest = it.partition("=")
        value, _, label = rest.partition("|")
        if not line.strip().isdigit() or not 0 < int(line) <= n_lines or not re.search(r"\d", value):
            raise SystemExit(f"--stat {it!r}: use LINE=NUMBER|label, e.g. 3=73%|of stalls open after midnight")
        out.append(Stat(int(line) - 1, value.strip(), label.strip()))
    return out


def parse_charts(items: list[str], n_lines: int) -> list[Chart]:
    out = []
    for it in items:
        line, _, rest = it.partition("=")
        data, _, title = rest.partition("|")
        bars = []
        for part in data.split(","):
            m = re.match(r"\s*(.+?)\s+(-?[\d.]+)\s*$", part)
            if not m:
                raise SystemExit(f"--chart {it!r}: each bar is 'label number', e.g. 2=Mon 3, Tue 5, Wed 9|Stalls open")
            bars.append((m.group(1), float(m.group(2))))
        if not line.strip().isdigit() or not 0 < int(line) <= n_lines or not 1 < len(bars) <= 8:
            raise SystemExit(f"--chart {it!r}: give a line number and 2 to 8 bars")
        out.append(Chart(int(line) - 1, bars, title.strip()))
    return out


def _panel(start: float, end: float, w: int, h: int) -> str:
    return (f"Dialogue: 5,{_t(start)},{_t(end)},Card,,0,0,0,,{{\\an7\\pos(0,0)\\p1\\bord0\\shad0\\1c&H00171311&"
            f"\\fad(150,200)}}m 0 0 l {w} 0 {w} {h} 0 {h}{{\\p0}}")


def _rect(layer: int, start: float, end: float, x: int, y: int, bw: int, bh: int, colour: str, extra: str = "") -> str:
    """A filled rectangle with its bottom-left corner at (x, y)."""
    return (f"Dialogue: {layer},{_t(start)},{_t(end)},Card,,0,0,0,,{{\\an1\\pos({x},{y})\\p1\\bord0\\shad0\\1c{colour}{extra}}}"
            f"m 0 0 l {bw} 0 {bw} {bh} 0 {bh}{{\\p0}}")


def count_frames(value: str, steps: int = 24) -> list[str]:
    """The number on its way up: "73%" -> "0%", "3%", ... "73%" (ease-out)."""
    m = re.search(r"-?[\d,]*\.?\d+", value)
    if not m:
        return [value]
    raw = m.group(0)
    target = float(raw.replace(",", ""))
    decimals = len(raw.split(".")[1]) if "." in raw else 0
    commas = "," in raw
    out = []
    for k in range(steps + 1):
        f = 1 - (1 - k / steps) ** 3
        n = target * f
        s = f"{n:,.{decimals}f}" if commas else f"{n:.{decimals}f}"
        out.append(value[: m.start()] + s + value[m.end():])
    return out


def stat_events(st: Stat, start: float, end: float, w: int, h: int, accent: str) -> list[str]:
    """Big-number card: the number counts up as the line is said; the label
    follows underneath."""
    hi = ass_colour(accent)
    vertical = h > w
    big = round((0.22 if vertical else 0.2) * min(w, h))
    small = round((0.05 if vertical else 0.045) * min(w, h))
    cx, cy = w // 2, round(h * (0.46 if vertical else 0.5))
    rows = [_panel(start, end, w, h)]
    frames = count_frames(st.value)
    run = min(1.1, max(0.4, 0.6 * (end - start)))
    step = run / (len(frames) - 1)
    for k, txt in enumerate(frames):
        s = start + 0.15 + k * step
        e = start + 0.15 + (k + 1) * step if k < len(frames) - 1 else end
        last = k == len(frames) - 1
        pop = "\\fscx104\\fscy104\\t(0,180,\\fscx100\\fscy100)\\fad(0,200)" if last else ""
        rows.append(f"Dialogue: 7,{_t(s)},{_t(e)},CardText,,0,0,0,,{{\\an5\\q2\\pos({cx},{cy})\\fs{big}\\1c{hi}{pop}}}{_esc(txt)}")
    if st.label:
        rows.append(f"Dialogue: 7,{_t(start + 0.35)},{_t(end)},CardText,,0,0,0,,{{\\an8\\pos({cx},{cy + round(big * 0.62)})"
                    f"\\fs{small * 1.0:.0f}\\fnInter SemiBold\\alpha&HFF&\\t(0,300,\\alpha&H00&)\\fad(0,200)}}{_esc(st.label)}")
    return rows


def chart_events(ch: Chart, start: float, end: float, w: int, h: int, accent: str) -> list[str]:
    """Bar chart card: bars grow up one after another, values appear on top,
    the tallest bar is in the accent colour."""
    hi = ass_colour(accent)
    grey = "&H00E7DED9&"
    vertical = h > w
    left, right = round(0.1 * w), round(0.9 * w)
    base = round(h * (0.72 if vertical else 0.8))
    top = round(h * (0.3 if vertical else 0.28))
    n = len(ch.bars)
    slot = (right - left) / n
    bw = round(slot * 0.62)
    peak = max(v for _, v in ch.bars) or 1.0
    lab = round((0.035 if vertical else 0.032) * min(w, h))
    val = round(lab * 1.25)
    rows = [_panel(start, end, w, h)]
    if ch.title:
        rows.append(f"Dialogue: 7,{_t(start + 0.1)},{_t(end)},CardText,,0,0,0,,{{\\an7\\pos({left},{round(h * 0.12)})"
                    f"\\fs{round(lab * 1.6)}\\fad(200,200)}}{_esc(ch.title)}")
    rows.append(_rect(6, start + 0.15, end, left, base + 3, right - left, 3, "&H00808080&", "\\fad(150,200)"))
    for i, (name, v) in enumerate(ch.bars):
        x = round(left + slot * i + (slot - bw) / 2)
        bh = max(2, round((base - top) * max(v, 0) / peak))
        t0 = 0.25 + 0.12 * i
        ms0, ms1 = int(t0 * 1000), int((t0 + 0.5) * 1000)
        col = hi if v == peak else grey
        rows.append(_rect(6, start, end, x, base, bw, bh, col, f"\\fscy0\\t({ms0},{ms1},0.5,\\fscy100)\\fad(0,200)"))
        num = f"{v:g}"
        rows.append(f"Dialogue: 7,{_t(start + t0 + 0.4)},{_t(end)},CardText,,0,0,0,,{{\\an2\\pos({x + bw // 2},{base - bh - 8})"
                    f"\\fs{val}\\fad(150,200)}}{_esc(num)}")
        rows.append(f"Dialogue: 7,{_t(start + t0)},{_t(end)},CardText,,0,0,0,,{{\\an8\\pos({x + bw // 2},{base + 14})"
                    f"\\fs{lab}\\fnInter SemiBold\\1c&H00C8C8C8&\\fad(150,200)}}{_esc(name)}")
    return rows
