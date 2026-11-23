"""What Venus learns about one creator's taste, from what they keep and what they set aside.

Kept only on the creator's computer (VENUS_HOME/taste.json, by default ~/.venus).
Nothing here is ever sent anywhere.

How it learns:
- `alvenus check` remembers the notes it gave on each storyboard. A note that is
  gone at the next check was taken: the creator kept the editor's advice.
- `alvenus approve` counts the notes still standing as set aside: the creator
  liked it their way. It also remembers the style and kind they approved.
- The creator's AI records a plain "no thanks" or a chosen opening with
  `alvenus taste aside CODE`, `alvenus taste keep CODE` or `alvenus taste pick NAME`.

How it is used: a kind of note this creator has set aside at least twice, more
often than they took it, goes quiet (a weak point becomes a note, a note is only
listed as set aside). Notes about facts, missing words and missing pictures
never go quiet. Openings are offered in the order this creator has picked them.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

NEVER_QUIET = {"fact", "empty", "picture-missing", "beat-missing"}


def path() -> Path:
    return Path(os.environ.get("VENUS_HOME") or Path.home() / ".venus") / "taste.json"


def load() -> dict:
    try:
        d = json.loads(path().read_text(encoding="utf-8"))
        if isinstance(d, dict):
            return {"notes": d.get("notes") or {}, "picks": d.get("picks") or {}, "last": d.get("last") or {}}
    except (OSError, ValueError):
        pass
    return {"notes": {}, "picks": {}, "last": {}}


def save(d: dict) -> None:
    p = path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8")
        tmp.replace(p)
    except OSError:
        pass  # learning is a bonus; a read-only home must never stop a check


def _note(d: dict, code: str) -> dict:
    return d["notes"].setdefault(code, {"kept": 0, "aside": 0, "why": []})


def mark(code: str, kept: bool, why: str = "", d: dict | None = None) -> dict:
    own = d is None
    d = load() if own else d
    n = _note(d, code)
    n["kept" if kept else "aside"] += 1
    if why:
        n["why"] = (n["why"] + [why.strip()[:160]])[-3:]
    n["at"] = time.strftime("%Y-%m-%d")
    if own:
        save(d)
    return d


def pick(name: str, d: dict | None = None) -> None:
    own = d is None
    d = load() if own else d
    d["picks"][name] = int(d["picks"].get(name, 0)) + 1
    if own:
        save(d)


def score(name: str) -> int:
    return int(load()["picks"].get(name, 0))


def quiet(code: str, d: dict | None = None) -> bool:
    if not code or code in NEVER_QUIET:
        return False
    n = (d or load())["notes"].get(code) or {}
    return n.get("aside", 0) >= 2 and n.get("aside", 0) > n.get("kept", 0)


def apply(findings: list) -> list:
    """Quiet the kinds of notes this creator keeps setting aside."""
    d = load()
    if not d["notes"]:
        return findings
    for f in findings:
        if quiet(f.code, d):
            if f.level == "weak":
                f.level, f.what = "note", f.what + " (you usually keep this as it is)"
            elif f.level == "note":
                f.level = "quiet"
    return findings


def seen(storyboard: Path, findings: list) -> None:
    """After a check: notes from the last check that are gone now were taken."""
    d = load()
    key = str(Path(storyboard).resolve())
    now = sorted({f.code for f in findings if f.code and f.level in ("weak", "note")})
    for code in set(d["last"].get(key) or []) - set(now):
        mark(code, True, d=d)
    d["last"][key] = now
    if len(d["last"]) > 200:  # keep the file small
        for k in list(d["last"])[:-200]:
            d["last"].pop(k)
    save(d)


def approved(storyboard: Path, sb: dict, findings: list) -> None:
    """At approval: what still stands is how the creator likes it."""
    d = load()
    for code in sorted({f.code for f in findings if f.code and f.level in ("weak", "note")}):
        mark(code, False, d=d)
    for k in ("style", "aspect"):
        if sb.get(k):
            pick(f"{k}:{sb[k]}", d)
    if (sb.get("brief") or {}).get("kind"):
        pick(f"kind:{sb['brief']['kind']}", d)
    d["last"].pop(str(Path(storyboard).resolve()), None)
    save(d)


def forget(code: str | None = None) -> None:
    d = load()
    if code:
        d["notes"].pop(code, None)
        d["picks"].pop(code, None)
    else:
        d = {"notes": {}, "picks": {}, "last": {}}
    save(d)


def summary(d: dict | None = None) -> dict:
    d = d or load()
    q = sorted(c for c in d["notes"] if quiet(c, d))
    took = sorted((c for c, n in d["notes"].items() if n.get("kept", 0) > n.get("aside", 0)), key=lambda c: -d["notes"][c]["kept"])
    likes = sorted(d["picks"].items(), key=lambda kv: -kv[1])
    return {"quiet": q, "takes": took, "likes": [k for k, _ in likes[:8]],
            "why": {c: d["notes"][c].get("why") for c in q if d["notes"][c].get("why")}, "file": str(path())}
