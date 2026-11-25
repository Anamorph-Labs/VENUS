"""The "stack" caption look: one big word, with the rest of the card in small
bold type on one row above it and, when words follow the big one, one row
below. Learned from short-form edits where the line is read at a glance:

    giving                In
    SPACE                 DIFFICULT
         to each                  times

Everything in a card shares one edge (left, centre or right, from where the
card sits) measured on the letters themselves, not their boxes, so the small
rows and the big word line up exactly. Rows sit on a baseline grid, the small
type is a fixed share of the big word, and a row gets smaller before it would
ever wrap. Words pop in as they are said; the big word lands from slightly
larger with a short blur and then holds still, so it never drifts off the edge.

A card is one scene's caption (or one script line): the creator decides where
a card begins and ends, and which word is big ("caption_big", one or more
words in a row)."""

from __future__ import annotations

from functools import lru_cache

BIG_FONT, BIG_FILE = "Inter Display ExtraBold", "InterDisplay-ExtraBold.otf"
SMALL_FONT, SMALL_FILE = "Inter Display", "InterDisplay-Bold.otf"  # drawn bold (\b1)
WHITE = "&H00F6FAFC&"
BIG_FIRST: set[int] = set()  # lines (scenes) whose card opens on the big word, the rest flat under it
SIDE: dict[int, str] = {}  # line -> "above" or "below": every small word on that side of the big word
NUDGE: dict[int, tuple[float, ...]] = {}  # line -> small rows x, y, big word x, y, row above x, y, row below x, y (shares of the frame)
SMALL_SHARE = 0.30  # small type = this share of the big word's size
STEP = 1.16  # baseline to baseline of small rows, in small sizes
GAP = 0.18  # space between a small row and the big word, in small sizes: the rows hug the big word


@lru_cache(maxsize=None)
def _font(file: str):
    from PIL import ImageFont

    from .style import FONTS

    return ImageFont.truetype(str(FONTS / file), 400)


def measure(text: str, size: float, file: str) -> dict:
    """libass-scale metrics of `text` at `size`: advance, ink left/right from
    the pen, cap top / ink bottom from the baseline, ascent."""
    f = _font(file)
    asc, desc = f.getmetrics()
    k = size / (asc + desc)  # libass sets ascent + descent = size
    l, t, r, b = f.getbbox(text, anchor="ls") if text else (0, 0, 0, 0)
    return {"adv": f.getlength(text) * k, "l": l * k, "r": r * k, "top": t * k, "bot": b * k, "asc": asc * k, "k": k}


def _key_range(g) -> tuple[int, int]:
    """The big word(s): the creator's marked run, else the carrying word."""
    marked = [j for j, x in enumerate(g) if getattr(x, "mark", False)]
    if marked:
        a = marked[0]
        b = a
        while b + 1 < len(g) and getattr(g[b + 1], "mark", False):
            b += 1
        return a, b + 1
    from .style import _key_word

    k = _key_word(g)
    return k, k + 1


def _clean(s: str, big: bool = False) -> str:
    """A word as shown: no full stop at the end of a card (a closing quote
    stays); the big word also drops a trailing comma or colon."""
    s = s.strip()
    q = s[-1] if s[-1:] in "\"”’'" else ""
    core = s[:-1] if q else s
    if core.endswith(".") and not core.endswith(".."):
        core = core[:-1]
    if big:
        core = core.rstrip(",;:")
    return core + q


def layout(texts: list[str], k0: int, k1: int, w: int, h: int, max_w: float, big_first: bool = False, side: str | None = None) -> dict:
    """Rows of one card, before it is placed. Returns rows [(word indexes,
    font, size, baseline y)], the card's ink width and height, and per-row ink
    widths. y = 0 is the card's top (cap height of its first row)."""
    big_text = " ".join(texts[k0:k1])
    pre, post = list(range(0, k0)), list(range(k1, len(texts)))
    if big_first or side == "below":
        pre, post = [], pre + post
    elif side == "above":
        pre, post = pre + post, []
    bs = 0.205 * min(w, h) * (1.25 if h > w else 1)
    while bs > 0.08 * min(w, h) and (lambda m: m["r"] - m["l"])(measure(big_text, bs, BIG_FILE)) > max_w:
        bs *= 0.96
    ss = bs * SMALL_SHARE
    ss = max(ss, 0.058 * min(w, h))
    bm = measure(big_text, bs, BIG_FILE)

    big_w = bm["r"] - bm["l"]
    floor = max(ss * 0.75, 0.05 * min(w, h))

    def row_size(idx):  # one row, within the big word's width while it stays easy to read; smaller type before it would ever wrap
        s = ss
        txt = " ".join(texts[i] for i in idx)
        ink = lambda s: (lambda m: m["r"] - m["l"])(measure(txt, s, SMALL_FILE))
        while s * 0.95 >= floor and ink(s) > big_w:
            s *= 0.95
        while s > ss * 0.6 and ink(s) > max_w:
            s *= 0.95
        return s

    rows, y = [], 0.0
    if pre:
        s = row_size(pre)
        m = measure(" ".join(texts[i] for i in pre), s, SMALL_FILE)
        y = -m["top"]
        rows.append((pre, SMALL_FILE, s, y))
        y += GAP * s - bm["top"]
    else:
        y = -bm["top"]
    rows.append(([k0], BIG_FILE, bs, y))  # the big run is drawn as one piece
    bottom = y + (bm["bot"] if any(c in big_text for c in "gjpqy,") else 0)
    if post:
        s = row_size(post)
        m = measure(" ".join(texts[i] for i in post), s, SMALL_FILE)
        y = bottom + GAP * s - m["top"]
        rows.append((post, SMALL_FILE, s, y))
        bottom = y + m["bot"]
    inks = []
    for idx, file, s, _ in rows:
        txt = big_text if file == BIG_FILE else " ".join(texts[i] for i in idx)
        m = measure(txt, s, file)
        inks.append((m["l"], m["r"]))
    width = max(r - l for l, r in inks)
    return {"rows": rows, "inks": inks, "w": width, "h": bottom, "big": big_text}


def stack_events(words, w: int, h: int, accent: str, skip: set[int] = frozenset()) -> list[str]:
    from .placement import safe_box
    from .style import _esc, _t, _where

    ws = [x for x in words if x.line not in skip]
    groups: list[list] = []
    for x in ws:  # a card is one line (a scene's caption): the creator chose where it breaks
        if groups and groups[-1][-1].line == x.line:
            groups[-1].append(x)
        else:
            groups.append([x])
    L, T, R, B = safe_box(w, h)
    max_w = (R - L) * 0.96
    out = []
    for gi, g in enumerate(groups):
        nxt = groups[gi + 1][0].start if gi + 1 < len(groups) else None
        g_end = g[-1].end + 0.6 if nxt is None else min(g[-1].end + 0.6, nxt - 0.02)
        k0, k1 = _key_range(g)
        texts = [_clean(x.text, k0 <= j < k1) for j, x in enumerate(g)]
        lay = layout(texts, k0, k1, w, h, max_w, g[0].line in BIG_FIRST, SIDE.get(g[0].line))
        sx, sy, bx, by, upx, upy, dnx, dny = (tuple(NUDGE.get(g[0].line, ())) + (0.0,) * 8)[:8]
        big_y = next(yb for _, f, _, yb in lay["rows"] if f == BIG_FILE)
        at = _where(g, g_end, lay["w"], lay["h"], w, h)
        if at is None:
            an, ax, ay = 2, w // 2, round(h * (0.7 if h > w else 0.8))
        else:
            an, ax, ay = at
        col, row = (an - 1) % 3, (an - 1) // 3
        top = ay - lay["h"] if row == 0 else ay - lay["h"] / 2 if row == 1 else ay
        x_left = ax if col == 0 else ax - lay["w"] / 2 if col == 1 else ax - lay["w"]
        x_left = min(max(x_left, L), R - lay["w"])
        top = min(max(top, T), B - lay["h"])
        for (idx, file, s, yb), (il, ir) in zip(lay["rows"], lay["inks"]):
            rw = ir - il
            edge = x_left if col == 0 else x_left + (lay["w"] - rw) / 2 if col == 1 else x_left + lay["w"] - rw
            pen = edge - il  # the pen position that puts the ink edge on the card's edge
            big = file == BIG_FILE
            # the creator moved this row on its own: the small row or the big word, by a share of the frame
            part = "big" if big else "above" if yb < big_y else "below"
            dx, dy = (bx * w, by * h) if big else ((sx + upx) * w, (sy + upy) * h) if part == "above" else ((sx + dnx) * w, (sy + dny) * h)
            if dx or dy:  # a moved row still stays inside the frame's safe area
                edge = min(max(edge + dx, L), R - rw)
                dy = min(max(dy, T - top), B - lay["h"] - top) if big else dy
            pen = edge - il
            base = top + yb + dy
            pieces = [(k0, lay["big"])] if big else [(i, texts[i]) for i in idx]
            x = pen
            for n, (i, txt) in enumerate(pieces):
                if n:
                    x += measure(" ", s, file)["adv"]
                m = measure(txt, s, file)
                cx, cy = x + m["adv"] / 2, base - m["asc"] + s / 2  # \an5: the centre of the word's box
                t0 = max(g[0].start, g[i].start - 0.04)
                sh = max(2, round(s * 0.10))
                look = (f"\\bord{sh}\\3c&H000000&\\3a&HA8&\\blur{max(2, round(s * 0.22))}\\shad0\\1c{WHITE}")
                if big:
                    anim = "\\fscx145\\fscy145\\t(0,220,\\fscx97\\fscy97)\\t(220,360,\\fscx100\\fscy100)\\fad(70,140)"
                    font = f"\\fn{BIG_FONT}\\b0"
                else:
                    anim = "\\fscx60\\fscy60\\t(0,170,\\fscx106\\fscy106)\\t(170,260,\\fscx100\\fscy100)\\fad(60,140)"
                    font = f"\\fn{SMALL_FONT}\\b1"
                if t0 < g_end:
                    out.append(f"Dialogue: {3 if big else 2},{_t(t0)},{_t(g_end)},Cap,{part},0,0,0,,"
                               f"{{\\an5\\pos({cx:.1f},{cy:.1f}){font}\\fs{s:.1f}{look}{anim}}}{_esc(txt)}")
                x += m["adv"]
    return out
