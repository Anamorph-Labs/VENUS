"""The look of a cut: colour grades, animated captions and motion titles.

Everything on screen is drawn with libass (inside FFmpeg) from one .ass file,
using the Inter fonts shipped in alvenus/fonts, so a cut looks the same on
every computer."""

from __future__ import annotations

from pathlib import Path

FONTS = Path(__file__).parent / "fonts"

# Colour grades, as FFmpeg filters. Applied to the speaker and B-roll alike so
# they match; kept gentle, the way a colourist would on a first pass.
LOOKS = {
    "natural": "",
    "warm": "colorbalance=rs=0.05:gs=0.01:bs=-0.05:rm=0.04:bm=-0.04,eq=saturation=1.08:gamma=1.02",
    "cool": "colorbalance=rs=-0.04:bs=0.06:rm=-0.03:bm=0.04,eq=saturation=1.02",
    "film": "colorbalance=rs=-0.06:gs=-0.01:bs=0.06:rh=0.07:gh=0.02:bh=-0.06,"
            "curves=all='0/0.04 0.25/0.22 0.75/0.79 1/0.96',eq=saturation=0.92,vignette=PI/5,noise=alls=5:allf=t",
    "punchy": "eq=contrast=1.1:saturation=1.22,unsharp=5:5:0.4",
    "mono": "hue=s=0,curves=all='0/0.02 0.5/0.47 1/0.98',vignette=PI/5,noise=alls=5:allf=t",
}


def ass_colour(hex_rgb: str, alpha: int = 0) -> str:
    h = hex_rgb.lstrip("#")
    if len(h) != 6:
        raise SystemExit(f"colour {hex_rgb!r}: use #RRGGBB, e.g. #FFD23F")
    return f"&H{alpha:02X}{h[4:6]}{h[2:4]}{h[0:2]}".upper()


def _t(t: float) -> str:
    cs = int(round(max(0.0, t) * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", "\\N")


def chunks(words, vertical: bool) -> list[list]:
    """Short phrases that read at a glance: a few words, broken at punctuation."""
    max_chars, max_words = (18, 4) if vertical else (32, 7)
    out, cur = [], []
    for w in words:
        if cur and (len(" ".join(x.text for x in cur + [w])) > max_chars or len(cur) >= max_words):
            out.append(cur)
            cur = []
        cur.append(w)
        if w.text[-1:] in ",.?!;:":
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def caption_events(words, w: int, h: int, accent: str, skip: set[int] = frozenset()) -> list[str]:
    """One event per spoken word: the phrase stays put, the word being said
    lights up in the accent colour with a small pop, words still to come wait
    slightly dimmed. Highlighted words sit on an accent marker block (drawn
    on a layer below with the same layout), in dark text. Lines in `skip`
    (shown as full-screen cards) get no captions."""
    vertical = h > w
    groups = chunks([x for x in words if x.line not in skip], vertical)
    hi = ass_colour(accent)
    dark = "&H00141414&"
    pop = "\\t(0,90,\\fscx112\\fscy112)\\t(90,190,\\fscx100\\fscy100)"
    rows = []
    for g_i, g in enumerate(groups):
        nxt = groups[g_i + 1][0].start if g_i + 1 < len(groups) else None
        g_end = g[-1].end + 0.2
        if nxt is not None:
            g_end = min(g_end, nxt)
        for i, word in enumerate(g):
            s = word.start
            e = g[i + 1].start if i + 1 < len(g) else g_end
            if e - s < 0.02:
                continue
            top, box = [], []
            for j, x in enumerate(g):
                t = _esc(x.text)
                anim = pop if j == i else ""
                if x.mark:
                    fill = f"\\1c{dark}\\3a&HFF&\\4a&HFF&"  # crisp dark text on the marker
                elif j == i:
                    fill = f"\\1c{hi}"
                elif j > i:
                    fill = "\\1a&H50&"
                else:
                    fill = ""
                top.append(f"{{{fill}{anim}}}{t}{{\\r}}" if fill or anim else t)
                show = "\\3a&H00&" if x.mark else "\\3a&HFF&"
                # a space between two marked words is part of the marker, so the block is unbroken
                sp = " " if j and x.mark and g[j - 1].mark else ""
                box.append(f"{{\\1a&HFF&\\3c{hi}{show}{anim}}}{sp}{t}{{\\r}}")
            enter = "{\\fad(80,0)}" if i == 0 else ""
            rows.append(f"Dialogue: 2,{_t(s)},{_t(e)},Cap,,0,0,0,,{enter}{' '.join(top)}")
            if any(x.mark for x in g):
                joined = box[0] + "".join(("" if g[j].mark and g[j - 1].mark else " ") + b for j, b in enumerate(box[1:], 1))
                rows.append(f"Dialogue: 1,{_t(s)},{_t(e)},CapBox,,0,0,0,,{enter}{joined}")
    return rows


def text_width(text: str, size: float, font: str = "InterDisplay-Black.otf") -> float:
    """How wide libass will set `text` at `size` (it scales a font so its
    ascent plus descent equals the size)."""
    try:
        from PIL import ImageFont

        f = ImageFont.truetype(str(FONTS / font), 200)
        asc, desc = f.getmetrics()
        return f.getlength(text) * size / (asc + desc)
    except Exception:  # no Pillow: a safe guess
        return len(text) * size * 0.55


TITLE_STYLES = {
    "track": "letters close in from wide spacing as they rise, accent bar draws out",
    "reveal": "the line rises out from behind an invisible edge, like a slot",
    "type": "typed out letter by letter behind an accent cursor",
    "block": "an accent block wipes across and leaves the title behind it",
    "stamp": "lands hard from big to size with a quick settle",
}


def title_events(text: str, w: int, h: int, accent: str, start: float, end: float, centre: bool,
                 kind: str = "track") -> list[str]:
    """A motion title in one of TITLE_STYLES."""
    size = round((0.085 if h > w else 0.075) * min(w, h))
    cx = w // 2
    y = h // 2 - size if centre else round((0.14 if h > w else 0.11) * h)
    rise = round(0.025 * h)
    ms = int((end - start) * 1000)
    out_fade = min(400, ms // 4)
    bar_w, bar_h = round(0.16 * w if w < h else 0.12 * w), max(6, round(size * 0.11))
    bar_y = y + round(size * 1.3)
    hi = ass_colour(accent)
    tw = min(w * 0.94, text_width(text, size) + size * 0.12)
    x0, line_h = round(cx - tw / 2), round(size * 1.25)
    head = f"Dialogue: 3,{_t(start)},{_t(end)},Title,,0,0,0,,"
    rect = lambda bw, bh: f"m 0 0 l {bw} 0 {bw} {bh} 0 {bh}"
    bar = (f"Dialogue: 3,{_t(start + 0.25)},{_t(end)},Title,,0,0,0,,"
           f"{{\\an8\\pos({cx},{bar_y})\\p1\\bord0\\shad0\\1c{hi}\\fscx0\\t(0,450,0.5,\\fscx100)\\fad(0,{out_fade})}}"
           f"{rect(bar_w, bar_h)}{{\\p0}}")
    if kind == "reveal":
        txt = (head + f"{{\\an8\\q2\\shad0\\clip(0,{y - 4},{w},{y + line_h})\\move({cx},{y + line_h},{cx},{y},0,520)"
               f"\\fad(0,{out_fade})}}{_esc(text)}")
        return [txt, bar]
    if kind == "type":
        step = max(25, min(70, 900 // max(1, len(text))))
        body = "".join(f"{{\\alpha&HFF&\\t({i * step},{i * step + 1},\\alpha&H00&)}}{_esc(c)}" for i, c in enumerate(text))
        txt = head + f"{{\\an8\\q2\\pos({cx},{y})\\fad(0,{out_fade})}}" + body
        done = len(text) * step
        cur_w = max(6, round(size * 0.09))
        cursor = (head + f"{{\\an7\\p1\\bord0\\shad0\\1c{hi}\\move({x0 + round(tw / len(text))},{y + round(size * 0.12)},{x0 + round(tw)},{y + round(size * 0.12)},0,{done - step})"
                  f"\\t({done + 300},{done + 400},\\alpha&HFF&)}}{rect(cur_w, round(size * 1.0))}{{\\p0}}")
        return [txt, cursor]
    if kind == "block":
        top, bot = y - round(size * 0.05), y + line_h
        x1 = x0 + round(tw)
        block = (head + f"{{\\an7\\pos({x0},{top})\\p1\\bord0\\shad0\\1c{hi}\\clip({x0},{top},{x0},{bot})"
                 f"\\t(0,320,0.6,\\clip({x0},{top},{x1},{bot}))\\t(380,700,1.6,\\clip({x1},{top},{x1},{bot}))}}"
                 f"{rect(round(tw), bot - top)}{{\\p0}}")
        txt = (head + f"{{\\an8\\q2\\pos({cx},{y})\\clip({x0},{top},{x0},{bot})"
               f"\\t(380,700,1.6,\\clip({x0},{top},{x1},{bot}))\\fad(0,{out_fade})}}{_esc(text)}")
        return [txt, block]
    if kind == "stamp":
        txt = (head + f"{{\\an5\\q2\\pos({cx},{y + size // 2})\\fscx165\\fscy165\\alpha&HFF&"
               f"\\t(0,170,1.8,\\fscx96\\fscy96\\alpha&H00&)\\t(170,300,\\fscx100\\fscy100)\\fad(0,{out_fade})}}{_esc(text)}")
        return [txt, bar]
    txt = (head + f"{{\\an8\\q2\\move({cx},{y + rise},{cx},{y},0,650)\\fsp{round(size * 0.22)}\\alpha&HFF&"
           f"\\t(0,650,0.45,\\fsp0\\alpha&H00&)\\fad(0,{out_fade})}}{_esc(text)}")
    return [txt, bar]


def write_ass(path: Path, w: int, h: int, accent: str, words=None, title: str | None = None,
              end_card: str | None = None, cut_len: float = 0.0, card_len: float = 0.0,
              lower_thirds=(), cards=(), extra_rows=(), skip=frozenset(), title_style: str = "track") -> None:
    """lower_thirds: [(LowerThird, start)]; cards: [(words, start, end, line)];
    extra_rows: ready-made events (stat and chart cards) on lines in `skip`."""
    from . import graphics

    vertical = h > w
    cap = round((0.062 if vertical else 0.055) * min(w, h))
    big = round((0.085 if vertical else 0.075) * min(w, h))
    rows = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {w}", f"PlayResY: {h}", "WrapStyle: 0",
        "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Cap,Inter ExtraBold,{cap},&H00FFFFFF,&H00FFFFFF,&H00101010,&H90000000,0,0,0,0,100,100,0,0,1,"
        f"{max(2, round(cap * 0.09))},{max(1, round(cap * 0.05))},2,{round(0.08 * w)},{round(0.08 * w)},{round((0.2 if vertical else 0.07) * h)},1",
        # Same layout as Cap; its opaque box (BorderStyle 3) is the highlighter marker.
        f"Style: CapBox,Inter ExtraBold,{cap},&HFFFFFFFF,&HFFFFFFFF,&HFF101010,&HFF000000,0,0,0,0,100,100,0,0,3,"
        f"{max(2, round(cap * 0.12))},0,2,{round(0.08 * w)},{round(0.08 * w)},{round((0.2 if vertical else 0.07) * h)},1",
        f"Style: Title,Inter Display Black,{big},&H00FFFFFF,&H00FFFFFF,&H00101010,&H80000000,0,0,0,0,100,100,0,0,1,"
        f"{max(2, round(big * 0.04))},{max(1, round(big * 0.04))},8,{round(0.06 * w)},{round(0.06 * w)},0,1",
    ] + graphics.styles(w, h) + [
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    if words:
        rows += caption_events(words, w, h, accent, skip={c[3] for c in cards} | set(skip))
    for lt, start in lower_thirds:
        rows += graphics.lower_third_events(lt, start, w, h, accent)
    for ws, start, end, _ in cards:
        rows += graphics.card_events(ws, start, end, w, h, accent)
    rows += list(extra_rows)
    if title:
        rows += title_events(title, w, h, accent, 0.1, min(3.0, max(1.5, cut_len - 0.5)), centre=False, kind=title_style)
    if end_card:
        rows += title_events(end_card, w, h, accent, cut_len + 0.15, cut_len + card_len, centre=True, kind=title_style)
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def ass_filter(path: Path) -> str:
    esc = lambda p: str(p).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")
    return f"subtitles='{esc(path)}':fontsdir='{esc(FONTS)}'"
