"""The look of a cut: colour grades, animated captions and motion titles.

Everything on screen is drawn with libass (inside FFmpeg) from one .ass file,
using the Inter fonts shipped in alvenus/fonts, so a cut looks the same on
every computer."""

from __future__ import annotations

import re
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
    "doc": "colorbalance=rs=-0.03:bs=0.04:rh=0.03:bh=-0.02,curves=all='0/0.05 0.3/0.28 0.7/0.71 1/0.94',"
           "eq=saturation=0.82,vignette=PI/4.5,noise=alls=3:allf=t",
    "travel": "colorbalance=rs=0.04:bs=-0.05:rm=0.05:gm=0.01:bm=-0.04:rh=0.04:bh=-0.02,curves=all='0/0.03 0.5/0.52 1/0.97',"
              "eq=saturation=1.16:contrast=1.04,vignette=PI/6",
    # old brown photographs: lifted blacks, warm paper tone, soft grain and a heavy vignette
    "sepia": "hue=s=0,curves=all='0/0.07 0.35/0.3 0.75/0.72 1/0.92',colorchannelmixer=rr=1.07:gg=0.9:bb=0.68:gb=0.02:rb=0.02,"
             "vignette=PI/3.6,noise=alls=5:allf=t",
    # black-and-white archive: deep blacks, hard contrast, coarse moving grain (lets a red accent sing)
    "archive": "hue=s=0,curves=all='0/0 0.2/0.12 0.55/0.55 0.85/0.9 1/0.97',colorchannelmixer=rr=1.02:bb=0.97,"
               "vignette=PI/4,noise=alls=7:allf=t",
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



# A scene's own word look, set by the creator in Studio (or by their AI):
# font, weight, colour and where the words sit. It is laid over whatever
# the look drew, so it works the same for captions, moving type, titles and
# the designed looks. The accent colour stays the accent (it marks the big word).
WORD_FONTS = ("sans", "serif", "serif-italic", "tall", "typewriter", "hand")
WORD_WEIGHTS = ("regular", "bold", "heavy")
_SANS = {"regular": "Inter SemiBold", "bold": "Inter ExtraBold", "heavy": "Inter Display Black"}
_ONE = {"serif": "Libre Baskerville", "serif-italic": "Instrument Serif", "tall": "Big Shoulders",
        "typewriter": "DM Mono", "hand": "Nothing You Could Do"}
_INTER = ("Inter Display Black", "Inter Display ExtraBold", "Inter Display", "Inter ExtraBold", "Inter SemiBold")
WORD_LOOK: list = []  # [(t0, t1, look)] while a cut is being finished


def word_look(sc: dict) -> dict:
    """The word look a scene asks for ({} = the design's own)."""
    out = {}
    if sc.get("words_font") in WORD_FONTS:
        out["font"] = sc["words_font"]
    if sc.get("words_weight") in WORD_WEIGHTS:
        out["weight"] = sc["words_weight"]
    c = sc.get("words_colour")
    if isinstance(c, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", c):
        out["colour"] = c
    for k in ("x", "y"):
        try:
            v = max(-0.5, min(0.5, float(sc.get("words_" + k) or 0)))
        except (TypeError, ValueError):
            v = 0.0
        if v:
            out[k] = v
    return out


def _family(look: dict, current: str) -> str:
    font, weight = look.get("font"), look.get("weight")
    if font and font != "sans":
        return _ONE[font]
    if font == "sans" or current in _INTER:
        return _SANS[weight or "bold"] if (font == "sans" or weight) else current
    return current


def restyle(rows: list[str], look: dict, w: int, h: int, accent: str | None = None) -> list[str]:
    """Lay a scene's word look over ready-made ASS rows."""
    if not look:
        return rows
    dx, dy = look.get("x", 0.0) * w, look.get("y", 0.0) * h
    keep = ass_colour(accent)[-6:].upper() if accent and re.fullmatch(r"#?[0-9A-Fa-f]{6}", accent) else None
    col = ass_colour(look["colour"]) + "&" if look.get("colour") else None
    out = []
    for r in rows:
        if not r.startswith("Dialogue:"):
            out.append(r)
            continue
        f = r.split(",", 9)
        if len(f) < 10:
            out.append(r)
            continue
        text = f[9]
        if dx or dy:
            sh = lambda m, xs: ",".join(f"{float(v) + (dx if i in xs else dy):.0f}" for i, v in enumerate(m.split(",")))
            text = re.sub(r"\\pos\(([-\d.]+,[-\d.]+)\)", lambda m: f"\\pos({sh(m.group(1), (0,))})", text)
            text = re.sub(r"\\org\(([-\d.]+,[-\d.]+)\)", lambda m: f"\\org({sh(m.group(1), (0,))})", text)
            text = re.sub(r"\\move\(([-\d.]+,[-\d.]+,[-\d.]+,[-\d.]+)((?:,[-\d.]+){0,2})\)",
                          lambda m: f"\\move({sh(m.group(1), (0, 2))}{m.group(2)})", text)
            text = re.sub(r"\\(i?clip)\(([-\d.]+,[-\d.]+,[-\d.]+,[-\d.]+)\)",
                          lambda m: f"\\{m.group(1)}({sh(m.group(2), (0, 2))})", text)
            if "\\pos(" not in text and "\\move(" not in text:  # placed by the style's margins
                an = re.search(r"\\an(\d)", text)
                top = (int(an.group(1)) >= 7) if an else f[3].strip() == "Title"
                try:
                    f[5], f[6] = str(max(0, int(f[5]) + round(dx))), str(max(0, int(f[6]) - round(dx)))
                    f[7] = str(max(0, int(f[7]) + (round(dy) if top else -round(dy))))
                except ValueError:
                    pass
        if "\\p1" not in text and "\\p2" not in text and "\\p4" not in text:  # words, not drawn shapes
            pre = ""
            if look.get("font") or look.get("weight"):
                cur = re.search(r"\\fn([^\\}]+)", text)
                style_font = {"Cap": "Inter ExtraBold", "CapBox": "Inter ExtraBold", "Title": "Inter Display Black"}.get(f[3].strip(), "")
                text = re.sub(r"\\fn([^\\}]+)", lambda m: "\\fn" + _family(look, m.group(1)), text)
                fam = _family(look, cur.group(1) if cur else style_font)
                if fam:
                    pre += "\\fn" + fam
                    # a reset (\r) between words goes back to the row's style: keep the chosen type after it
                    text = re.sub(r"\\r(?=[\\}])", lambda m: "\\r\\fn" + fam, text)
                if look.get("weight") and look.get("font") not in (None, "sans") or (look.get("weight") and fam not in _INTER):
                    b = "\\b0" if look["weight"] == "regular" else "\\b1"
                    text = re.sub(r"\\b\d", lambda m: b, text)
                    pre += b
            if col:
                text = re.sub(r"\\(1?c)&H([0-9A-Fa-f]{6,8})&",
                              lambda m: m.group(0) if keep and m.group(2)[-6:].upper() == keep else f"\\{m.group(1)}{col}", text)
                pre += "\\1c" + col
            if pre:
                text = ("{" + pre + text[1:]) if text.startswith("{") else "{" + pre + "}" + text
        f[9] = text
        out.append(",".join(f))
    return out


def restyle_timed(rows: list[str], w: int, h: int, accent: str | None = None) -> list[str]:
    """WORD_LOOK applied to the rows that start inside each scene (see restyle)."""
    if not WORD_LOOK:
        return rows
    out = []
    for r in rows:
        if r.startswith("Dialogue:"):
            f = r.split(",", 3)
            a, b = _secs(f[1]), _secs(f[2])
            hit = next((lk for t0, t1, lk in WORD_LOOK if t0 - 0.05 <= a < t1 and b <= t1 + 1.0), None)
            if hit:
                r = restyle([r], hit, w, h, accent)[0]
        out.append(r)
    return out


def _secs(t: str) -> float:
    try:
        hh, mm, ss = t.strip().split(":")
        return int(hh) * 3600 + int(mm) * 60 + float(ss)
    except ValueError:
        return -1.0

# Caption cards: short, following the voice. A card holds CARD_WORDS[0] to
# CARD_WORDS[1] words (2 to 6 unless the creator picks otherwise), breaks at
# punctuation and at each new line of the script, and never leaves one word
# on a card by itself when it can join a neighbour.
CARD_WORDS = (2, 6)
_JOIN = {"the", "a", "an", "of", "to", "and", "or", "but", "with", "in", "on", "at", "for", "my", "your",
         "our", "their", "this", "that", "his", "her", "its", "from", "into", "by"}


def chunks(words, vertical: bool) -> list[list]:
    """Caption cards that read at a glance (see CARD_WORDS)."""
    lo, hi = CARD_WORDS
    max_chars = 30 if vertical else 44  # two short rows at most
    pieces, cur = [], []
    for w in words:  # first: phrases, split where the script line changes or punctuation ends a thought
        if cur and getattr(w, "line", None) != getattr(cur[-1], "line", None):
            pieces.append(cur)
            cur = []
        cur.append(w)
        if w.text[-1:] in ",.?!;:":
            pieces.append(cur)
            cur = []
    if cur:
        pieces.append(cur)
    out: list[list] = []
    for pc in pieces:  # then: the best cut of each phrase into cards
        out += _cards(pc, lo, hi, max_chars)
    merged: list[list] = []
    for g in out:  # a lone word joins its neighbour on the same line when the card stays within the limit
        if merged and (len(g) < lo or len(merged[-1]) < lo) and len(merged[-1]) + len(g) <= hi \
                and getattr(g[0], "line", None) == getattr(merged[-1][-1], "line", None):
            merged[-1] = merged[-1] + g
        else:
            merged.append(g)
    return merged


def _cards(pc: list, lo: int, hi: int, max_chars: int) -> list[list]:
    """Cut one phrase into cards: each lo..hi words and not too wide, sizes
    even, and no card ending on a joining word ("the", "of"), which belongs
    with the word after it. The best cut is found by trying them all."""
    n = len(pc)
    if n <= hi and len(" ".join(x.text for x in pc)) <= max_chars:
        return [pc]
    ideal = n / max(1, -(-n // hi))
    best = [0.0] + [float("inf")] * n
    back = [0] * (n + 1)
    for j in range(1, n + 1):
        for i in range(max(0, j - hi), j):
            card = pc[i:j]
            c = (len(card) - ideal) ** 2
            if len(card) < lo and n >= lo:
                c += 40
            if len(" ".join(x.text for x in card)) > max_chars:
                c += 100
            if j < n and card[-1].text.lower().strip(",.?!;:") in _JOIN:
                c += 15
            if best[i] + c < best[j]:
                best[j], back[j] = best[i] + c, i
    cuts, j = [], n
    while j > 0:
        cuts.append((back[j], j))
        j = back[j]
    return [pc[i:j] for i, j in reversed(cuts)]


def _even(items: list, n: int) -> list[list]:
    """items split into n runs as equal as can be (5 -> 3 + 2, never 4 + 1)."""
    k, r = divmod(len(items), n)
    out, i = [], 0
    for j in range(n):
        m = k + (1 if j < r else 0)
        if m:
            out.append(items[i:i + m])
        i += m
    return out


CAPTION_MODE = "pop"  # "pop" (below), "bracket" or "keyword" (interview looks from the Venus 1 board)
CAPTION_MODES = ("pop", "classic", "bracket", "keyword", "stack")
# The type: Venus's own fonts, unless the brand kit gives the creator's
# (brand.fonts()). FONT_MAP swaps a Venus font for the creator's everywhere
# on screen (captions, titles, cards, charts); KIT_FILES says where those
# font files are, so text is measured and drawn in the font that is shown.
FONT_FILES = {"Inter ExtraBold": "Inter-ExtraBold.otf", "Inter SemiBold": "Inter-SemiBold.otf",
              "Instrument Serif": "InstrumentSerif-Italic.ttf", "Inter Display Black": "InterDisplay-Black.otf",
              "Inter Display ExtraBold": "InterDisplay-ExtraBold.otf", "Inter Display": "InterDisplay-Bold.otf"}
FONT_MAP: dict[str, str] = {}
KIT_FILES: dict[str, Path] = {}
BRANDED = False  # a brand kit is in use: accents come from it, not from a look's own colours
PLACE = None  # a placement.Planner while a cut is being finished: where each caption card goes
GOLD = "&H004AB0E8&"  # warm gold (#E8B04A) for the keyword look
_STOP = {"the", "a", "an", "and", "or", "but", "to", "of", "in", "on", "at", "for", "is", "it", "that", "this", "i", "you",
         "we", "they", "he", "she", "be", "are", "was", "were", "so", "just", "with", "my", "your", "our", "as", "if", "do"}


def _key_word(g) -> int:
    """Which word of a phrase carries it: a highlighted one, else the longest
    word that is not a small joining word."""
    for j, x in enumerate(g):
        if getattr(x, "mark", False):
            return j
    best = max(range(len(g)), key=lambda j: (g[j].text.strip(",.?!;:").lower() not in _STOP, len(g[j].text)))
    return best


def bracket_events(words, w: int, h: int, accent: str, skip: set[int] = frozenset()) -> list[str]:
    """Interview captions, one word at a time in small mono type inside
    brackets ("[word]"), sitting at chest height under the face: quiet, so
    the speaker stays the picture."""
    vertical = h > w
    fs = round((0.03 if vertical else 0.032) * min(w, h) * (1.3 if vertical else 1))
    y = round(h * (0.66 if vertical else 0.78))
    rows = []
    ws = [x for x in words if x.line not in skip]
    for i, x in enumerate(ws):
        e = x.end + 0.12
        if i + 1 < len(ws):
            e = min(e, ws[i + 1].start) if ws[i + 1].start > x.start + 0.04 else x.end
        if e - x.start < 0.04:
            e = x.start + 0.04
        word = _esc(x.text.strip(",.?!;:"))
        col = ass_colour(accent) if getattr(x, "mark", False) else "&H00F2F2F2&"
        rows.append(f"Dialogue: 2,{_t(x.start)},{_t(e)},Cap,,0,0,0,,{{\\an5\\pos({w // 2},{y})\\fnDM Mono\\fs{fs}\\bord0"
                    f"\\shad{max(1, fs // 14)}\\4c&H80000000&\\1c{col}}}[{word}]")
    return rows


def _where(g, g_end: float, bw: float, bh: float, w: int, h: int):
    """(ASS alignment, x, y) for a caption card: the planner's choice when one
    is running (placement.py), else the usual bottom-centre spot (None)."""
    if PLACE is None:
        return None
    slot = PLACE.place(g[0].start, g_end, bw, bh, getattr(g[0], "line", -1))
    return PLACE.anchor(slot)


def keyword_events(words, w: int, h: int, accent: str, skip: set[int] = frozenset()) -> list[str]:
    """The produced-podcast look: each phrase in small clean type with its
    one carrying word set large above it in gold italic serif, landing as it
    is said and staying for the phrase. One small row at most: when the rest
    of the phrase is wider than the frame allows, its type gets smaller, it
    never stacks into more rows."""
    from .placement import safe_box

    vertical = h > w
    groups = chunks([x for x in words if x.line not in skip], vertical)
    small = round((0.034 if vertical else 0.036) * min(w, h) * (1.25 if vertical else 1))
    big = round(small * 2.8)
    y = round(h * (0.7 if vertical else 0.8))
    L, _, R, _ = safe_box(w, h)
    rows = []
    for g_i, g in enumerate(groups):
        nxt = groups[g_i + 1][0].start if g_i + 1 < len(groups) else None
        g_end = g[-1].end + 0.25 if nxt is None else min(g[-1].end + 0.25, nxt)
        k = _key_word(g)
        key = g[k]
        rest_text = " ".join(x.text for j, x in enumerate(g) if j != k)
        fs = small
        if rest_text:
            _, fs = fit_lines(rest_text, small, (R - L), max_lines=1)  # one row, smaller type if it must
            fs = round(min(small, fs))
        bf = round(big * fs / small)  # the small row and the big word scale together
        key_t = key.text.strip(",.?!;:")
        bw = max(text_width(key_t, bf, "InstrumentSerif-Italic.ttf"), text_width(rest_text, fs, "Inter-SemiBold.otf") if rest_text else 0)
        bh = bf * 1.02 + (fs * 1.25 if rest_text else 0)
        at = _where(g, g_end, bw, bh, w, h)
        if at is None:  # the classic spot: big word sitting on the small row's top edge
            kx, ky, kan, rx, ry, ran = w // 2, y - round(fs * 1.3), 2, w // 2, y - round(fs * 1.1), 8
        else:
            an, ax, ay = at
            col, row = (an - 1) % 3, (an - 1) // 3
            top = ay - bh if row == 0 else ay - bh / 2 if row == 1 else ay
            kan, ran = (7, 7) if col == 0 else (9, 9) if col == 2 else (8, 8)
            kx = rx = ax
            ky, ry = round(top), round(top + bf * 1.02)
        if key.start < g_end:
            rows.append(f"Dialogue: 3,{_t(key.start)},{_t(g_end)},Cap,,0,0,0,,{{\\an{kan}\\pos({kx},{ky})"
                        f"\\fnInstrument Serif\\i1\\fs{bf}\\bord0\\shad{max(1, bf // 24)}\\4c&H90000000&\\1c{ass_colour(accent) if BRANDED else GOLD}"
                        f"\\fscx90\\fscy90\\t(0,160,\\fscx100\\fscy100)\\fad(60,120)}}{_esc(key_t)}")
        if rest_text:
            rows.append(f"Dialogue: 2,{_t(g[0].start)},{_t(g_end)},Cap,,0,0,0,,{{\\an{ran}\\pos({rx},{ry})"
                        f"\\fnInter SemiBold\\fs{fs}\\bord0\\shad{max(1, fs // 16)}\\4c&H90000000&\\fad(80,120)}}{_esc(rest_text)}")
    return rows


def caption_events(words, w: int, h: int, accent: str, skip: set[int] = frozenset()) -> list[str]:
    if CAPTION_MODE == "bracket":
        return bracket_events(words, w, h, accent, skip)
    if CAPTION_MODE == "keyword":
        return keyword_events(words, w, h, accent, skip)
    if CAPTION_MODE == "stack":
        from .stackcaps import stack_events

        return stack_events(words, w, h, accent, skip)
    return pop_events(words, w, h, accent, skip)


def pop_events(words, w: int, h: int, accent: str, skip: set[int] = frozenset()) -> list[str]:
    """One event per spoken word: the phrase stays put, the word being said
    lights up in the accent colour with a small pop, words still to come wait
    slightly dimmed. Highlighted words sit on an accent marker block (drawn
    on a layer below with the same layout), in dark text. Lines in `skip`
    (shown as full-screen cards) get no captions. A card too wide for one row
    breaks into two rows of even length (never one word left alone below)."""
    from .placement import safe_box

    vertical = h > w
    groups = chunks([x for x in words if x.line not in skip], vertical)
    hi = ass_colour(accent)
    dark = "&H00141414&"
    pop = "\\t(0,90,\\fscx112\\fscy112)\\t(90,190,\\fscx100\\fscy100)"
    cap = round((0.062 if vertical else 0.055) * min(w, h))
    L, _, R, _ = safe_box(w, h)
    rows = []
    for g_i, g in enumerate(groups):
        nxt = groups[g_i + 1][0].start if g_i + 1 < len(groups) else None
        g_end = g[-1].end + 0.2
        if nxt is not None:
            g_end = min(g_end, nxt)
        texts = [x.text for x in g]
        lines = [" ".join(texts)]
        if text_width(lines[0], cap, "Inter-ExtraBold.otf") > (R - L) * 0.94 and len(g) >= 2:
            lines = _balanced(texts, 2)
        brk = len(lines[0].split()) if len(lines) > 1 else -1
        bw = max(text_width(x, cap, "Inter-ExtraBold.otf") for x in lines)
        at = _where(g, g_end, bw, cap * 1.2 * len(lines), w, h)
        place = f"\\an{at[0]}\\pos({at[1]},{at[2]})" if at else ""
        for i, word in enumerate(g):
            s0 = word.start
            e = g[i + 1].start if i + 1 < len(g) else g_end
            if e - s0 < 0.02:
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
                sp = " " if j and x.mark and g[j - 1].mark and j != brk else ""
                box.append(f"{{\\1a&HFF&\\3c{hi}{show}{anim}}}{sp}{t}{{\\r}}")
            enter = f"{{\\fad(80,0){place}}}" if i == 0 else (f"{{{place}}}" if place else "")
            joined_top = "".join(("\\N" if j == brk else " " if j else "") + x for j, x in enumerate(top))
            rows.append(f"Dialogue: 2,{_t(s0)},{_t(e)},Cap,,0,0,0,,{enter}{joined_top}")
            if any(x.mark for x in g):
                joined = box[0] + "".join(("\\N" if j == brk else "" if g[j].mark and g[j - 1].mark else " ") + b for j, b in enumerate(box[1:], 1))
                rows.append(f"Dialogue: 1,{_t(s0)},{_t(e)},CapBox,,0,0,0,,{enter}{joined}")
    return rows


def text_width(text: str, size: float, font: str = "InterDisplay-Black.otf") -> float:
    """How wide libass will set `text` at `size` (it scales a font so its
    ascent plus descent equals the size)."""
    try:
        from PIL import ImageFont

        fam = next((k for k, v in FONT_FILES.items() if v == font), None)
        mine = KIT_FILES.get(FONT_MAP.get(fam, "")) if fam else None
        f = ImageFont.truetype(str(mine or (FONTS / font)), 200)
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
    "chapter": "documentary chapter: a small spaced label over a serif title rising slowly, a hairline drawing out ('Part one|The night shift')",
    "place": "travel arrival: the place in huge condensed capitals tracking in, the country by hand across it, coordinates typed below ('Lisbon|Portugal|38.72 N, 9.14 W')",
}


def fit_lines(text: str, size: float, max_w: float, max_lines: int = 2) -> tuple[list[str], float]:
    """Break `text` into balanced lines no wider than max_w, shrinking the
    type (to 60% at most) rather than ever running off the frame."""
    words = text.split()
    for _ in range(12):
        for n in range(1, max_lines + 1):
            lines = _balanced(words, n)
            if max(text_width(x, size) for x in lines) <= max_w:
                return lines, size
        size *= 0.92
    return _balanced(words, max_lines), size


def _balanced(words: list[str], n: int) -> list[str]:
    """Split words into n lines of similar length."""
    if n <= 1 or len(words) <= 1:
        return [" ".join(words)]
    total = sum(len(x) + 1 for x in words)
    lines, cur, target = [], [], total / n
    for x in words:
        if cur and sum(len(y) + 1 for y in cur) + len(x) / 2 > target and len(lines) < n - 1:
            lines.append(" ".join(cur))
            cur = []
        cur.append(x)
    return lines + [" ".join(cur)]


def title_events(text: str, w: int, h: int, accent: str, start: float, end: float, centre: bool,
                 kind: str = "track") -> list[str]:
    """A motion title in one of TITLE_STYLES; long titles wrap to two lines
    and shrink a little rather than run off the frame."""
    if kind in ("chapter", "place"):
        from . import genre

        return (genre.chapter_title if kind == "chapter" else genre.place_title)(text, w, h, accent, start, end, centre)
    size0 = round((0.085 if h > w else 0.075) * min(w, h))
    lines, size = fit_lines(text, size0, 0.86 * w)
    size = round(size)
    n = len(lines)
    line_h = round(size * 1.2)
    block_h = line_h * n
    cx = w // 2
    y = h // 2 - block_h // 2 - size // 3 if centre else round((0.14 if h > w else 0.11) * h)
    rise = round(0.025 * h)
    ms = int((end - start) * 1000)
    out_fade = min(400, ms // 4)
    bar_w, bar_h = round(0.16 * w if w < h else 0.12 * w), max(6, round(size * 0.11))
    bar_y = y + block_h + round(size * 0.12)
    hi = ass_colour(accent)
    tw = min(w * 0.94, max(text_width(x, size) for x in lines) + size * 0.12)
    x0 = round(cx - tw / 2)
    body = "\\N".join(_esc(x) for x in lines)
    fs = f"\\fs{size}" if size != size0 else ""
    head = f"Dialogue: 3,{_t(start)},{_t(end)},Title,,0,0,0,,"
    rect = lambda bw, bh: f"m 0 0 l {bw} 0 {bw} {bh} 0 {bh}"
    bar = (f"Dialogue: 3,{_t(start + 0.25)},{_t(end)},Title,,0,0,0,,"
           f"{{\\an8\\pos({cx},{bar_y})\\p1\\bord0\\shad0\\1c{hi}\\fscx0\\t(0,450,0.5,\\fscx100)\\fad(0,{out_fade})}}"
           f"{rect(bar_w, bar_h)}{{\\p0}}")
    if kind == "reveal":
        txt = (head + f"{{\\an8\\q2{fs}\\shad0\\clip(0,{y - 4},{w},{y + block_h + 6})\\move({cx},{y + block_h},{cx},{y},0,520)"
               f"\\fad(0,{out_fade})}}{body}")
        return [txt, bar]
    if kind == "type":
        chars = len(text)
        step = max(25, min(70, 900 // max(1, chars)))
        k, parts = 0, []
        for li, line in enumerate(lines):
            if li:
                parts.append("\\N")
            for c in line:
                parts.append(f"{{\\alpha&HFF&\\t({k * step},{k * step + 1},\\alpha&H00&)}}{_esc(c)}")
                k += 1
        txt = head + f"{{\\an8\\q2{fs}\\pos({cx},{y})\\fad(0,{out_fade})}}" + "".join(parts)
        done = k * step
        if n > 1:  # the cursor only rides along a single line; two lines get the accent bar
            return [txt, bar.replace(f"{_t(start + 0.25)}", f"{_t(start + done / 1000)}", 1)]
        cur_w = max(6, round(size * 0.09))
        cursor = (head + f"{{\\an7\\p1\\bord0\\shad0\\1c{hi}\\move({x0 + round(tw / max(1, chars))},{y + round(size * 0.12)},{x0 + round(tw)},{y + round(size * 0.12)},0,{done - step})"
                  f"\\t({done + 300},{done + 400},\\alpha&HFF&)}}{rect(cur_w, round(size * 1.0))}{{\\p0}}")
        return [txt, cursor]
    if kind == "block":
        top, bot = y - round(size * 0.05), y + block_h + round(size * 0.05)
        x1 = x0 + round(tw)
        block = (head + f"{{\\an7\\pos({x0},{top})\\p1\\bord0\\shad0\\1c{hi}\\clip({x0},{top},{x0},{bot})"
                 f"\\t(0,320,0.6,\\clip({x0},{top},{x1},{bot}))\\t(380,700,1.6,\\clip({x1},{top},{x1},{bot}))}}"
                 f"{rect(round(tw), bot - top)}{{\\p0}}")
        txt = (head + f"{{\\an8\\q2{fs}\\pos({cx},{y})\\clip({x0},{top},{x0},{bot})"
               f"\\t(380,700,1.6,\\clip({x0},{top},{x1},{bot}))\\fad(0,{out_fade})}}{body}")
        return [txt, block]
    if kind == "stamp":
        txt = (head + f"{{\\an5\\q2{fs}\\pos({cx},{y + block_h // 2})\\fscx165\\fscy165\\alpha&HFF&"
               f"\\t(0,170,1.8,\\fscx96\\fscy96\\alpha&H00&)\\t(170,300,\\fscx100\\fscy100)\\fad(0,{out_fade})}}{body}")
        return [txt, bar]
    txt = (head + f"{{\\an8\\q2{fs}\\move({cx},{y + rise},{cx},{y},0,650)\\fsp{round(size * 0.22)}\\alpha&HFF&"
           f"\\t(0,650,0.45,\\fsp0\\alpha&H00&)\\fad(0,{out_fade})}}{body}")
    return [txt, bar]


def write_ass(path: Path, w: int, h: int, accent: str, words=None, title: str | None = None,
              end_card: str | None = None, cut_len: float = 0.0, card_len: float = 0.0,
              lower_thirds=(), cards=(), extra_rows=(), skip=frozenset(), title_style: str = "track", extras: bool = True) -> None:
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
    mine = []  # the scenes' own words: each scene's word look goes over these
    if words:
        mine += caption_events(words, w, h, accent, skip={c[3] for c in cards} | set(skip))
    for lt, start in lower_thirds:
        rows += graphics.lower_third_events(lt, start, w, h, accent)
    for ws, start, end, _ in cards:
        mine += graphics.card_events(ws, start, end, w, h, accent)
    mine += list(extra_rows)
    mine = restyle_timed(mine, w, h, accent)
    import os

    if mine and os.environ.get("VENUS_CAPS_OUT"):  # Studio's word mover: the scene's own words on their own, to lift off the picture
        Path(os.environ["VENUS_CAPS_OUT"]).write_text(_fonts_mapped("\n".join(rows + mine) + "\n"), encoding="utf-8")
    if not os.environ.get("VENUS_NO_CAPS"):  # (and the picture without them, to lift them off)
        rows += mine
    from . import genre

    if extras:
        rows += genre.events(w, h, cut_len + card_len, accent)
    if title:
        rows += title_events(title, w, h, accent, 0.1, min(3.0, max(1.5, cut_len - 0.5)), centre=False, kind=title_style)
    if end_card:
        rows += title_events(end_card, w, h, accent, cut_len + 0.15, cut_len + card_len, centre=True, kind=title_style)
    path.write_text(_fonts_mapped("\n".join(rows) + "\n"), encoding="utf-8")


def _fonts_mapped(text: str) -> str:
    for ours, theirs in FONT_MAP.items():  # the creator's fonts, everywhere on screen
        text = text.replace(f",{ours},", f",{theirs},").replace(f"\\fn{ours}\\", f"\\fn{theirs}\\").replace(f"\\fn{ours}}}", f"\\fn{theirs}}}")
    return text


def fonts_dir() -> Path:
    """Venus's fonts, plus the creator's own font files when the kit gives them."""
    if not KIT_FILES:
        return FONTS
    import hashlib
    import os
    import tempfile

    key = hashlib.sha256("|".join(sorted(str(p) for p in KIT_FILES.values())).encode()).hexdigest()[:10]
    d = Path(tempfile.gettempdir()) / f"venus-fonts-{key}"
    d.mkdir(exist_ok=True)
    for f in list(FONTS.glob("*.[ot]tf")) + list(KIT_FILES.values()):
        link = d / Path(f).name
        if not link.exists():
            try:
                os.symlink(Path(f).resolve(), link)
            except OSError:
                import shutil

                shutil.copy2(f, link)
    return d


def ass_filter(path: Path) -> str:
    esc = lambda p: str(p).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")
    return f"subtitles='{esc(path)}':fontsdir='{esc(fonts_dir())}'"
