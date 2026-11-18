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


PANELS = True  # off for storyboards, whose footage-free scenes bring their own background


def _panel(start: float, end: float, w: int, h: int) -> str:
    if not PANELS:
        return f"Comment: 5,{_t(start)},{_t(end)},Card,,0,0,0,,no panel"
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


# --- Line chart, quote card, progress bar ---------------------------------

@dataclass
class Quote:
    line: int
    who: str = ""
    text: str = ""


def parse_line_charts(items: list[str], n_lines: int) -> list[Chart]:
    """Same form as --chart, 2 to 24 points: "LINE=2019 4, 2020 6, 2021 9|Title"."""
    out = []
    for it in items:
        try:
            ch = parse_charts([it], n_lines)[0]
        except SystemExit:
            ch = None
        if ch is None:  # parse_charts caps at 8; re-parse for longer runs
            line, _, rest = it.partition("=")
            data, _, title = rest.partition("|")
            pts = [re.match(r"\s*(.+?)\s+(-?[\d.]+)\s*$", p) for p in data.split(",")]
            if not line.strip().isdigit() or not 0 < int(line) <= n_lines or not all(pts) or not 1 < len(pts) <= 24:
                raise SystemExit(f"--line-chart {it!r}: give LINE=label number, label number, ... (2 to 24 points)|title")
            ch = Chart(int(line) - 1, [(m.group(1), float(m.group(2))) for m in pts], title.strip())
        out.append(ch)
    return out


def parse_quotes(items: list[str], script: list[str]) -> list[Quote]:
    n_lines = len(script)
    out = []
    for it in items:
        line, _, who = it.partition("=")
        if not line.strip().isdigit() or not 0 < int(line) <= n_lines:
            raise SystemExit(f"--quote {it!r}: use LINE or LINE=Who said it, e.g. 4=Mara Ilić")
        out.append(Quote(int(line) - 1, who.strip(), script[int(line) - 1].strip()))
    return out


def _seg(x0: float, y0: float, x1: float, y1: float, th: float) -> str:
    """A straight stroke from (x0, y0) to (x1, y1), th thick, as a filled quad."""
    dx, dy = x1 - x0, y1 - y0
    ln = (dx * dx + dy * dy) ** 0.5 or 1
    nx, ny = -dy / ln * th / 2, dx / ln * th / 2
    p = [(x0 + nx, y0 + ny), (x1 + nx, y1 + ny), (x1 - nx, y1 - ny), (x0 - nx, y0 - ny)]
    return "m " + " l ".join(f"{round(a)} {round(b)}" for a, b in p) + " "


def _dot(x: float, y: float, r: float) -> str:
    k = 0.5523 * r
    return (f"m {round(x)} {round(y - r)} b {round(x + k)} {round(y - r)} {round(x + r)} {round(y - k)} {round(x + r)} {round(y)} "
            f"b {round(x + r)} {round(y + k)} {round(x + k)} {round(y + r)} {round(x)} {round(y + r)} "
            f"b {round(x - k)} {round(y + r)} {round(x - r)} {round(y + k)} {round(x - r)} {round(y)} "
            f"b {round(x - r)} {round(y - k)} {round(x - k)} {round(y - r)} {round(x)} {round(y - r)} ")


def line_chart_events(ch: Chart, start: float, end: float, w: int, h: int, accent: str) -> list[str]:
    """Line chart card: the line draws itself from left to right over a soft
    accent wash, a dot marks each point, and the last value lands at the end."""
    hi = ass_colour(accent)
    vertical = h > w
    left, right = round(0.12 * w), round(0.88 * w)
    base = round(h * (0.7 if vertical else 0.8))
    top = round(h * (0.34 if vertical else 0.3))
    vals = [v for _, v in ch.bars]
    lo_v, hi_v = min(0.0, min(vals)), max(vals)
    span = (hi_v - lo_v) or 1.0
    n = len(vals)
    xs = [left + (right - left) * i / (n - 1) for i in range(n)]
    ys = [base - (base - top) * (v - lo_v) / span for v in vals]
    th = max(4, round(0.008 * min(w, h)))
    lab = round((0.033 if vertical else 0.03) * min(w, h))
    draw_ms = int(min(1600, max(700, 0.55 * (end - start) * 1000)))
    t0 = 0.3
    ms0 = int(t0 * 1000)
    reveal = f"\\clip({left - th},0,{left - th},{h})\\t({ms0},{ms0 + draw_ms},0.7,\\clip({left - th},0,{right + 3 * th},{h}))"
    rows = [_panel(start, end, w, h)]
    if ch.title:
        rows.append(f"Dialogue: 7,{_t(start + 0.1)},{_t(end)},CardText,,0,0,0,,{{\\an7\\pos({left},{round(h * 0.12)})"
                    f"\\fs{round(lab * 1.6)}\\fad(200,200)}}{_esc(ch.title)}")
    rows.append(_rect(6, start + 0.15, end, left, base + 3, right - left, 3, "&H00808080&", "\\fad(150,200)"))
    area = f"m {round(xs[0])} {base} " + " ".join(f"l {round(x)} {round(y)}" for x, y in zip(xs, ys)) + f" l {round(xs[-1])} {base}"
    rows.append(f"Dialogue: 6,{_t(start)},{_t(end)},Card,,0,0,0,,{{\\an7\\pos(0,0)\\p1\\bord0\\shad0\\1c{hi}\\1a&HC8&{reveal}"
                f"\\fad(0,200)}}{area}{{\\p0}}")
    stroke = "".join(_seg(x0, y0, x1, y1, th) for x0, y0, x1, y1 in zip(xs, ys, xs[1:], ys[1:]))
    stroke += "".join(_dot(x, y, th * 0.5) for x, y in zip(xs[1:-1], ys[1:-1]))  # round the joints
    rows.append(f"Dialogue: 7,{_t(start)},{_t(end)},Card,,0,0,0,,{{\\an7\\pos(0,0)\\p1\\bord0\\shad0\\1c{hi}{reveal}"
                f"\\fad(0,200)}}{stroke}{{\\p0}}")
    step = max(1, n // 8)  # at most ~8 labels under the axis
    for i, (name, v) in enumerate(ch.bars):
        at = start + t0 + draw_ms / 1000 * (xs[i] - left) / max(1, right - left)
        rows.append(f"Dialogue: 8,{_t(at)},{_t(end)},Card,,0,0,0,,{{\\an7\\pos(0,0)\\p1\\bord0\\shad0\\1c&H00FFFFFF&"
                    f"\\fad(120,200)}}{_dot(xs[i], ys[i], th * 1.3)}{{\\p0}}")
        if i % step == 0 or i == n - 1:
            rows.append(f"Dialogue: 7,{_t(start + 0.2)},{_t(end)},CardText,,0,0,0,,{{\\an8\\pos({round(xs[i])},{base + 14})"
                        f"\\fs{lab}\\fnInter SemiBold\\1c&H00C8C8C8&\\fad(150,200)}}{_esc(name)}")
        if i == n - 1 or v == max(vals):
            rows.append(f"Dialogue: 8,{_t(at + 0.05)},{_t(end)},CardText,,0,0,0,,{{\\an2\\pos({round(xs[i])},{round(ys[i] - th * 3)})"
                        f"\\fs{round(lab * 1.5)}\\1c{hi if i == n - 1 else '&H00FFFFFF&'}\\fscx80\\fscy80\\t(0,180,\\fscx100\\fscy100)"
                        f"\\fad(100,200)}}{_esc(f'{v:g}')}")
    return rows


def quote_events(q: Quote, start: float, end: float, w: int, h: int, accent: str) -> list[str]:
    """Pull-quote card: a large accent quotation mark drops in, the line's
    words rise into place, and who said it follows underneath."""
    hi = ass_colour(accent)
    vertical = h > w
    size = round((0.078 if vertical else 0.075) * min(w, h))
    m = round(0.1 * w)
    cy = round(h * (0.45 if vertical else 0.47))
    rows = [_panel(start, end, w, h)]
    mark_size = size * 4
    rows.append(f"Dialogue: 7,{_t(start + 0.1)},{_t(end)},CardText,,0,0,0,,{{\\an1\\pos({m},{cy - round(size * 1.2)})"
                f"\\fs{mark_size}\\1c{hi}\\fscx130\\fscy130\\alpha&HFF&\\t(0,260,0.6,\\fscx100\\fscy100\\alpha&H00&)\\fad(0,200)}}“")
    rows.append(f"Dialogue: 7,{_t(start + 0.25)},{_t(end)},CardText,,{m},{m},0,,{{\\an7\\move({m},{cy - round(size * 0.6)},{m},{cy - round(size * 0.9)},0,450)"
                f"\\fs{size}\\q0\\alpha&HFF&\\t(0,450,0.6,\\alpha&H00&)\\fad(0,200)}}{_esc(q.text)}")
    if q.who:
        rows.append(f"Dialogue: 7,{_t(start + 0.7)},{_t(end)},CardText,,0,0,0,,{{\\an7\\pos({m},{round(h * (0.78 if vertical else 0.82))})"
                    f"\\fs{round(size * 0.55)}\\fnInter SemiBold\\1c{hi}\\alpha&HFF&\\t(0,300,\\alpha&H00&)\\fad(0,200)}}— {_esc(q.who)}")
    return rows


def progress_events(length: float, w: int, h: int, accent: str, marks: list[float] = ()) -> list[str]:
    """A thin bar along the bottom edge that fills across the whole video,
    with a small notch at each new scene: viewers see how much is left."""
    hi = ass_colour(accent)
    bh = max(4, round(0.006 * h))
    ms = int(length * 1000)
    rows = [_rect(9, 0, length, 0, h, w, bh, "&H00FFFFFF&", "\\1a&HB0&"),
            _rect(9, 0, length, 0, h, w, bh, hi, f"\\fscx0\\t(0,{ms},\\fscx100)")]
    for t in marks:
        if 0 < t < length:
            rows.append(_rect(10, 0, length, round(w * t / length), h, max(2, bh // 2), bh, "&H00101010&", "\\1a&H60&"))
    return rows


# --- Explainer kit: pins, routes, timelines, kinetic type ------------------

@dataclass
class Pin:
    x: float  # 0..1 across the frame
    y: float  # 0..1 down the frame
    label: str = ""


@dataclass
class MapCard:
    line: int
    image: str
    pins: list  # [Pin]
    route: bool = True  # draw a line from pin to pin


@dataclass
class Timeline:
    line: int
    items: list  # [(when, what)]
    title: str = ""


def parse_maps(items: list[str], n_lines: int) -> list[MapCard]:
    """LINE=IMAGE|x,y Label; x,y Label  (x, y from 0 to 1 across and down the frame)."""
    out = []
    for it in items:
        line, _, rest = it.partition("=")
        image, _, pins_s = rest.partition("|")
        pins = []
        for part in [p for p in pins_s.split(";") if p.strip()]:
            m = re.match(r"\s*([\d.]+)\s*,\s*([\d.]+)\s*(.*)$", part)
            if not m or not (0 <= float(m.group(1)) <= 1 and 0 <= float(m.group(2)) <= 1):
                raise SystemExit(f"--map {it!r}: each pin is 'x,y Label' with x and y from 0 to 1, e.g. 0.3,0.6 Old port")
            pins.append(Pin(float(m.group(1)), float(m.group(2)), m.group(3).strip()))
        if not line.strip().isdigit() or not 0 < int(line) <= n_lines or not pins:
            raise SystemExit(f"--map {it!r}: use LINE=IMAGE|x,y Label; x,y Label")
        out.append(MapCard(int(line) - 1, image.strip(), pins))
    return out


def parse_timelines(items: list[str], n_lines: int) -> list[Timeline]:
    """LINE=1990 First stall, 2005 Night market opens, 2024 500 stalls|Title"""
    out = []
    for it in items:
        line, _, rest = it.partition("=")
        data, _, title = rest.partition("|")
        ev = []
        for part in [p for p in data.split(",") if p.strip()]:
            when, _, what = part.strip().partition(" ")
            ev.append((when, what.strip()))
        if not line.strip().isdigit() or not 0 < int(line) <= n_lines or not 1 < len(ev) <= 7:
            raise SystemExit(f"--timeline {it!r}: use LINE=WHEN what, WHEN what, ...|title (2 to 7 points)")
        out.append(Timeline(int(line) - 1, ev, title.strip()))
    return out


def pin_events(pins: list, start: float, end: float, w: int, h: int, accent: str, route: bool = True,
               gap: float = 0.55) -> list[str]:
    """Pins drop in one after another with a ring that pulses out; a label
    slides from each; a route draws itself from pin to pin."""
    hi = ass_colour(accent)
    r = max(8, round(0.012 * min(w, h)))
    lab = round(0.032 * min(w, h))
    th = max(4, round(0.006 * min(w, h)))
    rows = []
    pts = [(p.x * w, p.y * h) for p in pins]
    for i, ((x, y), p) in enumerate(zip(pts, pins)):
        t = start + 0.3 + gap * i
        if t >= end:
            break
        if route and i:
            x0, y0 = pts[i - 1]
            # A gentle arc, drawn as short straight pieces revealed in order.
            mx, my = (x0 + x) / 2, (y0 + y) / 2 - 0.12 * ((x - x0) ** 2 + (y - y0) ** 2) ** 0.5
            seg_t0 = t - gap * 0.85
            n = 14
            arc = [((1 - u) ** 2 * x0 + 2 * (1 - u) * u * mx + u * u * x, (1 - u) ** 2 * y0 + 2 * (1 - u) * u * my + u * u * y)
                   for u in [k / n for k in range(n + 1)]]
            for k in range(n):
                if k % 2:  # dashed, like a route on a map
                    continue
                a0 = seg_t0 + (gap * 0.7) * k / n
                rows.append(f"Dialogue: 6,{_t(a0)},{_t(end)},Card,,0,0,0,,{{\\an7\\pos(0,0)\\p1\\bord0\\shad0\\1c{hi}\\fad(60,200)}}"
                            f"{_seg(*arc[k], *arc[k + 1], th)}{{\\p0}}")
        # Each dot is drawn round its own centre and placed there, so it grows from where it sits.
        ring = (f"Dialogue: 7,{_t(t)},{_t(min(end, t + 0.9))},Card,,0,0,0,,{{\\an5\\pos({round(x)},{round(y)})\\p1\\bord{max(2, th // 2)}\\shad0"
                f"\\1a&HFF&\\3c{hi}\\t(0,800,\\fscx260\\fscy260\\3a&HFF&)}}{_dot(0, 0, r)}{{\\p0}}")
        dot = (f"Dialogue: 8,{_t(t)},{_t(end)},Card,,0,0,0,,{{\\an5\\pos({round(x)},{round(y)})\\p1\\bord{max(2, th // 2)}\\3c&H00FFFFFF&\\shad0\\1c{hi}"
               f"\\fscx0\\fscy0\\t(0,160,\\fscx125\\fscy125)\\t(160,260,\\fscx100\\fscy100)\\fad(0,200)}}"
               f"{_dot(0, 0, r)}{{\\p0}}")
        rows += [ring, dot]
        if p.label:
            right = x < w * 0.7
            an, lx = (4, round(x + r * 2.2)) if right else (6, round(x - r * 2.2))
            rows.append(f"Dialogue: 8,{_t(t + 0.15)},{_t(end)},LT,,0,0,0,,{{\\an{an}\\pos({lx},{round(y)})\\fs{lab}\\bord0"
                        f"\\4c&H00141414&\\shad0\\alpha&HFF&\\t(0,250,\\alpha&H00&)\\fad(0,200)}}{_esc(p.label)}")
    return rows


def map_events(mc: MapCard, start: float, end: float, w: int, h: int, accent: str) -> list[str]:
    """The pins and route of a map card (the image itself is laid under them
    by the finishing pass)."""
    return pin_events(mc.pins, start, end, w, h, accent, mc.route, gap=min(0.8, max(0.35, (end - start - 0.8) / max(1, len(mc.pins)))))


def timeline_events(tl: Timeline, start: float, end: float, w: int, h: int, accent: str) -> list[str]:
    """A line draws across the screen; each moment pops in along it with its
    date above and what happened below. The latest moment is in accent."""
    hi = ass_colour(accent)
    vertical = h > w
    left, right = round(0.1 * w), round(0.9 * w)
    y = round(h * 0.52)
    th = max(4, round(0.006 * min(w, h)))
    lab = round(0.036 * min(w, h))
    n = len(tl.items)
    draw = min(1.4, max(0.6, 0.5 * (end - start)))
    rows = [_panel(start, end, w, h)]
    if tl.title:
        rows.append(f"Dialogue: 7,{_t(start + 0.1)},{_t(end)},CardText,,0,0,0,,{{\\an7\\pos({left},{round(h * 0.14)})"
                    f"\\fs{round(lab * 1.6)}\\fad(200,200)}}{_esc(tl.title)}")
    ms0, ms1 = 250, 250 + int(draw * 1000)
    rows.append(f"Dialogue: 6,{_t(start)},{_t(end)},Card,,0,0,0,,{{\\an7\\pos(0,0)\\p1\\bord0\\shad0\\1c&H00808080&"
                f"\\clip({left},0,{left},{h})\\t({ms0},{ms1},0.6,\\clip({left},0,{right},{h}))\\fad(0,200)}}"
                f"{_seg(left, y, right, y, th)}{{\\p0}}")
    for i, (when, what) in enumerate(tl.items):
        x = left + (right - left) * (i / (n - 1))
        t = start + 0.25 + draw * (i / (n - 1))
        col = hi if i == n - 1 else "&H00FFFFFF&"
        rows.append(f"Dialogue: 8,{_t(t)},{_t(end)},Card,,0,0,0,,{{\\an5\\pos({round(x)},{y})\\p1\\bord0\\shad0\\1c{col}"
                    f"\\fscx0\\fscy0\\t(0,180,\\fscx130\\fscy130)\\t(180,280,\\fscx100\\fscy100)\\fad(0,200)}}"
                    f"{_dot(0, 0, th * 2.2)}{{\\p0}}")
        # Labels stay inside the frame: a label at either end is nudged in rather than cut off.
        from .style import text_width

        def keep_in(text: str, size: float, font: str = "InterDisplay-Black.otf") -> int:
            half = text_width(text, size, font) / 2
            return round(min(max(x, 0.04 * w + half), 0.96 * w - half))
        up = i % 2 == 0 or not vertical  # on a narrow screen, alternate above and below
        wy, ty = (y - th * 5, y + th * 5) if up else (y + th * 5, y - th * 5)
        rows.append(f"Dialogue: 8,{_t(t + 0.05)},{_t(end)},CardText,,0,0,0,,{{\\an{2 if up else 8}\\pos({keep_in(when, lab * 1.5)},{wy})"
                    f"\\fs{round(lab * 1.5)}\\1c{col}\\fad(150,200)}}{_esc(when)}")
        if what:
            rows.append(f"Dialogue: 8,{_t(t + 0.15)},{_t(end)},CardText,,0,0,0,,{{\\an{8 if up else 2}\\pos({keep_in(what, lab, 'Inter-SemiBold.otf')},{ty})"
                        f"\\fs{lab}\\fnInter SemiBold\\1c&H00D0D0D0&\\q0\\fad(150,200)}}{_esc(what)}")
    return rows


def kinetic_events(words, start: float, end: float, w: int, h: int, accent: str, emphasis: set[str] = frozenset()) -> list[str]:
    """Kinetic type: each word slams in as it is said, stacked into lines
    of big type; important words are bigger and in the accent colour."""
    hi = ass_colour(accent)
    vertical = h > w
    base = round(0.1 * min(w, h))
    m = round(0.08 * w)
    rows = [_panel(start, end, w, h)]
    if not words:
        return rows
    # Lay words out into lines that fit, measuring roughly (0.55 em per letter).
    lines, cur, cur_w = [], [], 0.0
    for wd in words:
        key = re.sub(r"[^\w']", "", wd.text.lower())
        big = key in emphasis or (not emphasis and len(key) >= 7)
        size = round(base * (1.45 if big else 1.0))
        ww = (len(wd.text) + 1) * 0.48 * size  # Inter ExtraBold runs about half an em a letter
        if cur and cur_w + ww > w - 2 * m:
            lines.append(cur)
            cur, cur_w = [], 0.0
        cur.append((wd, size, big, ww))
        cur_w += ww
    if cur:
        lines.append(cur)
    lh = [max(s for _, s, _, _ in ln) * 1.1 for ln in lines]
    y = (h - sum(lh)) / 2
    # Each word is its own event carrying the whole line, the other words
    # invisible: libass lays the line out once, so spacing is exact and every
    # word lands exactly where it will stay.
    for ln, hgt in zip(lines, lh):
        y += hgt
        for k, (wd, size, big, _) in enumerate(ln):
            t = max(start, wd.start)
            parts = []
            for i, (o, osz, obig, _) in enumerate(ln):
                if i == k:
                    col = f"\\1c{hi}" if big else ""
                    parts.append(f"{{\\fs{osz}{col}\\alpha&H80&\\fscx140\\fscy140\\t(0,140,0.6,\\fscx100\\fscy100\\alpha&H00&)}}{_esc(o.text)}{{\\r}}")
                else:
                    parts.append(f"{{\\fs{osz}\\alpha&HFF&}}{_esc(o.text)}{{\\r}}")
            rows.append(f"Dialogue: 7,{_t(t)},{_t(end)},CardText,,0,0,0,,{{\\an1\\q2\\pos({m},{round(y)})\\fad(0,200)}}" + " ".join(parts))
    return rows


def split_label_events(label: str, side: str, start: float, end: float, w: int, h: int, accent: str) -> list[str]:
    """A label pill on one half of a split screen: dark text on the accent
    colour, sliding up into place."""
    hi = ass_colour(accent)
    vertical = h > w
    size = round(0.04 * min(w, h))
    if vertical:
        x, y = w // 2, (h // 2 - round(0.04 * h)) if side == "left" else (h - round(0.06 * h))
    else:
        x, y = (w // 4 if side == "left" else 3 * w // 4), h - round(0.1 * h)
    t = start + (0.2 if side == "left" else 0.4)
    return [f"Dialogue: 8,{_t(t)},{_t(end)},CapBox,,0,0,0,,{{\\an2\\pos({x},{y})\\fs{size}\\3c{hi}\\3a&H00&\\bord{max(4, size // 3)}"
            f"\\1c&H00141414&\\1a&H00&\\move({x},{y + size},{x},{y},0,250)\\alpha&HFF&\\t(0,250,\\alpha&H00&)\\fad(0,200)}}{_esc(label)}"]
