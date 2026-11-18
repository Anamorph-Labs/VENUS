"""The edit plan: one small JSON file holding every choice behind a cut.

Each cut writes `<out>.plan.json`. The person or their AI edits it (swap a
take, add a cutaway, change the music) and runs `alvenus cut --plan it.json`.
Flags typed on the command line still win over the plan."""

from __future__ import annotations

import json
from pathlib import Path

# plan key -> (command-line dest, how to turn the plan value into the flag value)
_SIMPLE = {
    "script": "script", "out": "out", "aspect": "aspect", "captions": "captions",
    "model": "model", "max_pause": "max_pause", "keep_pauses": "keep_pauses",
    "beat": "beat", "scene_beat": "scene_beat", "music": "music", "music_lufs": "music_lufs",
    "title": "title", "end_card": "end_card", "look": "look", "caption_style": "caption_style", "accent": "accent",
    "transition": "transition", "transition_seconds": "transition_seconds", "preset": "preset", "reframe": "reframe", "noise_db": "noise_db", "min_silence": "min_silence",
}

HELP = (
    "Edit this file and run: alvenus cut --plan THIS_FILE. "
    "picks: {line: take number or \"none\"} overrules the automatic choice (take numbers are in the "
    ".decisions.json file; chosen_now shows what the last cut used). broll: cutaway shots laid over "
    "a line with the voice kept, {line, file, from_second}. Blank values mean off."
)


def load(path: Path) -> dict:
    """Plan file -> argparse defaults."""
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise SystemExit(f"--plan {path}: can't read it ({e})")
    base = path.parent
    d: dict = {}
    for key, dest in _SIMPLE.items():
        if plan.get(key) not in (None, ""):
            d[dest] = plan[key]
    for key in ("script", "out", "music"):
        if key in d:
            d[key] = str((base / d[key]).resolve()) if not Path(d[key]).is_absolute() else d[key]
    if plan.get("takes"):
        takes = plan["takes"] if isinstance(plan["takes"], list) else [plan["takes"]]
        d["takes"] = [t if Path(t).is_absolute() else str((base / t).resolve()) for t in takes]
    if "punch_in" in plan:
        d["no_punch_in"] = not plan["punch_in"]
    d["pick"] = [f"{k}={v}" for k, v in (plan.get("picks") or {}).items()]
    d["lower_third"] = [f"{x['line']}={x['name']}" + (f"|{x['role']}" if x.get("role") else "") for x in plan.get("lower_thirds") or []]
    d["card"] = [str(n) for n in plan.get("cards") or []]
    d["highlight"] = [f"{x['line']}={x['words']}" for x in plan.get("highlights") or []]
    d["broll"] = []
    for b in plan.get("broll") or []:
        f = b["file"] if Path(b["file"]).is_absolute() else str((base / b["file"]).resolve())
        d["broll"].append(f"{b['line']}={f}" + (f"@{b['from_second']}" if b.get("from_second") else ""))
    return d


def _abs(p) -> str:
    return str(Path(p).resolve())


def write(path: Path, a, choices, cutaways) -> None:
    picks = {}
    for p in a.pick or []:
        line, _, take = p.partition("=")
        picks[line.strip()] = take.strip() if take.strip().lower() == "none" else int(take)
    plan = {
        "_how_to_use": HELP,
        # Absolute paths, so the plan works from any folder.
        "script": _abs(a.script), "takes": [_abs(t) for t in a.takes], "out": _abs(a.out),
        "aspect": a.aspect, "captions": bool(a.captions),
        "picks": picks,
        "chosen_now": {str(c.line + 1): (c.take.index if c.take else "none") for c in choices},
        "max_pause": None if a.keep_pauses else a.max_pause, "keep_pauses": bool(a.keep_pauses),
        "beat": a.beat, "scene_beat": a.scene_beat, "punch_in": not a.no_punch_in,
        "broll": [{"line": c.line + 1, "file": str(c.path), "from_second": c.offset} for c in cutaways],
        "lower_thirds": [{"line": int(x.split("=")[0]), "name": x.split("=", 1)[1].split("|")[0],
                          "role": (x.split("|", 1)[1] if "|" in x else "")} for x in getattr(a, "lower_third", None) or []],
        "cards": [int(x) for x in getattr(a, "card", None) or []],
        "highlights": [{"line": int(x.split("=")[0]), "words": x.split("=", 1)[1]} for x in getattr(a, "highlight", None) or []],
        "music": _abs(a.music) if a.music else None, "music_lufs": a.music_lufs,
        "title": a.title, "end_card": a.end_card,
        "look": a.look, "caption_style": a.caption_style, "accent": a.accent,
        "transition": getattr(a, "transition", "cut"), "transition_seconds": getattr(a, "transition_seconds", 0.5),
        "preset": getattr(a, "preset", None), "reframe": getattr(a, "reframe", "auto"),
        "model": a.model,
    }
    path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
