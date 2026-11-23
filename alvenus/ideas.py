"""Ideas typed into Studio's "Describe your video" box, waiting for the creator's own AI.

Venus never writes the words of a video itself: the creator's AI (Claude, Codex...)
does. So when the creator types an idea in Studio, Venus

  1. writes the brief (the idea word for word, plus what the creator picked:
     kind, length, shape, look) into a new folder,
  2. lays out the storyboard by the story recipe for that kind of video (one
     scene per beat, each with its job, no words yet) as a node file, and opens
     it in Studio, so the creator sees the shape of the video at once,
  3. puts the idea in the inbox (~/.venus/ideas), where the AI finds it:

       alvenus ideas                 what is waiting
       alvenus ideas --wait          wait for the next idea (for an AI that listens)
       alvenus ideas start ID        the AI has filled the brief: lay the scenes out again from it
       alvenus ideas ready ID        the AI has written every scene and the story check passed

While the AI writes, each scene it fills appears in Studio's strip. Nothing is
rendered until the creator has read the storyboard and pressed Render.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from . import brief as br
from . import nodes as nd

STATES = {
    "waiting": "waiting for your AI",
    "writing": "your AI is writing it",
    "ready": "ready for you to read",
}


def inbox() -> Path:
    d = Path(os.environ.get("VENUS_HOME") or Path.home() / ".venus") / "ideas"
    d.mkdir(parents=True, exist_ok=True)
    return d


def slug(text: str) -> str:
    words = re.findall(r"[a-z0-9]+", text.lower())
    stop = {"a", "an", "the", "on", "of", "about", "why", "how", "for", "in", "my", "to", "and", "second", "seconds", "video",
            "reel", "explainer", "short", "make", "me", "is", "with", "what"}
    keep = [w for w in words if w not in stop and not w.isdigit()][:4] or ["idea"]
    return "-".join(keep)


def _guess(text: str) -> dict:
    """What the idea itself already says: length, shape, kind ("a 30 second reel on..." -> 30, 9:16)."""
    t = text.lower()
    g: dict = {}
    if m := re.search(r"(\d{1,3})\s*(?:s\b|sec|second)", t):
        g["seconds"] = int(m.group(1))
    elif m := re.search(r"(\d)\s*(?:min|minute)", t):
        g["seconds"] = int(m.group(1)) * 60
    if re.search(r"\b(reel|reels|short|shorts|tiktok|vertical|story|stories)\b", t):
        g["aspect"] = "9:16"
    elif re.search(r"\b(youtube|wide|landscape)\b", t):
        g["aspect"] = "16:9"
    for kind, words in (("travel", r"\b(trip|travel|holiday|vacation|journey)\b"), ("list", r"\b(top \d|top-\d|\d things|ranking|list)\b"),
                        ("ad", r"\b(ad|advert|product|launch|promo)\b"), ("story", r"\b(story of|how .* became|history)\b"),
                        ("explainer", r"\b(why|how|explain|explainer|what is)\b")):
        if re.search(words, t):
            g["kind"] = kind
            break
    return g


def create(text: str, folder: Path, kind: str = "", seconds: float | None = None, aspect: str = "", look: str = "") -> dict:
    """A new idea from Studio: brief + laid-out node file in its own folder, and an inbox entry. Returns the entry."""
    text = " ".join(str(text).split())
    if len(text) < 8:
        raise ValueError("say a little more: what is the video about, and who is it for?")
    g = _guess(text)
    kind = kind or g.get("kind") or "explainer"
    if kind not in br.RECIPES:
        raise ValueError(f"kind: choose one of {', '.join(br.KINDS)}")
    seconds = float(seconds or g.get("seconds") or (45 if kind == "story" else 30))
    seconds = max(10.0, min(180.0, seconds))
    r = br.RECIPES[kind]
    aspect = aspect or g.get("aspect") or r["aspect"]
    if aspect not in br.ASPECTS:
        raise ValueError(f"shape: choose one of {', '.join(br.ASPECTS)}")
    name = slug(text)
    base = Path(folder)
    d = base / name
    n = 2
    while d.exists():
        d = base / f"{name}-{n}"
        n += 1
    d.mkdir(parents=True)
    b = br.new(text)
    b.update({"kind": kind, "seconds": seconds, "aspect": aspect, "look": look or "any", "material": "none"})
    b["_how_to_fill"] = br.QUESTIONS
    b["_next"] = (f"Fill audience, point and mood (ask the creator only what the idea doesn't tell you), then: "
                  f"alvenus ideas start {d.name}")
    (d / "brief.json").write_text(json.dumps(b, indent=2), encoding="utf-8")
    nodes_path = d / f"{d.name}.nodes.json"
    lay_out(b, nodes_path, status="waiting")
    entry = {"id": d.name, "idea": text, "brief": str((d / "brief.json").resolve()), "nodes": str(nodes_path.resolve()),
             "status": "waiting", "at": time.strftime("%Y-%m-%d %H:%M"), "kind": kind, "seconds": seconds, "aspect": aspect}
    save(entry)
    return entry


def lay_out(b: dict, nodes_path: Path, status: str) -> None:
    """The recipe's skeleton (one scene per beat, its job written on it) as a node file Studio can open."""
    sk = br.skeleton({**b, "audience": b.get("audience") or "-", "point": b.get("point") or "-", "mood": b.get("mood") or "-"})
    sk["brief"] = {k: b.get(k) for k in br.QUESTIONS}
    sk["_idea"] = {"text": b["idea"], "status": status}
    doc = nd.to_nodes(sk)
    nd.write(nodes_path, doc)


def save(entry: dict) -> None:
    (inbox() / f"{entry['id']}.json").write_text(json.dumps(entry, indent=2), encoding="utf-8")


def entries(status: str | None = None) -> list[dict]:
    out = []
    for p in sorted(inbox().glob("*.json"), key=lambda p: p.stat().st_mtime):
        try:
            e = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not Path(e.get("nodes", "")).exists():
            continue  # its folder was deleted
        if status is None or e.get("status") == status:
            out.append(e)
    return out


def find(ident: str) -> dict:
    for e in entries():
        if e["id"] == ident or Path(e["nodes"]) == Path(ident).resolve():
            return e
    raise SystemExit(f"no idea called {ident!r}; waiting now: {', '.join(e['id'] for e in entries()) or 'none'}")


def set_status(e: dict, status: str) -> None:
    e["status"] = status
    save(e)
    p = Path(e["nodes"])
    doc = nd.read(p)
    for n in doc["nodes"]:
        if n["kind"] == "settings":
            idea = dict((n.get("params") or {}).get("_idea") or {"text": e["idea"]})
            idea["status"] = status
            n.setdefault("params", {})["_idea"] = idea
    nd.write(p, doc)


def start(ident: str) -> dict:
    """The AI filled the brief: check it and lay the scenes out again from it (only while no scene has words)."""
    e = find(ident)
    b = br.read(Path(e["brief"]))
    probs = br.problems(b)
    if probs:
        raise SystemExit("finish the brief first:\n  " + "\n  ".join(probs))
    p = Path(e["nodes"])
    from .storycheck import empty

    sb = nd.to_storyboard(nd.read(p))
    if all(empty(sc) for sc in sb.get("scenes") or []):
        lay_out(b, p, status="writing")
    e.update(kind=b["kind"], seconds=b["seconds"], aspect=b["aspect"])
    set_status(e, "writing")
    return e


def instructions(e: dict) -> str:
    p = e["nodes"]
    return "\n".join([
        f"New idea from Studio ({e['at']}): \"{e['idea']}\"",
        f"  id       {e['id']}   ({STATES.get(e['status'], e['status'])})",
        f"  brief    {e['brief']}",
        f"  scenes   {p}   (open in the creator's Studio now)",
        "Steps:",
        "  1. Fill the brief: audience, point (the ONE thing to remember), mood; fix kind/seconds/aspect/look if the idea says",
        "     otherwise. Ask the creator only what you can't tell. Then: alvenus ideas start " + e["id"],
        f"  2. Write each scene for its beat (its _job says what it must do), one at a time, so the creator watches them appear:",
        f"       alvenus nodes show {p}",
        f"       alvenus nodes set {p} scene1.words.text=\"...\"     (a picture: scene2.picture.file=\"icon:NAME\"; alvenus icons search WORDS)",
        f"  3. alvenus check {p}   until it passes, then: alvenus ideas ready {e['id']}",
        "  4. Tell the creator it is ready to read in Studio. Never render it yourself: they press Render after reading it.",
    ])
