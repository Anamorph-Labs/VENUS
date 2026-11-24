"""Blend: cut your own clips the way one or more references are cut.

A recipe says which parts of which references to follow, in order, and what to
take from each part:

- rhythm: how long each shot lasts (turned into beats of the reference's music,
  then played on the beats of your song, so the feel survives a new tempo);
- effects: what each shot is (white and black flash frames, negatives, line
  drawings, blueprints, black and white, posters, colour pops, dots, light
  bursts, a subject on a plain colour), redone on your shot;
- light: bright and dark shots in the same places;
- content: what is in each shot (a hand, a clock, stars...), so Venus picks the
  moment in your clips that shows the same thing, where it can.

    {"refs": {"A": "ref1.read.json", "B": "ref2.mp4"},
     "parts": [{"ref": "B", "from": 0, "to": 3.2, "take": ["rhythm", "effects", "light"]},
               {"ref": "A", "from": 13.0, "to": 17.8}],
     "look": "A", "shape": "9:16", "length": null, "on_beat": true}

`alvenus blend RECIPE --clips ... --music ... --out OUT.mp4` plans the cut and
writes, before anything is rendered: the montage plan (OUT.montage.json), a
side-by-side sheet (each reference shot above the shot of yours that answers
it) and a plain report of where every shot comes from. Render it when it's
right with `alvenus montage --plan OUT.montage.json` (or `blend --render`)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

TAKE = ("rhythm", "effects", "light", "content")
# what a reference shot is -> the effect that redoes it on your shot (order matters: looks first, then light)
FX = [("lines", "sketch"), ("blueprint", "blueprint"), ("chalk", "chalk"), ("mono", "mono"), ("poster", "poster"),
      ("pop", "pop"), ("plain", "solid"), ("dots", "dots"), ("negative", "negative"), ("burst", "burst")]
FILL = {"white": "#FFFFFF", "black": "#000000"}


# --- the recipe ----------------------------------------------------------------

def load_recipe(path: Path) -> dict:
    r = json.loads(Path(path).read_text(encoding="utf-8"))
    base = Path(path).parent
    if not isinstance(r.get("refs"), dict) or not r["refs"]:
        raise SystemExit("recipe: 'refs' must name the references, e.g. {\"A\": \"ref1.mp4\"}")
    r["refs"] = {k: str((base / v) if not Path(v).is_absolute() else Path(v)) for k, v in r["refs"].items()}
    if not r.get("parts"):
        raise SystemExit("recipe: 'parts' is empty; list which part of which reference to follow")
    for p in r["parts"]:
        if p.get("ref") not in r["refs"]:
            raise SystemExit(f"recipe: part {p} names a reference that isn't in 'refs'")
        bad = [t for t in p.get("take", TAKE) if t not in TAKE]
        if bad:
            raise SystemExit(f"recipe: take {bad}? choose from {', '.join(TAKE)}")
    return r


def reading(ref: str, say=print) -> dict:
    """A reference's reading: a .read.json, or a video read now (and kept beside it)."""
    p = Path(ref)
    if p.suffix == ".json":
        return json.loads(p.read_text(encoding="utf-8"))
    cached = p.with_suffix(".read.json")
    if cached.exists() and cached.stat().st_mtime >= p.stat().st_mtime:
        r = json.loads(cached.read_text(encoding="utf-8"))
        from .read import VERSION

        if r.get("version") == VERSION:
            return r
    from .read import read

    return read(p, say=say)


# --- 1. slots: the cut to follow -------------------------------------------------

def slots(recipe: dict, readings: dict[str, dict], music_beat: float | None, fps: float = 30.0,
          music_beats: list[float] | None = None) -> list[dict]:
    out: list[dict] = []
    for pi, part in enumerate(recipe["parts"]):
        r = readings[part["ref"]]
        take = set(part.get("take", TAKE))
        a, b = float(part.get("from", 0)), float(part.get("to", r["seconds"]))
        ref_beat = (r.get("music") or {}).get("beat_seconds")
        for s in r["shots"]:
            s0, s1 = s["start"], s["start"] + s["seconds"]
            lo, hi = max(a, s0), min(b, s1)
            if hi - lo < 0.5 / r["frame"]["fps"]:
                continue
            sec = hi - lo
            if "rhythm" not in take:
                sec = music_beat or 0.5
            elif recipe.get("on_beat", True) and music_beat and ref_beat:
                sec = sec / ref_beat * music_beat * _tempo_fold(ref_beat, music_beat)
            out.append({"part": pi, "ref": part["ref"], "ref_shot": s["n"], "ref_at": round((lo + hi) / 2, 3),
                        "seconds": sec, "kinds": list(s["kinds"]) if "effects" in take else [],
                        "light": s["light"] if "light" in take else None,
                        "subject": (s.get("subject") or [])[:1] if "content" in take else [],
                        "busy": s["motion"].get("busy", 0.0), "camera": s["motion"].get("camera", ""),
                        "background": s.get("background"), "palette": s.get("palette", []),
                        "subject_height": s.get("subject_height"),
                        "pop_colour": s.get("pop_colour")})
    if not out:
        raise SystemExit("recipe: those parts hold no shots; check each part's from/to against the reading")
    total = sum(x["seconds"] for x in out)
    if recipe.get("length"):
        k = float(recipe["length"]) / total
        for x in out:
            x["seconds"] *= k
    times = np.cumsum([0.0] + [x["seconds"] for x in out])
    if recipe.get("on_beat", True) and music_beats and len(music_beats) > 1:
        times = _snap(times, music_beats, _subdivision(readings, recipe))
    frames = np.round(times * fps).astype(int)  # whole frames, kept in step with the music
    keep = []
    for i, x in enumerate(out):
        n = int(frames[i + 1] - frames[i])
        if n <= 0:
            continue
        x["frames"] = n
        x["seconds"] = round(n / fps, 4)
        keep.append(x)
    return keep


def _tempo_fold(ref_beat: float, music_beat: float) -> float:
    """Keep the reference's feel at a new tempo: double or halve until the two
    beats are within a factor of about 1.4 (a 70 bpm song cut like a 140 bpm reel
    counts in half beats, not twice as slow)."""
    r = music_beat / ref_beat
    k = 1.0
    while r * k > 1.42:
        k /= 2
    while r * k < 0.71:
        k *= 2
    return k


def _subdivision(readings: dict, recipe: dict) -> int:
    best = 1
    for p in recipe["parts"]:
        m = readings[p["ref"]].get("music") or {}
        if m.get("cuts_on_quarter_beat", 0) >= 0.7 and m.get("cuts_on_half_beat", 0) < 0.6:
            best = max(best, 4)
        elif m.get("cuts_on_half_beat", 0) >= 0.5 and m.get("cuts_on_beat", 0) < 0.6:
            best = max(best, 2)
    return best


def _snap(times: np.ndarray, beats: list[float], sub: int) -> np.ndarray:
    """Move each cut onto the song's grid (beats, half or quarter beats) when one
    is near; tiny flash frames stay where they are, between grid points."""
    period = (beats[-1] - beats[0]) / max(1, len(beats) - 1)
    grid = period / sub
    first = beats[0] % grid
    out = times.copy()
    for i in range(1, len(times) - 1):
        g = first + round((times[i] - first) / grid) * grid
        room = min(times[i] - out[i - 1], times[i + 1] - times[i])
        if abs(g - times[i]) < min(0.35 * grid, 0.45 * room + 1e-6) and g > out[i - 1]:
            out[i] = g
    return out


# --- 2. your shots for the slots -------------------------------------------------

def _content_index(files: list[Path]) -> dict | None:
    """CLIP pictures of every clip every half second, to match what's in a shot."""
    try:
        from . import footage

        if not (footage.model_dir() / "vision_model_quantized.onnx").exists():
            return None
        idx = {}
        for f in files:
            times, arr = footage._frames(f, 0.5)
            if len(arr):
                idx[str(f)] = (np.array(times), footage.embed_frames(arr))
        return idx
    except Exception:
        return None


def choose(sl: list[dict], clips: list, seed: int = 0, in_order: bool = False, match: dict | None = None) -> list:
    """For every slot, the stretch of your clips that answers it: the same kind of
    movement and light, the same kind of thing in it (when CLIP is here), never
    the same clip twice running, spread over all the clips."""
    from .montage import AFPS, Shot, _quality

    rng = np.random.default_rng(seed)
    text = {}
    if match:
        from . import footage

        words = sorted({x["subject"][0] for x in sl if x["subject"]})
        if words:
            text = dict(zip(words, footage.embed_text(words)))
    all_motion = np.concatenate([np.array(c.motion) for c in clips])
    m_lo, m_hi = np.percentile(all_motion, 10), np.percentile(all_motion, 90)
    busy = np.array([x["busy"] for x in sl])
    b_lo, b_hi = (np.percentile(busy, 10), np.percentile(busy, 90)) if len(busy) else (0, 1)
    used: dict[str, list[tuple[float, float]]] = {c.path: [] for c in clips}
    shots: list = []
    last, k_content = None, 0
    for x in sl:
        d = x["seconds"]
        fill = next((FILL[k] for k in x["kinds"] if k in FILL), None)
        if fill is None and "solid" in x["kinds"] and x["palette"]:
            fill = x["palette"][0][0]
        if fill is not None:  # a flash or black beat: no picture needed
            src = shots[-1].clip if shots else clips[0].path
            st = shots[-1].start if shots else 0.0
            shots.append(Shot(src, st, d, why=f"{x['ref']} shot {x['ref_shot']}: {_what(x)}", fx=["fill"],
                              fxo={"fill.colour": fill}))
            continue
        want = m_lo + (m_hi - m_lo) * float(np.clip((x["busy"] - b_lo) / ((b_hi - b_lo) or 1), 0, 1))
        best, best_score, why_c = None, -1e9, ""
        order = clips
        if in_order:
            order = [clips[k_content % len(clips)]]
        for _round in (0, 1):
            for ci in order:
                if ci.path == last and len(clips) > 1 and not in_order:
                    continue
                need = d
                speed = 1.0
                if ci.seconds < need + 0.1:
                    speed = max(0.4, (ci.seconds - 0.1) / need)
                    need = d * speed
                for s in np.arange(0.0, max(0.0, ci.seconds - need) + 1e-6, 0.1 if d < 0.5 else 0.25):
                    e_ = s + need
                    if e_ > ci.seconds - 0.03:
                        break
                    if any(s < c < e_ for c in ci.cuts):
                        continue
                    if _round == 0 and any(s < u1 and e_ > u0 for u0, u1 in used[ci.path]):
                        continue
                    a, b = int(s * AFPS), max(int(s * AFPS) + 1, int(e_ * AFPS))
                    mot = float(np.mean(ci.motion[a:b])) if b <= len(ci.motion) else 0.0
                    score = _quality(ci, a, b) - abs(mot - want) / ((m_hi - m_lo) or 1) * 0.6
                    if x["light"] is not None and not ({"negative", "plain", "dots"} & set(x["kinds"])):
                        lum = float(np.mean(ci.luma[a:b])) if b <= len(ci.luma) else 128
                        score -= abs(lum - x["light"]) / 255 * 0.8
                    sim = 0.0
                    if text and x["subject"] and ci.path in match:
                        tt, emb = match[ci.path]
                        near = np.abs(tt - (s + need / 2)).argmin()
                        sim = float(emb[near] @ text[x["subject"][0]])
                        score += (sim - 0.2) * 12  # CLIP similarities sit around 0.18-0.32
                    score -= 0.3 * len(used[ci.path])
                    score += rng.uniform(0, 0.04)
                    if score > best_score:
                        best, best_score, why_c = (ci, float(s), speed), score, (f"looks like {x['subject'][0]} ({sim:.2f})" if sim > 0.24 else "")
            if best is not None:
                break
            for u in used.values():
                u.clear()
        if best is None:
            best = (clips[0], 0.0, max(0.4, (clips[0].seconds - 0.1) / d))
        ci, s, speed = best
        used[ci.path].append((s, s + d * speed))
        fx, fxo = effects_for(x)
        why = f"{x['ref']} shot {x['ref_shot']}: {_what(x)}" + (f"; {why_c}" if why_c else "")
        shots.append(Shot(ci.path, round(s, 3), d, speed=round(speed, 3), why=why, fx=fx, fxo=fxo))
        last = ci.path
        k_content += 1
    return shots


LOOKS_FX = ("sketch", "blueprint", "chalk", "dots", "poster", "pop", "mono")  # one of these at most: they would fight


def effects_for(x: dict) -> tuple[list[str], dict]:
    fx, fxo = [], {}
    for kind, name in FX:
        if kind in x["kinds"]:
            fx.append(name)
    looks = [f for f in fx if f in LOOKS_FX]
    if len(looks) > 1:
        keep = min(looks, key=LOOKS_FX.index)
        fx = [f for f in fx if f not in LOOKS_FX or f == keep]
    if "solid" in fx:
        bg = x.get("background") or "#000000"
        fxo["solid.colours"] = bg
        fxo["solid.invert"] = False
        if x.get("subject_height") and x["subject_height"] < 0.7:  # a small figure on the colour, as in the reference
            fxo["solid.size"] = max(0.12, x["subject_height"])
        if "negative" in fx:  # the plain colour already is the negative one: invert the subject only
            fx.remove("negative")
            fxo["solid.invert"] = True
        fx = ["solid"] + [f for f in fx if f != "solid"]
    if "dots" in fx:
        fxo["dots.across"] = 60
    if "burst" in fx:  # the burst comes after the looks so it lights the redone picture
        fx = [f for f in fx if f != "burst"] + ["burst"]
    return fx, fxo


def _what(x: dict) -> str:
    from .read import KINDS

    bits = [KINDS[k] for k in x["kinds"]]
    if x["subject"]:
        bits.append(x["subject"][0])
    return ", ".join(bits) or "a plain shot"


# --- 3. before rendering: the sheet and the report -----------------------------

def sheet(sl: list[dict], shots: list, readings: dict, out: Path, size: tuple[int, int], cols: int = 12) -> None:
    """Each reference shot (top) above the shot of yours that answers it, with your
    shot's effects already on it, so the plan can be judged before rendering."""
    from PIL import Image, ImageDraw

    from .fx import apply
    from .read import TAG, _font, frames as ref_frames

    w, h = size
    tw = 104 if h > w else 150
    th = int(tw * h / w)
    cache: dict = {}

    def ref_pic(ref: str, t: float):
        if ref not in cache:
            fr, fps = ref_frames(Path(readings[ref]["file"]), width=160)
            cache[ref] = (fr, fps)
        fr, fps = cache[ref]
        return Image.fromarray(fr[min(len(fr) - 1, int(t * fps))])

    def my_pic(sh) -> Image.Image:
        import subprocess

        from .montage import IMAGES

        t = 0.0 if Path(sh.clip).suffix.lower() in IMAGES else sh.start + sh.source_length() / 2
        raw = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-ss", f"{t:.3f}", "-i", sh.clip, "-frames:v", "1", "-vf",
                              f"scale={tw * 2}:{th * 2}:force_original_aspect_ratio=increase,crop={tw * 2}:{th * 2},format=rgb24",
                              "-f", "rawvideo", "-"], capture_output=True).stdout
        if len(raw) < tw * th * 12:
            return Image.new("RGB", (tw, th), (40, 40, 40))
        f = np.frombuffer(raw[: tw * th * 12], np.uint8).reshape(th * 2, tw * 2, 3)
        if sh.fx:
            try:
                f = apply(np.repeat(f[None], 3, axis=0), 30.0, sh.fx, sh.fxo)[1]
            except Exception:
                pass
        return Image.fromarray(f).resize((tw, th), Image.BILINEAR)

    cell_w, cell_h = tw + 6, 2 * th + 40
    rows = (len(sl) + cols - 1) // cols
    im = Image.new("RGB", (cols * cell_w + 6, 30 + rows * cell_h), (18, 18, 20))
    d = ImageDraw.Draw(im)
    f11, f13 = _font(11), _font(13)
    d.text((8, 8), "top: the reference shot  ·  under it: your shot, effects on  ·  number, length, where it comes from", fill=(230, 230, 230), font=f13)
    for k, (x, sh) in enumerate(zip(sl, shots)):
        cx, cy = 6 + (k % cols) * cell_w, 30 + (k // cols) * cell_h
        top = ref_pic(x["ref"], x["ref_at"]).resize((tw, th), Image.BILINEAR)
        im.paste(top, (cx, cy))
        im.paste(my_pic(sh), (cx, cy + th + 2))
        d.text((cx + 3, cy + 2), str(k + 1), fill=(255, 255, 255), font=f13, stroke_width=2, stroke_fill=(0, 0, 0))
        d.text((cx, cy + 2 * th + 4), f"{x['seconds']:.2f}s  {x['ref']}#{x['ref_shot']}", fill=(200, 200, 200), font=f11)
        tag = " ".join(TAG[t] for t in x["kinds"][:2])
        d.text((cx, cy + 2 * th + 18), tag[:20], fill=(255, 210, 63), font=f11)
    im.save(out, quality=88)


def report(recipe: dict, readings: dict, sl: list[dict], shots: list, music: Path | None, out: Path) -> str:
    lines = [f"# Blend plan for {out.name}", "", "Nothing is rendered yet. Check the sheet, then render with "
             f"`alvenus montage --plan {out.with_suffix('.montage.json').name}`.", "", "## Following", ""]
    for i, p in enumerate(recipe["parts"]):
        r = readings[p["ref"]]
        n = sum(1 for x in sl if x["part"] == i)
        secs = sum(x["seconds"] for x in sl if x["part"] == i)
        parts = [q for q in r["parts"] if q["to"] > float(p.get("from", 0)) and q["from"] < float(p.get("to", r["seconds"]))]
        feel = "; ".join(q["words"].split(";")[0] for q in parts)
        lines.append(f"{i + 1}. **{p['ref']} ({r['name']}) {float(p.get('from', 0)):.1f}-{float(p.get('to', r['seconds'])):.1f} s**, "
                     f"taking {', '.join(p.get('take', TAKE))}: {n} shots, {secs:.1f} s here. In the reference: {feel}.")
    lines.append("")
    if recipe.get("look") in readings:
        lines.append(f"Colour: graded toward {recipe['look']} ({readings[recipe['look']]['name']}).")
    else:
        lines.append("Colour: left as the clips are (no look chosen in the recipe).")
    lines += ["", "## Every shot", "", "| # | length | follows | yours | effects |", "|---|---|---|---|---|"]
    for k, (x, sh) in enumerate(zip(sl, shots)):
        yours = "-" if sh.fx == ["fill"] else f"{Path(sh.clip).name} at {sh.start:.2f} s" + (f" ({sh.why.split('; ', 1)[1]})" if "; " in sh.why else "")
        lines.append(f"| {k + 1} | {x['seconds']:.2f} s ({x['frames']}f) | {x['ref']} shot {x['ref_shot']}: {_what(x)} | {yours} | {', '.join(sh.fx) or '-'} |")
    lines.append("")
    return "\n".join(lines)


# --- the whole step ---------------------------------------------------------------

def plan(recipe_path: Path, clips: list[str], music: Path, out: Path, seed: int = 0, in_order: bool = False,
         say=print) -> tuple[list, dict, Path]:
    from .montage import analyse, find_clips, song_map, save_plan
    from .style import LOOKS

    recipe = load_recipe(recipe_path)
    readings = {k: reading(v, say=say) for k, v in recipe["refs"].items()}
    for k, r in readings.items():
        say(f"{k} = {r['name']}: {r['in_one_line']}")
    files = find_clips(clips)
    if not files:
        raise SystemExit("no clips found")
    say(f"looking at {len(files)} clip(s)")
    infos = [analyse(f) for f in files]
    beats, _, _ = song_map(music)
    beat = (beats[1] - beats[0]) if len(beats) > 1 else None
    sl = slots(recipe, readings, beat, music_beats=beats)
    want_content = any("content" in p.get("take", TAKE) for p in recipe["parts"])
    match = _content_index(files) if want_content else None
    if want_content and match is None:
        say("   (CLIP isn't here: shots are matched by movement and light, not by what's in them)")
    shots = choose(sl, infos, seed=seed, in_order=in_order, match=match)
    shape = recipe.get("shape")
    if not shape:  # only when every reference used agrees; never a guess
        shapes = {readings[p["ref"]]["frame"]["shape"] for p in recipe["parts"]}
        if len(shapes) != 1 or not next(iter(shapes)):
            raise SystemExit(f"recipe: the references are different shapes ({', '.join(sorted(shapes))}); "
                             "set \"shape\" to the one the person wants")
        shape = shapes.pop()
    look = "natural"
    if recipe.get("look") in readings and readings[recipe["look"]].get("colour"):
        from .learnstyle import grade

        look = f"ref-{readings[recipe['look']]['name']}"
        LOOKS[look] = grade(readings[recipe["look"]]["colour"])
    out.parent.mkdir(parents=True, exist_ok=True)
    plan_path = out.with_suffix(".montage.json")
    settings = {"music": str(Path(music).resolve()), "out": str(out.resolve()), "aspect": shape, "look": look,
                "look_filter": LOOKS.get(look, ""), "title": None, "accent": "#FFD23F", "title_style": "stamp",
                "recipe": str(Path(recipe_path).resolve())}
    save_plan(plan_path, shots, settings)
    sizes = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080), "4:5": (1080, 1350)}
    w_, h_ = sizes.get(shape, (1080, 1920))
    sheet(sl, shots, readings, out.with_suffix(".blend.jpg"), (w_, h_))
    out.with_suffix(".blend.md").write_text(report(recipe, readings, sl, shots, music, out), encoding="utf-8")
    return shots, settings, plan_path
