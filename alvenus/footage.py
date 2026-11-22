"""Ask your footage: find the moment you mean in a folder of clips by saying
what is in it ("someone laughing", "lanterns at night", "a close-up of hands").

Venus looks at every clip once, about one frame a second, with CLIP (a free
model from OpenAI, MIT licence, run on this computer), and keeps what it saw
in a small index beside the clips. Each question after that takes a moment.
Nothing leaves the computer.

The model is downloaded once (about 150 MB) from Hugging Face into the same
cache as Whisper."""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path

import numpy as np

from .media import duration, has_video

REPO = "Xenova/clip-vit-base-patch32"  # ONNX export of openai/clip-vit-base-patch32 (MIT)
FILES = ["onnx/text_model_quantized.onnx", "onnx/vision_model_quantized.onnx", "tokenizer.json"]
VIDEO = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".mts"}
IMAGES = {".jpg", ".jpeg", ".png", ".webp"}
MEAN = np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32)
STD = np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32)
INDEX = ".venus-footage.json"
SHEET = "venus-found"  # the results picture Venus writes: never searched itself
VERSION = 1


def model_dir() -> Path:
    base = os.environ.get("ALVENUS_MODELS") or os.path.join(os.path.expanduser("~"), ".cache", "al-venus")
    return Path(base) / "clip-vit-b32"


def fetch() -> Path:
    import urllib.request

    d = model_dir()
    d.mkdir(parents=True, exist_ok=True)
    for f in FILES:
        dest = d / Path(f).name
        if dest.exists() and dest.stat().st_size > 0:
            continue
        print(f"downloading {Path(f).name} (once; about {'65' if 'text' in f else '90' if 'vision' in f else '2'} MB)")
        tmp = dest.with_suffix(dest.suffix + ".part")
        urllib.request.urlretrieve(f"https://huggingface.co/{REPO}/resolve/main/{f}", tmp)  # nosec B310
        tmp.rename(dest)
    return d


# --- CLIP's word pieces (byte-level BPE), in plain Python -----------------

def _bytes_to_unicode() -> dict[int, str]:
    bs = list(range(ord("!"), ord("~") + 1)) + list(range(ord("¡"), ord("¬") + 1)) + list(range(ord("®"), ord("ÿ") + 1))
    cs, n = bs[:], 0
    for b in range(256):
        if b not in bs:
            bs.append(b)
            cs.append(256 + n)
            n += 1
    return dict(zip(bs, map(chr, cs)))


class _Tokenizer:
    PAT = re.compile(r"'s|'t|'re|'ve|'m|'ll|'d|[^\W\d_]+|\d|[^\s\w]+|_+", re.UNICODE)

    def __init__(self, path: Path):
        m = json.loads(path.read_text(encoding="utf-8"))["model"]
        self.vocab = m["vocab"]
        merges = [tuple(x.split()) if isinstance(x, str) else tuple(x) for x in m["merges"]]
        self.ranks = {pair: i for i, pair in enumerate(merges)}
        self.b2u = _bytes_to_unicode()
        self.cache: dict[str, list[str]] = {}

    def _bpe(self, word: str) -> list[str]:
        if word in self.cache:
            return self.cache[word]
        parts = list(word[:-1]) + [word[-1] + "</w>"]
        while len(parts) > 1:
            pairs = [(self.ranks.get((a, b), 1 << 30), i) for i, (a, b) in enumerate(zip(parts, parts[1:]))]
            rank, i = min(pairs)
            if rank == 1 << 30:
                break
            parts = parts[:i] + [parts[i] + parts[i + 1]] + parts[i + 2:]
        self.cache[word] = parts
        return parts

    def encode(self, text: str) -> list[int]:
        text = re.sub(r"\s+", " ", text).strip().lower()
        ids = [self.vocab["<|startoftext|>"]]
        for w in self.PAT.findall(text):
            w = "".join(self.b2u[b] for b in w.encode("utf-8"))
            ids += [self.vocab[p] for p in self._bpe(w) if p in self.vocab]
        return ids[:76] + [self.vocab["<|endoftext|>"]]


@lru_cache(maxsize=1)
def _models():
    import onnxruntime as ort

    d = fetch()
    opt = ort.SessionOptions()
    opt.log_severity_level = 3
    return (ort.InferenceSession(str(d / "text_model_quantized.onnx"), opt),
            ort.InferenceSession(str(d / "vision_model_quantized.onnx"), opt),
            _Tokenizer(d / "tokenizer.json"))


def _unit(x: np.ndarray) -> np.ndarray:
    return x / np.maximum(np.linalg.norm(x, axis=-1, keepdims=True), 1e-8)


def embed_text(queries: list[str]) -> np.ndarray:
    text, _, tok = _models()
    out = []
    for q in queries:  # one at a time: no padding to get wrong
        ids = np.array([tok.encode(f"a photo of {q}")], dtype=np.int64)
        out.append(text.run(None, {"input_ids": ids})[0][0])
    return _unit(np.array(out, dtype=np.float32))


def _frames(path: Path, every: float) -> tuple[list[float], np.ndarray]:
    """Frames at 224x224 (short side scaled, centre cropped), every `every` s."""
    import subprocess

    still = path.suffix.lower() in IMAGES
    vf = f"{'' if still else f'fps=1/{every:g},'}scale=224:224:force_original_aspect_ratio=increase:flags=bicubic,crop=224:224,format=rgb24"
    proc = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(path), "-vf", vf, "-f", "rawvideo", "-"],
                          capture_output=True)
    if proc.returncode != 0:
        return [], np.zeros((0, 224, 224, 3), np.uint8)
    arr = np.frombuffer(proc.stdout, np.uint8)
    arr = arr[: len(arr) // (224 * 224 * 3) * 224 * 224 * 3].reshape(-1, 224, 224, 3)
    times = [0.0] if still else [round(every * (k + 0.5), 2) for k in range(len(arr))]
    return times, arr


def embed_frames(arr: np.ndarray) -> np.ndarray:
    _, vision, _ = _models()
    out = []
    for k in range(0, len(arr), 16):
        x = (arr[k:k + 16].astype(np.float32) / 255.0 - MEAN) / STD
        out.append(vision.run(None, {"pixel_values": x.transpose(0, 3, 1, 2).copy()})[0])
    return _unit(np.concatenate(out).astype(np.float32)) if out else np.zeros((0, 512), np.float32)


def _files(items: list[str]) -> list[Path]:
    files: list[Path] = []
    for it in items:
        p = Path(it)
        if p.is_dir():
            files += sorted(f for f in p.rglob("*") if f.suffix.lower() in VIDEO | IMAGES
                          and not f.name.startswith(".") and not f.stem.startswith(SHEET))
        elif p.exists():
            files.append(p)
    return files


def index(items: list[str], every: float = 1.0, say=print) -> list[dict]:
    """Look at every clip (once: unchanged files are read from the index)."""
    files = _files(items)
    if not files:
        raise SystemExit("no clips or pictures found")
    out = []
    for folder in sorted({f.parent for f in files}):
        path = folder / INDEX
        try:
            old = json.loads(path.read_text(encoding="utf-8"))
            old = old["files"] if old.get("version") == VERSION else {}
        except (OSError, ValueError, KeyError):
            old = {}
        new, changed = {}, False
        for f in [x for x in files if x.parent == folder]:
            st = f.stat()
            key = f"{st.st_size}:{st.st_mtime_ns}:{every}"
            if f.name in old and old[f.name].get("key") == key:
                new[f.name] = old[f.name]
            else:
                if f.suffix.lower() not in IMAGES and not has_video(f):
                    continue
                say(f"   looking at {f.name}")
                times, arr = _frames(f, every if f.suffix.lower() in IMAGES else min(every, max(0.25, duration(f) / 4)))
                emb = embed_frames(arr)
                new[f.name] = {"key": key, "times": times, "vectors": np.round(emb, 4).tolist()}
                changed = True
        if changed or set(new) != set(old):
            path.write_text(json.dumps({"version": VERSION, "files": new}), encoding="utf-8")
        out += [{"file": folder / name, **v} for name, v in new.items()]
    return out


def find(query: str, items: list[str], top: int = 5, every: float = 1.0, say=print) -> list[dict]:
    """The moments that best match the question: file, from, to, how sure."""
    clips = index(items, every, say)
    q = embed_text([query])[0]
    hits = []
    for c in clips:
        v = np.array(c["vectors"], dtype=np.float32)
        if not len(v):
            continue
        s = v @ q
        best = int(np.argmax(s))
        # widen to the neighbouring frames that score nearly as well: the moment, not one frame
        lo = hi = best
        while lo > 0 and s[lo - 1] >= s[best] - 0.015:
            lo -= 1
        while hi < len(s) - 1 and s[hi + 1] >= s[best] - 0.015:
            hi += 1
        step = (c["times"][1] - c["times"][0]) if len(c["times"]) > 1 else 1.0
        hits.append({"file": str(c["file"]), "from": max(0.0, round(c["times"][lo] - step / 2, 2)),
                     "to": round(c["times"][hi] + step / 2, 2), "at": c["times"][best], "score": float(s[best])})
    hits.sort(key=lambda h: -h["score"])
    if hits:  # how sure, against the spread of this folder: the best is 100, an average clip about 0
        scores = np.array([h["score"] for h in hits])
        mid, spread = float(np.median(scores)), float(scores.max() - np.median(scores)) or 1.0
        for h in hits:
            h["match"] = int(round(100 * max(0.0, (h["score"] - mid) / spread)))
    return hits[:top]


def sheet(hits: list[dict], query: str, out: Path) -> None:
    """The found moments side by side, labelled, to check at a glance."""
    from .media import run

    if not hits:
        return
    args = ["ffmpeg", "-nostdin", "-y", "-v", "error"]
    for h in hits:
        args += (["-i", h["file"]] if Path(h["file"]).suffix.lower() in IMAGES else ["-ss", f"{h['at']:.2f}", "-i", h["file"]])
    esc = lambda s: s.replace("\\", "/").replace(":", r"\:").replace("'", "").replace("%", r"\%")
    parts = [f"[{i}:v]trim=end_frame=1,scale=384:216:force_original_aspect_ratio=decrease,pad=384:216:(ow-iw)/2:(oh-ih)/2,setsar=1,"
             f"drawtext=text='{i + 1}  {esc(Path(h['file']).name)} @ {h['at']:.1f}s':x=6:y=h-th-6:fontsize=15:fontcolor=white:"
             f"box=1:boxcolor=black@0.6[f{i}]" for i, h in enumerate(hits)]
    parts.append("".join(f"[f{i}]" for i in range(len(hits))) + (f"hstack=inputs={len(hits)}[s]" if len(hits) > 1 else "null[s]"))
    run(args + ["-filter_complex", ";".join(parts), "-map", "[s]", "-frames:v", "1", str(out)])
