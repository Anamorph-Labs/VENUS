"""The story critic: reads a storyboard before anything is drawn and says,
in plain words, what is weak and how to fix it.

Two levels. "weak" stops the storyboard: it can't be approved until it is
fixed (or the creator says build it anyway). "note" is advice an editor
would give; it never blocks. Each finding names the scene and its beat, so
the AI can fix that one scene and leave the rest.

What it looks for, in the order a viewer meets it:
  hook     the first scene is short, sharp and not a greeting;
  clarity  each scene says one thing and has time to be read;
  turn     something changes in the middle (explainers, stories, ads);
  payoff   the ending says the point to remember and echoes the hook;
  truth    every number on screen is in the brief's facts, with a source;
  rhythm   length close to the brief, no scene too long, forms that vary.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

GRAPHIC = {"text", "stat", "chart", "line_chart", "quote", "timeline", "list", "compare", "title"}
PICTURE = {"clip", "image", "split", "map", "archive"}
GREETINGS = ("welcome", "hi ", "hi,", "hello", "hey ", "hey,", "in this video", "today we", "today i", "let's talk",
             "lets talk", "in today's", "have you ever wondered", "did you know")
CONTRAST = re.compile(r"\b(but|actually|instead|yet|wrong|myth|not|isn't|doesn't|don't|never|until|however|turns out|truth)\b", re.I)
STOP = set("a an the and or but of to in on at for with is are was were be it its this that these those you your we our "
           "i my me they them their he she his her as by from so if than then into out up down over just very more most "
           "can will do does did not no yes".split())


@dataclass
class Finding:
    level: str  # "weak" or "note"
    scene: int  # 1-based; 0 for the whole video
    beat: str
    what: str
    fix: str

    def line(self) -> str:
        where = "whole video" if not self.scene else f"scene {self.scene}" + (f" ({self.beat})" if self.beat else "")
        return f"[{self.level}] {where}: {self.what}. Fix: {self.fix}"


def words_of(sc: dict) -> list[str]:
    """Every word the scene puts on screen."""
    bits = [str(sc.get(k) or "") for k in ("text", "caption", "label", "title", "who", "subtitle", "value", "detail", "tag")]
    bits += [str(x) for x in sc.get("items") or [] if not isinstance(x, (list, tuple))]
    bits += [" ".join(str(y) for y in x) for x in sc.get("items") or [] if isinstance(x, (list, tuple))]
    for side in ("left", "right"):
        s = sc.get(side)
        if isinstance(s, dict):
            bits += [str(s.get("title") or ""), str(s.get("label") or "")] + [str(p) for p in s.get("points") or []]
    bits += [str(b[0]) for b in (sc.get("bars") or []) + (sc.get("points") or []) if isinstance(b, (list, tuple)) and b]
    bits += [str(p.get("label") or "") for p in sc.get("pins") or [] if isinstance(p, dict)]
    if isinstance(sc.get("callout"), dict):
        bits.append(str(sc["callout"].get("label") or ""))
    text = " ".join(bits)
    text = re.sub(r"[*_=]{1,2}", "", text)  # mark-up for the designed looks
    return text.split()


def _content(words: list[str] | str) -> set[str]:
    if isinstance(words, str):
        words = words.split()
    out = set()
    for w in words:
        w = re.sub(r"[^\w%]", "", w.lower())
        if w and w not in STOP and len(w) > 2:
            out.add(w[:-1] if w.endswith("s") and len(w) > 4 else w)
    return out


def empty(sc: dict) -> str | None:
    """What a scene still lacks, or None when it has what its form needs."""
    t = sc.get("type")
    need = {"text": ("text",), "title": ("text",), "stat": ("value",), "chart": ("bars",), "line_chart": ("points",),
            "quote": ("text",), "timeline": ("items",), "list": ("items",), "clip": ("file",), "image": ("file",),
            "archive": ("file",), "map": ("image", "pins")}.get(t, ())
    for k in need:
        if sc.get(k) in (None, "", []):
            return f"no {k} yet"
    if t in ("compare", "split"):
        for side in ("left", "right"):
            s = sc.get(side) or {}
            if not s.get("title" if t == "compare" else "file"):
                return f"no {side} {'title' if t == 'compare' else 'file'} yet"
    return None


def need_seconds(sc: dict) -> float:
    """About how long the scene's words take to read (graphics need a moment more)."""
    n = len(words_of(sc))
    return 0.5 + 0.28 * n + (0.6 if sc.get("type") in ("chart", "line_chart", "timeline", "compare", "list") else 0.0)


_NUM = re.compile(r"(?<![\w#])(\d[\d,]*(?:\.\d+)?)(\s?%|\s?(?:x|km|kg|mph|kmh|hrs?|hours?|years?|min|minutes?|percent|million|billion|k)\b)?", re.I)


def numbers(sc: dict) -> list[str]:
    """Numbers the scene states as facts: values, percentages, measures. A
    bare small count ("3 reasons", "#2") is not a claim, so it is left out."""
    text = " ".join(words_of(sc))
    out = []
    for m in _NUM.finditer(text):
        raw, unit = m.group(1), m.group(2)
        try:
            v = float(raw.replace(",", ""))
        except ValueError:
            continue
        if unit or v > 10:
            out.append(m.group(0).strip())
    if sc.get("type") in ("chart", "line_chart"):
        out += [f"{b[1]:g}" for b in (sc.get("bars") or []) + (sc.get("points") or [])
                if isinstance(b, (list, tuple)) and len(b) > 1 and isinstance(b[1], (int, float))]
    return out


def _norm_num(s: str) -> str:
    s = re.match(r"[\d,.]*", s).group(0).replace(",", "").rstrip(".")
    try:
        return f"{float(s):g}"
    except ValueError:
        return s


def check(sb: dict) -> list[Finding]:
    scenes = sb.get("scenes") or []
    b = sb.get("brief") or {}
    kind = b.get("kind") or ""
    out: list[Finding] = []

    def add(level, i, what, fix):
        beat = scenes[i - 1].get("beat", "") if i else ""
        out.append(Finding(level, i, beat, what, fix))

    if not scenes:
        return [Finding("weak", 0, "", "there are no scenes", "write the scenes")]
    for i, sc in enumerate(scenes, 1):
        if why := empty(sc):
            add("weak", i, f"{why}", f"write it: {sc.get('_job') or 'what this scene is for'}")

    # hook
    first, fw = scenes[0], words_of(scenes[0])
    head = " ".join(fw).lower()
    if any(head.startswith(g.strip()) or g in f" {head}" for g in GREETINGS):
        add("weak", 1, f"it opens with a greeting or a warm-up (\"{' '.join(fw[:5])}...\"); viewers leave in the first two seconds",
            "open on the most surprising claim, number or shot instead")
    if float(first.get("seconds") or 3) > 3.5:
        add("weak", 1, f"the hook lasts {float(first['seconds']):g} s", "keep the first scene under 3 seconds")
    if len(fw) > 10:
        add("weak", 1, f"the hook has {len(fw)} words", "cut it to 7 words or fewer; one sharp line")
    if first.get("type") == "title" and not first.get("file"):
        add("note", 1, "a plain title is a slow way to start", "put the claim or a shot first, the title second")
    if kind == "travel" and first.get("type") not in PICTURE:
        add("note", 1, "a travel reel usually opens on its best shot, before any words", "make the hook a clip")

    # clarity, one idea per scene
    for i, sc in enumerate(scenes, 1):
        w = words_of(sc)
        d = float(sc.get("seconds") or 3)
        if sc.get("type") in ("text", "title", "quote") and sc.get("text"):
            body = re.sub(r"[*_=]", "", str(sc["text"])).strip()
            sentences = [s for s in re.split(r"(?<=[.!?])\s+", body) if s.strip()]
            set_and_turn = (len(sentences) == 2 and len(w) <= 12 and CONTRAST.match(sentences[1].split()[0] if sentences[1].split() else ""))
            if len(sentences) > 1 and sc.get("type") != "quote" and not set_and_turn:  # "It looks empty. But..." is one idea
                add("weak", i, f"it says {len(sentences)} things (\"{sentences[0][:40]}\" and more)",
                    "keep one sentence here; give the next one a scene of its own")
            elif len(w) > 14 and sc.get("type") == "text":
                add("weak", i, f"{len(w)} words is a paragraph, not a line", "cut to about 10 words, or split into two scenes")
        for it in sc.get("items") or []:
            if isinstance(it, str) and len(it.split()) > 7:
                add("note", i, f"the point \"{it[:40]}\" is long for a list", "keep list points to 6 words or fewer")
                break
        need = need_seconds(sc)
        if w and need > d + 0.3:
            add("weak", i, f"{len(w)} words need about {need:.1f} s to read but the scene has {d:g} s",
                f"give it {need:.1f} s or say less")
        if d > 8:
            add("weak", i, f"{d:g} s is long for one scene; attention drops", "split it into two scenes or cut it to 6 s")
        elif i > 1 and d < 1.5:
            add("note", i, f"{d:g} s is a flash", "give it at least 1.5 s unless it is meant as a quick cut")

    # turn
    if kind in ("explainer", "story", "ad"):
        mid = scenes[1:-1]
        turns = lambda sc: sc.get("type") == "compare" or bool(CONTRAST.search(" ".join(words_of(sc))))  # noqa: E731
        for i, sc in enumerate(scenes, 1):
            if sc.get("beat") == "turn" and not empty(sc) and not turns(sc):
                add("weak", i, "the turn doesn't turn: nothing here goes against what the viewer expects",
                    "say what people believe and why it is wrong (\"You'd think... but\"), or show a before and after")
        if not any(turns(sc) for sc in mid):
            add("weak", 0, "nothing changes in the middle: no surprise, no \"but\"",
                "add a turn: what people believe, and why it is wrong, or a before and after")

    # payoff
    last = scenes[-1]
    lw = words_of(last)
    if last.get("type") in ("title",) and kind != "travel":
        add("note", len(scenes), "the video ends on a title, which tells but doesn't land", "end on the line to remember")
    point = str(b.get("point") or "")
    if point:
        pc = _content(point)
        said = max((len(pc & _content(words_of(sc))) for sc in scenes[-2:]), default=0)
        if pc and said < max(1, (len(pc) + 1) // 2):
            add("weak", len(scenes), f"the ending doesn't say the point to remember (\"{point}\")",
                "say it plainly in the last scene, in a few words")
    if kind in ("explainer", "story", "ad") and len(scenes) > 2 and lw:
        if not (_content(fw) & _content(lw)) and not (point and _content(point) & _content(lw)):
            add("note", len(scenes), "the ending doesn't echo the hook", "repeat one word or image from the first scene, so it feels closed")

    # truth
    facts = " ".join(f"{f.get('fact', '')} {f.get('source', '')}" for f in b.get("facts") or [] if isinstance(f, dict))
    known = {_norm_num(m.group(1)) for m in _NUM.finditer(facts + " " + str(b.get("idea") or ""))}
    if "brief" in sb:
        for i, sc in enumerate(scenes, 1):
            for n in numbers(sc):
                if _norm_num(n) not in known:
                    add("weak", i, f"\"{n}\" is not in the brief's facts", "add it to brief.facts with where it comes from, or take it out")
                    break

    # rhythm
    total = sum(float(sc.get("seconds") or 3) for sc in scenes)
    if b.get("seconds"):
        want = float(b["seconds"])
        off = (total - want) / want
        if abs(off) > 0.3:
            add("weak", 0, f"the scenes add up to {total:.0f} s; the brief asks for {want:g} s",
                "cut or add scenes" if off > 0 else "add a scene or give scenes more time")
        elif abs(off) > 0.15:
            add("note", 0, f"{total:.0f} s against {want:g} s asked", "close enough to build, but worth a trim")
    run, prev = 1, None
    for i, sc in enumerate(scenes, 1):
        run = run + 1 if sc.get("type") == prev else 1
        prev = sc.get("type")
        if run == 3 and prev not in PICTURE:  # shots in a row are normal; the same graphic three times is not
            add("note", i, f"three {prev} scenes in a row", "change the form of the middle one")
    if not any(sc.get("type") in PICTURE for sc in scenes):
        g = 0
        for i, sc in enumerate(scenes, 1):
            g = g + 1 if sc.get("type") in GRAPHIC else 0
        # a video of designed scenes only is fine, but say so once
        if len(scenes) > 6 and not sb.get("design") and not str(sb.get("style", "")).startswith(("mono", "vox")):
            add("note", 0, "every scene is type and graphics with no picture", "add a photo or a clip, or use a designed look (mono-editorial, vox-paper)")
    if kind == "travel":
        lens = sorted(float(sc.get("seconds") or 3) for sc in scenes)
        med = lens[len(lens) // 2]
        if not any(sc.get("beat") == "quiet" and float(sc.get("seconds") or 0) >= 1.2 * med for sc in scenes):
            add("note", 0, "no slow shot to breathe before the end", "give one shot near the end about twice the usual length")
        if not any(sc.get("place") or sc.get("type") in ("title", "map") for sc in scenes[:3]):
            add("note", 0, "the viewer doesn't learn where this is in the first scenes", "add the place: a title, a map or a place stamp")

    # beats from the recipe
    beats = [sc.get("beat") for sc in scenes if sc.get("beat")]
    if beats:
        for need in ("hook", "payoff"):
            if need not in beats:
                add("weak", 0, f"the {need} beat is missing", f"keep a {need} scene from the recipe")
    order = {"weak": 0, "note": 1}
    return sorted(out, key=lambda f: (order[f.level], f.scene))


def weak(findings: list[Finding]) -> list[Finding]:
    return [f for f in findings if f.level == "weak"]


def board(sb: dict, findings: list[Finding] | None = None) -> str:
    """The storyboard as a page to show the creator before anything is made:
    the brief, then one row per scene (beat, what is on screen, seconds)."""
    from .story import WHAT

    b = sb.get("brief") or {}
    lines = ["# Storyboard", ""]
    if b:
        lines += [f"**Idea:** {b.get('idea', '')}", ""]
        for k, label in (("audience", "For"), ("point", "The one thing to remember"), ("kind", "Kind"),
                         ("seconds", "Length"), ("aspect", "Shape"), ("mood", "Mood")):
            if b.get(k):
                lines.append(f"- {label}: {b[k]}" + (" s" if k == "seconds" else ""))
        lines.append("")
    total, t = 0.0, 0.0
    lines += ["| # | Beat | Time | On screen | Form |", "|---|---|---|---|---|"]
    for i, sc in enumerate(sb.get("scenes") or [], 1):
        d = float(sc.get("seconds") or 3)
        what = " ".join(words_of(sc)) or (str(sc.get("file") or "").rsplit("/", 1)[-1])
        if sc.get("type") in PICTURE and sc.get("file"):
            what = f"[{str(sc['file']).rsplit('/', 1)[-1]}] " + " ".join(words_of(sc))
        what = what.replace("|", "/")
        lines.append(f"| {i} | {sc.get('beat', '')} | {t:.1f}-{t + d:.1f} s | {what[:90] or '(empty)'} | {WHAT.get(sc.get('type'), sc.get('type'))} |")
        t += d
        total += d
    lines += ["", f"About {total:.0f} seconds" + (f", style {sb['style']}" if sb.get("style") else "") + (f", ends on \"{sb['end_card']}\"" if sb.get("end_card") else "") + ".", ""]
    if findings is not None:
        w = weak(findings)
        n = [f for f in findings if f.level == "note"]
        lines.append("**Story check:** " + ("ready to approve." if not w else f"{len(w)} thing{'s' if len(w) > 1 else ''} to fix first."))
        lines += [f"- {f.line()}" for f in w + n]
        lines.append("")
    return "\n".join(lines)
