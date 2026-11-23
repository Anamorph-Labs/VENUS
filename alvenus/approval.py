"""No video before the storyboard is approved.

The creator (or their AI, on the creator's word) approves a storyboard with
`alvenus approve FILE --by NAME`. That writes FILE.approved.json beside it:
who, when, and a fingerprint of the storyboard's content. `alvenus make`
builds only when the fingerprint still matches, so a storyboard changed after
approval has to be shown and approved again. Notes for the AI (keys starting
with "_") don't count as content.

Venus Studio stamps approval itself when the creator presses a build or
preview button there: pressing it is the creator's approval of what is on
screen."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path


def _clean(x):
    if isinstance(x, dict):
        return {k: _clean(v) for k, v in sorted(x.items()) if not str(k).startswith("_")}
    if isinstance(x, list):
        return [_clean(v) for v in x]
    return x


def content(path: Path) -> dict:
    """The storyboard a file describes, as written (before paths are resolved)."""
    from . import nodes as nd

    path = Path(path)
    if nd.is_nodes(path):
        sb = nd.to_storyboard(nd.read(path))
        side = path.with_name("brief.json")
        if sb.get("_idea") and side.exists():  # an idea from Studio: the brief file is where the AI keeps it up to date
            try:
                from .brief import QUESTIONS

                b = json.loads(side.read_text(encoding="utf-8"))
                sb["brief"] = {**(sb.get("brief") or {}), **{k: b[k] for k in QUESTIONS if k in b}}
            except (OSError, ValueError):
                pass
        return sb
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise SystemExit(f"{path}: can't read the storyboard ({e})")


def fingerprint(sb: dict) -> str:
    return hashlib.sha256(json.dumps(_clean(sb), sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def stamp_path(path: Path) -> Path:
    path = Path(path)
    return path.with_name(path.name + ".approved.json") if not path.name.endswith(".json") else path.with_name(path.name[:-5] + ".approved.json")


def approve(path: Path, by: str, note: str = "") -> dict:
    rec = {"approved_by": by, "at": time.strftime("%Y-%m-%d %H:%M"), "fingerprint": fingerprint(content(path))}
    if note:
        rec["note"] = note
    stamp_path(path).write_text(json.dumps(rec, indent=2), encoding="utf-8")
    return rec


def status(path: Path) -> tuple[bool, str]:
    """(approved and unchanged since, a plain sentence saying so)."""
    sp = stamp_path(path)
    if not sp.exists():
        return False, "not approved yet"
    try:
        rec = json.loads(sp.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False, f"{sp.name} can't be read; approve it again"
    if rec.get("fingerprint") != fingerprint(content(path)):
        return False, f"changed since {rec.get('approved_by', 'someone')} approved it at {rec.get('at', '?')}"
    return True, f"approved by {rec.get('approved_by', '?')} at {rec.get('at', '?')}"


def require(path: Path) -> str:
    ok, why = status(path)
    if not ok:
        raise SystemExit(
            f"{Path(path).name}: {why}. Venus makes a video only from an approved storyboard.\n"
            f"  1. alvenus check {path}      (the story check, and a board to show the creator)\n"
            f"  2. show the creator the board and get their yes\n"
            f"  3. alvenus approve {path} --by NAME\n"
            f"  then make it again.")
    return why
