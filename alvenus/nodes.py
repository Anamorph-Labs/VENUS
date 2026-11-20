"""Nodes: a video as small named pieces that you and your AI can point at.

A node file (NAME.nodes.json) holds the same video as a storyboard, cut into
nodes: the settings, the sound, one node per scene and, under each scene, its
parts (how it comes in, its words, its picture, its marks, its graphic).

- Every node has an id ("scene3.words"), so a change names exactly what it
  touches: "make scene3.words bigger" is `nodes set v.nodes.json scene3.words.size=1.3`.
- A node can be locked. Nothing changes a locked node by accident: `nodes set`
  refuses, the self-review leaves it alone, and a build stops if it was edited.
- A build redraws only the scenes whose nodes changed, and says which.
- Style nodes hold settings several scenes share ("use": ["calm"]). Change the
  style and every scene that uses it follows; a scene's own nodes still win.

A storyboard turns into nodes and back without losing anything, so the two
can be used side by side.
"""

from __future__ import annotations

import copy
import difflib
import hashlib
import json
import re
from pathlib import Path

FORMAT = 1
PARTS = ("in", "words", "picture", "mark", "graphic")  # in this order under each scene
KINDS = ("settings", "sound", "style", "scene") + PARTS
GRAPHIC_TYPES = {"stat", "chart", "line_chart", "timeline", "list", "compare", "map", "split"}
PART_KEYS = {
    "in": ("transition",),
    "words": ("text", "caption", "big_words", "subtitle", "who"),
    "picture": ("file", "from", "label", "push", "darken"),
    "mark": ("callout", "note"),
    "graphic": ("value", "label", "bars", "points", "items", "title", "pins", "route", "image", "left", "right"),
}
SOUND_KEYS = ("music", "music_lufs", "voiceover", "sound_effects")
WHAT = {
    "settings": "how the whole video looks: shape, design, colour, transitions",
    "sound": "music and voice",
    "style": "settings shared by the scenes that use it",
    "scene": "one scene: its type, length and background",
    "in": "how the scene comes in (its transition)",
    "words": "the words on screen",
    "picture": "the photo or clip, and how it is printed",
    "mark": "notes and marks drawn on the picture",
    "graphic": "the number, chart, list, map or comparison",
}


def _controls() -> dict[str, str]:
    from .paper import CONTROLS

    return CONTROLS


def part_params(part: str) -> list[str]:
    """Every param a part node can hold."""
    pre = part + "_"
    return list(PART_KEYS[part]) + [k[len(pre):] for k in _controls() if k.startswith(pre)]


def _place(kind: str | None, key: str) -> tuple[str | None, str]:
    """Which part of a scene a storyboard key belongs to, and its name there."""
    for part in ("words", "picture", "mark"):
        if key.startswith(part + "_") and key in _controls():
            return part, key[len(part) + 1:]
    order = ("graphic", "in", "words", "picture", "mark") if kind in GRAPHIC_TYPES else ("in", "words", "picture", "mark")
    for part in order:
        if key in PART_KEYS[part]:
            return part, key
    return None, key


def scene_key(part: str, name: str) -> str | None:
    """The storyboard key a part's param stands for (None: not a param of that part)."""
    if name in PART_KEYS[part]:
        return name
    if f"{part}_{name}" in _controls():
        return f"{part}_{name}"
    return None


def _style_key(name: str) -> str | None:
    """A style's param ("words.size", "picture.darken", "seconds") as a storyboard key."""
    if "." in name:
        part, _, p = name.partition(".")
        return scene_key(part, p) if part in PART_KEYS else None
    known = {"seconds", "dark", "background"} | {k for keys in PART_KEYS.values() for k in keys} | set(_controls())
    return name if name in known else None


# ------------------------------------------------------------------ convert


def to_nodes(sb: dict) -> dict:
    """A storyboard as a node file."""
    nodes = [{"id": "settings", "kind": "settings",
              "params": {k: v for k, v in sb.items() if k not in SOUND_KEYS and k != "scenes"}},
             {"id": "sound", "kind": "sound", "params": {k: sb[k] for k in SOUND_KEYS if k in sb}}]
    for i, sc in enumerate(sb.get("scenes") or []):
        sid = f"scene{i + 1}"
        own: dict = {}
        parts: dict[str, dict] = {}
        for k, v in sc.items():
            part, name = _place(sc.get("type"), k)
            if part:
                parts.setdefault(part, {})[name] = v
            else:
                own[k] = v
        nodes.append({"id": sid, "kind": "scene", "params": own})
        nodes += [{"id": f"{sid}.{p}", "kind": p, "of": sid, "params": parts[p]} for p in PARTS if p in parts]
    return {"venus_nodes": FORMAT, "nodes": nodes}


def scenes_of(doc: dict) -> list[dict]:
    return [n for n in doc["nodes"] if n.get("kind") == "scene"]


def parts_of(doc: dict, sid: str) -> list[dict]:
    got = [n for n in doc["nodes"] if n.get("of") == sid and n.get("kind") in PARTS]
    return sorted(got, key=lambda n: PARTS.index(n["kind"]))


def to_storyboard(doc: dict) -> dict:
    """The node file as a storyboard (styles folded into the scenes that use them)."""
    sb: dict = {}
    for n in doc["nodes"]:
        if n.get("kind") in ("settings", "sound"):
            sb.update(copy.deepcopy(n.get("params") or {}))
    styles = {n["id"]: n for n in doc["nodes"] if n.get("kind") == "style"}
    scenes = []
    for sn in scenes_of(doc):
        sc: dict = {}
        from_style = set()
        for st in sn.get("use") or []:
            for name, v in (styles.get(st, {}).get("params") or {}).items():
                k = _style_key(name)
                if k:
                    sc[k] = copy.deepcopy(v)
                    from_style.add(k)
        own = [(k, v) for k, v in (sn.get("params") or {}).items()]
        for pn in parts_of(doc, sn["id"]):
            own += [(scene_key(pn["kind"], p) or f"{pn['kind']}_{p}", v) for p, v in (pn.get("params") or {}).items()]
        for k, v in own:
            if v is None and k in from_style:  # null: drop what the style set
                sc.pop(k, None)
            else:
                sc[k] = copy.deepcopy(v)
        scenes.append(sc)
    sb["scenes"] = scenes
    return sb


# ------------------------------------------------------------------- checks


def node_hash(n: dict) -> str:
    blob = json.dumps({k: n.get(k) for k in ("kind", "of", "params", "use")}, sort_keys=True, default=str)
    return hashlib.sha1(blob.encode()).hexdigest()[:10]


def lock_hash(doc: dict, n: dict) -> str:
    """What a lock protects: the node; for a scene also its parts and the styles it uses."""
    if n.get("kind") != "scene":
        return node_hash(n)
    styles = {s["id"]: s for s in doc["nodes"] if s.get("kind") == "style"}
    group = [node_hash(n)] + [p["kind"] + node_hash(p) for p in parts_of(doc, n["id"])]
    group += [node_hash(styles[s]) for s in n.get("use") or [] if s in styles]
    return hashlib.sha1("|".join(group).encode()).hexdigest()[:10]


def _near(word: str, options) -> str:
    m = difflib.get_close_matches(word, list(options), n=1)
    return f" (did you mean {m[0]}?)" if m else ""


def check(doc: dict) -> list[str]:
    """What is wrong with a node file, in plain words ([] = nothing)."""
    if not isinstance(doc, dict) or not isinstance(doc.get("nodes"), list):
        return ['a node file is {"venus_nodes": 1, "nodes": [...]}']
    out, seen = [], {}
    for n in doc["nodes"]:
        nid = n.get("id") if isinstance(n, dict) else None
        if not isinstance(nid, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", nid):
            out.append(f"node {n!r:.60}: needs an id made of letters, numbers, - and _")
            continue
        if nid in seen:
            out.append(f"{nid}: two nodes have this id")
        seen[nid] = n
        if n.get("kind") not in KINDS:
            out.append(f"{nid}: kind {n.get('kind')!r} is not one of {', '.join(KINDS)}")
        if not isinstance(n.get("params", {}), dict):
            out.append(f"{nid}: params must be {{name: value}}")
    if out:
        return out
    scenes = {n["id"] for n in scenes_of(doc)}
    styles = {n["id"] for n in doc["nodes"] if n["kind"] == "style"}
    for kind in ("settings", "sound"):
        if sum(n["kind"] == kind for n in doc["nodes"]) > 1:
            out.append(f"only one {kind} node, please")
    if not scenes:
        out.append("no scene nodes")
    owned: dict[tuple[str, str], str] = {}
    for n in doc["nodes"]:
        nid, kind, params = n["id"], n["kind"], n.get("params") or {}
        if kind == "scene":
            if "." in nid:
                out.append(f"{nid}: a scene's id can't have a dot in it (dots join a scene to its parts: {nid.split('.')[0]}.words)")
            for st in n.get("use") or []:
                if st not in styles:
                    out.append(f"{nid}: uses style {st!r}, but there is no style node with that id" + _near(st, styles))
            for k in params:
                part, _ = _place(params.get("type"), k)
                if part:
                    out.append(f"{nid}: {k} belongs in its {part} node ({nid}.{part})")
        elif kind in PARTS:
            sid = n.get("of")
            if sid not in scenes:
                out.append(f"{nid}: \"of\" must name its scene" + (f"; there is no scene {sid!r}" + _near(str(sid), scenes) if sid else ""))
                continue
            for p in params:
                k = scene_key(kind, p)
                if not k:
                    out.append(f"{nid}: a {kind} node has no {p!r}" + _near(p, part_params(kind))
                               + f"; it can hold {', '.join(part_params(kind))}")
                elif (sid, k) in owned:
                    out.append(f"{nid}: {p} is already set by {owned[(sid, k)]}")
                else:
                    owned[(sid, k)] = nid
            if sum(m.get("of") == sid and m.get("kind") == kind for m in doc["nodes"]) > 1:
                out.append(f"{sid} has more than one {kind} node")
        elif kind == "style":
            for p in params:
                if not _style_key(p):
                    out.append(f"{nid}: style param {p!r} is not a scene setting (use words.size, picture.shape, seconds, dark...)")
        if n.get("locked") and n.get("lock") and n["lock"] != lock_hash(doc, n):
            out.append(f"{nid} is locked, but it has changed since it was locked. Undo the change, "
                       f"or unlock it first (alvenus nodes unlock FILE {nid})")
    return out


def frozen(doc: dict) -> set[str]:
    """What the self-review must leave alone, in autofix's terms."""
    out = set()
    ids = [n["id"] for n in scenes_of(doc)]
    for n in doc["nodes"]:
        if not n.get("locked"):
            continue
        if n["kind"] == "settings":
            out.add("end_card_seconds")
        sid = n["id"] if n["kind"] == "scene" else n.get("of")
        if sid not in ids:
            continue
        i = ids.index(sid)
        keys = {"scene": ("seconds", "darken", "transition"), "picture": ("darken",), "in": ("transition",)}.get(n["kind"], ())
        out |= {f"{i}:{k}" for k in keys}
    return out


# ---------------------------------------------------------------- read/write


def is_nodes(path: Path) -> bool:
    try:
        return "venus_nodes" in json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return False


def read(path: Path) -> dict:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise SystemExit(f"{path}: can't read the node file ({e})")
    if "venus_nodes" not in doc:
        raise SystemExit(f"{path} is not a node file; turn a storyboard into one with: alvenus nodes init {path}")
    return doc


def tidy(doc: dict) -> dict:
    """Nodes in reading order: settings, sound, styles, then each scene followed by its parts."""
    top = [n for n in doc["nodes"] if n.get("kind") in ("settings", "sound")]
    top.sort(key=lambda n: n["kind"] != "settings")
    styles = [n for n in doc["nodes"] if n.get("kind") == "style"]
    body = []
    for sn in scenes_of(doc):
        body += [sn] + parts_of(doc, sn["id"])
    rest = [n for n in doc["nodes"] if n not in top + styles + body]
    return {**doc, "nodes": top + styles + body + rest}


def write(path: Path, doc: dict) -> None:
    doc = tidy(doc)
    lines = ["{", f'  "venus_nodes": {doc.get("venus_nodes", FORMAT)},', '  "nodes": [']
    # one node per line, so a diff (or the person) sees exactly which node changed
    for i, n in enumerate(doc["nodes"]):
        lines.append("    " + json.dumps(n, ensure_ascii=False) + ("," if i < len(doc["nodes"]) - 1 else ""))
    lines += ["  ]", "}"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def last_path(path: Path) -> Path:
    name = path.name[:-5] if path.name.endswith(".json") else path.name
    return path.with_name(name + ".last.json")


def read_last(path: Path) -> dict:
    try:
        return json.loads(last_path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def changes(doc: dict, last: dict) -> list[str]:
    """Node ids that are new or changed since the last build (and "-id" for removed)."""
    before = last.get("hashes") or {}
    now = {n["id"]: node_hash(n) for n in doc["nodes"]}
    if not before:
        return []
    return [k for k, v in now.items() if before.get(k) != v] + [f"-{k}" for k in before if k not in now]


def save_last(path: Path, doc: dict, video: Path, spans: dict, redrawn: list[str]) -> None:
    import time

    ids = [n["id"] for n in scenes_of(doc)]
    last_path(path).write_text(json.dumps({
        "built": time.strftime("%Y-%m-%d %H:%M"), "video": str(video.resolve()),
        "hashes": {n["id"]: node_hash(n) for n in doc["nodes"]},
        "spans": {ids[i]: [round(a, 3), round(b, 3)] for i, (a, b) in spans.items() if i < len(ids)},
        "redrawn": redrawn}, indent=1), encoding="utf-8")


# ------------------------------------------------------------------- editing


def find(doc: dict, nid: str) -> dict | None:
    return next((n for n in doc["nodes"] if n.get("id") == nid), None)


def _guard(doc: dict, n: dict, force: bool) -> None:
    """Refuse to touch a locked node (or a part or style of a locked scene)."""
    holders = [n]
    if n.get("of"):
        holders.append(find(doc, n["of"]) or {})
    if n.get("kind") == "style":
        holders += [s for s in scenes_of(doc) if n["id"] in (s.get("use") or [])]
    locked = [h["id"] for h in holders if h.get("locked")]
    if locked and not force:
        raise SystemExit(f"{n['id']} is locked ({', '.join(locked)}); unlock it first, or add --force to change it and keep the lock")


def relock(doc: dict) -> None:
    """Stamp every lock with what its node holds now (after a forced change)."""
    for n in doc["nodes"]:
        if n.get("locked"):
            n["lock"] = lock_hash(doc, n)


def resolve(doc: dict, target: str) -> tuple[dict, str]:
    """"scene3.words.size" -> (the scene3.words node, "size"), making the part node if it is missing."""
    bits = target.split(".")
    for cut in range(len(bits) - 1, 0, -1):
        nid, param = ".".join(bits[:cut]), ".".join(bits[cut:])
        n = find(doc, nid)
        if n:
            return n, param
        if cut == 2 and bits[1] in PARTS and find(doc, bits[0]) and find(doc, bits[0])["kind"] == "scene":
            n = {"id": nid, "kind": bits[1], "of": bits[0], "params": {}}
            doc["nodes"].append(n)
            return n, param
    ids = [n["id"] for n in doc["nodes"]]
    raise SystemExit(f"{target}: no node to put that on" + _near(bits[0], ids) + "; write it as NODE.PARAM, like scene3.words.size")


def parse_value(raw: str):
    try:
        return json.loads(raw)
    except ValueError:
        return raw


def set_param(doc: dict, target: str, value, force: bool = False) -> dict:
    n, param = resolve(doc, target)
    _guard(doc, n, force)
    params = n.setdefault("params", {})
    if n["kind"] not in ("style",) and "." in param:  # nested: split's left.label
        head, _, rest = param.partition(".")
        box = params.setdefault(head, {})
        if not isinstance(box, dict):
            raise SystemExit(f"{n['id']}.{head} is not a group of settings")
        if value is None:
            box.pop(rest, None)
        else:
            box[rest] = value
    elif value is None:
        params.pop(param, None)
    else:
        params[param] = value
    if n["kind"] in PARTS and not params:
        doc["nodes"].remove(n)  # an empty part is the same as none
    if force:
        relock(doc)
    return n


def set_scene_key(doc: dict, sid: str, key: str, value) -> None:
    """Put a storyboard key back on the right node of a scene (used for the self-review's fixes)."""
    sn = find(doc, sid)
    part, name = _place((sn.get("params") or {}).get("type"), key)
    if part:
        pn = find(doc, f"{sid}.{part}") or {"id": f"{sid}.{part}", "kind": part, "of": sid, "params": {}}
        if pn not in doc["nodes"]:
            doc["nodes"].append(pn)
        pn["params"][name] = value
    else:
        sn.setdefault("params", {})[key] = value


def lock(doc: dict, ids: list[str], on: bool = True) -> list[str]:
    done = []
    for nid in ids:
        n = find(doc, nid)
        if not n:
            raise SystemExit(f"no node {nid!r}" + _near(nid, [m["id"] for m in doc["nodes"]]))
        if on:
            n["locked"], n["lock"] = True, lock_hash(doc, n)
        else:
            n.pop("locked", None)
            n.pop("lock", None)
        done.append(nid)
    return done


def use(doc: dict, style: str, scenes: list[str], on: bool = True, force: bool = False) -> list[str]:
    """Wire scenes to a style node (made if it isn't there yet), or unwire them."""
    st = find(doc, style)
    if st and st["kind"] != "style":
        raise SystemExit(f"{style} is a {st['kind']} node, not a style")
    if not st:
        if not on:
            raise SystemExit(f"no style {style!r}")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", style):
            raise SystemExit(f"{style}: a style's id is letters, numbers, - and _")
        st = {"id": style, "kind": "style", "params": {}}
        doc["nodes"].append(st)
    done = []
    for sid in scenes:
        sn = find(doc, sid)
        if not sn or sn["kind"] != "scene":
            raise SystemExit(f"{sid}: not a scene" + _near(sid, [x["id"] for x in scenes_of(doc)]))
        _guard(doc, sn, force)
        have = list(sn.get("use") or [])
        if on and style not in have:
            sn["use"] = have + [style]
        elif not on and style in have:
            have.remove(style)
            if have:
                sn["use"] = have
            else:
                sn.pop("use", None)
        done.append(sid)
    if force:
        relock(doc)
    return done


def _new_scene_id(doc: dict) -> str:
    taken = {n["id"] for n in doc["nodes"]}
    k = len(scenes_of(doc)) + 1
    while f"scene{k}" in taken:
        k += 1
    return f"scene{k}"


def move(doc: dict, sid: str, after: str | None = None, before: str | None = None, first: bool = False) -> None:
    n = find(doc, sid)
    if not n or n["kind"] != "scene":
        raise SystemExit(f"{sid}: only scenes move (their parts go with them)")
    order = [s for s in scenes_of(doc) if s is not n]
    if first:
        at = 0
    else:
        ref = find(doc, after or before or "")
        if not ref or ref["kind"] != "scene" or ref is n:
            raise SystemExit("say where: --after SCENE, --before SCENE or --first")
        at = order.index(ref) + (1 if after else 0)
    order.insert(at, n)
    others = [m for m in doc["nodes"] if m.get("kind") != "scene"]
    doc["nodes"] = others + order  # tidy() puts parts back under their scenes


def copy_scene(doc: dict, sid: str, new: str | None = None) -> str:
    n = find(doc, sid)
    if not n or n["kind"] != "scene":
        raise SystemExit(f"{sid}: give a scene to copy")
    new = new or _new_scene_id(doc)
    if find(doc, new) or "." in new:
        raise SystemExit(f"{new}: that id is taken (or has a dot in it)")
    c = {k: copy.deepcopy(v) for k, v in n.items() if k not in ("locked", "lock")}
    c["id"] = new
    parts = [{**{k: copy.deepcopy(v) for k, v in p.items() if k not in ("locked", "lock")},
              "id": f"{new}.{p['kind']}", "of": new} for p in parts_of(doc, sid)]
    i = doc["nodes"].index(n)
    doc["nodes"][i + 1:i + 1] = [c] + parts
    return new


def remove(doc: dict, nid: str, force: bool = False) -> list[str]:
    n = find(doc, nid)
    if not n:
        raise SystemExit(f"no node {nid!r}")
    if n["kind"] in ("settings", "sound"):
        raise SystemExit(f"{nid} can't be removed; set its params to null instead")
    _guard(doc, n, force)
    gone = [n] + (parts_of(doc, nid) if n["kind"] == "scene" else [])
    if n["kind"] == "style":
        for s in scenes_of(doc):
            if nid in (s.get("use") or []):
                s["use"] = [u for u in s["use"] if u != nid] or None
                if s["use"] is None:
                    s.pop("use")
    doc["nodes"] = [m for m in doc["nodes"] if m not in gone]
    return [m["id"] for m in gone]


def absolute_files(doc: dict, base: Path) -> None:
    """Make relative file names absolute, for a copy saved somewhere else."""
    def fix(v):
        return v if not isinstance(v, str) or Path(v).is_absolute() else str((base / v).resolve())

    for n in doc["nodes"]:
        p = n.get("params") or {}
        for k in ("file", "image", "music", "voiceover"):
            if p.get(k):
                p[k] = fix(p[k])
        for side in ("left", "right"):
            if isinstance(p.get(side), dict) and p[side].get("file"):
                p[side]["file"] = fix(p[side]["file"])


# ---------------------------------------------------------------------- show


def _short(v, n: int = 46) -> str:
    s = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else (f'"{v}"' if " " in v or not v else v)
    if isinstance(v, str) and ("/" in v or "\\" in v) and Path(v).suffix:
        s = Path(v).name
    return s if len(s) <= n else s[:n - 3] + "..."


def _line(params: dict) -> str:
    return "  ".join(f"{k}={_short(v)}" for k, v in params.items())


PACK_KEYS = ("aspect", "look", "accent", "transition", "transition_seconds", "title_style", "background", "design")


def effective(sb: dict) -> dict:
    """The storyboard with its style pack's settings filled in (its own still win)."""
    from .presets import pack

    return {**pack(sb.get("style"), *PACK_KEYS), **sb}


def show(doc: dict, last: dict | None = None, only: list[str] | None = None) -> str:
    """The node map as text: short enough for an AI to read every time."""
    changed = set(changes(doc, last or {}))
    sb = effective(to_storyboard(doc))
    scenes = scenes_of(doc)
    total = sum(float(s.get("seconds", 3.0)) for s in sb["scenes"])

    def tag(n):
        bits = []
        if n.get("locked"):
            bits.append("LOCKED")
        if n["id"] in changed:
            bits.append("changed")
        return f"  [{', '.join(bits)}]" if bits else ""

    out = []
    if not only:
        out.append(f"{len(scenes)} scenes, about {total:.0f} s" + (f", design {sb['design']}" if sb.get("design") else "")
                   + (f", style pack {sb['style']}" if sb.get("style") else ""))
    want = lambda n: not only or n["id"] in only or n.get("of") in only
    for n in tidy(doc)["nodes"]:
        if n["kind"] in ("settings", "sound", "style") and want(n):
            users = [s["id"] for s in scenes if n["id"] in (s.get("use") or [])]
            out.append(f"{n['id']:<12}{_line(n.get('params') or {}) or '(empty)'}" + (f"   (used by {', '.join(users)})" if users else "") + tag(n))
    trans = sb.get("transition", "crossfade")
    for k, sn in enumerate(scenes):
        if not want(sn):
            continue
        p = dict(sn.get("params") or {})
        kind = p.pop("type", "?")
        sec = p.pop("seconds", None)
        head = f"#{k + 1} {sn['id']}  {kind}" + (f" {sec:g}s" if isinstance(sec, (int, float)) else "")
        if sn.get("use"):
            head += f"  use: {', '.join(sn['use'])}"
        if p:
            head += "  " + _line(p)
        out.append(head + tag(sn))
        for pn in parts_of(doc, sn["id"]):
            out.append(f"   .{pn['kind']:<9}{_line(pn.get('params') or {})}" + tag(pn))
        if k + 1 < len(scenes):
            nxt = find(doc, f"{scenes[k + 1]['id']}.in")
            out.append(f"   -> {((nxt or {}).get('params') or {}).get('transition') or trans}")
    gone = [c[1:] for c in changed if c.startswith("-")]
    if gone:
        out.append("removed since the last build: " + ", ".join(gone))
    return "\n".join(out)


def guide() -> str:
    """What each node kind can hold, for the AI writing the changes."""
    from .paper import CONTROLS

    rows = ["Node kinds and what they hold (set with: alvenus nodes set FILE NODE.PARAM=VALUE):"]
    rows.append("  settings   every storyboard setting: aspect, style, design, look, accent, transition, transition_seconds, "
                "cut_on_beat, captions, end_card, title_style, background, label...")
    rows.append("  sound      " + ", ".join(SOUND_KEYS))
    rows.append("  style      any scene setting, written part.param (words.size, picture.shape, seconds, dark); "
                "scenes join with \"use\": [\"style-id\"]")
    rows.append("  scene      type, seconds, background, dark (and any other scene setting that is not a part's)")
    for part in PARTS:
        rows.append(f"  {part:<10} " + ", ".join(PART_KEYS[part]))
        for k, why in CONTROLS.items():
            if k.startswith(part + "_"):
                rows.append(f"{'':13}{k[len(part) + 1:]}: {why}")
    rows.append("  (for chart, stat, list, map, compare and split scenes, label/title/items/... live in the graphic node)")
    return "\n".join(rows)
