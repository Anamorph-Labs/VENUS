"""Three directions for one idea, to pick from before anything is made.

An editor rarely shows one cut. Venus lays the same story out three ways, each
with the reason it exists, and draws a few still frames of each so choosing is
a glance:

  A  your look      the storyboard as written, in its own style
  B  the opposite   the other energy: calm and designed if yours is punchy, quick and bold if yours is calm
  C  tighter        the same style, every scene down to the time its words need, and one scene that
                    can go (the question, or a second step), for feeds where attention is short

Each direction gets the story check too (hook, one idea per scene, the turn,
the payoff), so the creator sees which one tells the story best, not only
which one looks best. Nothing is rendered as a video: only a few frames.

    alvenus directions STORYBOARD            write the three, a page of frames and the reasons
    alvenus directions STORYBOARD --pick B   use direction B (the storyboard then needs the creator's yes again)
"""

from __future__ import annotations

import copy
import json
import shutil
import tempfile
from pathlib import Path

from . import storycheck

ENERGETIC = {"reels-punchy", "hype", "creative-edit", "travel-reel"}
LOOK_KEYS = ("look", "accent", "transition", "transition_seconds", "title_style", "background", "design", "letterbox",
             "lower_third_style", "quote_style")
DROPPABLE = ("question", "step", "moment", "item", "rise", "proof")  # in this order; never the hook, the turn or the payoff


def _opposite(style: str, aspect: str) -> tuple[str, str]:
    vertical = aspect in ("9:16", "4:5")
    if style in ENERGETIC:
        pick = "vox-paper" if vertical else "editorial"
        return pick, "calmer and designed: slower changes, paper and print instead of flashes, more room for each line"
    if style in ("vox-paper", "mono-editorial", "editorial", "calm-story", "dreamy", "documentary", "archive-doc", "sepia-film"):
        pick = "hype" if vertical else "reels-punchy"
        return pick, "quicker and bolder: hard scene changes, titles that land, a darker frame with light that moves"
    pick = "vox-paper" if vertical else "mono-editorial"
    return pick, "designed instead of plain: a printed page, hand-drawn marks and one accent colour"


def _clean(sb: dict) -> dict:
    return {k: v for k, v in copy.deepcopy(sb).items() if not k.startswith("_") or k in ("_idea",)}


def make(sb: dict) -> list[dict]:
    """[{tag, name, why, style, seconds, storyboard, glance, weak}] for A, B and C."""
    from .presets import PRESETS

    aspect = sb.get("aspect") or (sb.get("brief") or {}).get("aspect") or "16:9"
    own = sb.get("style") or ("reels-punchy" if aspect in ("9:16", "4:5") else "explainer")
    out = []

    a = _clean(sb)
    a["style"] = own
    out.append(("A", "Your look", f"as written, in the {own} style", a))

    other, why = _opposite(own, aspect)
    b = _clean(sb)
    for k in LOOK_KEYS:
        b.pop(k, None)
    b["style"] = other
    pace = 0.9 if other in ENERGETIC else 1.12
    for sc in b["scenes"]:
        d = float(sc.get("seconds", 3.0)) * pace
        sc["seconds"] = round(max(d, storycheck.need_seconds(sc) + 0.2, 1.6), 1)
        sc.pop("transition", None)
    out.append(("B", "The opposite energy", f"{why} ({other} style)", b))

    c = _clean(sb)
    c["style"] = own
    scenes = c["scenes"]
    dropped = None
    if len(scenes) > 4:
        beats = [x.get("beat") for x in scenes]
        for beat in DROPPABLE:
            idx = [i for i, x in enumerate(beats) if x == beat]
            if beat == "question" and idx:
                dropped = idx[0]
            elif len(idx) > 1:  # two steps: keep the stronger (fewer words says it faster), drop the other
                dropped = max(idx[1:], key=lambda i: len(storycheck.words_of(scenes[i])))
            if dropped is not None:
                break
    gone = ""
    if dropped is not None:
        gone = f", without the {scenes[dropped].get('beat') or 'scene'} scene (\"{' '.join(storycheck.words_of(scenes[dropped])[:6])}...\")"
        scenes.pop(dropped)
    for i, sc in enumerate(scenes):
        need = storycheck.need_seconds(sc) + (1.0 if i == len(scenes) - 1 else 0.3)
        d = float(sc.get("seconds", 3.0))
        sc["seconds"] = round(max(1.6, min(d, max(need, d * 0.7))), 1)
        if i == 0:
            sc["seconds"] = min(sc["seconds"], max(2.2, round(need, 1)))
    if isinstance(c.get("brief"), dict) and c["brief"].get("seconds"):  # the shorter length is the point of this direction
        c["brief"]["seconds"] = round(sum(float(x.get("seconds", 3)) for x in scenes))
    out.append(("C", "Tighter", f"the same style, every scene only as long as its words need{gone}", c))

    res = []
    for tag, name, why, v in out:
        f = storycheck.check(v)
        res.append({"tag": tag, "name": name, "why": why, "style": v.get("style"), "storyboard": v,
                    "seconds": round(sum(float(x.get("seconds", 3)) for x in v["scenes"]), 1),
                    "glance": storycheck.glance(v, f), "weak": [x.line() for x in storycheck.weak(f)],
                    "known_style": v.get("style") in PRESETS})
    return res


def key_scenes(n: int) -> list[int]:
    """Which scenes to show as frames: the hook, the middle and the payoff."""
    return sorted({0, n // 2, n - 1}) if n > 2 else list(range(n))


def still(sb: dict, k: int, base: Path, w: int, h: int, out: Path) -> None:
    """One frame of scene k, as it will look (a quick small draft of that scene alone; nothing else is kept)."""
    import subprocess  # nosec B404

    from . import media, story
    from .presets import pack

    full = {**pack(sb.get("style"), "aspect", "look", "accent", "transition", "transition_seconds", "title_style",
                   "background", "design", "letterbox", "lower_third_style", "quote_style"), **copy.deepcopy(sb)}
    full = story.load(base / "_directions.json", full)
    one = {**full, "scenes": [full["scenes"][k]], "end_card": None, "music": None, "progress": False,
           "_place": (k, len(full["scenes"]))}
    tmp = Path(tempfile.mkdtemp(prefix="venus-dir-"))
    was = media.DRAFT
    try:
        media.DRAFT = True
        clip = tmp / "s.mp4"
        story.build(one, clip, f"{w}x{h}")
        d = float(full["scenes"][k].get("seconds", 3))
        subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", f"{d * 0.72:.2f}", "-i", str(clip), "-frames:v", "1",  # nosec B603 B607
                        "-q:v", "3", str(out)], check=True, capture_output=True)
    finally:
        media.DRAFT = was
        shutil.rmtree(tmp, ignore_errors=True)


def sheet(dirs: list[dict], base: Path, out: Path) -> Path:
    """A page: one row per direction (its frames, its name, length, why, and the story at a glance)."""
    from PIL import Image, ImageDraw

    from .paper import _font

    aspect = dirs[0]["storyboard"].get("aspect", "16:9")
    w, h = {"9:16": (216, 384), "4:5": (240, 300), "1:1": (270, 270)}.get(aspect, (384, 216))
    tmp = Path(tempfile.mkdtemp(prefix="venus-dirs-"))
    rows = []
    for d in dirs:
        frames = []
        for k in key_scenes(len(d["storyboard"]["scenes"])):
            f = tmp / f"{d['tag']}-{k}.jpg"
            try:
                still(d["storyboard"], k, base, w, h, f)
                frames.append(Image.open(f).convert("RGB").resize((w, h)))
            except Exception:  # nosec B112 - a frame that can't be drawn leaves a blank, not a failure
                frames.append(Image.new("RGB", (w, h), (60, 58, 54)))
        rows.append(frames)
    pad, text_w = 16, 420
    W = pad + 3 * (w + pad) + text_w
    H = pad + len(dirs) * (h + pad)
    page = Image.new("RGB", (W, H), (246, 242, 234))
    dr = ImageDraw.Draw(page)
    big, small, mono = _font("InstrumentSerif-Italic.ttf", 34), _font("LibreBaskerville-Regular.ttf", 14), _font("DMMono-Regular.ttf", 14)
    for r, (d, frames) in enumerate(zip(dirs, rows)):
        y = pad + r * (h + pad)
        for i, im in enumerate(frames):
            page.paste(im, (pad + i * (w + pad), y))
        x = pad + 3 * (w + pad)
        dr.text((x, y), f"{d['tag']}  {d['name']}", fill=(34, 32, 29), font=big)
        dr.text((x, y + 44), f"{d['style']} · {d['seconds']:g} s · {len(d['storyboard']['scenes'])} scenes", fill=(43, 74, 120), font=mono)
        yy, line = y + 70, ""
        for word in d["why"].split() + [None]:
            t = (line + " " + word).strip() if word else line
            if word is None or dr.textlength(t, font=small) > text_w - 20:
                dr.text((x, yy), line, fill=(94, 88, 80), font=small)
                yy += 20
                line = word or ""
            else:
                line = t
        yy += 6
        for label, ok in d["glance"]:
            dr.text((x, yy), f"{'+' if ok else 'x'} {label}", fill=(34, 32, 29) if ok else (150, 60, 40), font=mono)
            yy += 19
    shutil.rmtree(tmp, ignore_errors=True)
    page.save(out, quality=88)
    return out


def write(path: Path, frames: bool = True) -> tuple[list[dict], Path, Path | None]:
    """Write the three directions beside a storyboard (or node file); returns (directions, page.md, sheet.jpg)."""
    from .approval import content

    path = Path(path)
    sb = content(path)
    todo = [i + 1 for i, sc in enumerate(sb.get("scenes") or []) if storycheck.empty(sc)]
    if todo:
        raise SystemExit(f"write the scenes first (not written yet: scene {', '.join(map(str, todo))}); "
                         "then the three directions can show them")
    dirs = make(sb)
    stem = path.name[:-len(".nodes.json")] if path.name.endswith(".nodes.json") else path.stem
    folder = path.with_name(stem + ".directions")
    folder.mkdir(exist_ok=True)
    for d in dirs:
        (folder / f"{d['tag']}.json").write_text(json.dumps(d["storyboard"], indent=2, ensure_ascii=False), encoding="utf-8")
    jpg = sheet(dirs, path.parent, path.with_name(stem + ".directions.jpg")) if frames else None
    md = ["# Three directions", "", f"The same story, three ways. Pick one with `alvenus directions {path.name} --pick A` (or B, C);",
          "the storyboard then needs the creator's yes again before anything is made.", ""]
    for d in dirs:
        md += [f"## {d['tag']}. {d['name']}  ({d['style']}, {d['seconds']:g} s, {len(d['storyboard']['scenes'])} scenes)", "",
               d["why"][0].upper() + d["why"][1:] + ".", ""]
        md += [f"- {'✓' if ok else '✗'} {label}" for label, ok in d["glance"]]
        md += [f"- weak: {w}" for w in d["weak"][:3]] + [""]
    mdp = path.with_name(stem + ".directions.md")
    mdp.write_text("\n".join(md), encoding="utf-8")
    return dirs, mdp, jpg


def pick(path: Path, tag: str) -> dict:
    """Use direction A, B or C: the storyboard (or node file) becomes that direction."""
    from . import nodes as nd

    path = Path(path)
    stem = path.name[:-len(".nodes.json")] if path.name.endswith(".nodes.json") else path.stem
    f = path.with_name(stem + ".directions") / f"{tag.upper()}.json"
    if not f.exists():
        raise SystemExit(f"no direction {tag}: run alvenus directions {path} first")
    v = json.loads(f.read_text(encoding="utf-8"))
    if nd.is_nodes(path):
        nd.write(path, nd.to_nodes(v))
    else:
        path.write_text(json.dumps(v, indent=2, ensure_ascii=False), encoding="utf-8")
    return v
