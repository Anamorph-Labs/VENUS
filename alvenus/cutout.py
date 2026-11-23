"""Cut-outs: find the person or the object in a shot and lift it off its
background, so effects can work on the subject alone (a glowing silhouette,
words behind a person, one flower in colour, a figure on a plain colour).

Three ways to find the subject, all free and on your own computer:

- "plain": the shot already sits on a plain background (a white or black
  studio, an AI picture on one colour). Venus reads the colour around the
  edges and keeps whatever differs from it. No model, instant.
- "person": MODNet, a small portrait model (Apache-2.0, about 25 MB, fetched
  once). Fast enough for every frame of a video.
- "object": U-2-Net (Apache-2.0, about 175 MB, fetched once). Finds any main
  subject (a flower, a camera, a wheel, an animal). About a quarter of a
  second a frame and 1 GB of memory, so it suits ordinary laptops; on long
  shots it runs on a dozen frames and holds the nearest between.

"auto" picks "plain" when the edges of the frame are one colour, "object"
for a still picture or a short shot (under about two-thirds of a second),
and "person" otherwise.

Models live in ~/.cache/al-venus (or $ALVENUS_MODELS)."""

from __future__ import annotations

import os
import threading
from pathlib import Path

import numpy as np

MODELS = {
    "person": ("Xenova/modnet", "onnx/model.onnx", "modnet.onnx", 25),
    "object": ("danielgatis/rembg", "u2net.onnx", "u2net.onnx", 175),
}
KINDS = ("auto", "plain", "person", "object")
OBJECT_RUNS = 12  # at most this many object passes per shot; frames between hold the nearest
_SESSIONS: dict = {}
_LOCK = threading.Lock()
_RUN = threading.Lock()


def model_path(kind: str) -> Path:
    base = os.environ.get("ALVENUS_MODELS") or os.path.join(os.path.expanduser("~"), ".cache", "al-venus")
    return Path(base) / "cutout" / MODELS[kind][2]


def fetch(kind: str) -> Path:
    import urllib.request

    repo, f, _, mb = MODELS[kind]
    url = (f"https://github.com/{repo}/releases/download/v0.0.0/{f}" if repo == "danielgatis/rembg"
           else f"https://huggingface.co/{repo}/resolve/main/{f}")
    dest = model_path(kind)
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"downloading the {kind} cut-out model (once; about {mb} MB)")
    tmp = dest.with_suffix(".part")
    urllib.request.urlretrieve(url, tmp)  # nosec B310
    tmp.rename(dest)
    return dest


def _session(kind: str):
    with _LOCK:
        return _open(kind)


def _open(kind: str):
    if kind not in _SESSIONS:
        import onnxruntime as ort

        so = ort.SessionOptions()
        so.log_severity_level = 3  # the models print harmless warnings otherwise
        _SESSIONS[kind] = ort.InferenceSession(str(fetch(kind)), so, providers=["CPUExecutionProvider"])
    return _SESSIONS[kind]


# --- the three finders ---------------------------------------------------------

def border_colour(frame: np.ndarray) -> tuple[np.ndarray, float]:
    """The colour around the frame's edges and how even it is (0 = one flat colour)."""
    h, w = frame.shape[:2]
    b = max(2, min(h, w) // 40)
    ring = np.concatenate([frame[:b].reshape(-1, 3), frame[-b:].reshape(-1, 3),
                           frame[:, :b].reshape(-1, 3), frame[:, -b:].reshape(-1, 3)]).astype(np.float32)
    med = np.median(ring, axis=0)
    spread = float(np.percentile(np.abs(ring - med).sum(axis=1), 80))
    return med, spread


def is_plain(frame: np.ndarray) -> bool:
    return border_colour(frame)[1] < 30


def plain_mask(frame: np.ndarray) -> np.ndarray:
    """Everything that differs from the edge colour, softly."""
    from PIL import Image, ImageFilter

    bg, _ = border_colour(frame)
    d = np.abs(frame.astype(np.float32) - bg).sum(axis=2)
    m = np.clip((d - 28) / 40, 0, 1)
    im = Image.fromarray((m * 255).astype(np.uint8))
    im = im.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))  # close pin holes
    return np.asarray(im.filter(ImageFilter.GaussianBlur(1)), np.float32) / 255


def _norm(frame: np.ndarray, w: int, h: int, mean, std) -> np.ndarray:
    from PIL import Image

    x = np.asarray(Image.fromarray(frame).resize((w, h), Image.BILINEAR), np.float32) / 255
    x = (x - np.array(mean, np.float32)) / np.array(std, np.float32)
    return x.transpose(2, 0, 1)[None]


def _back(m: np.ndarray, w: int, h: int) -> np.ndarray:
    from PIL import Image

    return np.asarray(Image.fromarray((np.clip(m, 0, 1) * 255).astype(np.uint8)).resize((w, h), Image.BILINEAR), np.float32) / 255


def person_mask(frame: np.ndarray) -> np.ndarray:
    h, w = frame.shape[:2]
    s = 512 / max(h, w)
    mw, mh = max(32, round(w * s / 32) * 32), max(32, round(h * s / 32) * 32)
    sess = _session("person")
    y = sess.run(None, {sess.get_inputs()[0].name: _norm(frame, mw, mh, (0.5,) * 3, (0.5,) * 3)})[0][0, 0]
    return _back(y, w, h)


_CACHE: dict = {}  # the same picture is never cut out twice (stills repeat, renders run again)


def object_mask(frame: np.ndarray) -> np.ndarray:
    import hashlib

    h, w = frame.shape[:2]
    key = (hashlib.sha1(frame[::8, ::8].tobytes()).hexdigest(), w, h)  # nosec B324 (a cache key, not security)
    if key in _CACHE:
        return _CACHE[key]
    sess = _session("object")
    x = _norm(frame, 320, 320, (0.485, 0.456, 0.406), (0.229, 0.224, 0.225))
    with _RUN:  # one pass at a time keeps memory low when shots render side by side
        y = sess.run(None, {sess.get_inputs()[0].name: x})[0][0, 0]
    y = (y - y.min()) / (y.max() - y.min() + 1e-6)
    m = _back(np.clip((y - 0.08) / 0.84, 0, 1), w, h)
    if len(_CACHE) > 64:
        _CACHE.clear()
    _CACHE[key] = m
    return m


def choose(frames: np.ndarray) -> str:
    if is_plain(frames[0]) and is_plain(frames[len(frames) // 2]):
        return "plain"
    still = len(frames) == 1 or float(np.abs(frames[0].astype(np.int16) - frames[-1]).mean()) < 2.0
    return "object" if still or len(frames) <= 20 else "person"


def masks(frames: np.ndarray, kind: str = "auto") -> np.ndarray:
    """One soft mask (0..1, H x W) per frame of an N x H x W x 3 uint8 array."""
    if kind not in KINDS:
        raise SystemExit(f"cut-out {kind!r}: choose one of {', '.join(KINDS)}")
    k = choose(frames) if kind == "auto" else kind
    n = len(frames)
    if k == "plain":
        return np.stack([plain_mask(f) for f in frames])
    if k == "person":
        return np.stack([person_mask(f) for f in frames])
    # Object model: up to a dozen frames, the rest hold the nearest one. A
    # still (every frame the same) needs just one.
    still = float(np.abs(frames[0].astype(np.int16) - frames[-1]).mean()) < 2.0
    idx = [0] if still else sorted(set(np.linspace(0, n - 1, min(n, OBJECT_RUNS)).round().astype(int).tolist()))
    got = {i: object_mask(frames[i]) for i in idx}
    keys = np.array(idx)
    return np.stack([got[int(keys[np.abs(keys - i).argmin()])] for i in range(n)])


def bbox(m: np.ndarray, thr: float = 0.5) -> tuple[int, int, int, int] | None:
    ys, xs = np.nonzero(m > thr)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


# --- the command: alvenus cutout ------------------------------------------------

def cutout_file(src: Path, out: Path, kind: str = "auto") -> str:
    """A picture becomes a PNG with see-through background; a video becomes a
    MOV (ProRes 4444) with see-through background, ready for any editor."""
    from .fxrender import read_frames, is_image

    if is_image(src):
        from PIL import Image

        f = np.asarray(Image.open(src).convert("RGB"))
        k = choose(f[None]) if kind == "auto" else kind
        m = masks(f[None], k)[0]
        rgba = np.dstack([f, (m * 255).astype(np.uint8)])
        out = out.with_suffix(".png")
        Image.fromarray(rgba, "RGBA").save(out)
        return f"{out} ({k})"
    import subprocess

    frames, fps = read_frames(src)
    k = choose(frames) if kind == "auto" else kind
    ms = masks(frames, k)
    h, w = frames.shape[1:3]
    out = out.with_suffix(".mov")
    p = subprocess.Popen(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{w}x{h}",
                          "-r", f"{fps:g}", "-i", "-", "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le", str(out)],
                         stdin=subprocess.PIPE)
    for f, m in zip(frames, ms):
        p.stdin.write(np.dstack([f, (m * 255).astype(np.uint8)]).tobytes())
    p.stdin.close()
    if p.wait():
        raise RuntimeError("ffmpeg could not write the cut-out")
    return f"{out} ({k}, {len(frames)} frames)"
