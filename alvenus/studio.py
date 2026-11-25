"""Venus (the editor, by Anamorph Labs): a node editor for a video, in the browser, on this computer.

`alvenus studio video.nodes.json` opens a page laid out like a colour or
compositing page in a finishing app: a viewer at the top, the scenes along
the bottom, the selected scene's nodes wired left to right in the middle, and
an inspector on the right with sliders, colours and lists for the node in hand.

Every change is written to the node file at once, so the person's own AI
can work on the same file side by side: what it changes
shows up here within a second, outlined, and what the person describes in a
node's box is kept on the node for that AI to read (`alvenus nodes listen`).
Nothing leaves the computer; no paid service is called.
"""

from __future__ import annotations

import copy
import os
import hashlib
import json
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import nodes as nd
from .approval import approve

MEDIA_KIND = {**{e: "picture" for e in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".heic")},
              **{e: "clip" for e in (".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi")},
              **{e: "audio" for e in (".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".aif", ".aiff")}}
MEDIA_MAX = 8 << 30  # one file brought in from Studio: 8 GB at most
PREVIEW_SIZES = {"16:9": (960, 540), "9:16": (540, 960), "1:1": (720, 720), "4:5": (720, 900)}


LOOK_NAMES = {  # plain names for the style packs, as people see them
    "reels-punchy": "Punchy reel", "cinematic-doc": "Cinematic documentary", "explainer": "Explainer",
    "podcast-clip": "Podcast clip", "calm-story": "Calm story", "editorial": "Editorial", "dreamy": "Dreamy",
    "hype": "Hype", "mono-editorial": "Black-and-white editorial", "vox-paper": "Paper collage",
    "talk-studio": "Talking head, dark studio", "talk-paper": "Talking head, paper", "documentary": "Documentary",
    "archive-doc": "Archive documentary", "sepia-film": "Sepia film", "travel-reel": "Travel reel",
    "creative-edit": "Creative edit", "trailer": "Trailer", "video-essay": "Video essay",
    "interview-wall": "Interview wall", "podcast-gold": "Podcast, gold", "data-explainer": "Data explainer",
    "wide-band": "Wide band (cinema bars)"}


def look_name(k: str) -> str:
    return LOOK_NAMES.get(k) or k.replace("-", " ").capitalize()


def schema() -> dict:
    """The controls the inspector draws for each kind of node."""
    from .backgrounds import KINDS as BGS
    from .archive import FRAMES
    from .cut import TRANSITIONS
    from .paper import DESIGNS, PHOTOS, SHAPES
    from .presets import PRESETS
    from .style import TITLE_STYLES

    num = lambda lo, hi, step, why="", default=None: {"type": "number", "min": lo, "max": hi, "step": step, "why": why, "default": default}
    pick = lambda opts, why="", default=None, labels=None: {"type": "select", "options": list(opts), "why": why, "default": default,
                                                           **({"labels": labels} if labels else {})}
    text = lambda why="", long=False: {"type": "text", "long": long, "why": why}
    flag = lambda why="", default=None: {"type": "bool", "why": why, "default": default}
    colour = lambda why="", accent=False: {"type": "colour", "accent": accent, "why": why}
    trans = [t for t in TRANSITIONS if t != "cut"]
    return {
        "settings": {"style": pick(PRESETS, "a style pack: look, colour, transitions", None, {k: look_name(k) for k in PRESETS}),
                     "design": pick(DESIGNS, "the designed look", None, {"mono": "Black and white", "paper": "Paper collage"}),
                     "aspect": pick(("16:9", "9:16", "1:1", "4:5"), "shape of the video"), "accent": colour("the one accent colour"),
                     "transition": pick(TRANSITIONS, "how scenes change"), "transition_seconds": num(0.1, 1.2, 0.05, "", 0.4),
                     "title_style": pick(TITLE_STYLES), "quote_style": pick(("card", "verse"), "quotes as a card or quietly over the picture"), "label": text("a small name printed on every page, like a channel name"),
                     "end_card": text("the last words on screen"), "background": pick(BGS, "behind scenes without footage"), "captions": flag("", True),
                     "caption_style": pick(("pop", "keyword", "stack"), "pop: each word lights up as it is said; keyword: one big word over a small row; stack: one big bold word, small rows above and below on one edge", "pop"),
                     "caption_words": text("words per caption card, fewest-most (2-6 unless you choose)"),
                     "caption_placement": pick(("auto", "fixed"), "auto: each card sits where the picture leaves room; fixed: always bottom centre", "auto"),
                     "cut_on_beat": flag("", True),
                     "venus_mark": flag("a small \"Made with Venus\" mark in the corner for the last 2 seconds", True)},
        "sound": {"music": {"type": "media", "media": "audio", "why": "a song or music track: Browse, or drop the file here"},
                  "music_lufs": num(-30, -8, 1, "how loud the music is overall (-16 suits phones)", -16),
                  "voiceover": {"type": "media", "media": "audio", "why": "your recorded voice: Browse, or drop the file here"},
                  "music_duck": num(0, 24, 1, "how far the music dips under the voice, in dB", 12),
                  "voice_gap": num(0, 20, 1, "the voice always sits at least this far over the music, measured on every line (0 = off)", 10),
                  "sound_effects": flag("whooshes and pops", True),
                  "sfx_volume": num(-12, 12, 1, "sound effects louder (+) or softer (-), in dB", 0)},
        "scene": {"seconds": num(0.8, 15, 0.1, "how long the scene lasts", 3), "dark": flag("dark paper instead of light for this scene", False),
                  "background": pick(BGS, "behind a scene without footage")},
        "in": {"transition": pick(trans, "how this scene comes in")},
        "picture": {"file": {"type": "media", "media": "picture", "why": "Browse, drop a photo or clip here, or pick one from Media"}, "from": num(0, 600, 0.1, "start of the clip, in seconds", 0),
                    "size": num(0.5, 1.4, 0.01, "how big the photo sits on the page", 1), "angle": num(-12, 12, 0.5, "turn a still photo left (-) or right (+)", 0),
                    "push": num(-0.2, 0.2, 0.01, "a slow zoom in (+) or out (-) while the scene plays", 0), "label": text("a small caption under the photo"),
                    "frame": pick(FRAMES, "clouds or ink round the picture")},
        "look": {"photo": pick(PHOTOS, "how the photo is printed"), "darken": num(0, 0.6, 0.01, "darken the picture", 0)},
        "shape": {"shape": pick(SHAPES, "what sits behind the print"), "shape_colour": colour("the colour of the shape behind the photo", accent=True)},
        "words": {"text": text("words of a title or text scene", True), "caption": text("words beside a picture", True),
                  "caption_big": text("the word set big on this scene's caption card"),
                  "caption_order": pick(("normal", "big-first"), "stack captions: big-first puts the big word on top and the rest flat under it", "normal"),
                  "caption_place": pick(("auto", "top", "middle", "bottom", "top-left", "top-right", "bottom-left", "bottom-right"),
                                        "where this scene's caption card sits; auto: Venus picks from the picture", "auto"),
                  "caption_small": pick(("auto", "above", "below"), "stack captions: where the small words sit, around the big word", "auto"),
                  "caption_small_x": num(-0.5, 0.5, 0.005, "stack captions: move the small words left (-) or right (+), or drag them in the picture", 0),
                  "caption_small_y": num(-0.5, 0.5, 0.005, "stack captions: move the small words up (-) or down (+)", 0),
                  "caption_big_x": num(-0.5, 0.5, 0.005, "stack captions: move the big word left (-) or right (+), or drag it in the picture", 0),
                  "caption_big_y": num(-0.5, 0.5, 0.005, "stack captions: move the big word up (-) or down (+)", 0),
                  "subtitle": text("small line under a title"), "who": text("who said it"),
                  "year": text("archive: the year beside the photo"), "tag": text("archive: one word in the red tag"),
                  "detail": text("archive: a short typed line under the tag"), "credit": text("an opening credit, Role|Name"),
                  "big_words": {"type": "list", "why": "the huge words"},
                  "size": num(0.4, 2.5, 0.05, "size of the words", 1), "speed": num(0.05, 1.5, 0.01, "seconds between words", None),
                  "delay": num(0, 5, 0.05, "wait before the first word", 0.25), "align": pick(("left", "centre", "right")),
                  "caps": flag("capitals")},
        "marks": {"callout": {"type": "callout", "why": "a loop and a label pointing at one spot"},
                  "note": text("a handwritten note by the arrow"), "colour": colour("colour of the marks"),
                  "show": flag("show the automatic label or arrow", True)},
        "graphic": {k: {"type": "json", "why": ""} for k in nd.PART_KEYS["graphic"]},
    }


class Studio:
    def __init__(self, path: Path):
        self.path = path.resolve()
        self.lock = threading.RLock()
        self._plays: dict[str, threading.Lock] = {}  # one lock per draft file being built
        self.cache = self.path.parent / ".venus-cache" / "studio"
        self.cache.mkdir(parents=True, exist_ok=True)
        self.history: list[str] = []
        self.future: list[str] = []
        self.version = 0
        self.mtime = 0.0
        self.text = ""
        self.by_ai: dict[str, float] = {}  # node id -> when the AI (or anything outside Studio) changed it
        self.render = {"state": "idle"}
        self.proc = None  # the render running now, so Stop can end it
        self.playing: dict[str, str] = {}
        self.upd: dict = {}  # new-version check and the update in progress
        self.dirs: dict = {}  # the three directions, when asked for
        self.port = 8765
        self._load(first=True)

    # ------------------------------------------------------------ the file
    def _load(self, first: bool = False) -> None:
        text = self.path.read_text(encoding="utf-8")
        if text == self.text:
            self.mtime = self.path.stat().st_mtime
            return
        old = None if first else json.loads(self.text)
        doc = json.loads(text)
        if old is not None:  # changed outside Studio: by the person's AI, or by hand
            before = {n["id"]: nd.node_hash(n) for n in old["nodes"]}
            before_asks = {n["id"]: json.dumps(n.get("ask"), sort_keys=True) for n in old["nodes"]}
            now = time.time()
            for n in doc["nodes"]:
                if before.get(n["id"]) != nd.node_hash(n) or before_asks.get(n["id"]) != json.dumps(n.get("ask"), sort_keys=True):
                    self.by_ai[n["id"]] = now
            self.history.append(self.text)
            self.future.clear()
        self.text, self.doc = text, doc
        self.mtime = self.path.stat().st_mtime
        self.version += 1

    def poll(self) -> None:
        with self.lock:
            try:
                if self.path.stat().st_mtime != self.mtime:
                    self._load()
            except (OSError, ValueError):
                pass  # half-written by someone else; read it next time

    def _save(self, doc: dict) -> None:
        problems = nd.check(doc)
        if not problems:
            from . import story

            try:
                story.load(self.path, nd.to_storyboard(doc))
            except SystemExit as e:
                problems = [x.strip() for x in str(e).splitlines()[1:]] or [str(e)]
        if problems:
            raise ValueError("; ".join(problems))
        self.history.append(self.text)
        self.future.clear()
        nd.write(self.path, doc)
        self.text = self.path.read_text(encoding="utf-8")
        self.doc = json.loads(self.text)
        self.mtime = self.path.stat().st_mtime
        self.version += 1

    def change(self, fn) -> None:
        with self.lock:
            doc = copy.deepcopy(self.doc)
            try:
                fn(doc)
            except SystemExit as e:
                raise ValueError(str(e))
            self._save(doc)

    def undo(self, redo: bool = False) -> None:
        with self.lock:
            src, dst = (self.future, self.history) if redo else (self.history, self.future)
            if not src:
                raise ValueError("nothing to " + ("redo" if redo else "undo"))
            dst.append(self.text)
            text = src.pop()
            self.path.write_text(text, encoding="utf-8")
            self.text, self.doc = text, json.loads(text)
            self.mtime = self.path.stat().st_mtime
            self.version += 1

    # ------------------------------------------------------------- state
    def storyboard(self) -> dict:
        from . import story

        sb = nd.effective(story.load(self.path, nd.to_storyboard(self.doc)))
        return sb

    def state(self) -> dict:
        from .storycheck import empty

        with self.lock:
            doc = self.doc
            sb = nd.effective(nd.to_storyboard(doc))
            last = nd.read_last(self.path)
            changed = [c for c in nd.changes(doc, last) if not c.startswith("-")]
            scenes = []
            for k, sn in enumerate(nd.scenes_of(doc)):
                sc = sb["scenes"][k]
                styled = {}
                for u in sn.get("use") or []:
                    for name, v in ((nd.find(doc, u) or {}).get("params") or {}).items():
                        key = nd._style_key(name)
                        if key:
                            styled[key] = {"value": v, "from": u}
                scenes.append({"id": sn["id"], "n": k + 1, "styled": styled, "type": (sn.get("params") or {}).get("type"),
                               "seconds": float(sc.get("seconds", 3.0)), "use": sn.get("use") or [],
                               "graph": nd.graph(doc, sn["id"]),
                               "key": self._key(sb, k), "label": (sc.get("caption") or sc.get("text") or sc.get("title")
                                                                  or sc.get("value") or "")[:60],
                               "beat": sc.get("beat"), "unwritten": bool(sc.get("_job")) and bool(empty(sc))})
            now = time.time()
            return {"version": self.version, "file": self.path.name, "doc": doc, "scenes": scenes, "idea": sb.get("_idea"),
                    "aspect": sb.get("aspect", "16:9"), "design": sb.get("design"), "transition": sb.get("transition", "crossfade"),
                    "byAI": [k for k, t in self.by_ai.items() if now - t < 600], "changed": changed,
                    "built": last.get("built"), "canUndo": bool(self.history), "canRedo": bool(self.future),
                    "render": self.render_state(), "asks": [n["id"] for n in nd.asks(doc)], "problems": nd.check(doc),
                    "aiSeen": nd.ai_seen(self.path), "path": str(self.path.resolve())}

    def _key(self, sb: dict, k: int) -> str:
        sc = sb["scenes"][k]
        keep = {kk: sb.get(kk) for kk in ("design", "accent", "aspect", "label", "background", "style")}
        stamp = []
        for f in (sc.get("file"), sc.get("image")):
            p = Path(f) if f else None
            if p and not p.is_absolute():
                p = self.path.parent / p
            if p and p.exists():
                stamp.append((str(p), p.stat().st_mtime_ns))
        blob = json.dumps([sc, keep, k, len(sb["scenes"]), stamp, 3], sort_keys=True, default=str)
        return hashlib.sha256(blob.encode()).hexdigest()[:14]

    # ----------------------------------------------------------- pictures
    def preview(self, sid: str, at: float) -> Path:
        """A true frame of one scene at a point in it (0 to 1)."""
        with self.lock:
            sb = self.storyboard()
            ids = [n["id"] for n in nd.scenes_of(self.doc)]
        if sid not in ids:
            raise ValueError(f"no scene {sid}")
        k = ids.index(sid)
        sc = sb["scenes"][k]
        d = float(sc.get("seconds", 3.0))
        t = round(max(0.05, min(0.98, at)) * d, 2)
        out = self.cache / f"{self._key(sb, k)}-{t:.2f}.jpg"
        if out.exists():
            return out
        w, h = PREVIEW_SIZES.get(sb.get("aspect", "16:9"), (960, 540))
        from .storycheck import empty

        if sc.get("_job") and empty(sc):  # laid out by the recipe, not written yet: show what this beat is for
            placeholder(sc, k + 1, w, h, out)
            return out
        design = sb.get("design")
        if design and sc["type"] in ("title", "text", "clip", "image"):
            from .paper import plain, still

            first = next((x for x in sb["scenes"] if x["type"] == "title" and x.get("text")), None)
            sc = {**sc, "_design": design, "_accent": sb.get("accent", "#D4F01E"), "_k": k, "_total": len(ids)}
            if design == "mono":
                sc["_label"] = sb.get("label") or (plain(first["text"]) if first else "")
                sc["_words"] = plain(sc.get("text") or sc.get("caption") or "")
            still(sc, w, h, d, t, out)
            return out
        clip = self.play(sid)  # other scenes: a quick draft of the scene, and a frame from it
        subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", str(clip), "-frames:v", "1",
                        "-vf", f"scale={w}:{h}", "-q:v", "3", str(out)], check=True, capture_output=True)
        return out

    def play(self, sid: str) -> Path:
        """The scene alone as a quick draft video, to watch it move."""
        with self.lock:
            sb = self.storyboard()
            ids = [n["id"] for n in nd.scenes_of(self.doc)]
        k = ids.index(sid)
        out = self.cache / f"play-{self._key(sb, k)}.mp4"
        with self._once(out):
            if not out.exists():
                approve(self.path, "you, in Studio")  # pressing play on a scene is the creator's yes to it
                subprocess.run([sys.executable, "-m", "alvenus", "make", str(self.path), "--scene", sid, "--draft", "--out", str(out)],
                               check=True, capture_output=True, cwd=str(self.path.parent))
        return out

    def _once(self, out: Path) -> threading.Lock:
        """One lock per draft file: a frame preview and Play (or two clicks) wait for one build
        instead of building the same draft at once and deleting each other's working files."""
        with self.lock:
            return self._plays.setdefault(out.name, threading.Lock())

    def draft(self) -> Path:
        """The whole video as a quick draft, to play it from start to end with a timeline."""
        with self.lock:
            sb = self.storyboard()
        keys = [self._key(sb, k) for k in range(len(sb["scenes"]))]
        rest = {k: v for k, v in sb.items() if k != "scenes"}
        tag = hashlib.sha256(json.dumps([keys, rest], sort_keys=True, default=str).encode()).hexdigest()[:14]
        out = self.cache / f"all-{tag}.mp4"
        with self._once(out):
            if not out.exists():
                approve(self.path, "you, in Studio")  # playing the whole video is the creator's yes to what is on screen
                subprocess.run([sys.executable, "-m", "alvenus", "make", str(self.path), "--draft", "--no-mark", "--out", str(out)],
                               check=True, capture_output=True, cwd=str(self.path.parent))
        return out

    # ----------------------------------------------------------- media
    def _inside(self, rel: str) -> Path:
        """A path the page asked about, only ever inside this project's folder."""
        root = self.path.parent.resolve()
        p = (root / rel).resolve()
        if p != root and root not in p.parents:
            raise ValueError("that file is outside this project")
        return p

    def media(self) -> list[dict]:
        """Photos, clips and sound in the project folder, and where each is used."""
        root = self.path.parent.resolve()
        with self.lock:
            doc = copy.deepcopy(self.doc)
        used: dict[str, list[str]] = {}
        for n in doc.get("nodes", []):
            for k, v in (n.get("params") or {}).items():
                if k in ("file", "music", "voiceover") and isinstance(v, str) and v:
                    where = {"music": "music", "voiceover": "voice"}.get(k) or n["id"].split(".")[0]
                    try:
                        key = str(self._inside(v).relative_to(root))
                    except ValueError:
                        key = v
                    used.setdefault(key, []).append(where)
        stem = self.path.name.split(".")[0]
        out, seen = [], 0
        for p in sorted(root.rglob("*")):
            rel = p.relative_to(root)
            if any(x.startswith(".") for x in rel.parts) or len(rel.parts) > 4 or not p.is_file():
                continue
            kind = MEDIA_KIND.get(p.suffix.lower())
            if not kind or p.name.startswith(stem + ".") or p.name.startswith(stem + "-v"):  # the video's own renders stay out
                continue
            seen += 1
            if seen > 500:
                break
            out.append({"path": str(rel), "name": p.name, "kind": kind, "size": p.stat().st_size,
                        "used": used.get(str(rel), []), "t": p.stat().st_mtime})
        out.sort(key=lambda m: (not m["used"], -m["t"]))
        return out

    def upload(self, name: str, src, length: int) -> str:
        """A file the creator dropped or picked: copied into the project's media folder. Returns its path in the project."""
        import re

        if length <= 0 or length > MEDIA_MAX:
            raise ValueError("that file is empty or too big to bring in (8 GB at most)")
        stem, dot, ext = Path(name).name.rpartition(".")
        if not dot or "." + ext.lower() not in MEDIA_KIND:
            raise ValueError("Venus takes photos, clips and sound files (for example jpg, png, mp4, mov, mp3, wav)")
        stem = re.sub(r"[^\w\-]+", "-", stem).strip("-")[:60] or "file"
        folder = self.path.parent / "media"
        folder.mkdir(exist_ok=True)
        dest, k = folder / f"{stem}.{ext.lower()}", 2
        if dest.exists() and dest.stat().st_size == length:  # the same file brought in again: keep the one already here
            left = length
            while left > 0:
                chunk = src.read(min(left, 1 << 20))
                if not chunk:
                    break
                left -= len(chunk)
            return str(dest.relative_to(self.path.parent))
        while dest.exists():
            dest, k = folder / f"{stem}-{k}.{ext.lower()}", k + 1
        part = dest.with_name(dest.name + ".part")
        left = length
        with part.open("wb") as fh:
            while left > 0:
                chunk = src.read(min(left, 1 << 20))
                if not chunk:
                    break
                fh.write(chunk)
                left -= len(chunk)
        if left:
            part.unlink(missing_ok=True)
            raise ValueError("the file did not arrive whole; try again")
        part.rename(dest)
        return str(dest.relative_to(self.path.parent))

    def thumb(self, rel: str) -> tuple[Path, str]:
        """A small picture of a media file: the photo itself, or one frame of a clip."""
        p = self._inside(rel)
        kind = MEDIA_KIND.get(p.suffix.lower())
        if not p.is_file() or kind not in ("picture", "clip"):
            raise ValueError("no picture for that file")
        if kind == "picture" and p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
            return p, {".png": "image/png", ".webp": "image/webp", ".gif": "image/gif"}.get(p.suffix.lower(), "image/jpeg")
        tag = hashlib.sha256(f"{p}:{p.stat().st_mtime_ns}".encode()).hexdigest()[:14]
        out = self.cache / f"thumb-{tag}.jpg"
        if not out.exists():
            subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", *(["-ss", "1"] if kind == "clip" else []), "-i", str(p),
                            "-frames:v", "1", "-vf", "scale=320:-2", "-q:v", "4", str(out)], check=True, capture_output=True)
            if not out.exists():  # a clip shorter than a second: its first frame
                subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(p), "-frames:v", "1", "-vf", "scale=320:-2",
                                str(out)], check=True, capture_output=True)
        return out, "image/jpeg"

    def story_check(self) -> dict:
        """The story check on what is on screen, for the creator to read before Render."""
        from . import storycheck
        from .approval import content

        f = storycheck.check(content(self.path))
        sb = content(self.path)
        return {"weak": [x.line() for x in storycheck.weak(f)], "notes": [x.line() for x in f if x.level == "note"],
                "question": storycheck.question(sb, f), "promise": storycheck.promise(sb),
                "openings": storycheck.openings(sb, f),
                "unwritten": [x.scene for x in f if x.level == "weak" and x.what.startswith("no ") and x.what.endswith(" yet")]}

    def start_render(self, anyway: bool = False) -> None:
        chk = self.story_check()
        if chk["unwritten"]:
            raise ValueError("not written yet: scene " + ", ".join(map(str, chk["unwritten"])) +
                             ". Your AI fills them in; then press Render.")
        if chk["weak"] and not anyway:
            raise ValueError("STORY:" + json.dumps({"weak": chk["weak"], "question": chk["question"],
                                                    "openings": chk["openings"]}))
        with self.lock:
            if self.render.get("state") == "running":
                raise ValueError("a render is already running")
            name = self.path.name[:-len(".nodes.json")] if self.path.name.endswith(".nodes.json") else self.path.stem
            out = self.path.with_name(name + ".mp4")
            self.render = {"state": "running", "started": time.time(), "video": out.name}

        approve(self.path, "you, in Studio")  # pressing Render is the creator's yes to what is on screen
        try:
            from . import storycheck, taste
            from .approval import content

            sb = content(self.path)
            taste.approved(self.path, sb, storycheck.check(sb))  # what still stands is how this creator likes it
        except Exception:  # nosec B110 - learning is a bonus and must never stop a render
            pass

        prog = self.cache / "render-progress.json"
        prog.unlink(missing_ok=True)
        self.render["progress"] = str(prog)

        def go():
            env = dict(os.environ, VENUS_PROGRESS=str(prog))
            group = {"start_new_session": True} if os.name == "posix" else {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
            p = subprocess.Popen([sys.executable, "-m", "alvenus", "make", str(self.path), "--out", str(out)],  # nosec B603
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=str(self.path.parent), env=env, **group)
            self.proc = p
            text = p.communicate()[0] or ""
            tail = [x for x in text.strip().splitlines() if x.strip()][-6:]
            stopped = self.render.get("stopping")
            self.render = {"state": "stopped" if stopped else "done" if p.returncode == 0 else "failed", "video": out.name, "log": tail,
                           "started": self.render["started"], "seconds": round(time.time() - self.render["started"])}
            self.proc = None

        threading.Thread(target=go, daemon=True).start()

    def stop_render(self) -> None:
        """Stop the render in progress (the last finished video, if any, stays as it was)."""
        p = getattr(self, "proc", None)
        if self.render.get("state") != "running" or p is None:
            raise ValueError("no render is running")
        self.render["stopping"] = True
        if os.name == "posix":  # the make and every ffmpeg it started
            import signal
            try:
                os.killpg(p.pid, signal.SIGTERM)
                return
            except OSError:
                pass
        p.terminate()

    def render_state(self) -> dict:
        """The render, with where it stands while it runs (scene k of n)."""
        r = {k: v for k, v in self.render.items() if k != "progress"}
        if r.get("state") == "running" and self.render.get("progress"):
            try:
                r.update(json.loads(Path(self.render["progress"]).read_text(encoding="utf-8")))
            except (OSError, ValueError):
                pass
        return r

    def start_directions(self) -> dict:
        """Lay the storyboard out three ways (your look, the opposite energy, tighter) with frames of each."""
        from . import directions as dr

        if self.dirs.get("state") == "running":
            return {"state": "running"}
        self.dirs = {"state": "running", "started": time.time()}

        def go():
            try:
                dirs, md, jpg = dr.write(self.path)
                self.dirs = {"state": "done", "sheet": str(jpg), "list": [
                    {"tag": d["tag"], "name": d["name"], "why": d["why"], "style": d["style"], "seconds": d["seconds"],
                     "scenes": len(d["storyboard"]["scenes"]), "glance": d["glance"]} for d in dirs]}
            except (Exception, SystemExit) as e:  # never leave the page waiting
                self.dirs = {"state": "failed", "why": str(e)[-300:]}
        threading.Thread(target=go, daemon=True).start()
        return {"state": "running"}

    def pick_direction(self, tag: str) -> None:
        stem = self.path.name[:-len(".nodes.json")] if self.path.name.endswith(".nodes.json") else self.path.stem
        f = self.path.with_name(stem + ".directions") / f"{tag.upper()}.json"
        if tag.upper() not in ("A", "B", "C") or not f.exists():
            raise ValueError("make the three directions first")
        v = json.loads(f.read_text(encoding="utf-8"))
        self.change(lambda d: d.update(nodes=nd.to_nodes(v)["nodes"]))  # one step: Undo brings the old one back

    def update_state(self, now: bool = False) -> dict:
        from . import update as up

        u = self.upd
        if u.get("busy"):
            return {"busy": True, "log": list(u.get("log", []))}
        if u.get("done"):  # report how it went once (on success Studio restarts on the new version)
            u["done"] = False
            return {"busy": False, "result": u.get("result"), "check": u.get("check")}
        if now or "check" not in u:
            def go():
                u["check"] = up.check(quiet_cache=not now)
            if now:
                go()
            elif not u.get("checking"):
                u["checking"] = True
                threading.Thread(target=go, daemon=True).start()
        return {"check": u.get("check"), "busy": False}

    def start_update(self) -> dict:
        """Install the new version in the background, then restart Studio on it (the page reloads itself)."""
        from . import update as up

        u = self.upd
        if u.get("busy"):
            return {"busy": True}
        u.update(busy=True, log=[], done=False)

        def go():
            try:
                res = up.install(log=lambda m: u["log"].append(m))
            except SystemExit as e:
                res = {"ok": False, "why": str(e)}
            except Exception as e:  # never leave the page waiting
                res = {"ok": False, "why": f"{type(e).__name__}: {e}"}
            u.update(busy=False, done=True, result=res)
            if res.get("ok"):  # start the new Studio in place of this one, on the same file and port
                time.sleep(1.2)
                restart([str(self.path)])
        threading.Thread(target=go, daemon=True).start()
        return {"busy": True}


def restart(args: list[str]) -> None:
    """Start Studio again in place of this process, on the same port (the page reloads itself)."""
    os.execv(sys.executable, [sys.executable, "-m", "alvenus", "studio", *args, "--port", str(_PORT[0]), "--no-open"])  # nosec B606


_PORT = [8765]


def placeholder(sc: dict, n: int, w: int, h: int, out: Path) -> None:
    """A beat the AI has not written yet: its name and its job, on ivory, so the creator sees the shape of the video."""
    from PIL import Image, ImageDraw

    from .paper import _font

    img = Image.new("RGB", (w, h), (246, 242, 234))
    d = ImageDraw.Draw(img)
    u = min(w, h)
    m = round(u * 0.08)
    d.rounded_rectangle((m // 2, m // 2, w - m // 2, h - m // 2), radius=round(u * 0.04), outline=(201, 193, 181), width=2)
    small = _font("DMMono-Regular.ttf", round(u * 0.035))
    big = _font("InstrumentSerif-Italic.ttf", round(u * 0.085))
    body = _font("LibreBaskerville-Regular.ttf", round(u * 0.036))
    d.text((m, m), f"SCENE {n} · {str(sc.get('beat') or '').upper()} · {float(sc.get('seconds', 3)):g} s", fill=(43, 74, 120), font=small)
    d.text((m, m + round(u * 0.07)), str(sc.get("beat") or "scene").capitalize(), fill=(34, 32, 29), font=big)
    words, line, y = str(sc.get("_job") or "").split(), "", m + round(u * 0.2)
    for wd in words + [None]:
        trial = (line + " " + wd).strip() if wd else line
        if wd is None or d.textlength(trial, font=body) > w - 2 * m:
            d.text((m, y), line, fill=(94, 88, 80), font=body)
            y += round(u * 0.055)
            line = wd or ""
        else:
            line = trial
    d.text((m, h - m - round(u * 0.04)), "waiting for your AI to write it", fill=(140, 131, 120), font=small)
    img.save(out, quality=90)


def home_handler(folder: Path):
    """Studio with no file open: the welcome page, with the "Describe your video" box and the videos in this folder."""
    page = (Path(__file__).with_name("studio_home.html")).read_text(encoding="utf-8")

    def projects() -> list[dict]:
        out = []
        for p in sorted(list(folder.glob("*.nodes.json")) + list(folder.glob("*/*.nodes.json")),
                        key=lambda p: p.stat().st_mtime, reverse=True)[:30]:
            out.append({"path": str(p.relative_to(folder)), "name": p.name[:-len(".nodes.json")],
                        "at": time.strftime("%d %b, %H:%M", time.localtime(p.stat().st_mtime))})
        return out

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body: bytes, kind: str):
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code=200):
            self._send(code, json.dumps(obj).encode(), "application/json")

        def do_GET(self):
            u = urlparse(self.path)
            if u.path == "/":
                return self._send(200, page.encode(), "text/html; charset=utf-8")
            if u.path.startswith("/fonts/"):
                f = Path(__file__).with_name("studio_fonts") / Path(u.path).name
                kind = {".woff2": "font/woff2", ".png": "image/png", ".svg": "image/svg+xml", ".ico": "image/x-icon"}.get(f.suffix)
                if kind and f.exists():
                    return self._send(200, f.read_bytes(), kind)
            if u.path == "/api/home":
                from . import brief as br
                from .presets import PRESETS

                return self._json({"home": True, "folder": str(folder), "projects": projects(),
                                   "kinds": [[k, br.NAMES[k], br.RECIPES[k]["about"]] for k in br.KINDS],
                                   "looks": [[k, v.get("about", ""), look_name(k)] for k, v in PRESETS.items() if not v.get("talk")]})
            if u.path == "/api/state":
                return self._json({"home": True})
            self._json({"error": "not found"}, 404)

        def do_POST(self):
            u = urlparse(self.path)
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
            try:
                if u.path == "/api/idea":
                    from . import ideas

                    e = ideas.create(body.get("text", ""), folder, body.get("kind") or "", body.get("seconds") or None,
                                     body.get("aspect") or "", body.get("look") or "")
                    threading.Timer(0.6, lambda: restart([e["nodes"]])).start()
                    return self._json({"opening": e["nodes"], "id": e["id"]})
                if u.path == "/api/open":
                    known = {p["path"] for p in projects()}
                    if body.get("path") not in known:
                        raise ValueError("that video is not in this folder")
                    threading.Timer(0.6, lambda: restart([str(folder / body["path"])])).start()
                    return self._json({"opening": body["path"]})
            except (ValueError, OSError) as e:
                return self._json({"error": str(e)}, 400)
            self._json({"error": "unknown"}, 404)

    return H


def handler(st: Studio):
    page = (Path(__file__).with_name("studio.html")).read_text(encoding="utf-8")

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):  # quiet
            pass

        def _send(self, code: int, body: bytes, kind: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code: int = 200) -> None:
            self._send(code, json.dumps(obj, default=str).encode(), "application/json")

        def _file(self, p: Path, kind: str) -> None:
            size = p.stat().st_size
            rng = self.headers.get("Range")
            if rng and kind == "video/mp4":  # browsers seek videos with ranges
                a, _, b = rng.replace("bytes=", "").partition("-")
                a = int(a or 0)
                b = min(int(b) if b else size - 1, size - 1)
                self.send_response(206)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Range", f"bytes {a}-{b}/{size}")
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Length", str(b - a + 1))
                self.end_headers()
                with p.open("rb") as fh:
                    fh.seek(a)
                    left = b - a + 1
                    while left > 0:
                        chunk = fh.read(min(left, 1 << 20))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        left -= len(chunk)
                return
            self._send(200, p.read_bytes(), kind)

        def do_GET(self):
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            try:
                from .paper import LAYERS, TOOL_ON, TOOLS

                if u.path == "/":
                    return self._send(200, page.encode(), "text/html; charset=utf-8")
                if u.path.startswith("/fonts/"):  # the interface's own type, served from the package (nothing is fetched)
                    f = Path(__file__).with_name("studio_fonts") / Path(u.path).name
                    kind = {".woff2": "font/woff2", ".png": "image/png", ".svg": "image/svg+xml", ".ico": "image/x-icon"}.get(f.suffix)  # type, logo and tab icon
                    if kind and f.exists():
                        return self._send(200, f.read_bytes(), kind)
                if u.path == "/api/update":  # is a new Venus ready? (checked quietly, a few times a day)
                    return self._json(st.update_state(q.get("now") == "1"))
                if u.path == "/api/directions":
                    return self._json(st.dirs or {"state": "none"})
                if u.path == "/api/directions.jpg" and st.dirs.get("sheet") and Path(st.dirs["sheet"]).exists():
                    return self._file(Path(st.dirs["sheet"]), "image/jpeg")
                if u.path == "/api/state":
                    st.poll()
                    return self._json(st.state())
                if u.path == "/api/schema":
                    return self._json({"schema": schema(), "stages": [[a, b, list(c)] for a, b, c in nd.STAGES],
                                       "bypass": list(nd.BYPASS), "what": nd.WHAT, "file": st.path.name,
                                       "partKeys": {k: list(v) for k, v in nd.PART_KEYS.items()},
                                       "tools": {k: {p: list(r) for p, r in v.items()} for k, v in TOOLS.items()},
                                       "toolOn": {k: list(v) for k, v in TOOL_ON.items()}, "layers": list(LAYERS)})
                if u.path == "/api/preview":
                    return self._file(st.preview(q["scene"], float(q.get("at", 0.6))), "image/jpeg")
                if u.path == "/api/play":
                    return self._file(st.play(q["scene"]), "video/mp4")
                if u.path == "/api/draft":
                    return self._file(st.draft(), "video/mp4")
                if u.path == "/api/media":
                    return self._json({"media": st.media()})
                if u.path == "/api/thumb":
                    f, kind = st.thumb(q["file"])
                    return self._file(f, kind)
                if u.path == "/api/video":
                    v = st.path.with_name(st.render.get("video") or "")
                    if st.render.get("video") and v.exists():
                        return self._file(v, "video/mp4")
                    return self._json({"error": "no video yet"}, 404)
            except (ValueError, KeyError, subprocess.CalledProcessError) as e:
                msg = e.stderr.decode(errors="replace")[-400:] if isinstance(e, subprocess.CalledProcessError) and e.stderr else str(e)
                return self._json({"error": msg}, 400)
            self._json({"error": "not found"}, 404)

        def do_POST(self):
            u = urlparse(self.path)
            n = int(self.headers.get("Content-Length") or 0)
            if u.path == "/api/upload":  # a dropped or picked file arrives as the raw body, its name in a header
                from urllib.parse import unquote

                try:
                    return self._json({"path": st.upload(unquote(self.headers.get("X-Name") or "file"), self.rfile, n)})
                except ValueError as e:
                    return self._json({"error": str(e)}, 400)
            body = json.loads(self.rfile.read(n) or b"{}")
            try:
                op = u.path.rsplit("/", 1)[-1]
                if op == "set":
                    st.change(lambda d: [nd.set_param(d, t, v, body.get("force", False)) for t, v in body["changes"]])
                elif op == "describe":
                    did = []
                    st.change(lambda d: did.extend(nd.describe(d, body["node"], body["text"], body.get("stage"))))
                    return self._json({"did": did, "state": st.state()})
                elif op == "tool_add":
                    made = []
                    st.change(lambda d: made.append(nd.add_tool(d, body["scene"], body["tool"], body["on"], **(body.get("params") or {}))))
                    if body.get("before"):
                        st.change(lambda d: nd.move_tool(d, made[0], before=body["before"]))
                    return self._json({"made": made[0], "state": st.state()})
                elif op == "tool_copy":
                    made = []

                    def dup(d):
                        t = nd.find(d, body["node"])
                        if not t or t["kind"] != "tool":
                            raise SystemExit("only a tool can be duplicated here; scenes copy from the strip")
                        p = {k: v for k, v in t["params"].items() if k not in ("tool", "on")}
                        made.append(nd.add_tool(d, t["of"], t["params"]["tool"], t["params"]["on"], **p))
                    st.change(dup)
                    return self._json({"made": made[0], "state": st.state()})
                elif op == "tool_toggle":
                    st.change(lambda d: nd.toggle_tool(d, body["node"], body.get("on", True)))
                elif op == "tool_move":
                    st.change(lambda d: nd.move_tool(d, body["node"], body.get("on"), body.get("before")))
                elif op == "layers":
                    st.change(lambda d: nd.set_layers(d, body["scene"], body["order"]))
                elif op == "lock":
                    st.change(lambda d: nd.lock(d, [body["node"]], body.get("on", True)))
                elif op == "switch":
                    st.change(lambda d: nd.switch(d, body["scene"], body["stage"], body.get("on", True)))
                elif op == "use":
                    st.change(lambda d: nd.use(d, body["style"], [body["scene"]], body.get("on", True)))
                elif op == "move":
                    st.change(lambda d: nd.move(d, body["scene"], body.get("after"), body.get("before"), body.get("first", False)))
                elif op == "copy":
                    st.change(lambda d: nd.copy_scene(d, body["scene"]))
                elif op == "remove":
                    st.change(lambda d: nd.remove(d, body["node"]))
                elif op == "clear":  # the person has seen what the AI changed
                    st.by_ai.clear()
                elif op == "undo":
                    st.undo()
                elif op == "redo":
                    st.undo(redo=True)
                elif op == "render":
                    st.start_render(bool(body.get("anyway")))
                elif op == "render_stop":
                    st.stop_render()
                elif op == "directions":
                    return self._json(st.start_directions())
                elif op == "direction_pick":
                    st.pick_direction(str(body.get("tag", "")))
                elif op == "check":
                    return self._json(st.story_check())
                elif op == "home":  # "New video": back to the welcome page, in the folder Studio was started from
                    threading.Timer(0.6, lambda: restart([])).start()
                    return self._json({"restarting": True})
                elif op == "update":  # the person pressed Update: back up, install, check, roll back on failure
                    return self._json(st.start_update())
                else:
                    return self._json({"error": "unknown"}, 404)
            except (ValueError, KeyError) as e:
                return self._json({"error": str(e)}, 400)
            self._json({"state": st.state()})

    return H


def serve(path: Path | None, port: int = 8765, open_browser: bool = True) -> None:
    if path is not None and not nd.is_nodes(path):
        raise SystemExit(f"{path} is not a node file; make one with: alvenus nodes init STORYBOARD.json")
    st = Studio(path) if path is not None else None
    h = handler(st) if st else home_handler(Path.cwd())
    for p in range(port, port + 20):
        try:
            # (after a restart the old socket may linger for a moment: try the same port a few times first)
            for _ in range(20 if p == port else 1):
                try:
                    srv = ThreadingHTTPServer(("127.0.0.1", p), h)
                    break
                except OSError:
                    time.sleep(0.15)
            else:
                raise OSError
            break
        except OSError:
            continue
    else:
        raise SystemExit("no free port for Studio")
    _PORT[0] = p
    if st:
        st.port = p
    url = f"http://127.0.0.1:{p}/"
    print(f"Venus is open at {url} (press Ctrl+C to close it)")
    if st is None:
        print("Describe a video on the welcome page; your AI picks it up with: alvenus ideas")
    else:
        print(f"Your AI can work on the same file: alvenus nodes show {path}; descriptions you write wait in: alvenus nodes listen {path}")
    if open_browser:
        import webbrowser

        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nStudio closed")
