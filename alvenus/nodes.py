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
KINDS = ("settings", "sound", "style", "scene") + PARTS + ("tool",)
GRAPHIC_TYPES = {"stat", "chart", "line_chart", "timeline", "list", "compare", "map", "split"}
PART_KEYS = {
    "in": ("transition",),
    "words": ("text", "caption", "big_words", "subtitle", "who"),
    "picture": ("file", "from", "label", "push", "darken"),
    "mark": ("callout", "note"),
    "graphic": ("value", "label", "bars", "points", "items", "title", "pins", "route", "image", "left", "right"),
}
SOUND_KEYS = ("music", "music_lufs", "voiceover", "sound_effects")
# The stages of a scene as a node editor shows them (stage, part it lives in,
# its params), in the order the picture is made. Each stage can be switched
# off ("off": ["shape"] on the part) to compare with and without it.
STAGES = (
    ("in", "in", ("transition",)),
    ("picture", "picture", ("file", "from", "size", "angle", "push", "label")),
    ("look", "picture", ("photo", "darken")),
    ("shape", "picture", ("shape", "shape_colour")),
    ("graphic", "graphic", PART_KEYS["graphic"]),
    ("words", "words", ("text", "caption", "big_words", "subtitle", "who", "size", "speed", "delay", "align", "caps")),
    ("marks", "mark", ("callout", "note", "colour", "show")),
)
BYPASS = {  # what a scene looks like with a stage off
    "look": {"picture_photo": "colour", "darken": 0},
    "shape": {"picture_shape": "none"},
    "words": {"text": None, "caption": None, "subtitle": None, "who": None, "big_words": None},
    "marks": {"callout": None, "note": None, "mark_show": False},
}
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
    "tool": "a tool on one branch of the scene's graph: blur, glow, grade or vignette",
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
        tools = []
        for t in sc.get("tools") or []:
            t = dict(t) if isinstance(t, dict) else {"tool": t}
            name = str(t.pop("name", None) or t.get("tool"))
            while f"{sid}.{name}" in {x["id"] for x in tools} or name in PARTS:
                name = re.sub(r"\d*$", lambda m: str(int(m.group() or 1) + 1), name)
            off = t.pop("off", None)
            tools.append({"id": f"{sid}.{name}", "kind": "tool", "of": sid, "params": t, **({"off": ["tool"]} if off else {})})
        for k, v in sc.items():
            if k == "tools":
                continue
            part, name = _place(sc.get("type"), k)
            if part:
                parts.setdefault(part, {})[name] = v
            else:
                own[k] = v
        nodes.append({"id": sid, "kind": "scene", "params": own})
        nodes += [{"id": f"{sid}.{p}", "kind": p, "of": sid, "params": parts[p]} for p in PARTS if p in parts]
        nodes += tools
    return {"venus_nodes": FORMAT, "nodes": nodes}


def scenes_of(doc: dict) -> list[dict]:
    return [n for n in doc["nodes"] if n.get("kind") == "scene"]


def parts_of(doc: dict, sid: str) -> list[dict]:
    got = [n for n in doc["nodes"] if n.get("of") == sid and n.get("kind") in PARTS]
    return sorted(got, key=lambda n: PARTS.index(n["kind"]))


def tools_of(doc: dict, sid: str) -> list[dict]:
    """A scene's tool nodes, in the order they work."""
    return [n for n in doc["nodes"] if n.get("of") == sid and n.get("kind") == "tool"]


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
        off: set[str] = set()
        for pn in parts_of(doc, sn["id"]):
            own += [(scene_key(pn["kind"], p) or f"{pn['kind']}_{p}", v) for p, v in (pn.get("params") or {}).items()]
            off |= set(pn.get("off") or [])
        for k, v in own:
            if v is None and k in from_style:  # null: drop what the style set
                sc.pop(k, None)
            else:
                sc[k] = copy.deepcopy(v)
        for stage in off:  # a switched-off stage, as in a node editor: see the scene without it
            for k, v in BYPASS.get(stage, {}).items():
                if v is None:
                    sc.pop(k, None)
                else:
                    sc[k] = v
        tools = [{"name": t["id"].split(".", 1)[1], **copy.deepcopy(t.get("params") or {}), **({"off": True} if t.get("off") else {})}
                 for t in tools_of(doc, sn["id"])]
        if tools:
            sc["tools"] = tools
        scenes.append(sc)
    sb["scenes"] = scenes
    return sb


# ------------------------------------------------------------------- checks


def node_hash(n: dict) -> str:
    keep = {k: n.get(k) for k in ("kind", "of", "params", "use")}
    if n.get("off"):  # (only when set, so older locks still match)
        keep["off"] = n["off"]
    blob = json.dumps(keep, sort_keys=True, default=str)
    return hashlib.sha1(blob.encode()).hexdigest()[:10]


def lock_hash(doc: dict, n: dict) -> str:
    """What a lock protects: the node; for a scene also its parts and the styles it uses."""
    if n.get("kind") != "scene":
        return node_hash(n)
    styles = {s["id"]: s for s in doc["nodes"] if s.get("kind") == "style"}
    group = [node_hash(n)] + [p["kind"] + node_hash(p) for p in parts_of(doc, n["id"])]
    group += ["tool" + t["id"] + node_hash(t) for t in tools_of(doc, n["id"])]
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
        elif kind == "tool":
            from .paper import tool_problem

            if n.get("of") not in scenes:
                out.append(f"{nid}: \"of\" must name its scene")
            elif not nid.startswith(n["of"] + "."):
                out.append(f"{nid}: a tool's id starts with its scene ({n['of']}.blur)")
            if why := tool_problem(params):
                out.append(f"{nid}: {why}")
            if n.get("off") not in (None, ["tool"]):
                out.append(f"{nid}: a tool switches off with \"off\": [\"tool\"]")
        elif kind == "style":
            for p in params:
                if not _style_key(p):
                    out.append(f"{nid}: style param {p!r} is not a scene setting (use words.size, picture.shape, seconds, dark...)")
        for stage in (n.get("off") or []) if kind != "tool" else []:
            if kind not in PARTS or stage not in BYPASS or not any(st == stage and part == kind for st, part, _ in STAGES):
                out.append(f"{nid}: {stage!r} can't be switched off here" + (f"; on a {kind} node: "
                           + ", ".join(st for st, part, _ in STAGES if part == kind and st in BYPASS) if kind in PARTS else ""))
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
        body += [sn] + parts_of(doc, sn["id"]) + tools_of(doc, sn["id"])
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
    parts += [{**{k: copy.deepcopy(v) for k, v in t.items() if k not in ("locked", "lock")},
               "id": f"{new}.{t['id'].split('.', 1)[1]}", "of": new} for t in tools_of(doc, sid)]
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
    gone = [n] + (parts_of(doc, nid) + tools_of(doc, nid) if n["kind"] == "scene" else [])
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


PACK_KEYS = ("aspect", "look", "accent", "transition", "transition_seconds", "title_style", "background", "design", "letterbox", "lower_third_style")


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
        for tn in tools_of(doc, sn["id"]):
            tp = dict(tn.get("params") or {})
            what = f"{tp.pop('tool', '?')} on {tp.pop('on', '?')}"
            out.append(f"   .{tn['id'].split('.', 1)[1]:<9}{what}" + (f"  {_line(tp)}" if tp else "") + ("  (off)" if tn.get("off") else "") + tag(tn))
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
    from .paper import LAYERS, TOOL_ON, TOOLS

    rows.append("The scene as a graph: the paper, then its layers merged on top, bottom to top; usual order "
                + ", ".join(LAYERS) + ". Change it: alvenus nodes layers FILE sceneN shape words picture marks (words behind the picture) "
                "(or the scene param \"layers\"). A layer over the words draws the words into the scene itself.")
    rows.append("  tool       a node on one branch: alvenus nodes add FILE sceneN TOOL [param=value ...] --on BRANCH; "
                "branches: background (the paper), picture, words, marks, output (everything merged)")
    for t, ps in TOOLS.items():
        rows.append(f"{'':13}{t} (on {', '.join(TOOL_ON[t])}): " + ", ".join(f"{p} {lo:g} to {hi:g}" for p, (lo, hi, _) in ps.items()))
    rows.append(f"{'':13}change one: nodes set FILE sceneN.blur.amount=0.6; switch off: nodes off FILE sceneN.blur; remove: nodes remove FILE sceneN.blur")
    return "\n".join(rows)


# ------------------------------------------------------------- descriptions
#
# A person can describe what they want on any node ("warmer, slower"). Plain
# asks Venus understands are applied at once; every description is kept on
# the node as an "ask" for the person's own AI to read, act on and answer.

COLOURS = {"red": "#C8412F", "teal": "#2F8F8B", "yellow": "#F2C230", "blue": "#2F5FC8", "green": "#3C9A4A",
           "black": "#111111", "white": "#F4F2EE", "orange": "#E8792B", "pink": "#E87BA8", "purple": "#7A4FC8",
           "lime": "#D4F01E", "grey": "#8A8A8A", "gray": "#8A8A8A"}


def _rules():
    """(pattern, part, param, value or function of the current value); first hit per clause wins."""
    from .cut import TRANSITIONS

    mul = lambda k, lo, hi, d=1.0: (lambda cur: round(min(hi, max(lo, float(cur if cur is not None else d) * k)), 2))
    add = lambda k, lo, hi, d=0.0: (lambda cur: round(min(hi, max(lo, float(cur if cur is not None else d) + k)), 2))
    r = [
        (r"\b(no|without|remove|hide|lose)\b.*\bshape", "picture", "shape", "none"),
        (r"\b(circle|round)\b", "picture", "shape", "circle"),
        (r"\b(block|square|rectangle)\b", "picture", "shape", "block"),
        (r"\b(blob|paint|splash)\b", "picture", "shape", "blob"),
        (r"\b(colou?r photo|in colou?r|full colou?r)\b", "picture", "photo", "colour"),
        (r"\b(black and white|b&w|greyscale|grayscale|grey photo|gray photo)\b", "picture", "photo", "grey"),
        (r"\b(warm|warmer|vintage|sepia|old)\b", "picture", "photo", "warm"),
        (r"\btilt(ed)? left\b", "picture", "angle", -4),
        (r"\btilt(ed)?( right)?\b", "picture", "angle", 4),
        (r"\b(straight|level|no tilt)\b", "picture", "angle", 0),
        (r"\b(darker|dim)\b", "picture", "darken", add(0.12, 0, 0.6)),
        (r"\b(brighter|lighter)\b", "picture", "darken", add(-0.12, 0, 0.6)),
        (r"\b(zoom|push in|move in)\b", "picture", "push", 0.08),
        (r"\b(no zoom|keep still|no movement)\b", "picture", "push", 0),
        (r"\b(hide|no|remove)\b.*\b(label|arrow|mark|marks)\b", "mark", "show", False),
        (r"\b(show)\b.*\b(label|arrow|mark|marks)\b", "mark", "show", True),
        (r"\b(much |way )(bigger|larger)\b", "words", "size", mul(1.5, 0.4, 2.5)),
        (r"\b(bigger|larger|louder|bolder)\b", "words", "size", mul(1.2, 0.4, 2.5)),
        (r"\b(much |way )smaller\b", "words", "size", mul(0.6, 0.4, 2.5)),
        (r"\b(smaller|quieter|subtler)\b", "words", "size", mul(0.83, 0.4, 2.5)),
        (r"\b(faster|quicker|snappier)\b", "words", "speed", mul(0.7, 0.05, 1.5, 0.3)),
        (r"\b(slower|calmer|gentler)\b", "words", "speed", mul(1.4, 0.05, 1.5, 0.3)),
        (r"\b(later|wait)\b", "words", "delay", add(0.5, 0, 5, 0.25)),
        (r"\b(sooner|earlier|straight away|immediately)\b", "words", "delay", 0.0),
        (r"\b(centre|center|centred|centered|middle)\b", "words", "align", "centre"),
        (r"\b(left)\b", "words", "align", "left"),
        (r"\b(right)\b", "words", "align", "right"),
        (r"\b(caps|capitals|uppercase|all caps)\b", "words", "caps", True),
        (r"\b(lowercase|no caps|sentence case)\b", "words", "caps", False),
        (r"\b(longer|hold)\b", "scene", "seconds", add(0.8, 0.8, 15, 3.0)),
        (r"\b(shorter|tighter)\b", "scene", "seconds", add(-0.6, 0.8, 15, 3.0)),
        (r"\bdark (page|background|mood)\b|\bdarker page\b", "scene", "dark", True),
        (r"\blight (page|background)\b", "scene", "dark", False),
    ]
    for t in TRANSITIONS:
        if t != "cut":
            r.append((rf"\b{t}\b", "in", "transition", t))
    return r


_TARGET_WORDS = {"words": r"\b(words?|text|caption|type|title)\b", "picture": r"\b(picture|photo|image|print|shape)\b",
                 "mark": r"\b(mark|marks|label|arrow|note)\b", "scene": r"\b(scene|page)\b"}


_LAYER_WORDS = {"words": r"words?|text|caption|title|type", "picture": r"picture|photo|print|image|clip",
                "shape": r"shape|circle|block|blob|colou?r shape|paint", "marks": r"marks?|labels?|arrows?|notes?"}
_BRANCH_WORDS = {"background": r"background|paper|page|backdrop", "picture": r"picture|photo|print|image|clip",
                 "words": r"words?|text|caption|title|type", "marks": r"marks?|labels?|arrows?|notes?",
                 "output": r"everything|whole|all of it|output|scene|frame"}
_TOOL_WORDS = {"glow": r"glow(ing|y)?|bloom|shine|halo", "vignette": r"vignette|dark(er)? (edges|corners)|edges darker",
               "blur": r"blur(red|ry)?|soft(en|er)?|out of focus|defocus"}


def _graph_ask(clause: str, where: str):
    """A clause that changes the graph: ("layers", (layer, over|under, other)),
    ("tool", (tool, branch, params)) or ("untool", (tool, branch or None))."""
    alt = "|".join
    m = re.search(rf"\b({alt(_LAYER_WORDS.values())})\b.*?\b(behind|under|underneath|below|beneath|over|above|on top of|in front of)\b"
                  rf".*?\b({alt(_LAYER_WORDS.values())})\b", clause)
    if m:
        a = next(k for k, w in _LAYER_WORDS.items() if re.fullmatch(w, m.group(1)))
        b = next(k for k, w in _LAYER_WORDS.items() if re.fullmatch(w, m.group(3)))
        if a != b:
            return ("layers", (a, "under" if m.group(2) in ("behind", "under", "underneath", "below", "beneath") else "over", b))
    branch = next((b for b, w in _BRANCH_WORDS.items() if re.search(rf"\b({w})\b", clause)), None)
    here = {"picture": "picture", "words": "words", "mark": "marks", "marks": "marks"}.get(where)
    for tool, w in _TOOL_WORDS.items():
        if re.search(rf"\b({w})\b", clause):
            on = branch or here or {"blur": "background", "glow": "picture", "vignette": "output"}[tool]
            if re.search(r"\b(no|remove|without|lose|less of|off)\b", clause):
                return ("untool", (tool, branch or here))
            amount = 0.7 if re.search(r"\b(lots|heavy|strong|much|very|more)\b", clause) else 0.2 if re.search(
                r"\b(touch|bit|slight|subtle|little|light)\b", clause) else None
            return ("tool", (tool, on, {"amount": amount} if amount is not None else {}))
    grade = None
    if re.search(r"\b(more contrast|punchier|punchy|contrasty)\b", clause):
        grade = {"contrast": 1.25}
    elif re.search(r"\b(less contrast|flatter|softer contrast)\b", clause):
        grade = {"contrast": 0.8}
    elif re.search(r"\b(muted|desaturate[d]?|less colou?r|washed out)\b", clause):
        grade = {"saturation": 0.6}
    elif re.search(r"\b(vivid|saturated|more colou?r|richer)\b", clause):
        grade = {"saturation": 1.4}
    elif re.search(r"\b(cooler|colder|cold|blue tint)\b", clause):
        grade = {"warmth": -0.5}
    if grade:
        on = branch or here
        return ("tool", ("grade", on if on in ("background", "picture", "output") else "output", grade))
    return None


def understand(text: str, where: str) -> tuple[list[tuple[str, str, object]], list[str]]:
    """Plain asks Venus can do itself: [(part, param, value or fn)], and the clauses it left for the AI.
    `where` is the kind of node the person wrote on."""
    found, rest = [], []
    for clause in re.split(r"[,;.]|\band\b|\bbut\b", text.lower()):
        clause = clause.strip()
        if not clause:
            continue
        g = _graph_ask(clause, where)
        if g:
            found.append(g)
            continue
        hit = False
        sec = re.search(r"(\d+(?:\.\d+)?)\s*(s|sec|secs|seconds)\b", clause)
        if sec:
            found.append(("scene", "seconds", float(sec.group(1))))
            hit = True
        colour = next((c for c in COLOURS if re.search(rf"\b{c}\b", clause)), None)
        for pat, part, param, val in _rules():
            if hit:
                break
            if re.search(pat, clause):
                # "bigger picture" goes to the picture, "bigger" alone to where it was written
                named = next((p for p, w in _TARGET_WORDS.items() if re.search(w, clause)), None)
                if param in ("size",) and (named == "picture" or (where == "picture" and named != "words")):
                    part, val = "picture", (lambda k: (lambda cur: round(min(1.4, max(0.5, float(cur or 1) * k)), 2)))(
                        1.15 if re.search(r"bigger|larger", clause) else 0.87)
                found.append((part, param, val))
                hit = True
        if not hit and colour:
            named = next((p for p, w in _TARGET_WORDS.items() if re.search(w, clause)), None)
            part = "mark" if (named == "mark" or where == "mark") else "picture"
            found.append((part, "colour" if part == "mark" else "shape_colour", COLOURS[colour]))
            hit = True
        if not hit:
            rest.append(clause)
    return found, rest


def describe(doc: dict, nid: str, text: str, stage: str | None = None) -> list[str]:
    """Apply what Venus understands of a description written on a node, keep the
    whole description on the node for the person's AI, and say what was done."""
    import time

    n = find(doc, nid)
    if not n and nid.count(".") == 1 and nid.split(".")[1] in PARTS and (find(doc, nid.split(".")[0]) or {}).get("kind") == "scene":
        n = {"id": nid, "kind": nid.split(".")[1], "of": nid.split(".")[0], "params": {}}
        doc["nodes"].append(n)
    if not n:
        raise SystemExit(f"no node {nid!r}")
    _guard(doc, n, False)
    kind = n["kind"]
    sid = n["id"] if kind == "scene" else n.get("of")
    found, rest = understand(text, "mark" if stage == "marks" else "picture" if stage in ("look", "shape") else kind)
    done = []
    for item in found:
        if item[0] in ("layers", "tool", "untool"):
            if kind not in PARTS + ("scene", "tool") or not sid:
                rest.append(text)
                continue
            done.append(_graph_change(doc, sid, item))
            continue
        part, param, val = item
        if kind == "style":
            target = f"{nid}.{param}" if part == "scene" else f"{nid}.{part}.{param}"
            cur = (n.get("params") or {}).get(param if part == "scene" else f"{part}.{param}")
        elif kind in ("settings", "sound") or not sid:
            rest.append(f"{param} ({part})")
            continue
        else:
            target = f"{sid}.{param}" if part == "scene" else f"{sid}.{part}.{param}"
            holder = find(doc, sid if part == "scene" else f"{sid}.{part}")
            cur = ((holder or {}).get("params") or {}).get(param)
        if callable(val):
            val = val(cur)
        set_param(doc, target, val)
        done.append(f"{target.split('.', 1)[1] if part != 'scene' else param} = {json.dumps(val)}")
    n = find(doc, nid) or find(doc, sid) or n  # an emptied part may have gone
    n["ask"] = {"text": text, "applied": done, "left": rest, "status": "waiting" if rest else "applied",
                "when": time.strftime("%Y-%m-%d %H:%M:%S")}
    if stage:
        n["ask"]["stage"] = stage
    return done


def _graph_change(doc: dict, sid: str, item) -> str:
    what, arg = item
    if what == "layers":
        layer, where, other = arg
        order = layer_to(doc, sid, layer, where, other)
        return f"{layer} {where} {other} (layers: {', '.join(order)})"
    if what == "untool":
        tool, on = arg
        gone = [t for t in tools_of(doc, sid) if t["params"].get("tool") == tool and (on is None or t["params"].get("on") == on)]
        for t in gone:
            remove(doc, t["id"])
        return f"removed {', '.join(t['id'] for t in gone)}" if gone else f"no {tool} to remove"
    tool, on, params = arg
    have = next((t for t in tools_of(doc, sid) if t["params"].get("tool") == tool and t["params"].get("on") == on), None)
    if have:
        have["params"].update(params)
        have.pop("off", None)
        return f"{have['id']} {json.dumps(params) if params else 'on'}"
    return "added " + add_tool(doc, sid, tool, on, **params) + f" on the {on}"


def asks(doc: dict, every: bool = False) -> list[dict]:
    """Descriptions waiting for the person's AI (every=True: also those Venus already did)."""
    return [n for n in doc["nodes"] if n.get("ask") and (every or n["ask"].get("status") in ("waiting", "applied"))]


def answer(doc: dict, nid: str, note: str) -> None:
    n = find(doc, nid)
    if not n or not n.get("ask"):
        raise SystemExit(f"{nid} has no description waiting")
    n["ask"]["status"] = "done"
    n["ask"]["answer"] = note


def asks_text(doc: dict, path: str) -> str:
    """The waiting descriptions, as the person's AI should read them."""
    waiting = [n for n in asks(doc)]
    if not waiting:
        return "no descriptions waiting"
    out = []
    for n in waiting:
        a = n["ask"]
        out.append(f'{n["id"]}: "{a["text"]}"')
        if a.get("applied"):
            out.append("   Venus already did: " + "; ".join(a["applied"]) + " (check it fits, change it if not)")
        if a.get("left"):
            out.append("   for you to do: " + "; ".join(a["left"]))
        out.append("   now: " + (_line(n.get("params") or {}) or "(empty)"))
    out.append(f"Make each change with: alvenus nodes set {path} NODE.PARAM=VALUE ... (see: alvenus nodes guide)")
    out.append(f'Then tell the person what you did: alvenus nodes answer {path} NODE "what you changed, in a few plain words"')
    return "\n".join(out)


def switch(doc: dict, sid: str, stage: str, on: bool, force: bool = False) -> str:
    """Switch one stage of a scene off (to compare without it) or back on."""
    part = next((pt for st, pt, _ in STAGES if st == stage), None)
    if stage not in BYPASS or not part:
        raise SystemExit(f"{stage!r} can't be switched off; these can: {', '.join(BYPASS)}")
    sc = find(doc, sid)
    if not sc or sc["kind"] != "scene":
        raise SystemExit(f"{sid}: give a scene")
    n = find(doc, f"{sid}.{part}")
    if not n:
        if on:
            return f"{sid} {stage} is already on"
        n = {"id": f"{sid}.{part}", "kind": part, "of": sid, "params": {}}
        doc["nodes"].append(n)
    _guard(doc, n, force)
    off = [x for x in (n.get("off") or []) if x != stage] + ([] if on else [stage])
    if off:
        n["off"] = off
    else:
        n.pop("off", None)
        if not n.get("params") and not n.get("ask"):
            doc["nodes"].remove(n)
    if force:
        relock(doc)
    return f"{sid} {stage} {'on' if on else 'off'}"


# ------------------------------------------------------------- the graph


def add_tool(doc: dict, sid: str, tool: str, on: str, force: bool = False, **params) -> str:
    """Put a tool on one branch of a scene's graph (after the tools already there); its new id."""
    from .paper import TOOL_ON, TOOLS, tool_problem

    sc = find(doc, sid)
    if not sc or sc["kind"] != "scene":
        raise SystemExit(f"{sid}: give a scene")
    if tool not in TOOLS:
        raise SystemExit(f"{tool!r}: a tool is one of {', '.join(TOOLS)}" + _near(tool, TOOLS))
    if on not in TOOL_ON[tool]:
        raise SystemExit(f"{tool} can sit on {', '.join(TOOL_ON[tool])}")
    _guard(doc, sc, force)
    p = {"tool": tool, "on": on, **{k: v for k, v in params.items() if v is not None}}
    if why := tool_problem(p):
        raise SystemExit(why)
    taken = {n["id"] for n in doc["nodes"]}
    nid, k = f"{sid}.{tool}", 2
    while nid in taken:
        nid, k = f"{sid}.{tool}{k}", k + 1
    n = {"id": nid, "kind": "tool", "of": sid, "params": p}
    mine = tools_of(doc, sid)
    at = doc["nodes"].index(mine[-1]) + 1 if mine else len(doc["nodes"])
    doc["nodes"].insert(at, n)
    if force:
        relock(doc)
    return nid


def toggle_tool(doc: dict, nid: str, on: bool, force: bool = False) -> None:
    n = find(doc, nid)
    if not n or n["kind"] != "tool":
        raise SystemExit(f"{nid}: not a tool")
    _guard(doc, n, force)
    if on:
        n.pop("off", None)
    else:
        n["off"] = ["tool"]
    if force:
        relock(doc)


def move_tool(doc: dict, nid: str, on: str | None = None, before: str | None = None, force: bool = False) -> None:
    """Move a tool to another branch (on), or ahead of another tool (before)."""
    from .paper import TOOL_ON

    n = find(doc, nid)
    if not n or n["kind"] != "tool":
        raise SystemExit(f"{nid}: not a tool")
    _guard(doc, n, force)
    if on:
        if on not in TOOL_ON[n["params"]["tool"]]:
            raise SystemExit(f"{n['params']['tool']} can sit on {', '.join(TOOL_ON[n['params']['tool']])}")
        n["params"]["on"] = on
    doc["nodes"].remove(n)
    ref = find(doc, before) if before else None
    if ref is not None:
        doc["nodes"].insert(doc["nodes"].index(ref), n)
    else:
        mine = tools_of(doc, n["of"])
        at = doc["nodes"].index(mine[-1]) + 1 if mine else len(doc["nodes"])
        doc["nodes"].insert(at, n)
    if force:
        relock(doc)


def set_layers(doc: dict, sid: str, order: list[str], force: bool = False) -> list[str]:
    """Set what sits over what in a scene (bottom to top); the usual order is shape, picture, words, marks."""
    from .paper import LAYERS

    sc = find(doc, sid)
    if not sc or sc["kind"] != "scene":
        raise SystemExit(f"{sid}: give a scene")
    bad = [x for x in order if x not in LAYERS]
    if bad or len(set(order)) != len(order):
        raise SystemExit(f"layers are {', '.join(LAYERS)}, each once, bottom to top")
    _guard(doc, sc, force)
    full = list(order) + [x for x in LAYERS if x not in order]
    params = sc.setdefault("params", {})
    if full == list(LAYERS):
        params.pop("layers", None)
    else:
        params["layers"] = full
    if force:
        relock(doc)
    return full


def layer_to(doc: dict, sid: str, layer: str, where: str, other: str, force: bool = False) -> list[str]:
    """Put one layer just over or under another ("words", "under", "picture")."""
    from .paper import layers_of

    sc = find(doc, sid)
    if not sc or sc["kind"] != "scene":
        raise SystemExit(f"{sid}: give a scene")
    order = [x for x in layers_of(sc.get("params") or {}) if x != layer]
    if other not in order:
        raise SystemExit(f"{other!r} is not a layer")
    i = order.index(other)
    order.insert(i + (1 if where == "over" else 0), layer)
    return set_layers(doc, sid, order, force)


def graph(doc: dict, sid: str) -> dict:
    """A scene as a graph: branches (each a source and its tools) merged in layer
    order onto the paper, then the output tools. What Studio draws."""
    from .paper import layers_of

    sc = find(doc, sid)
    params = sc.get("params") or {}
    tools = tools_of(doc, sid)
    on = lambda b: [t["id"] for t in tools if (t.get("params") or {}).get("on") == b]
    return {"background": on("background"), "layers": layers_of(params),
            "branches": {b: on(b) for b in ("picture", "words", "marks")}, "output": on("output")}
