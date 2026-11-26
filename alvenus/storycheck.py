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
    code: str = ""  # a short name for the kind of note ("hook-greeting", "repeat"), so Venus can learn which ones a creator keeps
    at: str = ""  # the exact moment ("0:03-0:06")

    def line(self) -> str:
        where = "whole video" if not self.scene else f"scene {self.scene}" + (f" ({self.beat})" if self.beat else "")
        if self.at:
            where += f" at {self.at}"
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
    for k in ("page", "card"):  # words drawn on an editorial page or beside a tilted card
        if isinstance(sc.get(k), dict) and not (k == "page" and sc.get("text")):
            bits += [str(sc[k].get(x) or "") for x in ("text", "label", "note")]
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
            "archive": ("file",), "map": ("image", "pins"), "slam": ("text",), "date": ("text",), "scramble": ("text",)}.get(t, ())
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


def check(sb: dict, learn: bool = True) -> list[Finding]:
    """Read the storyboard the way a good editor does (CRAFT.md). With learn, notes this
    creator has set aside again and again are quieted (taste.py); facts never are."""
    scenes = sb.get("scenes") or []
    b = sb.get("brief") or {}
    kind = b.get("kind") or ""
    out: list[Finding] = []

    starts = [0.0]
    for sc in scenes:
        starts.append(starts[-1] + float(sc.get("seconds") or 3))

    def add(code, level, i, what, fix):
        beat = scenes[i - 1].get("beat", "") if i else ""
        at = f"{clock(starts[i - 1])}-{clock(starts[i])}" if i else ""
        out.append(Finding(level, i, beat, what, fix, code, at))

    if not scenes:
        return [Finding("weak", 0, "", "there are no scenes", "write the scenes", "empty")]
    from . import brand, pictures

    brand.board_findings(sb, add)
    for i, sc in enumerate(scenes, 1):
        if why := empty(sc):
            add("empty", "weak", i, f"{why}", f"write it: {sc.get('_job') or 'what this scene is for'}")
        for f in [sc.get("file")] + [(sc.get(k) or {}).get("file") for k in ("left", "right") if isinstance(sc.get(k), dict)]:
            if pictures.is_picture(f) and (why := pictures.problem(f)):
                add("picture-missing", "weak", i, f"the drawn picture can't be made ({why})", "pick names from: alvenus icons search WORDS")

    # hook
    first, fw = scenes[0], words_of(scenes[0])
    head = " ".join(fw).lower()
    if any(head.startswith(g.strip()) or g in f" {head}" for g in GREETINGS):
        add("hook-greeting", "weak", 1, f"it opens with a greeting or a warm-up (\"{' '.join(fw[:5])}...\"); viewers leave in the first two seconds",
            "open on the most surprising claim, number or shot instead")
    if float(first.get("seconds") or 3) > 3.5:
        add("hook-long", "weak", 1, f"the hook lasts {float(first['seconds']):g} s", "keep the first scene under 3 seconds")
    if len(fw) > 10:
        add("hook-wordy", "weak", 1, f"the hook has {len(fw)} words", "cut it to 7 words or fewer; one sharp line")
    if first.get("type") == "title" and not first.get("file"):
        add("hook-title", "note", 1, "a plain title is a slow way to start", "put the claim or a shot first, the title second")
    # does the hook land? it needs a reason to keep watching: a number, a turn, a question, "you", or a picture
    hook_txt = " ".join(fw)
    pull = (bool(_NUM.search(hook_txt)) or bool(CONTRAST.search(hook_txt)) or "?" in hook_txt
            or bool(re.search(r"\b(you|your)\b", hook_txt, re.I)) or first.get("type") in PICTURE | {"stat"})
    if fw and not pull:
        add("hook-no-pull", "weak", 1, f"the hook states without pulling (\"{' '.join(fw[:7])}\"): no number, no surprise, no question, no \"you\"",
            "give the viewer a reason to stay: a surprising number, a \"but\", a question, or speak to them (\"your phone...\")")
    point = str(b.get("point") or "")
    if len(scenes) > 3 and point and fw:
        pc = _content(point)
        if pc and len(pc & _content(fw)) >= max(2, (len(pc) * 2 + 2) // 3):
            add("hook-gives-away", "note", 1, "the hook already gives away the ending", "keep the answer back: open on the problem or the surprise, pay it off at the end")
    if kind == "travel" and first.get("type") not in PICTURE:
        add("travel-open", "note", 1, "a travel reel usually opens on its best shot, before any words", "make the hook a clip")

    # clarity, one idea per scene
    for i, sc in enumerate(scenes, 1):
        w = words_of(sc)
        d = float(sc.get("seconds") or 3)
        if sc.get("type") in ("text", "title", "quote") and sc.get("text"):
            body = re.sub(r"^\s*#?\d{1,2}[.):]\s+", "", re.sub(r"[*_=]", "", str(sc["text"])).strip())  # "1. " numbers a point
            sentences = [s for s in re.split(r"(?<=[.!?])\s+", body) if s.strip()]
            set_and_turn = (len(sentences) == 2 and len(w) <= 12 and CONTRAST.match(sentences[1].split()[0] if sentences[1].split() else ""))
            if len(sentences) > 1 and sc.get("type") != "quote" and not set_and_turn:  # "It looks empty. But..." is one idea
                add("two-ideas", "weak", i, f"it says {len(sentences)} things (\"{sentences[0][:40]}\" and more)",
                    "keep one sentence here; give the next one a scene of its own")
            elif len(w) > 14 and sc.get("type") == "text":
                add("paragraph", "weak", i, f"{len(w)} words is a paragraph, not a line", "cut to about 10 words, or split into two scenes")
        cap = re.sub(r"[*_=]", "", str(sc.get("caption") or "")).strip()
        if cap and sc.get("type") in PICTURE | {"title"}:  # a picture's caption is one idea too
            parts = [x for x in re.split(r"(?<=[.!?])\s+", cap) if x.strip()]
            if len(parts) > 1 and not (len(parts) == 2 and CONTRAST.match(parts[1].split()[0] if parts[1].split() else "")):
                add("caption-two", "weak", i, f"the caption says {len(parts)} things (\"{parts[0][:40]}\" and more)",
                    "keep one sentence under the picture; give the other a scene of its own")
            elif len(cap.split()) > 12:
                add("caption-long", "note", i, f"a {len(cap.split())}-word caption competes with the picture", "cut it to about 8 words")
        for it in sc.get("items") or []:
            if isinstance(it, str) and len(it.split()) > 7:
                add("list-long", "note", i, f"the point \"{it[:40]}\" is long for a list", "keep list points to 6 words or fewer")
                break
        need = need_seconds(sc)
        if w and need > d + 0.3:
            add("read-time", "weak", i, f"{len(w)} words need about {need:.1f} s to read but the scene has {d:g} s",
                f"give it {need:.1f} s or say less")
        if d > 8:
            add("scene-long", "weak", i, f"{d:g} s is long for one scene; attention drops", "split it into two scenes or cut it to 6 s")
        elif i > 1 and d < 1.5:
            add("flash", "note", i, f"{d:g} s is a flash", "give it at least 1.5 s unless it is meant as a quick cut")

    # turn
    if kind in ("explainer", "story", "ad"):
        mid = scenes[1:-1]
        turns = lambda sc: sc.get("type") == "compare" or bool(CONTRAST.search(" ".join(words_of(sc))))  # noqa: E731
        for i, sc in enumerate(scenes, 1):
            if sc.get("beat") == "turn" and not empty(sc) and not turns(sc):
                add("turn-flat", "weak", i, "the turn doesn't turn: nothing here goes against what the viewer expects",
                    "say what people believe and why it is wrong (\"You'd think... but\"), or show a before and after")
        if not any(turns(sc) for sc in mid):
            add("no-turn", "weak", 0, "nothing changes in the middle: no surprise, no \"but\"",
                "add a turn: what people believe, and why it is wrong, or a before and after")

    # payoff
    last = scenes[-1]
    lw = words_of(last)
    if last.get("type") in ("title",) and kind != "travel":
        add("end-title", "note", len(scenes), "the video ends on a title, which tells but doesn't land", "end on the line to remember")
    point = str(b.get("point") or "")
    if point:
        pc = _content(point)
        said = max((len(pc & _content(words_of(sc))) for sc in scenes[-2:]), default=0)
        if pc and said < max(1, (len(pc) + 1) // 2):
            add("end-no-point", "weak", len(scenes), f"the ending doesn't say the point to remember (\"{point}\")",
                "say it plainly in the last scene, in a few words")
    if lw and len(lw) > 12 and last.get("type") in ("text", "title", "image", "clip"):
        add("end-long", "weak", len(scenes), f"the last line has {len(lw)} words; a payoff people remember is short",
            "say the point in 8 words or fewer")
    if lw and " ".join(lw).rstrip().endswith("?") and kind != "ad":
        add("end-question", "note", len(scenes), "the video ends on a question", "end on the answer; a question at the end feels unfinished")
    if lw and float(last.get("seconds") or 3) < need_seconds(last) + 1.0:
        add("end-short-hold", "note", len(scenes), "the last line leaves no time to sink in", f"hold it about {need_seconds(last) + 1.2:.1f} s")
    if kind in ("explainer", "story", "ad") and len(scenes) > 2 and lw and not _asks_unanswered(scenes, point):
        if not (_content(fw) & _content(lw)) and not (point and _content(point) & _content(lw)):
            add("end-no-echo", "note", len(scenes), "the ending doesn't echo the hook", "repeat one word or image from the first scene, so it feels closed")

    # truth
    facts = " ".join(f"{f.get('fact', '')} {f.get('source', '')}" for f in b.get("facts") or [] if isinstance(f, dict))
    known = {_norm_num(m.group(1)) for m in _NUM.finditer(facts + " " + str(b.get("idea") or ""))}
    if "brief" in sb:
        for i, sc in enumerate(scenes, 1):
            for n in numbers(sc):
                if _norm_num(n) not in known:
                    add("fact", "weak", i, f"\"{n}\" is not in the brief's facts", "add it to brief.facts with where it comes from, or take it out")
                    break

    # rhythm
    total = sum(float(sc.get("seconds") or 3) for sc in scenes)
    if b.get("seconds"):
        want = float(b["seconds"])
        off = (total - want) / want
        if abs(off) > 0.3:
            add("length-off", "weak", 0, f"the scenes add up to {total:.0f} s; the brief asks for {want:g} s",
                "cut or add scenes" if off > 0 else "add a scene or give scenes more time")
        elif abs(off) > 0.15:
            add("length-near", "note", 0, f"{total:.0f} s against {want:g} s asked", "close enough to build, but worth a trim")
    run, prev = 1, None
    for i, sc in enumerate(scenes, 1):
        run = run + 1 if sc.get("type") == prev else 1
        prev = sc.get("type")
        if run == 3 and prev not in PICTURE:  # shots in a row are normal; the same graphic three times is not
            add("same-form", "note", i, f"three {prev} scenes in a row", "change the form of the middle one")
    if not any(sc.get("type") in PICTURE for sc in scenes):
        g = 0
        for i, sc in enumerate(scenes, 1):
            g = g + 1 if sc.get("type") in GRAPHIC else 0
        # a video of designed scenes only is fine, but say so once
        if len(scenes) > 6 and not sb.get("design") and not str(sb.get("style", "")).startswith(("mono", "vox")):
            add("no-picture", "note", 0, "every scene is type and graphics with no picture", "add a photo or a clip, or use a designed look (mono-editorial, vox-paper)")
    if kind == "travel":
        lens = sorted(float(sc.get("seconds") or 3) for sc in scenes)
        med = lens[len(lens) // 2]
        if not any(sc.get("beat") == "quiet" and float(sc.get("seconds") or 0) >= 1.2 * med for sc in scenes):
            add("travel-no-breath", "note", 0, "no slow shot to breathe before the end", "give one shot near the end about twice the usual length")
        if not any(sc.get("place") or sc.get("type") in ("title", "map") for sc in scenes[:3]):
            add("travel-no-place", "note", 0, "the viewer doesn't learn where this is in the first scenes", "add the place: a title, a map or a place stamp")

    # beats from the recipe
    beats = [sc.get("beat") for sc in scenes if sc.get("beat")]
    if beats:
        for need in ("hook", "payoff"):
            if need not in beats:
                add("beat-missing", "weak", 0, f"the {need} beat is missing", f"keep a {need} scene from the recipe")
    craft(sb, scenes, add)
    order = {"weak": 0, "note": 1}
    out = sorted(out, key=lambda f: (order[f.level], f.scene))
    if learn:
        from . import taste

        out = taste.apply(out)
    return out


def clock(t: float) -> str:
    t = max(0.0, t)
    return f"{int(t // 60)}:{int(t % 60):02d}"


def _roots(words) -> set[str]:
    """Content words cut to a rough root, so "sleeping" and "sleep" count as the same idea."""
    out = set()
    for w in _content(words):
        for end in ("ing", "ed", "es", "ly", "s"):
            if w.endswith(end) and len(w) - len(end) >= 3:
                w = w[: -len(end)]
                break
        out.add(w[:-1] if w.endswith("e") and len(w) > 3 else w)  # wake, waking, wakes: one root
    return out


def promise(sb: dict) -> str:
    """The video's promise in one line: what the viewer gets for watching. Every cut serves it."""
    b = sb.get("brief") or {}
    return str(b.get("promise") or b.get("point") or "").strip()


TEASE = re.compile(r"\b(why|how|secret|reason|what happens|the truth|nobody tells)\b", re.I)
COUNT_WORDS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
COUNTED = re.compile(r"\b(\d{1,2}|two|three|four|five|six|seven|eight|nine|ten)\s+(?:\w+\s)?(reasons|ways|things|steps|mistakes|tips|rules|signs|"
                     r"secrets|lessons|myths|questions|habits|tricks|places|facts)\b", re.I)
ORDINAL = re.compile(r"^\s*(#?\d{1,2}[.):]?|first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|one|two|three|four|five|"
                     r"six|seven|eight|nine|ten|number \w+|last|finally)\b", re.I)
CALLBACK = re.compile(r"\b(remember|as we saw|like before|that's why|which is why|this is why|back to)\b", re.I)
ANSWER = re.compile(r"\b(no answer|the answer|answered|replied|so (?:he|she|they|i|we) (?:said|gave|told))\b", re.I)
ASKED = re.compile(r"\b(asked|asks|ask|question|wondered|wants to know)\b", re.I)
AFTER = re.compile(r"^(so|then|after that|afterwards|that's when|because of that|later|in the end)\b", re.I)
PEOPLE = re.compile(r"\b(he|she|him|her|his|they|dad|mum|mom|father|mother|son|daughter|friend|boy|girl|man|woman)\b", re.I)
DANGLING = {"and", "or", "but", "because", "the", "a", "an", "of", "to", "with", "so", "that", "which", "when", "if", "is", "are",
            "was", "your", "my", "our", "their", "for", "into", "than"}
KNOWN_CAPS = {"I", "OK", "TV", "AI", "US", "UK", "USA", "EU", "UN", "CEO", "NASA", "DIY", "FAQ", "PM", "AM", "GPS", "DNA", "PC", "VS",
              "ID", "NYC", "LA", "BC", "AD", "OMG", "FBI", "CIA", "BBC", "CNN", "UFO", "SOS", "IQ", "XL", "XS", "HD", "4K"}


def _line_of(sc: dict) -> str:
    return re.sub(r"[*_=]", "", str(sc.get("text") or sc.get("caption") or "")).strip()


def _asks_unanswered(scenes: list[dict], point: str) -> bool:
    """The opening asks a question and the last two scenes never come back to it."""
    if len(scenes) < 3:
        return False
    hook = " ".join(words_of(scenes[0]))
    if "?" not in hook:
        return False
    back = _roots(hook) | _roots(point)
    return not any(back & _roots(words_of(sc)) for sc in scenes[-2:])


STANDIN = re.compile(r"\b(mock-?ups?|placeholder|dummy|lorem|fake (?:page|site|screen|button))\b", re.I)
OTHERWAY = re.compile(r"\b(or you can|alternatively|another way|or just ask|or ask your)\b", re.I)
PLACE = re.compile(r"\b(?:the )?(?:download|settings|sign[- ]?in|login|home|install|releases?|account) (?:page|button|menu|screen)\b|"
                   r"\bclick (?:the )?\w+ (?:button|link|tab)\b", re.I)
ROUTE = re.compile(r"\b(search|go to|open|visit|type|navigate|www\.|https?://|\.com\b|from the menu|in the menu)", re.I)


def craft(sb: dict, scenes: list[dict], add) -> None:
    """The checks from the craft guide (CRAFT.md) that a storyboard can show before
    anything is made: the promise, the opening paid off, setups paid off, things
    said twice, stretches where nothing changes, and cuts that land mid-thought."""
    n = len(scenes)
    b = sb.get("brief") or {}
    kind = b.get("kind") or ""
    words = [words_of(sc) for sc in scenes]
    roots = [_roots(w) for w in words]
    prom = promise(sb)

    # the opening is paid off
    if _asks_unanswered(scenes, str(b.get("point") or "")):
        add("hook-unanswered", "weak", n, f"the opening asks \"{' '.join(words[0])}\" and the ending never answers it",
            "answer the opening's question in the last scene, in its own words")
    elif n > 2 and TEASE.search(" ".join(words[0])) and not ((roots[0] | _roots(prom)) & (roots[-1] | roots[-2])):
        add("hook-unanswered", "note", n, "the opening promises a why or a how; the ending doesn't come back to it",
            "let the last line answer the opening")

    # setup and payoff: "3 reasons" needs three reasons
    for i, w in enumerate(words, 1):
        m = COUNTED.search(" ".join(w))
        if not m:
            continue
        want = int(m.group(1)) if m.group(1).isdigit() else COUNT_WORDS[m.group(1).lower()]
        if want < 2 or want > 10:
            continue
        rest = scenes[i:]
        listed = max((len(sc.get("items") or []) for sc in rest), default=0)
        numbered = sum(1 for sc in rest if ORDINAL.match(_line_of(sc) or str(sc.get("label") or sc.get("title") or "")))
        got = max(listed, numbered)
        if got and got < want:
            add("setup-unpaid", "weak", i, f"it promises {m.group(0)} but the video gives {got}",
                f"show all {want}, or promise {got}")
        elif not got and len(rest) < want:
            add("setup-unpaid", "weak", i, f"it promises {m.group(0)} but only {len(rest)} scene{'s' if len(rest) != 1 else ''} follow",
                f"give each of the {want} a scene, or promise fewer")
        elif not got:
            add("setup-unpaid", "note", i, f"it promises {m.group(0)}; the viewer can't count them",
                "number them on screen (\"1.\", \"2.\"...) so each one lands")
        break
    for i in range(2, n + 1):
        line = " ".join(words[i - 1])
        if (m := CALLBACK.search(line)) and not (roots[i - 1] - _roots(m.group(0))) & set().union(*roots[: i - 1]):
            add("callback-unset", "note", i, f"\"{m.group(0)}\" points back to something the video never set up",
                "set it up in an earlier scene, or drop the callback")

    # setup before payoff: the big reveal is earned, not spent early; nothing answers a question never asked
    point = str(b.get("point") or "")
    pc = _content(point)
    if pc and n >= 5:
        for i in range(2, max(2, n // 3) + 1):
            if len(pc & _content(words[i - 1])) >= max(2, (len(pc) * 2 + 2) // 3):
                add("payoff-early", "note", i, f"the point (\"{point}\") is already said here, before the setup has earned it",
                    "build to it: set up who, what and why first, and keep the reveal for the end (or open on it only as a deliberate flash-forward)")
                break
    asked = False
    for i in range(1, n + 1):
        line = " ".join(words[i - 1])
        if ANSWER.search(line) and not asked:
            add("answer-unasked", "note", i, f"\"{ANSWER.search(line).group(0)}\" answers a question the video never asked",
                "show the question first (who asks, what), so the answer lands")
            break
        asked = asked or "?" in line or bool(ASKED.search(line))
    if kind in ("story", "narrative", "trailer") and n >= 3 and AFTER.match(_line_of(scenes[0])):
        add("setup-missing", "note", 1, f"the video opens on what happened next (\"{' '.join(_line_of(scenes[0]).split()[:5])}...\")",
            "open on the setup: who, where, what they want; then this")

    # the same people and things look the same: tag them so Venus can check
    pic = [sc for sc in scenes if sc.get("type") in PICTURE and sc.get("file")]
    people = sum(1 for w in words if PEOPLE.search(" ".join(w)))
    if len(pic) >= 3 and people >= 2 and not any(sc.get("cast") for sc in scenes):
        add("cast-untagged", "note", 0, "the story follows people, but no scene says who is in its picture",
            "add \"cast\": [\"name\"] to each picture scene, then run alvenus cast to check each one looks the same throughout")

    # the same shot used twice close together reads as a mistake, not a callback
    t, at = 0.0, []
    for sc in scenes:
        at.append(t)
        t += float(sc.get("seconds") or 3)
    for i, sc in enumerate(scenes):
        f = sc.get("file")
        if not f or sc.get("type") not in PICTURE or sc.get("repeat_ok"):
            continue
        a0 = float(sc.get("from") or 0)
        a1 = a0 + float(sc.get("seconds") or 3)
        for j in range(i - 1, -1, -1):
            if at[i] - at[j] > 8:
                break
            o = scenes[j]
            if o.get("file") != f or o.get("type") not in PICTURE or o.get("repeat_ok"):
                continue
            b0 = float(o.get("from") or 0)
            if j == i - 1 and sc.get("type") == "image":
                continue  # one picture held across two scenes: the "still" note covers it
            if sc.get("type") == "image" or (a0 < b0 + float(o.get("seconds") or 3) and b0 < a1):
                add("repeat-shot", "weak", i + 1, f"the same shot as scene {j + 1}, {at[i] - at[j]:.0f} s earlier",
                    "use another clip, or another part of this one; if it is a deliberate callback, add \"repeat_ok\": true")
                break

    # how-tos: the real place, the real path, other ways kept apart
    if kind == "how-to" or sb.get("how_to"):
        for i, sc in enumerate(scenes, 1):
            line = _line_of(sc)
            if sc.get("placeholder") or STANDIN.search(str(sc.get("file") or "")) or STANDIN.search(line):
                add("stand-in", "note", i, "this shows a stand-in (a mock-up or placeholder), not the real page or button",
                    "record or screenshot the real one the viewer will use; a mock-up only if the real one doesn't exist yet")
            if OTHERWAY.search(line) and not sc.get("alternative"):
                add("other-way-mixed", "note", i, f"\"{OTHERWAY.search(line).group(0)}\" mixes another way into this step",
                    "give it its own scene with \"alternative\": \"Another way\" (it gets a clear label), so the main path stays simple")
        first = next((i for i, sc in enumerate(scenes) if PLACE.search(_line_of(sc))), None)
        if first is not None and not any(ROUTE.search(_line_of(sc)) for sc in scenes[: first + 1]):
            add("no-path", "note", first + 1, f"the viewer is shown \"{PLACE.search(_line_of(scenes[first])).group(0)}\" but not how to get there",
                "show the way there first, as the viewer would go: search, the site, the menu, then this")

    # clarity: who, what
    for i, sc in enumerate(scenes[:2], 1):
        line = _line_of(sc)
        if re.match(r"(he|she|they|his|her|their)\b", line, re.I) and not re.search(r"\b[A-Z][a-z]+\b", line[3:]) \
                and not sc.get("who") and not any(s.get("who") for s in scenes[: i - 1]):
            add("unclear-who", "note", i, f"\"{line.split()[0]}\" opens the video, but the viewer doesn't know who that is yet",
                "name them, or show them first")
            break
    seen = " ".join(str(b.get(k) or "") for k in ("idea", "audience")) + " " + " ".join(
        str(f.get("fact", "")) for f in b.get("facts") or [] if isinstance(f, dict))
    flagged = False
    for i, sc in enumerate(scenes, 1):
        line = _line_of(sc)
        toks = line.split()
        if flagged or sc.get("type") == "title" or not toks or sum(t.isupper() for t in toks) * 2 >= len(toks):
            seen += " " + line
            continue  # a shouted line is styling, not an acronym
        for t in re.findall(r"\b[A-Z][A-Z0-9]{1,5}\b", line):
            if t not in KNOWN_CAPS and t not in seen and not t.isdigit():
                add("unexplained", "note", i, f"the viewer may not know what \"{t}\" means", f"say it in full the first time, or show what {t} is")
                flagged = True
                break
        seen += " " + line

    # repetition: a point made twice when once would do (the last scene may echo the first: that closes the loop)
    said: dict[str, int] = {}
    for i in range(1, n + 1):
        if i == n or len(roots[i - 1]) < 3 or scenes[i - 1].get("beat") == "turn" or CONTRAST.search(" ".join(words[i - 1])):
            continue  # a turn builds on what came before: that is not saying it twice
        for j in range(1, i):
            a, c = roots[j - 1], roots[i - 1]
            if len(a) >= 3 and len(a & c) >= 2 and len(a & c) * 3 >= 2 * min(len(a), len(c)):
                add("repeat", "note", i, f"it says again what scene {j} said (\"{' '.join(words[j - 1][:6])}...\")",
                    "cut one, or make this one go further")
                break
    for i, sc in enumerate(scenes[:-1], 1):
        if sc.get("type") not in ("text", "quote", "stat", "title"):
            continue  # a chart or a map showing the number again is the picture of it, not a repeat
        for x in numbers(sc):
            if re.fullmatch(r"(1[89]|20)\d\d", x):
                continue  # a year
            k = _norm_num(x) + re.sub(r"[\d,.\s]", "", x).lower()
            if k in said and i - said[k] > 1 and float(_norm_num(x) or 0) > 10:
                add("repeat", "note", i, f"\"{x}\" was already said in scene {said[k]}", "say a number once, then build on it")
            said.setdefault(k, i)

    # attention: the same picture held too long
    run, held, start = 0.0, 0, 0
    for i, sc in enumerate(scenes + [{}], 1):
        f = sc.get("file")
        same = i > 1 and f and f == scenes[i - 2].get("file") and sc.get("type") == scenes[i - 2].get("type")
        if same:
            run += float(sc.get("seconds") or 3)
            held += 1
        else:
            if held and run >= 8:
                add("still", "note", start, f"the same shot stays on screen for {run:.0f} s across {held + 1} scenes",
                    "cut to another shot, a closer frame or a graphic in the middle")
            run, held, start = float(sc.get("seconds") or 3), 0, i

    # rhythm: a cut in the middle of a thought
    for i, sc in enumerate(scenes[:-1], 1):
        line = _line_of(sc)
        last = re.sub(r"[^\w']", "", line.split()[-1].lower()) if line.split() else ""
        if last in DANGLING and not line.endswith(("...", "…", ",", ":", "-", "—")):
            add("mid-thought", "weak" if last in ("the", "a", "an", "of", "to") else "note", i,
                f"the cut lands mid-thought (\"...{' '.join(line.split()[-4:])}\")",
                "end the scene on a whole thought, or finish the sentence before the cut")

    # every cut serves the promise
    if prom and n > 3:
        pr = _roots(prom) | _roots(str(b.get("idea") or "")) | _roots(str(b.get("point") or ""))
        for i in range(2, n):
            sc = scenes[i - 1]
            if sc.get("type") in ("text", "quote", "list") and not numbers(sc) and len(roots[i - 1]) >= 4 \
                    and not roots[i - 1] & (pr | roots[i - 2] | roots[i] | _roots(str(b.get("audience") or ""))):
                add("off-promise", "note", i, f"this scene doesn't connect to the promise (\"{prom}\") or to the scenes around it",
                    "tie it to the promise in a word or two, or cut it")


def openings(sb: dict, findings: list[Finding] | None = None, limit: int = 3) -> list[dict]:
    """Up to three better openings, each from the creator's own scenes (nothing new is
    invented), with the reason an editor would give. Offered only when the first
    three seconds are weak. Ordered by what this creator has picked before."""
    scenes = sb.get("scenes") or []
    if findings is None:
        findings = check(sb)
    if len(scenes) < 3 or not any(f.scene == 1 and f.level == "weak" for f in findings):
        return []
    out: list[dict] = []
    used: set[int] = {1}

    def offer(kind: str, i: int, why: str):
        tail = _line_of(scenes[i - 1]).split()
        if i in used or len(out) >= 4 or (tail and re.sub(r"[^\w']", "", tail[-1].lower()) in DANGLING):
            return  # never offer a line that is cut mid-thought
        used.add(i)
        sc = scenes[i - 1]
        line = (f"{sc.get('value')} {sc.get('label') or ''}".strip() if sc.get("type") == "stat" else " ".join(words_of(sc))) \
            or str(sc.get("file") or "").rsplit("/", 1)[-1]
        out.append({"kind": kind, "scene": i, "open_on": line, "why": why})

    for i, sc in enumerate(scenes, 1):
        if i > 1 and (sc.get("type") == "stat" or numbers(sc)) and len(words_of(sc)) <= 10:
            offer("number", i, "a hard number in the first second makes a stranger stop scrolling")
            break
    for i, sc in enumerate(scenes, 1):
        if i > 1 and (sc.get("beat") == "turn" or CONTRAST.search(" ".join(words_of(sc)))) and len(words_of(sc)) <= 12:
            offer("turn", i, "opening on the surprise makes the viewer wait for the why")
            break
    for i, sc in enumerate(scenes, 1):
        if i > 1 and sc.get("type") in PICTURE and sc.get("file"):
            offer("picture", i, "a strong shot is read faster than a sentence; let the words come second")
            break
    if len(scenes) > 3 and words_of(scenes[-1]) and len(words_of(scenes[-1])) <= 10:
        offer("flash-forward", len(scenes), "show the ending first, then how we got there; the viewer stays to see it make sense")
    from . import taste

    out.sort(key=lambda o: -taste.score("opening-" + o["kind"]))
    return out[:limit]


ASK = {
    "hook-greeting": "Would a stranger keep watching past \"{line}\"?",
    "hook-no-pull": "What in the first 3 seconds gives a stranger a reason to stay?",
    "hook-long": "Can the opening say its thing in under 3 seconds?",
    "hook-wordy": "Can the opening be one sharp line?",
    "hook-unanswered": "The opening asks a question: where does the video answer it?",
    "no-turn": "What does the viewer believe at the start that this video proves wrong?",
    "turn-flat": "What is the surprise at {at}?",
    "end-no-point": "What should the viewer remember when it ends, in a few words?",
    "setup-unpaid": "The video promises something at {at}: where is each part delivered?",
    "mid-thought": "Should the cut at {end} wait until the thought is finished?",
    "length-off": "Which scene can go, so the video fits its length?",
    "two-ideas": "Which one idea is scene {scene} about?",
    "fact": "Where does the number at {at} come from?",
}


def question(sb: dict, findings: list[Finding]) -> str:
    """The one question that unlocks the edit: the most important weak point, asked
    plainly and pointed at its moment. Empty when nothing is weak."""
    w = weak(findings)
    if not w:
        return ""
    order = ["empty", "fact", "hook-greeting", "hook-no-pull", "hook-unanswered", "no-turn", "end-no-point", "setup-unpaid",
             "turn-flat", "mid-thought", "hook-long", "hook-wordy", "two-ideas", "length-off"]
    f = min(w, key=lambda x: order.index(x.code) if x.code in order else len(order))
    scenes = sb.get("scenes") or []
    line = " ".join(words_of(scenes[f.scene - 1])[:6]) if f.scene and f.scene <= len(scenes) else ""
    q = ASK.get(f.code)
    if q:
        q = q.format(line=line + ("..." if line else ""), at=f.at or "the start", scene=f.scene, end=(f.at or "").split("-")[-1])
    else:
        q = f"{f.what[0].upper() + f.what[1:]}" + (f" (at {f.at})" if f.at else "") + f". Shall we {f.fix[0].lower() + f.fix[1:]}?"
    return q + (f" (scene {f.scene}, {f.at})" if f.scene and "{at}" not in (ASK.get(f.code) or "") and f.code in ASK else "")


def weak(findings: list[Finding]) -> list[Finding]:
    return [f for f in findings if f.level == "weak"]


def board(sb: dict, findings: list[Finding] | None = None, every: bool = False) -> str:
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
    if prom := promise(sb):
        lines += [f"**The promise:** {prom}", ""]
    total, t = 0.0, 0.0
    lines += ["| # | Beat | Time | On screen | Form |", "|---|---|---|---|---|"]
    for i, sc in enumerate(sb.get("scenes") or [], 1):
        d = float(sc.get("seconds") or 3)
        what = " ".join(words_of(sc)) or (str(sc.get("file") or "").rsplit("/", 1)[-1])
        if sc.get("type") in PICTURE and sc.get("file"):
            f = str(sc["file"])
            what = f"[{'drawn: ' + f if f.startswith(('icon:', 'scene:')) else f.rsplit('/', 1)[-1]}] " + " ".join(words_of(sc))
        what = what.replace("|", "/")
        lines.append(f"| {i} | {sc.get('beat', '')} | {t:.1f}-{t + d:.1f} s | {what[:90] or '(empty)'} | {WHAT.get(sc.get('type'), sc.get('type'))} |")
        t += d
        total += d
    lines += ["", f"About {total:.0f} seconds" + (f", style {sb['style']}" if sb.get("style") else "") + (f", ends on \"{sb['end_card']}\"" if sb.get("end_card") else "") + ".", ""]
    if findings is not None:
        w = weak(findings)
        n = [f for f in findings if f.level == "note"]
        lines.append("**Story check:** " + ("ready to approve." if not w else f"{len(w)} thing{'s' if len(w) > 1 else ''} to fix first."))
        lines.append("")
        for label, ok in glance(sb, findings):
            lines.append(f"- {'✓' if ok else '✗'} {label}")
        lines.append("")
        if q := question(sb, findings):
            lines += [f"**One question:** {q}", ""]
        if ops := openings(sb, findings):
            lines.append("**Better openings to try:**")
            lines += [f"{k}. Open on scene {o['scene']} (\"{o['open_on'][:60]}\"): {o['why']}." for k, o in enumerate(ops, 1)]
            lines.append("")
        first = ["hook-unanswered", "setup-unpaid", "mid-thought", "repeat", "unexplained", "unclear-who", "callback-unset", "still",
                 "off-promise", "end-no-echo", "hook-gives-away", "hook-title"]
        n = sorted(n, key=lambda f: first.index(f.code) if f.code in first else len(first))
        shown = n if every else sorted(n[:3], key=lambda f: f.scene)  # stay quiet unless a note makes the video clearly better
        lines += [f"- {f.line()}" for f in w + shown]
        if len(n) > len(shown):
            lines.append(f"- and {len(n) - len(shown)} smaller note{'s' if len(n) - len(shown) > 1 else ''} (alvenus check FILE --all)")
        if aside := sorted({f.code for f in findings if f.level == "quiet"}):
            lines.append(f"- left as you usually like it: {', '.join(aside)} (alvenus taste)")
        lines.append("")
    return "\n".join(lines)


def glance(sb: dict, findings: list[Finding]) -> list[tuple[str, bool]]:
    """The story at a glance, for the creator: the four things a good editor asks."""
    n = len(sb.get("scenes") or [])
    w = weak(findings)

    def bad(test) -> bool:
        return any(test(f) for f in w)

    return [
        ("The hook makes you stay (first 3 seconds)", not bad(lambda f: f.scene == 1)),
        ("One idea per scene", not bad(lambda f: "says" in f.what and "things" in f.what or "paragraph" in f.what)),
        ("Something turns in the middle", not bad(lambda f: "turn" in f.what or "nothing changes" in f.what)),
        ("The ending lands the point", not bad(lambda f: f.scene == n and n > 1 or "payoff" in f.what)),
    ]
