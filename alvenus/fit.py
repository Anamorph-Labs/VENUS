"""Does each picture show what is said over it?

For every scene with both a picture and words (its text, caption or spoken
line), Venus measures how well the picture matches the words (CLIP, on this
computer: the same model the footage search uses) and points out the scenes
that match far worse than the rest of the video. It is a measurement to look
at, never a verdict: a deliberate contrast between word and picture can be
the point. Scenes without words or without a picture are left out."""

from __future__ import annotations

from pathlib import Path

import numpy as np

LINE_KEYS = ("say", "voice", "line", "caption", "text")


def line_of(sc: dict) -> str:
    for k in LINE_KEYS:
        v = sc.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def weakest(scores: list[float], margin: float = 0.035, floor: float = 0.22) -> list[int]:
    """Which scores stand out as poor matches: well under the video's own
    middle, and low in themselves (CLIP's scores sit close together)."""
    if len(scores) < 3:
        return [k for k, s in enumerate(scores) if s < floor - 0.03]
    med = float(np.median(scores))
    return [k for k, s in enumerate(scores) if s < med - margin and s < floor]


def model_ready() -> bool:
    from . import footage

    return (footage.model_dir() / "vision_model_quantized.onnx").exists()


def check(sb: dict, fetch: bool = True) -> tuple[list[str], list[dict]]:
    """(plain notes, rows {"scene", "line", "match", "weak"}). Without the model
    (and fetch False) it says so and measures nothing."""
    from .cast import frame_of

    rows = []
    for i, sc in enumerate(sb.get("scenes") or [], 1):
        f, line = sc.get("file"), line_of(sc)
        if f and line and Path(str(f)).exists() and sc.get("type") in ("clip", "image"):
            rows.append({"scene": i, "file": str(f), "line": line, "match": None, "weak": False})
    if not rows:
        return [], []
    if not fetch and not model_ready():
        return ["picture-to-line check skipped: its model isn't on this computer yet (alvenus fit downloads it once, about 90 MB)"], rows
    try:
        from PIL import Image

        from . import footage

        pics = [frame_of(Path(r["file"])) for r in rows]
        keep = [k for k, p in enumerate(pics) if p is not None]
        arr = np.stack([np.asarray(Image.fromarray(pics[k]).resize((224, 224), Image.BICUBIC)) for k in keep])
        img = footage.embed_frames(arr)
        txt = footage.embed_text([rows[k]["line"][:200] for k in keep])
    except Exception as e:  # never stops the work; says it couldn't measure
        return [f"picture-to-line check couldn't run ({type(e).__name__})"], rows
    for j, k in enumerate(keep):
        rows[k]["match"] = round(float(img[j] @ txt[j]), 3)
    scored = [r for r in rows if r["match"] is not None]
    notes = []
    for k in weakest([r["match"] for r in scored]):
        r = scored[k]
        r["weak"] = True
        notes.append(f"scene {r['scene']}: the picture may not show what is said over it (\"{r['line'][:50]}\"; "
                     f"match {r['match']:.2f}, the video's middle is {float(np.median([x['match'] for x in scored])):.2f}). "
                     "Look at it: swap the picture, or keep it if the contrast is meant")
    return notes, rows
