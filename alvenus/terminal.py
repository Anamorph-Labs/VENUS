"""Terminal recordings to video.

A how-to often shows commands being typed. Recording the screen gives a blurry,
tiny terminal; a terminal recording keeps every character and when it came, so
Venus can draw the terminal itself, sharp at any size, at the real timing.

It reads:

- macOS `script -r FILE` (the timed typescript, played back by `script -p`);
- asciinema `.cast` files (versions 2 and 3);
- Linux `script --timing=TIMES FILE` (give the timing file with `timing=`);
- a plain typescript with no times (shown at an even typing pace).

Then it plays the bytes through a small terminal (cursor moves, erasing,
colours, wrapping, the alternate screen) and draws each moment in DM Mono, in
a window on the page. Long waits are cut short (`max_wait`), the whole thing
can be sped up (`speed`), and the size of the terminal comes from the
recording, from a `NAME.termsize` file beside it (`stty size` output), or is
given.

Themes: `venus` (ivory on ink, on an ivory page), `paper` (ink on ivory, the
colours in deep blue), `colour` (the terminal's own colours, on ink).

The result is an ordinary clip: use it as a `clip` scene; in a how-to the
screen camera then follows the typing on its own."""

from __future__ import annotations

import json
import re
import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .style import FONTS

IVORY = (244, 241, 234)
INK = (27, 27, 31)
DEEP_BLUE = (43, 74, 120)
WHITE = (255, 255, 255)

# ---------------------------------------------------------------- reading recordings


def _mac(data: bytes) -> list[tuple[float, bytes]] | None:
    """macOS / BSD `script -r`: records of (length u64, seconds u64, microseconds u32, direction u32)."""
    if len(data) < 24:
        return None
    for end in ("<", ">"):
        _, _, _, d = struct.unpack(end + "QQII", data[:24])
        if d == ord("s"):
            break
    else:
        return None
    out, i, t0 = [], 0, None
    while i + 24 <= len(data):
        n, sec, usec, d = struct.unpack(end + "QQII", data[i:i + 24])
        i += 24
        if n > len(data) - i:
            break
        t = sec + usec / 1e6
        t0 = t if t0 is None else t0
        if d == ord("o") and n:
            out.append((t - t0, data[i:i + n]))
        i += n
        if d == ord("e"):
            break
    return out


def _cast(text: str) -> tuple[list[tuple[float, bytes]], dict] | None:
    lines = text.splitlines()
    try:
        head = json.loads(lines[0])
    except (ValueError, IndexError):
        return None
    if not isinstance(head, dict) or "version" not in head:
        return None
    v3 = head.get("version") == 3
    term = head.get("term") or {}
    meta = {"cols": head.get("width") or term.get("cols"), "rows": head.get("height") or term.get("rows"),
            "title": head.get("title")}
    out, t = [], 0.0
    for ln in lines[1:]:
        if not ln.strip() or ln.lstrip().startswith("#"):
            continue
        try:
            e = json.loads(ln)
        except ValueError:
            continue
        t = t + float(e[0]) if v3 else float(e[0])
        if e[1] == "o":
            out.append((t, str(e[2]).encode("utf-8")))
        elif e[1] == "r" and isinstance(e[2], str) and "x" in e[2] and meta["cols"] is None:
            c, r = e[2].split("x")
            meta["cols"], meta["rows"] = int(c), int(r)
    return out, meta


def _linux(data: bytes, timing: str) -> list[tuple[float, bytes]]:
    """util-linux `script --timing`: the typescript starts with a header line; the timing file
    has "delay bytes" lines (classic) or "O delay bytes" lines (advanced)."""
    body = data[data.find(b"\n") + 1:] if data.startswith(b"Script started") else data
    out, t, i = [], 0.0, 0
    for ln in timing.splitlines():
        p = ln.split()
        if len(p) == 2:
            kind, d, n = "O", p[0], p[1]
        elif len(p) >= 3:
            kind, d, n = p[0], p[1], p[2]
        else:
            continue
        try:
            t += float(d)
        except ValueError:
            continue
        if kind == "O":
            k = int(n)
            out.append((t, body[i:i + k]))
            i += k
    return out


def _plain(data: bytes, per_sec: float = 60.0) -> list[tuple[float, bytes]]:
    if data.startswith(b"Script started"):
        data = data[data.find(b"\n") + 1:]
    data = re.sub(rb"\r?\nScript done[^\n]*\n?$", b"", data)
    return [(k / per_sec, data[k:k + 4]) for k in range(0, len(data), 4)]


def read(path: str | Path, timing: str | Path | None = None) -> tuple[list[tuple[float, bytes]], dict]:
    """The recording as (seconds, bytes) of what the terminal printed, and what it says of itself."""
    p = Path(path)
    data = p.read_bytes()
    meta: dict = {"kind": "plain", "cols": None, "rows": None, "title": None}
    if timing:
        ev = _linux(data, Path(timing).read_text(encoding="utf-8", errors="replace"))
        meta["kind"] = "script --timing"
    elif (ev := _mac(data)) is not None:
        meta["kind"] = "script -r"
    else:
        c = _cast(data.decode("utf-8", errors="replace")) if data[:1] == b"{" else None
        if c:
            ev, m = c
            meta.update(m, kind="asciinema")
        else:
            ev = _plain(data)
    size = p.with_suffix(".termsize")
    if meta["cols"] is None and size.exists():
        nums = [int(x) for x in re.findall(r"\d+", size.read_text(encoding="utf-8", errors="replace"))[:2]]
        if len(nums) == 2:
            meta["cols"], meta["rows"] = max(nums), min(nums)  # `stty size` says rows cols; columns are the wider
    return ev, meta


# ---------------------------------------------------------------- the terminal

_BASE = [(0, 0, 0), (205, 49, 49), (13, 188, 121), (229, 229, 16), (36, 114, 200), (188, 63, 188), (17, 168, 205),
         (229, 229, 229), (102, 102, 102), (241, 76, 76), (35, 209, 139), (245, 245, 67), (59, 142, 234),
         (214, 112, 214), (41, 184, 219), (255, 255, 255)]


def _xterm(n: int) -> tuple[int, int, int]:
    if n < 16:
        return _BASE[n]
    if n < 232:
        n -= 16
        lv = [0, 95, 135, 175, 215, 255]
        return lv[n // 36], lv[n // 6 % 6], lv[n % 6]
    g = 8 + (n - 232) * 10
    return g, g, g


@dataclass
class Cell:
    ch: str = " "
    fg: object = None  # None = default, int = palette, tuple = rgb
    bg: object = None
    bold: bool = False
    rev: bool = False


class Screen:
    """Enough of a VT100/xterm for shells, installers and progress bars."""

    def __init__(self, cols: int, rows: int):
        self.cols, self.rows = cols, rows
        self.grid = [[Cell() for _ in range(cols)] for _ in range(rows)]
        self.x = self.y = 0
        self.wrap = False
        self.attr = Cell()
        self.top, self.bot = 0, rows - 1
        self.saved = (0, 0)
        self.show_cursor = True
        self.title = None
        self._main = None
        self._buf = b""
        self._state = "text"
        self._seq = ""

    # the bytes come in pieces; a UTF-8 character or an escape may be split between them
    def feed(self, b: bytes) -> None:
        b = self._buf + b
        cut = len(b)
        for k in range(1, 4):  # keep an unfinished UTF-8 character for next time
            if k <= len(b) and b[-k] & 0xC0 == 0xC0:
                need = 2 if b[-k] & 0xE0 == 0xC0 else 3 if b[-k] & 0xF0 == 0xE0 else 4
                if need > k:
                    cut = len(b) - k
                break
            if k <= len(b) and b[-k] & 0xC0 != 0x80:
                break
        self._buf = b[cut:]
        for ch in b[:cut].decode("utf-8", errors="replace"):
            self._char(ch)

    def _char(self, ch: str) -> None:
        st = self._state
        if st == "text":
            if ch == "\x1b":
                self._state, self._seq = "esc", ""
            elif ch < " " or ch == "\x7f":
                self._control(ch)
            else:
                self._put(ch)
        elif st == "esc":
            if ch == "[":
                self._state = "csi"
            elif ch == "]":
                self._state = "osc"
            elif ch in "()*+":
                self._state = "charset"
            else:
                self._state = "text"
                self._esc(ch)
        elif st == "charset":
            self._state = "text"
        elif st == "csi":
            if "@" <= ch <= "~":
                self._state = "text"
                self._csi(self._seq, ch)
            else:
                self._seq += ch
        elif st == "osc":
            if ch == "\x07" or (ch == "\\" and self._seq.endswith("\x1b")):
                self._state = "text"
                s = self._seq.rstrip("\x1b")
                if s[:2] in ("0;", "2;"):
                    self.title = s[2:] or None
            else:
                self._seq += ch

    def _control(self, ch: str) -> None:
        if ch == "\r":
            self.x, self.wrap = 0, False
        elif ch in "\n\x0b\x0c":
            self._down()
        elif ch == "\b":
            self.x, self.wrap = max(0, self.x - 1), False
        elif ch == "\t":
            self.x = min(self.cols - 1, (self.x // 8 + 1) * 8)

    def _down(self) -> None:
        self.wrap = False
        if self.y == self.bot:
            self._scroll(1)
        elif self.y < self.rows - 1:
            self.y += 1

    def _blank(self) -> Cell:
        return Cell(bg=self.attr.bg)

    def _scroll(self, n: int) -> None:
        for _ in range(n):
            del self.grid[self.top]
            self.grid.insert(self.bot, [self._blank() for _ in range(self.cols)])

    def _scroll_down(self, n: int) -> None:
        for _ in range(n):
            del self.grid[self.bot]
            self.grid.insert(self.top, [self._blank() for _ in range(self.cols)])

    def _put(self, ch: str) -> None:
        if self.wrap:
            self.x = 0
            self._down()
        a = self.attr
        self.grid[self.y][self.x] = Cell(ch, a.fg, a.bg, a.bold, a.rev)
        if self.x == self.cols - 1:
            self.wrap = True  # wrap only when the next character comes (as real terminals do)
        else:
            self.x += 1

    def _esc(self, ch: str) -> None:
        if ch == "7":
            self.saved = (self.x, self.y)
        elif ch == "8":
            self.x, self.y = self.saved
        elif ch == "M":
            if self.y == self.top:
                self._scroll_down(1)
            else:
                self.y = max(0, self.y - 1)
        elif ch == "D":
            self._down()
        elif ch == "E":
            self.x = 0
            self._down()
        elif ch == "c":
            self.__init__(self.cols, self.rows)

    def _csi(self, seq: str, f: str) -> None:
        priv = seq[:1] in "?>=<" and seq[:1] != ""
        body = seq[1:] if priv else seq
        ps = [int(p) if p.isdigit() else None for p in re.split(r"[;:]", body)] if body else []
        n = (ps[0] if ps and ps[0] else 1)
        self.wrap = False if f not in "m" else self.wrap
        if priv:
            if f in "hl" and seq[:1] == "?":
                on = f == "h"
                for p in ps:
                    if p == 25:
                        self.show_cursor = on
                    elif p in (47, 1047, 1049):
                        self._alt(on)
            return
        if f == "A":
            self.y = max(self.top if self.y >= self.top else 0, self.y - n)
        elif f == "B":
            self.y = min(self.bot if self.y <= self.bot else self.rows - 1, self.y + n)
        elif f in "Ca":
            self.x = min(self.cols - 1, self.x + n)
        elif f == "D":
            self.x = max(0, self.x - n)
        elif f == "E":
            self.x, self.y = 0, min(self.rows - 1, self.y + n)
        elif f == "F":
            self.x, self.y = 0, max(0, self.y - n)
        elif f in "G`":
            self.x = min(self.cols - 1, n - 1)
        elif f == "d":
            self.y = min(self.rows - 1, n - 1)
        elif f in "Hf":
            r = ps[0] if ps and ps[0] else 1
            c = ps[1] if len(ps) > 1 and ps[1] else 1
            self.y, self.x = min(self.rows - 1, r - 1), min(self.cols - 1, c - 1)
        elif f == "J":
            m = ps[0] if ps and ps[0] is not None else 0
            rows = range(self.y + 1, self.rows) if m == 0 else range(0, self.y) if m == 1 else range(self.rows)
            for r in rows:
                self.grid[r] = [self._blank() for _ in range(self.cols)]
            if m == 0:
                self._erase(self.y, self.x, self.cols)
            elif m == 1:
                self._erase(self.y, 0, self.x + 1)
        elif f == "K":
            m = ps[0] if ps and ps[0] is not None else 0
            a, b = (self.x, self.cols) if m == 0 else (0, self.x + 1) if m == 1 else (0, self.cols)
            self._erase(self.y, a, b)
        elif f == "X":
            self._erase(self.y, self.x, min(self.cols, self.x + n))
        elif f == "P":
            row = self.grid[self.y]
            del row[self.x:self.x + n]
            row.extend(self._blank() for _ in range(self.cols - len(row)))
        elif f == "@":
            row = self.grid[self.y]
            for _ in range(n):
                row.insert(self.x, self._blank())
            del row[self.cols:]
        elif f in "LM" and self.top <= self.y <= self.bot:
            top = self.top
            self.top = self.y
            (self._scroll_down if f == "L" else self._scroll)(n)
            self.top = top
        elif f == "S":
            self._scroll(n)
        elif f == "T":
            self._scroll_down(n)
        elif f == "r":
            t = ps[0] if ps and ps[0] else 1
            b = ps[1] if len(ps) > 1 and ps[1] else self.rows
            if t < b:
                self.top, self.bot = t - 1, min(self.rows, b) - 1
                self.x = self.y = 0
        elif f == "s":
            self.saved = (self.x, self.y)
        elif f == "u":
            self.x, self.y = self.saved
        elif f == "m":
            self._sgr(ps or [0])

    def _erase(self, r: int, a: int, b: int) -> None:
        for c in range(a, b):
            self.grid[r][c] = self._blank()

    def _alt(self, on: bool) -> None:
        if on and self._main is None:
            self._main = (self.grid, self.x, self.y)
            self.grid = [[Cell() for _ in range(self.cols)] for _ in range(self.rows)]
        elif not on and self._main is not None:
            self.grid, self.x, self.y = self._main
            self._main = None

    def _sgr(self, ps: list) -> None:
        a = self.attr
        i = 0
        while i < len(ps):
            p = ps[i] or 0
            if p == 0:
                self.attr = a = Cell()
            elif p == 1:
                a.bold = True
            elif p == 22:
                a.bold = False
            elif p == 7:
                a.rev = True
            elif p == 27:
                a.rev = False
            elif 30 <= p <= 37:
                a.fg = p - 30
            elif 90 <= p <= 97:
                a.fg = p - 90 + 8
            elif 40 <= p <= 47:
                a.bg = p - 40
            elif 100 <= p <= 107:
                a.bg = p - 100 + 8
            elif p == 39:
                a.fg = None
            elif p == 49:
                a.bg = None
            elif p in (38, 48) and i + 1 < len(ps):
                if ps[i + 1] == 5 and i + 2 < len(ps):
                    c = ps[i + 2] or 0
                    i += 2
                elif ps[i + 1] == 2 and i + 4 < len(ps):
                    c = tuple((v or 0) for v in ps[i + 2:i + 5])
                    i += 4
                else:
                    c = None
                    i += 1
                if p == 38:
                    a.fg = c
                else:
                    a.bg = c
            i += 1

    def text(self) -> str:
        return "\n".join("".join(c.ch for c in row).rstrip() for row in self.grid)


# ---------------------------------------------------------------- drawing

THEMES = {
    "venus": {"page": IVORY, "window": INK, "text": IVORY, "bright": WHITE, "bar": (38, 38, 44), "muted": (150, 147, 140)},
    "paper": {"page": (232, 228, 219), "window": IVORY, "text": INK, "bright": INK, "bar": (226, 222, 212), "muted": (120, 118, 112)},
    "colour": {"page": IVORY, "window": INK, "text": (229, 229, 229), "bright": WHITE, "bar": (38, 38, 44), "muted": (150, 147, 140)},
}


def _colour(theme: str, c, bold: bool, fg: bool) -> tuple[int, int, int] | None:
    th = THEMES[theme]
    if c is None:
        return (th["bright"] if bold else th["text"]) if fg else None
    rgb = c if isinstance(c, tuple) else _xterm(int(c) + (8 if bold and fg and isinstance(c, int) and c < 8 else 0))
    if theme == "colour":
        return rgb
    lum = 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]
    sat = max(rgb) - min(rgb)
    if theme == "paper":  # coloured words in deep blue; greys stay ink
        if not fg:
            return (220, 216, 205) if lum > 40 else None
        return DEEP_BLUE if sat > 60 else INK
    # venus: colours become ivory, a little brighter or dimmer by how light they were
    if not fg:
        return (52, 52, 60) if lum > 40 else None
    if sat < 30 and lum < 120:
        return th["muted"]
    return th["bright"] if (bold or lum > 170) else th["text"]


_FALLBACKS = ("/System/Library/Fonts/Menlo.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
              "C:/Windows/Fonts/consola.ttf", "/System/Library/Fonts/Apple Symbols.ttf")


def _fallback(size: int):
    """A font on this computer for characters DM Mono doesn't have (none is fine: they are drawn or left out)."""
    for f in _FALLBACKS:
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            continue
    return None


_HAS: dict = {}


def _has(font, ch: str) -> bool:
    """Whether the font has its own picture for this character (not the empty box)."""
    k = (id(font), ch)
    if k not in _HAS:
        try:
            m, none = font.getmask(ch), font.getmask("\ue000")  # a private character no font here draws
            _HAS[k] = (m.size, bytes(m)) != (none.size, bytes(none))
        except (OSError, ValueError):
            _HAS[k] = False
    return _HAS[k]


def _shape(d: ImageDraw.ImageDraw, ch: str, x: float, cw: float, chh: int, fill, back=INK) -> bool:
    """Line-drawing and block characters drawn as shapes, so bars and boxes join up in any font."""
    o = ord(ch)
    x0, x1 = int(x), int(x + cw)
    mx, my = int(x + cw / 2), chh // 2
    thin, thick = max(1, int(cw * 0.1)), max(2, int(cw * 0.22))
    if o in (0x2500, 0x2501, 0x2574, 0x2576, 0x2578, 0x257A):  # ─ ━ and half lines
        t = thick if o in (0x2501, 0x2578, 0x257A) else thin
        a = mx if o in (0x2576, 0x257A) else x0
        b = mx if o in (0x2574, 0x2578) else x1
        d.rectangle((a, my - t // 2, b, my - t // 2 + t - 1), fill=fill)
        return True
    if o in (0x2502, 0x2503):  # │ ┃
        t = thick if o == 0x2503 else thin
        d.rectangle((mx - t // 2, 0, mx - t // 2 + t - 1, chh), fill=fill)
        return True
    corners = {0x250C: "rd", 0x2510: "ld", 0x2514: "ru", 0x2518: "lu", 0x251C: "udr", 0x2524: "udl", 0x252C: "lrd",
               0x2534: "lru", 0x253C: "lrud", 0x256D: "rd", 0x256E: "ld", 0x2570: "ru", 0x256F: "lu"}
    if o in corners:
        for k in corners[o]:
            box = {"l": (x0, my, mx, my), "r": (mx, my, x1, my), "u": (mx, 0, mx, my), "d": (mx, my, mx, chh)}[k]
            d.rectangle((box[0] - (thin // 2 if k in "ud" else 0), box[1] - (thin // 2 if k in "lr" else 0),
                         box[2] + (thin - 1 - thin // 2 if k in "ud" else 0), box[3] + (thin - 1 - thin // 2 if k in "lr" else 0)),
                        fill=fill)
        return True
    if o == 0x2588 or 0x2589 <= o <= 0x258F:  # █ and left blocks ▉..▏
        part = 1.0 if o == 0x2588 else (0x2590 - o) / 8
        d.rectangle((x0, 0, int(x + cw * part) - 1 if part < 1 else x1, chh), fill=fill)
        return True
    if 0x2581 <= o <= 0x2587:  # lower blocks ▁..▇
        part = (o - 0x2580) / 8
        d.rectangle((x0, int(chh * (1 - part)), x1, chh), fill=fill)
        return True
    if o == 0x2580:
        d.rectangle((x0, 0, x1, my), fill=fill)
        return True
    if o in (0x2591, 0x2592, 0x2593):  # ░ ▒ ▓ as a softer fill
        k = {0x2591: 0.25, 0x2592: 0.5, 0x2593: 0.75}[o]
        c = tuple(int(f * k + b * (1 - k)) for f, b in zip(fill, back))
        d.rectangle((x0, 0, x1, chh), fill=c)
        return True
    if 0x2800 < o <= 0x28FF:  # braille spinners
        bits = o - 0x2800
        dots = [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2), (0, 3), (1, 3)]
        r = max(1, int(cw * 0.09))
        for k, (cx, cy) in enumerate(dots):
            if bits >> k & 1:
                px, py = x + cw * (0.3 + 0.4 * cx), chh * (0.2 + 0.2 * cy)
                d.ellipse((px - r, py - r, px + r, py + r), fill=fill)
        return True
    return False


class Painter:
    def __init__(self, cols: int, rows: int, w: int, h: int, theme: str = "venus", title: str | None = None,
                 bare: bool = False, font_px: int | None = None):
        if theme not in THEMES:
            raise SystemExit(f"theme is one of {', '.join(THEMES)}")
        self.cols, self.rows, self.w, self.h, self.theme, self.bare = cols, rows, w, h, theme, bare
        th = THEMES[theme]
        margin = 0 if bare else int(min(w, h) * 0.06)
        bar = 0 if bare else int(min(h * 0.045, w * 0.032))
        pad = int(min(w, h) * (0.012 if bare else 0.022))
        avail_w, avail_h = w - 2 * margin - 2 * pad, h - 2 * margin - bar - 2 * pad
        path = FONTS / "DMMono-Regular.ttf"
        size = font_px or 40
        if not font_px:  # the largest font that fits the columns and rows
            probe = ImageFont.truetype(str(path), 100)
            adv = probe.getlength("M") / 100
            size = int(min(avail_w / (cols * adv), avail_h / (rows * 1.32)))
        self.font = ImageFont.truetype(str(path), max(6, size))
        self.cw = self.font.getlength("M")
        self.ch = int(round(size * 1.32))
        self.fallback = _fallback(max(6, size))
        gw, gh = int(self.cw * cols), self.ch * rows
        ww, wh = gw + 2 * pad, gh + 2 * pad + bar
        self.wx, self.wy = (w - ww) // 2, (h - wh) // 2
        self.gx, self.gy = self.wx + pad, self.wy + bar + pad
        self.base = Image.new("RGB", (w, h), th["page"] if not bare else th["window"])
        if not bare:
            r = int(min(w, h) * 0.014)
            shadow = Image.new("L", (w, h), 0)
            ImageDraw.Draw(shadow).rounded_rectangle((self.wx, self.wy + r, self.wx + ww, self.wy + wh + r), r, fill=90)
            shadow = shadow.filter(ImageFilter.GaussianBlur(r * 2))
            self.base.paste((20, 20, 24), (0, 0), shadow)
            d = ImageDraw.Draw(self.base)
            d.rounded_rectangle((self.wx, self.wy, self.wx + ww, self.wy + wh), r, fill=th["window"])
            d.rounded_rectangle((self.wx, self.wy, self.wx + ww, self.wy + bar + r), r, fill=th["bar"])
            d.rectangle((self.wx, self.wy + bar, self.wx + ww, self.wy + bar + r), fill=th["window"])
            dot = bar * 0.22
            for k in range(3):
                cx, cy = self.wx + bar * 0.6 + k * bar * 0.62, self.wy + bar / 2
                d.ellipse((cx - dot, cy - dot, cx + dot, cy + dot), fill=th["muted"])
            self.title_font = ImageFont.truetype(str(path), max(8, int(bar * 0.42)))
            self.bar = bar
            self.ww = ww
        self._title = ""  # not yet drawn
        self._with_title = self.base
        self.set_title(title)
        self._rows: dict = {}

    def set_title(self, title: str | None) -> None:
        if self.bare or (title == self._title and self._title != ""):
            return
        self._title = title
        img = self.base.copy()
        if title:
            d = ImageDraw.Draw(img)
            th = THEMES[self.theme]
            t = title if len(title) < 80 else title[:77] + "..."
            d.text((self.wx + self.ww / 2, self.wy + self.bar / 2), t, font=self.title_font, fill=th["muted"], anchor="mm")
        self._with_title = img

    def _row(self, row: list[Cell]) -> Image.Image:
        key = tuple((c.ch, c.fg, c.bg, c.bold, c.rev) for c in row)
        img = self._rows.get(key)
        if img is not None:
            return img
        th = THEMES[self.theme]
        img = Image.new("RGB", (int(self.cw * self.cols) + 1, self.ch), th["window"])
        d = ImageDraw.Draw(img)
        k = 0
        while k < len(row):  # runs of the same look are drawn together
            c = row[k]
            j = k
            while j < len(row) and (row[j].fg, row[j].bg, row[j].bold, row[j].rev) == (c.fg, c.bg, c.bold, c.rev):
                j += 1
            fg = _colour(self.theme, c.fg, c.bold, True)
            bg = _colour(self.theme, c.bg, False, False)
            if c.rev:
                fg, bg = (bg or th["window"]), fg
            if bg is not None:
                d.rectangle((int(k * self.cw), 0, int(j * self.cw), self.ch), fill=bg)
            for m in range(k, j):  # one by one, so each sits exactly in its column
                if row[m].ch != " " and not _shape(d, row[m].ch, m * self.cw, self.cw, self.ch, fg, bg or th["window"]):
                    font = self.font if _has(self.font, row[m].ch) else self.fallback
                    if font is None or (font is self.fallback and not _has(font, row[m].ch)):
                        continue  # no font here has it: left out rather than an empty box
                    d.text((m * self.cw, self.ch * 0.14), row[m].ch, font=font, fill=fg,
                           stroke_width=1 if c.bold and self.theme == "colour" else 0, stroke_fill=fg)
            k = j
        if len(self._rows) > 4000:
            self._rows.clear()
        self._rows[key] = img
        return img

    def draw(self, s: Screen, cursor: bool) -> np.ndarray:
        img = self._with_title.copy()
        for r, row in enumerate(s.grid):
            if any(c.ch != " " or c.bg is not None or c.rev for c in row):
                img.paste(self._row(row), (self.gx, self.gy + r * self.ch))
        if cursor and s.show_cursor:
            th = THEMES[self.theme]
            x = self.gx + int(min(s.x, s.cols - 1) * self.cw)
            y = self.gy + s.y * self.ch
            ImageDraw.Draw(img).rectangle((x, y + 2, x + int(self.cw) - 1, y + self.ch - 2), fill=th["text"])
            ch = s.grid[s.y][min(s.x, s.cols - 1)].ch
            if ch != " ":
                ImageDraw.Draw(img).text((x, y + self.ch * 0.14), ch, font=self.font, fill=th["window"])
        return np.asarray(img)


# ---------------------------------------------------------------- timing and the clip


_HOME = re.compile(rb"(?:/Users/|/home/|[A-Za-z]:\\\\Users\\\\)([A-Za-z0-9._-]+)")


def private_pairs(events: list[tuple[float, bytes]], hide: list[str] | None = None, keep_home: bool = False) -> list[tuple[bytes, bytes]]:
    """What to swap before drawing. By default the home folder becomes ~ and the account name found
    in it becomes "you" (in a prompt, name@computer becomes you@computer). `hide` adds "TEXT=SHOWN"
    pairs (or "TEXT", shown as ***): names, emails, keys."""
    pairs: list[tuple[bytes, bytes]] = []
    for h in hide or []:
        a, _, b = str(h).partition("=")
        if a:
            pairs.append((a.encode("utf-8"), (b if _ else "***").encode("utf-8")))
    if not keep_home:
        stream = b"".join(b for _, b in events)
        names = {m.group(1) for m in _HOME.finditer(stream)}
        for n in sorted(names, key=len, reverse=True):
            for pre in (b"/Users/", b"/home/"):
                pairs.append((pre + n, b"~"))
            pairs.append((b"C:\\Users\\" + n, b"~"))
            for host in set(re.findall(rb"\b" + re.escape(n) + rb"@([A-Za-z0-9._-]+)", stream)):
                pairs.append((n + b"@" + host, b"you@computer"))
                pairs.append((host, b"computer"))  # the computer's name often carries the owner's too
            pairs.append((n, b"you"))
    return pairs


def scrub(events: list[tuple[float, bytes]], pairs: list[tuple[bytes, bytes]]) -> list[tuple[float, bytes]]:
    """Swap private text across the whole recording, even where it was printed in two pieces.
    Each event keeps its time; a swapped word appears with the piece it finished in."""
    if not pairs or not events:
        return events
    stream = b"".join(b for _, b in events)
    rx = re.compile(b"|".join(re.escape(a) for a, _ in sorted(pairs, key=lambda x: -len(x[0]))))
    swap = dict(pairs)
    ends, n = [], 0
    for _, b in events:
        n += len(b)
        ends.append(n)
    cuts, last = [], 0
    matches = list(rx.finditer(stream))
    built = bytearray()
    for m in matches:
        built += stream[last:m.start()]
        built += swap[m.group(0)]
        cuts.append((m.start(), m.end(), len(built) - len(swap[m.group(0)]), len(built)))
        last = m.end()
    built += stream[last:]

    def moved(i: int) -> int:  # an old position in the new stream (inside a swap: after it)
        sh = 0
        for a, b, na, nb in cuts:
            if i <= a:
                break
            if i < b:
                return nb
            sh = nb - b
        return i + sh

    out, prev = [], 0
    for (t, _), e in zip(events, ends):
        k = moved(e)
        if k > prev:
            out.append((t, bytes(built[prev:k])))
        prev = max(prev, k)
    return out


def retime(events: list[tuple[float, bytes]], speed: float = 1.0, max_wait: float = 1.5,
           start: float = 0.0, end: float | None = None) -> list[tuple[float, bytes]]:
    """Waits longer than max_wait are cut to max_wait; then everything plays `speed` times faster.
    Bytes before `start` are applied at once (the screen is set up as it was)."""
    out, t, last = [], 0.0, None
    for at, b in events:
        if end is not None and at > end:
            break
        if at < start:
            out.append((0.0, b))
            continue
        if last is not None:
            t += min(at - last, max_wait) if max_wait and max_wait > 0 else at - last
        last = at
        out.append((t / max(speed, 0.01), b))
    return out


def render(path: str | Path, out: str | Path, *, size: str = "1920x1080", fps: float = 30, cols: int | None = None,
           rows: int | None = None, theme: str = "venus", speed: float = 1.0, max_wait: float = 1.5,
           hold: float = 2.0, title: str | None = None, bare: bool = False, timing: str | None = None,
           start: float = 0.0, end: float | None = None, lead: float = 0.6,
           hide: list[str] | None = None, keep_home: bool = False) -> dict:
    """Draw the recording as an MP4 clip. Returns what was read and made."""
    from .motion import Writer

    events, meta = read(path, timing)
    events = scrub(events, private_pairs(events, hide, keep_home))
    cols = int(cols or meta.get("cols") or 80)
    rows = int(rows or meta.get("rows") or 24)
    w, h = (int(x) for x in size.lower().split("x"))
    w, h = w // 2 * 2, h // 2 * 2
    ev = retime(events, speed, max_wait, start, end)
    dur = (ev[-1][0] if ev else 0.0) + lead + hold
    s = Screen(cols, rows)
    p = Painter(cols, rows, w, h, theme, title or meta.get("title"), bare)
    wr = Writer(Path(out), w, h, fps)
    n = int(round(dur * fps))
    k, last_change, prev, frame = 0, -10.0, None, None
    try:
        for f in range(n):
            t = f / fps - lead
            moved = False
            while k < len(ev) and ev[k][0] <= t:
                s.feed(ev[k][1])
                k += 1
                moved = True
            if moved:
                last_change = t
                if not title:
                    p.set_title(s.title or meta.get("title"))
            # the cursor stays on while things happen, and blinks when the terminal waits
            on = (t - last_change) < 0.5 or int((t - last_change) * 1.8) % 2 == 0
            state = (moved, on)
            if frame is None or state != prev or moved:
                frame = p.draw(s, on)
            prev = state
            wr.put(frame)
    finally:
        wr.close()
    return {"out": str(out), "read_as": meta["kind"], "cols": cols, "rows": rows, "seconds": round(n / fps, 2),
            "recorded_seconds": round(events[-1][0], 2) if events else 0.0, "frames": n, "screen": s.text()}
