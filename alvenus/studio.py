"""Venus Studio: a node editor for a video, in the browser, on this computer.

`alvenus studio video.nodes.json` opens a page laid out like a colour or
compositing page in a finishing app: a viewer at the top, the scenes along
the bottom, the selected scene's nodes wired left to right in the middle, and
an inspector on the right with sliders, colours and lists for the node in hand.

Every change is written to the node file at once, so the person's own AI
(Claude, Codex...) can work on the same file side by side: what it changes
shows up here within a second, outlined, and what the person describes in a
node's box is kept on the node for that AI to read (`alvenus nodes listen`).
Nothing leaves the computer; no paid service is called.
"""

from __future__ import annotations

import copy
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

PREVIEW_SIZES = {"16:9": (960, 540), "9:16": (540, 960), "1:1": (720, 720), "4:5": (720, 900)}


def schema() -> dict:
    """The controls the inspector draws for each kind of node."""
    from .backgrounds import KINDS as BGS
    from .cut import TRANSITIONS
    from .paper import DESIGNS, PHOTOS, SHAPES
    from .presets import PRESETS
    from .style import TITLE_STYLES

    num = lambda lo, hi, step, why="", default=None: {"type": "number", "min": lo, "max": hi, "step": step, "why": why, "default": default}
    pick = lambda opts, why="", default=None: {"type": "select", "options": list(opts), "why": why, "default": default}
    text = lambda why="", long=False: {"type": "text", "long": long, "why": why}
    flag = lambda why="", default=None: {"type": "bool", "why": why, "default": default}
    colour = lambda why="", accent=False: {"type": "colour", "accent": accent, "why": why}
    trans = [t for t in TRANSITIONS if t != "cut"]
    return {
        "settings": {"style": pick(PRESETS, "a style pack: look, colour, transitions"), "design": pick(DESIGNS, "the designed look"),
                     "aspect": pick(("16:9", "9:16", "1:1", "4:5"), "shape of the video"), "accent": colour("the one accent colour"),
                     "transition": pick(TRANSITIONS, "how scenes change"), "transition_seconds": num(0.1, 1.2, 0.05, "", 0.4),
                     "title_style": pick(TITLE_STYLES), "label": text("the name printed on the page"),
                     "end_card": text("last words on screen"), "background": pick(BGS), "captions": flag("", True),
                     "cut_on_beat": flag("", True)},
        "sound": {"music": text("music file"), "music_lufs": num(-30, -8, 1, "music loudness", -16), "voiceover": text("voice file"),
                  "sound_effects": flag("whooshes and pops", True)},
        "scene": {"seconds": num(0.8, 15, 0.1, "how long the scene lasts", 3), "dark": flag("a dark page", False),
                  "background": pick(BGS, "behind a scene without footage")},
        "in": {"transition": pick(trans, "how this scene comes in")},
        "picture": {"file": text("photo or clip"), "from": num(0, 600, 0.1, "start of the clip, in seconds", 0),
                    "size": num(0.5, 1.4, 0.01, "size of the print", 1), "angle": num(-12, 12, 0.5, "tilt of a still print", 0),
                    "push": num(-0.2, 0.2, 0.01, "slow zoom (normal scenes)", 0), "label": text("figure caption under the print")},
        "look": {"photo": pick(PHOTOS, "how the photo is printed"), "darken": num(0, 0.6, 0.01, "darken the picture", 0)},
        "shape": {"shape": pick(SHAPES, "what sits behind the print"), "shape_colour": colour("its colour", accent=True)},
        "words": {"text": text("words of a title or text scene", True), "caption": text("words beside a picture", True),
                  "subtitle": text("small line under a title"), "who": text("who said it"),
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
        self.cache = self.path.parent / ".venus-cache" / "studio"
        self.cache.mkdir(parents=True, exist_ok=True)
        self.history: list[str] = []
        self.future: list[str] = []
        self.version = 0
        self.mtime = 0.0
        self.text = ""
        self.by_ai: dict[str, float] = {}  # node id -> when the AI (or anything outside Studio) changed it
        self.render = {"state": "idle"}
        self.playing: dict[str, str] = {}
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
                                                                  or sc.get("value") or "")[:60]})
            now = time.time()
            return {"version": self.version, "file": self.path.name, "doc": doc, "scenes": scenes,
                    "aspect": sb.get("aspect", "16:9"), "design": sb.get("design"), "transition": sb.get("transition", "crossfade"),
                    "byAI": [k for k, t in self.by_ai.items() if now - t < 600], "changed": changed,
                    "built": last.get("built"), "canUndo": bool(self.history), "canRedo": bool(self.future),
                    "render": self.render, "asks": [n["id"] for n in nd.asks(doc)], "problems": nd.check(doc)}

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
        return hashlib.sha1(blob.encode()).hexdigest()[:14]

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
        if not out.exists():
            subprocess.run([sys.executable, "-m", "alvenus", "make", str(self.path), "--scene", sid, "--draft", "--out", str(out)],
                           check=True, capture_output=True, cwd=str(self.path.parent))
        return out

    def start_render(self) -> None:
        with self.lock:
            if self.render.get("state") == "running":
                raise ValueError("a render is already running")
            name = self.path.name[:-len(".nodes.json")] if self.path.name.endswith(".nodes.json") else self.path.stem
            out = self.path.with_name(name + ".mp4")
            self.render = {"state": "running", "started": time.time(), "video": out.name}

        def go():
            r = subprocess.run([sys.executable, "-m", "alvenus", "make", str(self.path), "--out", str(out)],
                               capture_output=True, text=True, cwd=str(self.path.parent))
            tail = [x for x in (r.stdout + r.stderr).strip().splitlines() if x.strip()][-6:]
            self.render = {"state": "done" if r.returncode == 0 else "failed", "video": out.name, "log": tail,
                           "seconds": round(time.time() - self.render["started"])}

        threading.Thread(target=go, daemon=True).start()


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
                    if f.suffix == ".woff2" and f.exists():
                        return self._send(200, f.read_bytes(), "font/woff2")
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
                    st.start_render()
                else:
                    return self._json({"error": "unknown"}, 404)
            except (ValueError, KeyError) as e:
                return self._json({"error": str(e)}, 400)
            self._json({"state": st.state()})

    return H


def serve(path: Path, port: int = 8765, open_browser: bool = True) -> None:
    if not nd.is_nodes(path):
        raise SystemExit(f"{path} is not a node file; make one with: alvenus nodes init STORYBOARD.json")
    st = Studio(path)
    for p in range(port, port + 20):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", p), handler(st))
            break
        except OSError:
            continue
    else:
        raise SystemExit("no free port for Studio")
    url = f"http://127.0.0.1:{p}/"
    print(f"Venus Studio is open at {url} (press Ctrl+C to close it)")
    print(f"Your AI can work on the same file: alvenus nodes show {path}; descriptions you write wait in: alvenus nodes listen {path}")
    if open_browser:
        import webbrowser

        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nStudio closed")
