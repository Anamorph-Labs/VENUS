"""Finishing touches for two kinds of real-footage film: documentary and
travel. All of it is type and shapes drawn by libass over the finished
picture, so it works the same in `cut`, `montage` and `make`.

Documentary:
  - a cinema matte (letterbox bars, 2.39:1 by default) on wide frames;
  - chapter titles: a small spaced label over a serif title, a hairline drawing
    out between them (title style "chapter");
  - interview name tags in the same family: a hairline, the name in serif, the
    role in small spaced capitals (lower-third style "doc");
  - place and time stamps typed out letter by letter ("Juniper Street, 3:12 AM").
Travel:
  - arrival titles: the place in huge condensed capitals tracking in, the
    country written by hand across it, the coordinates typed underneath
    (title style "place"; "Lisbon|Portugal|38.72 N, 9.14 W");
  - a camcorder date stamp in the corner, warm orange with a soft glow.

Each command sets EXTRAS before it writes its .ass file; write_ass adds them.
"""

from __future__ import annotations

from .style import _esc, _t, ass_colour, text_width

EXTRAS: dict = {}  # archive: [(year, tag, note, t0, t1, scene)]; verses: [(text, source, t0, t1)]; credits: [(role, name, t0, t1)]; letterbox: ratio; datestamp: text; places / arrivals: [(text, t0, t1)]; lower_third_style: "doc"
LT_STYLES = ("bar", "doc")


def matte(w: int, h: int) -> int:
    """Height of each letterbox bar in pixels (0 when there is none)."""
    r = EXTRAS.get("letterbox")
    if not r or h > w:
        return 0
    r = 2.39 if r is True else float(r)
    return max(0, round((h - w / r) / 2))


def _rect(layer: int, t0: float, t1: float, x: int, y: int, bw: int, bh: int, colour: str, extra: str = "") -> str:
    return (f"Dialogue: {layer},{_t(t0)},{_t(t1)},Card,,0,0,0,,{{\\an7\\pos({x},{y})\\p1\\bord0\\shad0\\1c{colour}{extra}}}"
            f"m 0 0 l {bw} 0 {bw} {bh} 0 {bh}{{\\p0}}")


def events(w: int, h: int, total: float, accent: str) -> list[str]:
    rows: list[str] = []
    bar = matte(w, h)
    if bar:  # under everything else that is drawn (captions sit on the bar, like subtitles in a cinema)
        rows += [_rect(0, 0, total + 1, 0, 0, w, bar, "&H00000000&"), _rect(0, 0, total + 1, 0, h - bar, w, bar, "&H00000000&")]
    arrivals = EXTRAS.get("arrivals") or []
    route = [a[0].split("|")[0].strip() for a in arrivals]
    for k, (text, t0, t1) in enumerate(arrivals):  # travel: a light leak, then a big arrival title when we reach a place
        rows += leak(max(0.0, t0 - 0.12), w, h, k)
        rows += place_title(text, w, h, accent, t0, t1, route=route if len(route) > 1 else None, at=k)
    for text, t0, t1 in EXTRAS.get("places") or []:
        rows += place_stamp(text, t0, t1, w, h, accent)
    if EXTRAS.get("datestamp"):
        rows += datestamp(str(EXTRAS["datestamp"]), total, w, h)
    for year, tag, note, t0, t1, k in EXTRAS.get("archive") or []:  # k: the scene's place, which side its print sits
        rows += archive_card(year, tag, note, t0, t1, w, h, accent, k)
    for text, source, t0, t1 in EXTRAS.get("verses") or []:
        rows += verse_card(text, source, t0, t1, w, h, accent)
    for k, (role, name, t0, t1) in enumerate(EXTRAS.get("credits") or []):
        rows += credit(role, name, t0, t1, w, h, k)
    return rows


def place_stamp(text: str, t0: float, t1: float, w: int, h: int, accent: str) -> list[str]:
    """Where and when, typed out in a small mono face low on the left, with
    an accent square; gone after a few seconds."""
    u = min(w, h)
    size = round(u * (0.03 if h > w else 0.027))
    x = round(0.07 * w)
    y = h - matte(w, h) - round(h * (0.2 if h > w else 0.075)) - (round(0.14 * h) if h > w else 0)
    end = min(t1, t0 + 4.0)
    step = max(30, min(70, 1100 // max(1, len(text))))
    sq = round(size * 0.42)
    rows = [_rect(6, t0, end, x, y - round(size * 0.68), sq, sq, ass_colour(accent), "\\fad(120,300)")]
    chars = "".join(f"{{\\alpha&HFF&\\t({k * step},{k * step + 1},\\alpha&H00&)}}{_esc(c)}" for k, c in enumerate(text.upper()))
    rows.append(f"Dialogue: 6,{_t(t0 + 0.1)},{_t(end)},Card,,0,0,0,,{{\\an1\\pos({x + round(sq * 2.2)},{y})\\fnDM Mono\\fs{size}"
                f"\\fsp{round(size * 0.12)}\\bord{max(1, round(size * 0.06))}\\3c&H00101010&\\3a&H80&\\shad0\\1c&H00F2F2F2&\\fad(0,300)}}{chars}")
    return rows


def datestamp(text: str, total: float, w: int, h: int) -> list[str]:
    """A camcorder date in the corner: warm orange, slightly soft, glowing."""
    u = min(w, h)
    size = round(u * (0.04 if h > w else 0.036))
    x, y = w - round(0.06 * w), h - matte(w, h) - round(h * (0.12 if h > w else 0.07))
    body = _esc(text.upper())
    return [
        f"Dialogue: 6,{_t(0)},{_t(total + 1)},Card,,0,0,0,,{{\\an3\\pos({x},{y})\\fnDM Mono\\fs{size}\\fsp{round(size * 0.08)}"
        f"\\bord{max(2, round(size * 0.18))}\\blur{max(3, round(size * 0.25))}\\3c&H003C9AFF&\\3a&HB0&\\shad0\\1c&H003C9AFF&\\1a&HFF&}}{body}",
        f"Dialogue: 7,{_t(0)},{_t(total + 1)},Card,,0,0,0,,{{\\an3\\pos({x},{y})\\fnDM Mono\\fs{size}\\fsp{round(size * 0.08)}"
        f"\\bord0\\shad0\\blur0.6\\1c&H0060B4FF&}}{body}",
    ]


def lower_third(name: str, role: str, start: float, w: int, h: int, accent: str, length: float = 4.2) -> list[str]:
    """Documentary name tag: a hairline draws out, the name rises in serif,
    the role follows in small spaced capitals."""
    u = min(w, h)
    size = round(u * (0.048 if h > w else 0.045))
    small = round(size * 0.5)
    x = round(0.07 * w)
    base = h - matte(w, h) - round(h * (0.3 if h > w else 0.1)) - (round(small * 1.9) if role else 0)
    end = start + length
    line_w = round(min(w * 0.3, max(text_width(name, size, "LibreBaskerville-Regular.ttf"), size * 4)))
    rows = [_rect(4, start, end, x, base - round(size * 1.25), line_w, max(2, round(u * 0.0025)), "&H00FFFFFF&",
                  f"\\alpha&H40&\\clip({x},0,{x},{h})\\t(0,500,0.5,\\clip({x},0,{x + line_w},{h}))\\fad(0,350)")]
    rise = round(size * 0.35)
    rows.append(f"Dialogue: 4,{_t(start + 0.2)},{_t(end)},Card,,0,0,0,,{{\\an1\\fnLibre Baskerville\\fs{size}\\bord0"
                f"\\shad{max(1, round(size * 0.04))}\\4c&H00000000&\\4a&H60&\\1c&H00FFFFFF&\\move({x},{base + rise},{x},{base},0,600)"
                f"\\alpha&HFF&\\t(0,600,\\alpha&H00&)\\fad(0,350)}}{_esc(name)}")
    if role:
        rows.append(f"Dialogue: 4,{_t(start + 0.55)},{_t(end)},Card,,0,0,0,,{{\\an7\\pos({x},{base + round(small * 0.7)})\\fnDM Mono"
                    f"\\fs{small}\\fsp{round(small * 0.25)}\\bord0\\shad{max(1, round(small * 0.06))}\\4a&H60&\\1c&H00D8D8D8&"
                    f"\\alpha&HFF&\\t(0,500,\\alpha&H00&)\\fad(0,350)}}{_esc(role.upper())}")
    return rows


def chapter_title(text: str, w: int, h: int, accent: str, start: float, end: float, centre: bool) -> list[str]:
    """"Part one|The night shift": the label in small spaced capitals, a
    hairline drawing out, the title in serif rising slowly into place. Without
    a "|" the whole text is the title."""
    label, _, title = text.partition("|") if "|" in text else ("", "", text)
    u = min(w, h)
    size0 = round(u * (0.075 if h > w else 0.07))
    from .style import fit_lines

    lines, size = fit_lines(title.strip(), size0, 0.8 * w, max_lines=2)
    size = round(size)
    small = round(u * 0.024)
    ms = int((end - start) * 1000)
    out = min(600, ms // 4)
    lh = round(size * 1.25)
    # documentaries centre their chapter titles, the opening one included
    an, x = 8, w // 2
    y = h // 2 - (lh * len(lines)) // 2 + round(small * 1.2)
    # a soft dark band behind the words, so they read over any footage
    top, band = y - round(small * 3.2), lh * len(lines) + round(small * 5.2)
    rows = [_rect(2, start, end, -round(w * 0.05), top, round(w * 1.1), band, "&H00000000&",
                  f"\\alpha&HFF&\\t(0,600,\\alpha&H90&)\\blur{round(band * 0.35)}\\fad(0,{out})")]
    hi = ass_colour(accent)
    bw = round(min(w * 0.18, size * 3))
    lx = x - bw // 2
    rows.append(_rect(3, start + 0.3, end, lx, y - round(small * 0.9), bw, max(2, round(u * 0.0022)), hi,
                      f"\\clip({lx},0,{lx},{h})\\t(0,700,0.5,\\clip({lx},0,{lx + bw},{h}))\\fad(0,{out})"))
    if label.strip():
        rows.append(f"Dialogue: 3,{_t(start)},{_t(end)},Card,,0,0,0,,{{\\an2\\pos({x},{y - round(small * 1.6)})\\fnDM Mono"
                    f"\\fs{small}\\fsp{round(small * 0.45)}\\bord0\\shad0\\1c&H00E6E6E6&\\alpha&HFF&\\t(0,500,\\alpha&H00&)\\fad(0,{out})}}"
                    f"{_esc(label.strip().upper())}")
    body = "\\N".join(_esc(x_) for x_ in lines)
    rise = round(size * 0.3)
    rows.append(f"Dialogue: 3,{_t(start + 0.45)},{_t(end)},Card,,0,0,0,,{{\\an{an}\\q2\\fnLibre Baskerville\\fs{size}\\bord0"
                f"\\shad{max(1, round(size * 0.03))}\\4a&H70&\\1c&H00FFFFFF&\\move({x},{y + rise},{x},{y},0,1100)"
                f"\\alpha&HFF&\\t(0,900,\\alpha&H00&)\\fad(0,{out})}}{body}")
    return rows


def leak(t0: float, w: int, h: int, k: int = 0) -> list[str]:
    """A warm light leak washing across the frame for under a second, as when
    a film camera starts rolling: two soft blobs of orange and rose light."""
    from .graphics import _disc

    u = max(w, h)
    rows = []
    for j, (col, r, y, a) in enumerate((("&H002A8CFF&", 0.42, 0.35, "60"), ("&H006A5AF0&", 0.3, 0.7, "78"))):
        x0, x1 = (-0.2 * w, 1.2 * w) if (k + j) % 2 == 0 else (1.2 * w, -0.2 * w)
        rows.append(f"Dialogue: 8,{_t(t0)},{_t(t0 + 0.9)},Card,,0,0,0,,{{\\an7\\move({x0 - r * u:.0f},{y * h - r * u:.0f},{x1 - r * u:.0f},{y * h - r * u:.0f},0,900)"
                    f"\\p1\\bord0\\shad0\\1c{col}\\alpha&H{a}&\\blur{round(u * 0.06)}\\fad(200,350)}}{_disc(r * u)}{{\\p0}}")
    return rows


def place_title(text: str, w: int, h: int, accent: str, start: float, end: float, centre: bool = True,
                route: list[str] | None = None, at: int = 0) -> list[str]:
    """"Lisbon|Portugal|38.72 N, 9.14 W": the place in huge condensed
    capitals tracking in from wide, the second part written by hand across it
    in the accent colour, the coordinates typed underneath."""
    parts = [p.strip() for p in text.split("|")]
    place, hand, coords = (parts + ["", ""])[:3]
    u = min(w, h)
    size = round(u * (0.24 if h > w else 0.22))
    while size > u * 0.08 and text_width(place.upper(), size, "BigShoulders-Bold.ttf") * 1.08 > 0.9 * w:
        size = round(size * 0.92)
    cx = w // 2
    cy = round(h * (0.46 if h > w else 0.5)) if centre else round(h * 0.3)
    ms = int((end - start) * 1000)
    out = min(500, ms // 4)
    rows = [f"Dialogue: 3,{_t(start)},{_t(end)},Card,,0,0,0,,{{\\an5\\q2\\pos({cx},{cy})\\fnBig Shoulders\\b1\\fs{size}"
            f"\\fsp{round(size * 0.35)}\\bord0\\shad{max(2, round(size * 0.02))}\\4a&H80&\\1c&H00FFFFFF&\\alpha&HFF&"
            f"\\t(0,900,0.4,\\fsp{round(size * 0.04)}\\alpha&H00&)\\fad(0,{out})}}{_esc(place.upper())}"]
    if hand:
        hs = round(size * 0.42)
        rows.append(f"Dialogue: 4,{_t(start + 0.55)},{_t(end)},Card,,0,0,0,,{{\\an5\\pos({cx + round(size * 0.35)},{cy + round(size * 0.3)})"
                    f"\\fnNothing You Could Do\\fs{hs}\\frz6\\bord0\\shad{max(1, round(hs * 0.04))}\\4a&H70&\\1c{ass_colour(accent)}"
                    f"\\clip(0,0,{cx - round(size * 1.6)},{h})\\t(0,700,\\clip(0,0,{w},{h}))\\fad(0,{out})}}{_esc(hand)}")
    if coords:
        cs = round(u * 0.026)
        step = max(25, min(60, 900 // max(1, len(coords))))
        chars = "".join(f"{{\\alpha&HFF&\\t({k * step},{k * step + 1},\\alpha&H00&)}}{_esc(c)}" for k, c in enumerate(coords.upper()))
        rows.append(f"Dialogue: 4,{_t(start + 0.9)},{_t(end)},Card,,0,0,0,,{{\\an8\\pos({cx},{cy + round(size * 0.68)})\\fnDM Mono\\fs{cs}"
                    f"\\fsp{round(cs * 0.3)}\\bord0\\shad1\\4a&H80&\\1c&H00F0F0F0&\\fad(0,{out})}}{chars}")
    if route:
        rows += _route(route, at, cx, cy + round(size * 0.68) + round(u * 0.085), w, h, accent, start + 1.1, end, out)
    return rows


def _route(names: list[str], at: int, cx: int, y: int, w: int, h: int, accent: str, t0: float, t1: float, out: int) -> list[str]:
    """The trip so far: a dotted line through every place, the ones visited
    filled in the accent colour, this one ringed, the rest still hollow."""
    from .graphics import _disc

    u = min(w, h)
    span = min(0.62 * w, len(names) * u * 0.2)
    xs = [cx - span / 2 + span * i / (len(names) - 1) for i in range(len(names))]
    r = max(4, round(u * 0.009))
    hi = ass_colour(accent)
    fade = f"\\alpha&HFF&\\t(0,350,\\alpha&H00&)\\fad(0,{out})"
    rows = []
    dash, gap = max(4, round(u * 0.012)), max(4, round(u * 0.01))
    x = xs[0]
    while x < xs[-1]:
        seg = min(dash, xs[-1] - x)
        done = x < xs[at]
        rows.append(_rect(4, t0, t1, round(x), y - max(1, r // 4), round(seg), max(2, r // 2),
                          hi if done else "&H00F0F0F0&", fade + ("" if done else "\\1a&H70&")))
        x += dash + gap
    for i, px in enumerate(xs):
        if i <= at:
            rows.append(f"Dialogue: 5,{_t(t0)},{_t(t1)},Card,,0,0,0,,{{\\an5\\pos({px:.0f},{y})\\p1\\bord0\\shad0\\1c{hi}{fade}}}{_disc(r)}{{\\p0}}")
        else:
            rows.append(f"Dialogue: 5,{_t(t0)},{_t(t1)},Card,,0,0,0,,{{\\an5\\pos({px:.0f},{y})\\p1\\bord{max(1, r // 3)}\\3c&H00F0F0F0&"
                        f"\\1a&HFF&\\shad0\\3a&HFF&\\t(0,350,\\3a&H00&)\\fad(0,{out})}}{_disc(r)}{{\\p0}}")
        if i == at:
            rows.append(f"Dialogue: 5,{_t(t0)},{_t(t1)},Card,,0,0,0,,{{\\an5\\pos({px:.0f},{y})\\p1\\bord{max(1, r // 3)}\\3c{hi}\\1a&HFF&"
                        f"\\shad0\\fscx100\\fscy100\\t(0,600,\\fscx240\\fscy240\\3a&HFF&)}}{_disc(r)}{{\\p0}}")
        if len(names) <= 5:
            fs = round(u * 0.022)
            rows.append(f"Dialogue: 5,{_t(t0)},{_t(t1)},Card,,0,0,0,,{{\\an8\\pos({px:.0f},{y + r + round(fs * 0.6)})\\fnDM Mono\\fs{fs}"
                        f"\\fsp{round(fs * 0.15)}\\bord0\\shad1\\4a&H80&\\1c{hi if i == at else '&H00E8E8E8&'}{fade}}}{_esc(names[i].upper())}")
    return rows


# --- Archive documentary (from the Venus board, 21 Nov) ----------------------
# Old photographs brought to life on a timeline, quote cards with a red source
# tag, and film-opening credits in small spaced capitals.

def _tag(layer: int, t0: float, t1: float, text: str, x: int, y: int, size: int, accent: str, an: int = 7,
         delay_ms: int = 0) -> list[str]:
    """A small solid accent label with white capitals (the red tag of the archive films).
    (x, y) is its top-left corner, or its top-centre when an is 8."""
    tw = round(text_width(text.upper(), size, "Inter-ExtraBold.otf") * 1.04 + size * 0.12 * len(text))
    pad_x, pad_y = round(size * 0.45), round(size * 0.28)
    bw, bh = tw + 2 * pad_x, round(size * 1.15) + 2 * pad_y
    left = x - bw // 2 if an == 8 else x
    grow = f"\\clip({left},0,{left},99999)\\t({delay_ms},{delay_ms + 320},0.5,\\clip({left},0,{left + bw},99999))"
    rows = [_rect(layer, t0, t1, left, y, bw, bh, ass_colour(accent), grow + "\\fad(0,300)")]
    rows.append(f"Dialogue: {layer + 1},{_t(t0)},{_t(t1)},Card,,0,0,0,,{{\\an7\\pos({left + pad_x},{y + pad_y})\\fnInter ExtraBold"
                f"\\fs{size}\\fsp{round(size * 0.12)}\\bord0\\shad0\\1c&H00FFFFFF&\\alpha&HFF&\\t({delay_ms + 200},{delay_ms + 450},\\alpha&H00&)"
                f"\\fad(0,300)}}{_esc(text.upper())}")
    return rows


def archive_card(year: str, tag: str, note: str, t0: float, t1: float, w: int, h: int, accent: str, k: int = 0) -> list[str]:
    """Words for an archive photograph: the year large in serif beside the
    picture (it settles in from a soft blur), a red tag with one word, and a
    small typed note under the tag. They sit on the side away from the print
    (archive.scene_video puts it left on even scenes, right on odd ones)."""
    u = min(w, h)
    vertical = h > w
    right = k % 2 == 0
    big = round(u * (0.14 if vertical else 0.13))
    small = round(u * 0.03)
    tag_size = round(u * 0.036)
    rows: list[str] = []
    if year:
        x = round(w * (0.94 if right else 0.06)) if not vertical else w // 2
        y = round(h * (0.78 if not vertical else 0.89))
        an = (3 if right else 1) if not vertical else 2
        rows.append(f"Dialogue: 5,{_t(t0 + 0.15)},{_t(t1)},Card,,0,0,0,,{{\\an{an}\\pos({x},{y})\\fnLibre Baskerville\\fs{big}"
                    f"\\bord0\\shad{max(1, round(big * 0.03))}\\4a&H50&\\1c&H00F2F2F2&\\blur12\\alpha&HFF&"
                    f"\\t(0,700,0.6,\\blur0\\alpha&H00&)\\fad(0,350)}}{_esc(year)}")
    if tag:
        tx = round(w * (0.73 if right else 0.06)) if not vertical else round(w * 0.5)
        ty = round(h * (0.24 if not vertical else 0.1))
        rows += _tag(6, t0 + 0.35, t1, tag, tx, ty, tag_size, accent, an=8 if vertical else 7)
        if note:
            nx = tx if not vertical else w // 2
            rows.append(f"Dialogue: 6,{_t(t0 + 0.75)},{_t(t1)},Card,,0,0,0,,{{\\an{8 if vertical else 7}\\pos({nx},{ty + round(tag_size * 2.2)})"
                        f"\\fnDM Mono\\fs{small}\\fsp{round(small * 0.08)}\\bord0\\shad1\\4a&H60&\\1c&H00CFCFCF&"
                        f"\\alpha&HFF&\\t(0,400,\\alpha&H00&)\\fad(0,300)}}{_esc(note)}")
    return rows


def verse_card(text: str, source: str, t0: float, t1: float, w: int, h: int, accent: str) -> list[str]:
    """A quote laid quietly over a picture: centred serif lines that clear
    from a soft blur, and the source in a small red tag underneath."""
    from .style import fit_lines

    u = min(w, h)
    vertical = h > w
    size0 = round(u * (0.06 if vertical else 0.058))
    lines, size = fit_lines(text.strip(), size0, (0.8 if vertical else 0.5) * w, max_lines=5)
    size = round(size)
    lh = round(size * 1.3)
    x, y = w // 2, h // 2 - (lh * len(lines)) // 2 - round(size * 0.6)
    band = lh * len(lines) + round(size * 3)
    rows = [_rect(4, t0, t1, round(w * 0.12), y - round(size * 0.8), round(w * 0.76), band, "&H00000000&",
                  f"\\alpha&HFF&\\t(0,700,\\alpha&HA8&)\\blur{round(band * 0.4)}\\fad(0,400)")]
    body = "\\N".join(_esc(l) for l in lines)
    rows.append(f"Dialogue: 5,{_t(t0 + 0.2)},{_t(t1)},Card,,0,0,0,,{{\\an8\\q2\\pos({x},{y})\\fnLibre Baskerville\\fs{size}"
                f"\\bord0\\shad{max(1, round(size * 0.05))}\\4a&H40&\\1c&H00FFFFFF&\\blur8\\alpha&HFF&"
                f"\\t(0,900,0.6,\\blur0\\alpha&H00&)\\fad(0,400)}}{body}")
    if source:
        rows += _tag(6, t0 + 0.9, t1, source, x, y + lh * len(lines) + round(size * 0.5), round(size * 0.5), accent, an=8)
    return rows


def credit(role: str, name: str, t0: float, t1: float, w: int, h: int, k: int = 0) -> list[str]:
    """An opening credit in a corner of the frame: the role in tiny spaced
    capitals over the name in larger spaced capitals, fading up slowly. The
    corner moves round the frame from one credit to the next."""
    u = min(w, h)
    small = round(u * 0.019)
    size = round(u * 0.032)
    bar = matte(w, h)
    corner = [(1, 0.07, 0.86), (9, 0.93, 0.12), (3, 0.93, 0.86), (7, 0.07, 0.12)][k % 4]
    an, fx, fy = corner
    x = round(w * fx)
    bottom = an in (1, 3)
    y = round(h * fy) if not bar else (h - bar - round(h * 0.05) if bottom else bar + round(h * 0.05))
    halign = 1 if an in (1, 7) else 3
    gap = round(size * 1.25)
    yr, yn = (y - gap, y) if bottom else (y, y + gap)
    fade = f"\\alpha&HFF&\\t(0,900,\\alpha&H00&)\\fad(0,700)"
    rows = []
    if role:
        rows.append(f"Dialogue: 6,{_t(t0)},{_t(t1)},Card,,0,0,0,,{{\\an{halign}\\pos({x},{yr})\\fnDM Mono\\fs{small}"
                    f"\\fsp{round(small * 0.5)}\\bord0\\shad1\\4a&H70&\\1c&H00D6D6D6&{fade}}}{_esc(role.upper())}")
    rows.append(f"Dialogue: 6,{_t(t0 + 0.25)},{_t(t1)},Card,,0,0,0,,{{\\an{halign}\\pos({x},{yn})\\fnLibre Baskerville\\fs{size}"
                f"\\fsp{round(size * 0.3)}\\bord0\\shad1\\4a&H70&\\1c&H00F4F4F4&{fade}}}{_esc(name.upper())}")
    return rows
