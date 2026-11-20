"""Talk: a talking-head cut laid out like a produced show.

On some lines the speaker stays full frame; on others the picture opens up
into a designed set: the speaker in a framed window on one side, and on the
other the line's words arriving as they are said, or its graphic (a number
counting up, a chart, a quote, a timeline) drawn beside them. The face never
leaves the screen, so a number or a chart no longer interrupts the person.
Tall frames (9:16, 4:5) stack the window over the words instead.

A director picks the layout of each line from the story (graphics and marked
lines open up; the hook and the last line stay on the face; long runs of the
face get a words panel for rhythm). `--layout LINE=full|side` overrules it.

The set is drawn with Pillow (ink paper, a fine grid, hairlines, a chapter
label); the panel's words and graphics are libass, like every Venus graphic.
"""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

LAYOUTS = ("full", "side")
SETS = ("dark", "paper")  # ink set, or light grey editorial paper with ink type
# panel colours on the paper set: white type -> ink, light greys -> the kit's muted tones
PAPER_COLOURS = {"&H00FFFFFF": "&H001D2022", "&H00F4F2EE": "&H001D2022", "&H00E6E6E6": "&H0050585E",
                 "&H00E7DED9": "&H00B5C1C9", "&H00C8C8C8": "&H0078838C", "&H00D0D0D0": "&H0078838C"}
INK = (19, 20, 23)
_STOP = set("a an and are as at be but by can could do does did for from has have he her his i if in into is it its "
            "just me my no not of on or our out she so than that the their them then there they this to too up us very "
            "was we were what when where which who will with would you your about over under because right back".split())


def parse_layouts(items: list[str], n_lines: int) -> dict[int, str]:
    out = {}
    for it in items or []:
        line, _, kind = it.partition("=")
        kind = kind.strip().lower()
        if not line.strip().isdigit() or not 0 < int(line) <= n_lines or kind not in LAYOUTS:
            raise SystemExit(f"--layout {it!r}: use LINE=full or LINE=side, e.g. --layout 3=side")
        out[int(line) - 1] = kind
    return out


def parse_chapters(items: list[str], n_lines: int) -> dict[int, str]:
    out = {}
    for it in items or []:
        line, _, title = it.partition("=")
        if not line.strip().isdigit() or not 0 < int(line) <= n_lines or not title.strip():
            raise SystemExit(f"--chapter {it!r}: use LINE=Title, e.g. --chapter \"3=How it works\"")
        out[int(line) - 1] = title.strip()
    return out


def direct(spans: dict[int, tuple[float, float]], graphic: set[int], wordish: set[int], full: set[int],
           overrides: dict[int, str]) -> dict[int, str]:
    """Each line's layout: "full", "words" (speaker beside the words) or
    "graphic" (speaker beside the line's graphic), with a reason editors
    would give: graphics open up, the hook and the payoff stay on the face,
    and a long run of the face gets a words panel to keep the rhythm."""
    order = sorted(spans)
    out: dict[int, str] = {}
    since, last = 0.0, "full"
    for i, n in enumerate(order):
        t0, t1 = spans[n]
        d = t1 - t0
        if n in overrides:
            k = "full" if overrides[n] == "full" else ("graphic" if n in graphic else "words")
        elif n in full:
            k = "full"
        elif n in graphic:
            k = "graphic"
        elif i == 0 or i == len(order) - 1:
            k = "full"
        elif n in wordish:
            k = "words"
        elif since >= 5.0 and d >= 1.8 and last == "full":
            k = "words"
        else:
            k = "full"
        out[n] = k
        since = 0.0 if k != "full" else since + d
        last = k
    return out


def why(kind: str, n: int, graphic: set[int], wordish: set[int], overrides: dict[int, str], first: bool, last: bool) -> str:
    if n in overrides:
        return "you asked for it"
    if kind == "graphic":
        return "its graphic sits beside the speaker, so the face stays on screen"
    if kind == "words":
        return "a marked line: its key words land beside the speaker" if n in wordish else \
            "the face had held the screen a while; the words beside it reset attention"
    if first:
        return "the hook stays on the face"
    if last:
        return "the last line stays on the face"
    return "the face carries it"


def geometry(w: int, h: int, flip: bool = False) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int], bool]:
    """(speaker window, panel, side by side?) as (x, y, width, height), all even."""
    a, b, side = _geometry(w, h, flip)
    ev = lambda r: tuple(2 * round(v / 2) for v in r)
    return ev(a), ev(b), side


def _geometry(w: int, h: int, flip: bool):
    if w / h >= 1.2:
        m, top = round(0.055 * w), round(0.13 * h)
        fh = h - top - round(0.11 * h)
        fw = round(fh * 0.92)
        gap = round(0.05 * w)
        pw = w - 2 * m - fw - gap
        if flip:
            return (w - m - fw, top, fw, fh), (m, top, pw, fh), True
        return (m, top, fw, fh), (m + fw + gap, top, pw, fh), True
    m, top = round(0.06 * w), round(0.09 * h)
    fw = w - 2 * m
    fh = round(fw * (1.0 if h / w > 1.5 else 0.72))
    py = top + fh + round(0.035 * h)
    return (m, top, fw, fh), (m, py, fw, h - py - round(0.07 * h)), False


def _rgb(hex_rgb: str) -> tuple[int, int, int]:
    s = hex_rgb.lstrip("#")
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


def set_image(w: int, h: int, flip: bool, accent: str, label: str = "", number: str = "", out: Path | None = None,
              theme: str = "dark"):
    """The designed set behind the window and the panel: ink paper with a
    soft light from the window side, a fine grid, hairlines top and bottom,
    a chapter label and number, the window's shadow and a thin edge."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter, ImageFont

    from .style import FONTS

    (fx, fy, fw, fh), (px, py, pw, ph), _ = geometry(w, h, flip)
    u = min(w, h)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cx, cy = fx + fw / 2, fy + fh / 2
    r = np.sqrt(((xx - cx) / w) ** 2 + ((yy - cy) / h) ** 2)
    lift = np.clip(1 - r * 1.4, 0, 1) ** 2 * 14
    paper = theme == "paper"
    if paper:
        from .paper import paper_base

        img = paper_base("mono", w, h).convert("RGBA")
        ink = (29, 32, 34)
    else:
        base = np.stack([INK[0] + lift, INK[1] + lift, INK[2] + lift * 1.1], -1)
        img = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8)).convert("RGBA")
        ink = (255, 255, 255)
    grid = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    g = ImageDraw.Draw(grid)
    step = round(u * 0.05)
    for x in range(step // 2, w, step):
        g.line([(x, 0), (x, h)], fill=ink + ((12 if paper else 7),))
    for y in range(step // 2, h, step):
        g.line([(0, y), (w, y)], fill=ink + ((12 if paper else 7),))
    img = Image.alpha_composite(img, grid)
    m = round(0.055 * w) if w / h >= 1.2 else round(0.06 * w)
    over = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    hair = ink + ((90 if paper else 40),)
    low = max(fy + fh, py + ph)
    ty, by = round(fy * 0.62), h - round((h - low) * 0.45)
    d.line([(m, ty), (w - m, ty)], fill=hair, width=max(1, round(u * 0.0012)))
    d.line([(m, by), (w - m, by)], fill=hair, width=max(1, round(u * 0.0012)))
    fs = max(12, round(u * 0.021))
    try:
        mono = ImageFont.truetype(str(FONTS / "DMMono-Regular.ttf"), fs)
    except OSError:
        mono = ImageFont.load_default()
    a = _rgb(accent)
    dot = round(fs * 0.45)
    ly = ty - round(fs * 1.6)
    if label:
        d.rectangle([m, ly + round(fs * 0.3), m + dot, ly + round(fs * 0.3) + dot], fill=a + (255,))
        d.text((m + dot * 2.4, ly), label.upper(), font=mono, fill=(34, 32, 29, 255) if paper else (214, 210, 202, 255))
    if number:
        tw = d.textlength(number, font=mono)
        d.text((w - m - tw, ly), number, font=mono, fill=(110, 103, 94, 255) if paper else (150, 146, 140, 255))
    # a short accent rule where the panel begins
    d.rectangle([px, py, px + round(min(pw, ph) * 0.09), py + max(3, round(u * 0.005))], fill=a + (255,))
    img = Image.alpha_composite(img, over)
    # the window's shadow, then a thin light edge
    rad = round(u * 0.028)
    sh = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([fx + rad // 3, fy + rad // 2, fx + fw + rad // 3, fy + fh + rad], rad, fill=(0, 0, 0, 80 if paper else 170))
    img = Image.alpha_composite(img, sh.filter(ImageFilter.GaussianBlur(rad * 0.9)))
    edge = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    e = max(2, round(u * 0.002))
    ImageDraw.Draw(edge).rounded_rectangle([fx - e, fy - e, fx + fw + e - 1, fy + fh + e - 1], rad + e, fill=ink + ((40 if paper else 34),))
    img = Image.alpha_composite(img, edge)
    img = img.convert("RGB")
    if out:
        img.save(out)
    return img


def window_mask(fw: int, fh: int, u: int, out: Path) -> Path:
    from PIL import Image, ImageDraw

    m = Image.new("L", (fw, fh), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, fw - 1, fh - 1], round(u * 0.028), fill=255)
    m.save(out)
    return out


def key_words(words, emphasis: set[str]) -> set[str]:
    """The one or two words a panel should make big: the creator's marks,
    else a number, else the longest words that carry meaning."""
    keys = [re.sub(r"[^\w%']", "", x.text.lower()) for x in words]
    if emphasis:
        return {k for k in keys if k in emphasis}
    marked = {k for x, k in zip(words, keys) if x.mark}
    if marked:
        return marked
    nums = [k for k in keys if re.search(r"\d", k)]
    if nums:
        return set(nums[:1])
    content = sorted({k for k in keys if k not in _STOP and len(k) >= 4}, key=len, reverse=True)
    return set(content[:1 if len(keys) < 7 else 2])


def panel_words(words, t0: float, t1: float, pw: int, ph: int, accent: str, emphasis: set[str],
                ink: str = "&H00F4F2EE&") -> list[str]:
    """The line's words set in the panel, each arriving as it is said (out of
    a soft blur); the key words in an elegant serif italic, larger and in the
    accent colour, the rest in a heavy sans. Times are from the panel's start."""
    from .style import _esc, _t, ass_colour, text_width

    hi = ass_colour(accent)
    big = key_words(words, emphasis)
    size = min(pw * 0.125, ph * 0.17)
    for _ in range(14):
        lines, cur, cw = [], [], 0.0
        for wd in words:
            k = re.sub(r"[^\w%']", "", wd.text.lower())
            isbig = k in big
            s = size * (1.3 if isbig else 1.0)
            ww = text_width(wd.text, s, "InstrumentSerif-Italic.ttf" if isbig else "Inter-ExtraBold.otf") + size * 0.26
            if cur and cw + ww > pw * 0.98:
                lines.append(cur)
                cur, cw = [], 0.0
            cur.append((wd, s, isbig))
            cw += ww
        if cur:
            lines.append(cur)
        heights = [max(s for _, s, _ in ln) * 1.08 for ln in lines]
        if sum(heights) <= ph * 0.9 and len(lines) <= 5:
            break
        size *= 0.92
    y = (ph - sum(heights)) / 2 + ph * 0.02
    rows = []
    for ln, hgt in zip(lines, heights):
        y += hgt
        for k, (wd, s, isbig) in enumerate(ln):
            at = max(0.0, wd.start - t0 - 0.04)
            parts = []
            for i, (o, os_, obig) in enumerate(ln):
                face = "\\fnInstrument Serif\\i1" if obig else "\\fnInter ExtraBold\\i0"
                col = f"\\1c{hi}" if obig else f"\\1c{ink}"
                if i == k:
                    parts.append(f"{{{face}\\fs{os_:.0f}{col}\\alpha&HFF&\\blur8\\t(0,220,\\alpha&H00&\\blur0)}}{_esc(o.text)}")
                else:
                    parts.append(f"{{{face}\\fs{os_:.0f}\\alpha&HFF&}}{_esc(o.text)}")
            rows.append(f"Dialogue: 7,{_t(at)},{_t(t1 - t0)},CardText,,0,0,0,,{{\\an1\\q2\\bord0\\shad0\\pos(0,{round(y)})\\fad(0,180)}}"
                        + " ".join(parts))
    return rows


def _shift(rows: list[str], t0: float) -> list[str]:
    """Move ready-made events (drawn for the whole cut) to the panel's own clock."""
    from .style import _t

    def tsec(s: str) -> float:
        hh, mm, ss = s.split(":")
        return int(hh) * 3600 + int(mm) * 60 + float(ss)

    out = []
    for r in rows:
        head, rest = r.split(": ", 1)
        f = rest.split(",", 3)
        f[1], f[2] = _t(max(0.0, tsec(f[1]) - t0)), _t(max(0.0, tsec(f[2]) - t0))
        out.append(head + ": " + ",".join(f))
    return out


def build(base: Path, out: Path, w: int, h: int, fps: float, spans: dict[int, tuple[float, float]], kinds: dict[int, str],
          accent: str, words, graphic_rows, emphasis: dict[int, set[str]], chapters: dict[int, str], label: str,
          breaks: set[int], theme: str = "dark") -> tuple[list[str], list[str], list[str]]:
    """Pre-render each opened-up line's panel and return (ffmpeg input args,
    filter lines, notes) that lay the set, the speaker window and the panel
    over the cut. The filter reads [IN] and writes [talk]; inputs start at
    {FIRST}, filled in by the caller."""
    from . import graphics
    from .media import run
    from .style import ass_filter, write_ass

    lines = [n for n in sorted(kinds) if kinds[n] != "full" and n in spans]
    if not lines:
        return [], [], []
    tmp = out.with_name(out.stem + ".talk")
    tmp.mkdir(exist_ok=True)
    u = min(w, h)
    # chapter label and number for each line, and which side the speaker sits
    chap_of, scene_of, cur, ci, scene = {}, {}, label, 0, 0
    names = [chapters[n] for n in sorted(chapters)]
    for n in sorted(spans):
        if n in chapters:
            cur, ci = chapters[n], ci + 1
        chap_of[n] = (cur, f"{ci:02d} / {len(names):02d}" if names and ci else "")
        scene_of[n] = scene
        if n in breaks:
            scene += 1
    args, parts, notes = [], [], []
    from .reframe import track

    k = 0
    feeds = []
    for n in lines:
        t0, t1 = spans[n]
        flip = scene_of[n] % 2 == 1
        (fx, fy, fw, fh), (px, py, pw, ph), side = geometry(w, h, flip)
        lab, num = chap_of[n]
        bgp = tmp / f"set{n}.png"
        img = set_image(w, h, flip, accent, lab, num, bgp, theme)
        # the panel: its words or its graphic over its own piece of the set
        if kinds[n] == "graphic":
            was = graphics.PANELS
            graphics.PANELS = False
            try:
                rows = _shift(graphic_rows(n, pw, ph), t0)
            finally:
                graphics.PANELS = was
        else:
            ws = [x for x in (words or []) if x.line == n]
            rows = panel_words(ws, t0, t1, pw, ph, accent, emphasis.get(n, set()),
                               "&H001D2022&" if theme == "paper" else "&H00F4F2EE&") if ws else []
        crop = tmp / f"panel{n}.png"
        img.crop((px, py, px + pw, py + ph)).save(crop)
        ass = tmp / f"panel{n}.ass"
        write_ass(ass, pw, ph, accent, extra_rows=rows, cut_len=t1 - t0, extras=False)
        if theme == "paper":
            txt = ass.read_text(encoding="utf-8")
            for a_, b_ in PAPER_COLOURS.items():
                txt = txt.replace(a_, b_)
            ass.write_text(txt, encoding="utf-8")
        pv = tmp / f"panel{n}.mp4"
        run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-loop", "1", "-framerate", f"{fps:g}", "-t", f"{t1 - t0:.3f}", "-i", str(crop),
             "-vf", f"format=yuv420p,{ass_filter(ass)},format=yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
             "-pix_fmt", "yuv420p", str(pv)])
        mask = window_mask(fw, fh, u, tmp / f"mask{fw}x{fh}.png")
        # where the speaker is in the frame, so the window holds the face
        keys = track(base, t0, t1)
        centre = sorted(c for _, c in keys)[len(keys) // 2]
        if w / h > fw / fh:
            ch, cw = h, round(h * fw / fh)
            cx, cy = min(max(0, round(centre * w - cw / 2)), w - cw), 0
        else:
            cw, ch = w, round(w * fh / fw)
            cx, cy = 0, min(max(0, round(0.12 * h)), h - ch)
        args += ["-loop", "1", "-framerate", f"{fps:g}", "-t", f"{t1 + 0.5:.3f}", "-i", str(bgp),
                 "-i", str(pv), "-loop", "1", "-framerate", f"{fps:g}", "-t", f"{t1 + 0.5:.3f}", "-i", str(mask)]
        feeds.append((n, t0, t1, k, (fx, fy, fw, fh), (px, py), (cx, cy, cw, ch), side, flip))
        k += 3
    parts.append(f"[IN]split={len(feeds) + 1}[tk_main]" + "".join(f"[tk_s{j}]" for j in range(len(feeds))))
    v = "tk_main"
    for j, (n, t0, t1, k, (fx, fy, fw, fh), (px, py), (cx, cy, cw, ch), side, flip) in enumerate(feeds):
        en = f"enable='between(t,{t0:.3f},{t1 - 0.001:.3f})'"
        e = f"(clip((t-{t0:.3f})/0.32,0,1))"
        ease = f"(1-(1-{e})*(1-{e})*(1-{e}))"
        dx = round((0.04 if side else 0.0) * w) * (1 if flip else -1)
        dy = 0 if side else round(0.03 * h)
        parts.append(f"[{{FIRST+{k}}}:v]format=yuv420p,setpts=PTS-STARTPTS[tk_bg{j}]")
        parts.append(f"[{v}][tk_bg{j}]overlay=0:0:{en}[tk_a{j}]")
        parts.append(f"[tk_s{j}]trim=start={max(0.0, t0 - 0.1):.3f}:end={t1 + 0.1:.3f},crop={cw}:{ch}:{cx}:{cy},scale={fw}:{fh},setsar=1,format=yuva420p[tk_w{j}]")
        parts.append(f"[{{FIRST+{k + 2}}}:v]format=gray,setpts=PTS-STARTPTS[tk_m{j}]")
        parts.append(f"[tk_w{j}][tk_m{j}]alphamerge[tk_r{j}]")
        parts.append(f"[tk_a{j}][tk_r{j}]overlay=x='{fx}+{dx}*(1-{ease})':y='{fy}+{dy}*(1-{ease})':eval=frame:{en}[tk_b{j}]")
        parts.append(f"[{{FIRST+{k + 1}}}:v]setpts=PTS-STARTPTS+{t0:.3f}/TB[tk_p{j}]")
        pdx = -dx // 2
        parts.append(f"[tk_b{j}][tk_p{j}]overlay=x='{px}+{pdx}*(1-{ease})':y='{py}+{-dy}*(1-{ease})':eval=frame:eof_action=pass:{en}[tk_c{j}]")
        v = f"tk_c{j}"
    parts.append(f"[{v}]null[talk]")
    return args, parts, notes
