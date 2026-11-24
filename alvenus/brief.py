"""From a typed idea to a storyboard worth building.

Three steps, each a small file the person's own AI fills in and Venus checks:

  1. the brief: the few things a good editor asks before drawing anything
     (who it is for, the one thing to remember, length, shape, kind, mood,
     look, what material there is, where the facts come from);
  2. a storyboard skeleton laid out by a story recipe for that kind of video
     (beats with a job each, sized to the length asked for);
  3. the words and pictures, written by the AI into the skeleton, then
     checked (storycheck.py) and approved (approval.py) before any video
     is made.

Venus never writes the words itself: comprehension and taste in language
come from the person's AI. Venus gives it the questions, the shape and a
critic that says, in plain words, what is weak."""

from __future__ import annotations

import json
from pathlib import Path

ASPECTS = ("16:9", "9:16", "1:1", "4:5")

# what the AI must settle with the creator before a storyboard is written
QUESTIONS: dict[str, str] = {
    "idea": "the idea as the creator typed it, word for word",
    "audience": "who will watch it, in a few words (\"first-year students\", \"people planning a Kyoto trip\")",
    "point": "the ONE thing they should remember afterwards, as one short sentence",
    "promise": "what the video promises the viewer for watching, in one line (\"you'll see why your phone dies in the cold\"); every scene must serve it",
    "kind": "explainer, how-to, travel, story, list or ad",
    "seconds": "how long, in seconds (15 to 90 works best for these shapes)",
    "aspect": "16:9 (YouTube), 9:16 (Reels, Shorts), 1:1 or 4:5",
    "mood": "two or three words for the feel (\"calm, curious\", \"bright, fast\")",
    "look": "a Venus style pack (alvenus presets), or \"any\" to let the recipe choose",
    "material": "footage folders, photos, a song: paths, or \"none\" for a video made only of designed scenes",
    "facts": "every number, date and name the video may state, each with where it comes from; [] when it states none",
}
REQUIRED = ("idea", "audience", "point", "kind", "seconds", "aspect", "mood")

# One recipe per kind: the beats in order. share = part of the length;
# forms = the scene types that suit the beat (first is the default).
RECIPES: dict[str, dict] = {
    "explainer": {
        "about": "Explain one idea: a claim that stops the scroll, the question it raises, two or three steps of the "
                 "answer (one idea each), the turn (the part people get wrong), the proof, and the point to remember.",
        "look": "explainer", "aspect": "16:9", "end_card": "Follow for the next one",
        "beats": [
            ("hook", 0.08, ("text", "stat"), "a short, surprising claim or number, 7 words or fewer, in under 3 seconds"),
            ("question", 0.10, ("title",), "the question the hook raises, as the viewer would ask it"),
            ("step", 0.16, ("list", "chart", "image", "text"), "the first part of the answer: one idea, one picture"),
            ("step", 0.16, ("compare", "line_chart", "image", "text"), "the second part: one idea, a different form from the step before"),
            ("turn", 0.14, ("text", "compare"), "the surprise: what most people believe, and why it is wrong (\"but\", \"actually\")"),
            ("proof", 0.14, ("stat", "chart", "line_chart", "quote"), "one number or source that proves it, taken from the brief's facts"),
            ("payoff", 0.22, ("text",), "the point to remember, said plainly; echo a word from the hook"),
        ],
    },
    "travel": {
        "about": "A travel reel: open on the best moment, then the place, arriving, three to five moments that move "
                 "with the music, one quiet shot to breathe, and a closing line that says what the place felt like.",
        "look": "travel-reel", "aspect": "9:16", "end_card": None,
        "beats": [
            ("hook", 0.08, ("clip",), "the single most striking shot, under 3 seconds, before any title"),
            ("place", 0.12, ("title", "map"), "where and when: the place name (and country, date) over a wide shot or a map"),
            ("arrival", 0.12, ("clip", "image"), "getting there: a train window, a first street, a door opening"),
            ("moment", 0.12, ("clip", "image"), "a moment with people or movement"),
            ("moment", 0.12, ("clip", "image"), "a close detail: food, hands, a sign, texture"),
            ("moment", 0.12, ("clip", "split", "image"), "the place at its best: the view, the crowd, the light"),
            ("quiet", 0.16, ("clip", "image"), "one slow, longer shot to breathe before the end"),
            ("payoff", 0.16, ("text", "clip"), "one closing line over a last shot: what the place felt like, not what it was"),
        ],
    },
    "how-to": {
        "about": "Teach one task: show the result first, what the viewer needs before starting (each thing named is "
                 "explained: what it is and how to get it), then each step on the real screen in the order the viewer "
                 "will do it, and end on it working.",
        "look": "explainer", "aspect": "16:9", "end_card": None,
        "beats": [
            ("hook", 0.10, ("clip", "text"), "the finished result, shown working, in under 3 seconds"),
            ("need", 0.14, ("list", "text"), "what the viewer needs first; each thing named also says what it is and where to get it"),
            ("step", 0.18, ("clip", "image"), "the first step on the real screen, from where the viewer starts (search, site, menu, button)"),
            ("step", 0.18, ("clip", "image"), "the next step, on the real screen, in the viewer's own order"),
            ("step", 0.18, ("clip", "image"), "the last step; another way to do a step goes in its own scene marked \"alternative\""),
            ("payoff", 0.22, ("clip", "text"), "it working on the viewer's screen, and one line on what they can do now"),
        ],
    },
    "story": {
        "about": "A small true story: start in the hardest moment, go back to how it began, rise, then land on what it meant.",
        "look": "cinematic-doc", "aspect": "16:9", "end_card": "Thanks for watching",
        "beats": [
            ("hook", 0.08, ("text", "clip"), "drop the viewer into the hardest moment"),
            ("setup", 0.14, ("title", "image"), "who and where"),
            ("rise", 0.20, ("timeline", "clip", "image"), "how it grew or got worse, in order"),
            ("turn", 0.18, ("quote", "text"), "the moment it changed, in someone's own words if you have them"),
            ("proof", 0.14, ("stat", "image"), "one number or picture that shows how far it came"),
            ("payoff", 0.26, ("text",), "what it meant, in one line"),
        ],
    },
    "list": {
        "about": "A countdown: promise the best item, count down, recap them all.",
        "look": "reels-punchy", "aspect": "9:16", "end_card": "Save this for later",
        "beats": [
            ("hook", 0.10, ("text",), "promise the best item so they wait for it"),
            ("item", 0.13, ("stat", "image"), "#5"), ("item", 0.13, ("stat", "image"), "#4"), ("item", 0.13, ("stat", "image"), "#3"),
            ("item", 0.13, ("stat", "image"), "#2"), ("item", 0.14, ("stat", "image"), "#1, the one you promised"),
            ("payoff", 0.24, ("list",), "all of them again, shortest words, #1 first"),
        ],
    },
    "ad": {
        "about": "A product ad: the viewer's own problem, the product as the fix, proof, one clear action.",
        "look": "hype", "aspect": "9:16", "end_card": "Order today",
        "beats": [
            ("hook", 0.10, ("text",), "the viewer's own problem, as a question"),
            ("product", 0.14, ("title", "image"), "the product's name, shown"),
            ("turn", 0.22, ("compare",), "life without it against life with it"),
            ("proof", 0.16, ("stat",), "one number from the brief's facts"),
            ("step", 0.20, ("list", "image"), "two or three reasons, short"),
            ("payoff", 0.18, ("text",), "the promise, in four words or fewer"),
        ],
    },
}
KINDS = tuple(RECIPES)
NAMES = {"explainer": "explainer", "how-to": "how-to", "travel": "travel reel", "story": "short story", "list": "top-5 list", "ad": "product ad"}


def new(idea: str) -> dict:
    """A brief to fill in: the idea, then every question with what it wants."""
    b = {"venus_brief": 1, "idea": idea}
    b.update({k: "" for k in QUESTIONS if k != "idea"})
    b["facts"] = []
    b["_how_to_fill"] = {k: v for k, v in QUESTIONS.items()}
    b["_next"] = "Ask the creator what you cannot tell from the idea, fill every field, then: alvenus storyboard BRIEF sb.json"
    return b


def problems(b: dict) -> list[str]:
    """What is still missing or unusable in a brief, in plain words."""
    out = []
    for k in REQUIRED:
        if b.get(k) in (None, "", []):
            out.append(f"{k}: still empty ({QUESTIONS[k]})")
    if b.get("kind") and b["kind"] not in RECIPES:
        out.append(f"kind {b['kind']!r}: choose one of {', '.join(KINDS)}")
    try:
        s = float(b.get("seconds") or 0)
        if b.get("seconds") not in (None, "") and not 8 <= s <= 180:
            out.append(f"seconds {s:g}: keep it between 8 and 180")
    except (TypeError, ValueError):
        out.append(f"seconds {b.get('seconds')!r}: a number of seconds")
    if b.get("aspect") and b["aspect"] not in ASPECTS:
        out.append(f"aspect {b['aspect']!r}: choose one of {', '.join(ASPECTS)}")
    point = str(b.get("point") or "")
    if point and len(point.split()) > 16:
        out.append(f"point: {len(point.split())} words; the one thing to remember should fit in about 12")
    if point.count(".") + point.count(";") > 1:
        out.append("point: it holds more than one sentence; keep ONE thing to remember")
    facts = b.get("facts")
    if facts is not None and not isinstance(facts, list):
        out.append("facts: a list of {\"fact\": ..., \"source\": ...}")
    for i, f in enumerate(facts or []):
        if not (isinstance(f, dict) and f.get("fact") and f.get("source")):
            out.append(f"facts[{i + 1}]: needs both \"fact\" and \"source\" (a link, a book, or \"the creator\")")
    if b.get("look") and b["look"] != "any":
        from .presets import PRESETS

        if b["look"] not in PRESETS:
            out.append(f"look {b['look']!r}: choose one of {', '.join(PRESETS)} or \"any\"")
    if b.get("kind") == "travel" and str(b.get("material") or "none").strip().lower() in ("", "none"):
        out.append("material: a travel reel is made of the creator's own footage; give the folder of clips")
    return out


def read(path: Path) -> dict:
    try:
        b = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise SystemExit(f"{path}: can't read the brief ({e})")
    if not isinstance(b, dict) or "venus_brief" not in b:
        raise SystemExit(f"{path}: not a Venus brief (make one with: alvenus brief \"your idea\" {path})")
    return b


def lengths(kind: str, seconds: float) -> list[float]:
    beats = RECIPES[kind]["beats"]
    total = sum(s for _, s, _, _ in beats)
    out = [round(max(1.8, seconds * s / total), 1) for _, s, _, _ in beats]
    out[0] = min(out[0], 2.8)  # the hook is always short
    return out


def _blank(form: str) -> dict:
    """An empty scene of one form, with the fields it needs left blank."""
    return {
        "text": {"text": ""}, "title": {"text": ""}, "stat": {"value": "", "label": ""},
        "chart": {"bars": [], "title": ""}, "line_chart": {"points": [], "title": ""}, "quote": {"text": "", "who": ""},
        "timeline": {"items": [], "title": ""}, "map": {"image": "", "pins": []},
        "list": {"title": "", "items": []}, "compare": {"left": {"title": "", "points": []}, "right": {"title": "", "points": []}},
        "clip": {"file": "", "from": 0, "caption": ""}, "image": {"file": "", "caption": ""},
        "split": {"left": {"file": "", "label": ""}, "right": {"file": "", "label": ""}},
        "slam": {"text": "", "small": ""}, "date": {"text": ""}, "scramble": {"text": "", "to": ""},
    }.get(form, {})


def skeleton(b: dict) -> dict:
    """A storyboard laid out by the brief's recipe: one scene per beat, the
    beat's job written on it, its length set, its words left for the AI."""
    kind = b["kind"]
    r = RECIPES[kind]
    secs = lengths(kind, float(b["seconds"]))
    scenes = []
    for (beat, _, forms, job), d in zip(r["beats"], secs):
        sc = {"type": forms[0], **_blank(forms[0]), "seconds": d, "beat": beat, "_job": job}
        if kind == "travel" and forms[0] in ("title", "text"):
            sc["file"] = ""  # words over one of their shots
        if len(forms) > 1:
            sc["_other_forms"] = list(forms[1:])
        if forms[0] in ("image", "clip") and str(b.get("material") or "none").strip().lower() in ("", "none"):
            sc["type"] = "image"  # no footage: a drawn picture fills the slot
            sc["_picture_hint"] = ("no footage: draw it, \"file\": \"icon:NAME\" (or icon:A+B, icon:A>B>C, icon:A/B, "
                                   "scene:NAME); find names with: alvenus icons search WORDS")
        scenes.append(sc)
    look = b.get("look") if b.get("look") not in (None, "", "any") else r["look"]
    sb = {
        "brief": {k: b.get(k) for k in QUESTIONS},
        "aspect": b.get("aspect") or r["aspect"], "style": look,
        "_how_to_fill": ("Write each scene's words for its beat (the _job says what the beat must do). You may change a "
                         "scene's type to one of _other_forms, or split a beat into two scenes, but keep the beats in "
                         "order. Numbers and dates only from brief.facts. Then: alvenus check sb.json"),
        "scenes": scenes,
    }
    if r.get("end_card"):
        sb["end_card"] = r["end_card"]
    return sb


def describe() -> str:
    return "\n".join(f"  {k:10} {r['about']}" for k, r in RECIPES.items())
