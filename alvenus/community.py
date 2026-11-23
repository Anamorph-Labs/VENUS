"""Venus grows with its users: ideas and add-ons from the community.

Started by Anamorph Labs, built and evolved by the people who use it. How an
idea becomes a Venus feature (the same words appear in CONTRIBUTING.md, the
AI guide, Studio and the GitHub forms):

  1. Anyone, or their AI, writes the idea up with `alvenus suggest`. Venus
     checks it is complete and carries nothing private, then gives a link to
     a filled-in form on GitHub. The person presses submit themselves.
  2. Code never goes into Venus directly. Add-ons (new style packs and story
     recipes, as data files) may be proposed as code, but they land in a
     separate holding area, where automatic security checks run on them.
  3. Anamorph Labs reviews every proposal. The good ones are built into Venus
     by the Venus team, cleanly, even when the proposal came with code.
  4. When an idea ships, its author is thanked on GitHub, by email if they
     asked for it, and by name on the Anamorph Labs site.

Add-ons are data, never code: a JSON file in alvenus/addons/styles (a style
pack) or alvenus/addons/recipes (a story recipe for `alvenus storyboard`).
Venus reads them, checks every value against what it knows, and skips a bad
one with a note instead of failing. Data can't run anything, which is the
point: an add-on can only choose among things Venus already does safely.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from pathlib import Path

REPO = "Anamorph-Labs/Venus"
HOW_IT_WORKS = (
    "How ideas become Venus features: Venus is started by Anamorph Labs and grows with its users. "
    "Ideas are welcome from anyone, written up by them or their AI. Code is never added to Venus directly: "
    "proposals wait in a separate holding area, every one is scanned for security, and Anamorph Labs builds "
    "the good ones into Venus itself. When an idea ships, its author is thanked and credited by name."
)
ADDONS = Path(__file__).parent / "addons"
ADDON_KINDS = ("styles", "recipes")
NOTES: list[str] = []  # add-ons skipped at start-up, and why (shown by `alvenus suggest --addons`)

# ---------------------------------------------------------------- add-ons

STYLE_KEYS = {
    "about": str, "aspect": str, "captions": bool, "caption_style": str, "max_pause": (int, float), "beat": (int, float),
    "scene_beat": (int, float), "look": str, "voice": str, "transition": str, "transition_seconds": (int, float),
    "music_lufs": (int, float), "background": str, "title_style": str, "accent": str, "design": str, "letterbox": (str, int, float, bool),
    "lower_third_style": str, "quote_style": str, "by": str,
}


def style_problems(name: str, p: dict) -> list[str]:
    from .backgrounds import KINDS as BGS
    from .cut import TRANSITIONS
    from .paper import DESIGNS
    from .presets import PRESETS
    from .style import LOOKS, TITLE_STYLES

    out = []
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,30}", name):
        out.append("name: lowercase letters, digits and dashes, 2 to 31 long")
    if name in PRESETS and not PRESETS[name].get("addon"):
        out.append(f"{name!r} is a built-in style; pick a new name")
    for k, v in p.items():
        if k not in STYLE_KEYS:
            out.append(f"{k}: not a style setting (allowed: {', '.join(sorted(STYLE_KEYS))})")
        elif not isinstance(v, STYLE_KEYS[k]) or isinstance(v, bool) and STYLE_KEYS[k] in ((int, float),):
            out.append(f"{k}: wrong kind of value")
    for k in ("about", "by"):
        if not str(p.get(k) or "").strip():
            out.append(f"{k}: required ({'one line on what the style is for' if k == 'about' else 'who made it, for the credit'})")
    allowed = {"look": LOOKS, "transition": TRANSITIONS, "title_style": TITLE_STYLES, "background": BGS, "design": DESIGNS,
               "aspect": ("16:9", "9:16", "1:1", "4:5"), "quote_style": ("card", "verse")}
    for k, opts in allowed.items():
        if p.get(k) is not None and p[k] not in opts:
            out.append(f"{k} {p[k]!r}: choose one of {', '.join(opts)}")
    if p.get("accent") is not None and not re.fullmatch(r"#[0-9A-Fa-f]{6}", str(p["accent"])):
        out.append("accent: a colour like #C8102E")
    for k, lo, hi in (("transition_seconds", 0.05, 3), ("max_pause", 0, 5), ("beat", 0, 3), ("scene_beat", 0, 5), ("music_lufs", -40, -6)):
        if isinstance(p.get(k), (int, float)) and not lo <= p[k] <= hi:
            out.append(f"{k}: between {lo:g} and {hi:g}")
    if len(json.dumps(p)) > 4000:
        out.append("too large for a style pack")
    return out


def recipe_problems(name: str, r: dict) -> list[str]:
    from .brief import RECIPES
    from .story import KINDS

    out = []
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,30}", name):
        out.append("name: lowercase letters, digits and dashes, 2 to 31 long")
    if name in RECIPES and not RECIPES[name].get("addon"):
        out.append(f"{name!r} is a built-in recipe; pick a new name")
    for k in ("about", "by"):
        if not str(r.get(k) or "").strip():
            out.append(f"{k}: required")
    extra = set(r) - {"about", "by", "look", "aspect", "end_card", "beats", "name"}
    if extra:
        out.append(f"not recipe settings: {', '.join(sorted(extra))}")
    beats = r.get("beats")
    if not (isinstance(beats, list) and 3 <= len(beats) <= 14):
        return out + ["beats: a list of 3 to 14 [beat, share, [forms], job]"]
    for i, b in enumerate(beats, 1):
        if not (isinstance(b, list) and len(b) == 4 and isinstance(b[0], str) and isinstance(b[1], (int, float)) and 0 < b[1] <= 1
                and isinstance(b[2], list) and b[2] and all(f in KINDS for f in b[2]) and isinstance(b[3], str) and b[3].strip()):
            out.append(f"beat {i}: [name, share of the length (0 to 1), [scene forms from {', '.join(sorted(KINDS))}], what it must do]")
    names = [b[0] for b in beats if isinstance(b, list) and b]
    if names and (names[0] != "hook" or names[-1] != "payoff"):
        out.append("a recipe starts with a hook beat and ends with a payoff beat")
    return out


def load_addons(base: Path | None = None) -> None:
    """Read the add-on folder into the style packs and story recipes."""
    from .brief import NAMES, RECIPES
    from .presets import PRESETS

    base = base or ADDONS
    for f in sorted((base / "styles").glob("*.json")) if (base / "styles").is_dir() else []:
        try:
            p = json.loads(f.read_text(encoding="utf-8"))
            why = style_problems(f.stem, p) if isinstance(p, dict) else ["not a JSON object"]
        except (OSError, ValueError) as e:
            why = [f"can't read it ({e})"]
        if why:
            NOTES.append(f"style add-on {f.name} skipped: " + "; ".join(why))
            continue
        PRESETS[f.stem] = {**{k: v for k, v in p.items() if k != "by"}, "about": f"{p['about']} (add-on by {p['by']})", "addon": p["by"]}
    for f in sorted((base / "recipes").glob("*.json")) if (base / "recipes").is_dir() else []:
        try:
            r = json.loads(f.read_text(encoding="utf-8"))
            why = recipe_problems(f.stem, r) if isinstance(r, dict) else ["not a JSON object"]
        except (OSError, ValueError) as e:
            why = [f"can't read it ({e})"]
        if why:
            NOTES.append(f"recipe add-on {f.name} skipped: " + "; ".join(why))
            continue
        RECIPES[f.stem] = {"about": f"{r['about']} (add-on by {r['by']})", "look": r.get("look", "explainer"),
                           "aspect": r.get("aspect", "16:9"), "end_card": r.get("end_card"), "addon": r["by"],
                           "beats": [(b[0], float(b[1]), tuple(b[2]), b[3]) for b in r["beats"]]}
        NAMES.setdefault(f.stem, r.get("name") or f.stem.replace("-", " "))


# ---------------------------------------------------------------- suggestions

FIELDS = {
    "kind": "idea (no code needed) or add-on (a style pack or story recipe file)",
    "title": "the idea in a few words",
    "what": "what Venus would do that it can't today, in plain words",
    "why": "why it makes videos better, for whom",
    "example": "one concrete example: the video, the moment, what you'd see",
    "code": "optional: code or a sketch that shows the idea (we build it ourselves; this only explains it)",
    "addon_file": "for an add-on: the path of the style or recipe JSON file",
    "credit_name": "the name to thank on the Anamorph Labs site (or \"anonymous\")",
    "credit_link": "optional: a link to show with the name (a website or GitHub profile)",
}
NEED = ("kind", "title", "what", "why", "example", "credit_name")

PRIVATE = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "an email address (the form is public; send your email privately instead)"),
    (re.compile(r"\b(sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|xox[abpr]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{30,})"), "a key or token"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "a private key"),
    (re.compile(r"(/Users/|/home/|C:\\\\Users\\\\|C:\\Users\\)[^\s/\\]+"), "a path from your computer (it shows your user name)"),
    (re.compile(r"\b(password|passwd|secret)\s*[:=]\s*\S+", re.I), "a password"),
]


def new_suggestion(idea: str) -> dict:
    s = {"venus_suggestion": 1, "kind": "idea", "title": "", "what": idea, "why": "", "example": "", "code": "",
         "addon_file": "", "credit_name": "", "credit_link": ""}
    s["_how_to_fill"] = FIELDS
    s["_how_it_works"] = HOW_IT_WORKS
    return s


def private_bits(text: str) -> list[str]:
    return [what for rx, what in PRIVATE if rx.search(text)]


def suggestion_problems(s: dict) -> list[str]:
    out = [f"{k}: still empty ({FIELDS[k]})" for k in NEED if not str(s.get(k) or "").strip()]
    if s.get("kind") not in ("idea", "add-on"):
        out.append("kind: idea or add-on")
    if s.get("kind") == "add-on":
        f = Path(str(s.get("addon_file") or ""))
        if not f.is_file():
            out.append("addon_file: the add-on's JSON file, so Venus can check it before you send it")
        else:
            kind = "recipes" if "beats" in f.read_text(encoding="utf-8", errors="replace") else "styles"
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                why = (recipe_problems if kind == "recipes" else style_problems)(f.stem, data)
            except ValueError as e:
                why = [f"not valid JSON ({e})"]
            out += [f"add-on: {w}" for w in why]
    if len(str(s.get("what") or "").split()) > 300:
        out.append("what: keep it under 300 words; one idea per suggestion")
    text = " ".join(str(s.get(k) or "") for k in FIELDS if k not in ("credit_link",))
    out += [f"remove {w}" for w in private_bits(text)]
    return out


def form_link(s: dict) -> tuple[str, str]:
    """(a link that opens the filled-in form, the same text to paste if the link is too long)."""
    template = "share-addon.yml" if s.get("kind") == "add-on" else "suggest-feature.yml"
    body = {"what": s.get("what", ""), "why": s.get("why", ""), "example": s.get("example", ""),
            "code": s.get("code", ""), "credit": (s.get("credit_name", "") + (f" ({s['credit_link']})" if s.get("credit_link") else ""))}
    if s.get("kind") == "add-on" and s.get("addon_file"):
        body["addon"] = Path(s["addon_file"]).read_text(encoding="utf-8", errors="replace")
    q = {"template": template, "title": f"{'Add-on' if s.get('kind') == 'add-on' else 'Idea'}: {s.get('title', '')}", **{k: v for k, v in body.items() if v}}
    url = f"https://github.com/{REPO}/issues/new?" + urllib.parse.urlencode(q, quote_via=urllib.parse.quote)
    paste = "\n\n".join(f"## {k.title()}\n{v}" for k, v in body.items() if v)
    return url, paste
