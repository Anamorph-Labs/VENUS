"""The same person looks the same all the way through.

A story follows someone. If the father has three different faces, or the watch
is a pocket watch in one shot and a wristwatch in the next, the viewer loses
the thread. Each scene can say who and what is in its picture:

    {"type": "image", "file": "hug.jpg", "text": "...", "cast": ["father", "daughter (young)", "watch"]}

`alvenus cast STORYBOARD` then lays every picture of each one side by side on
a sheet, so the creator and their AI can see at a glance, and measures how
alike the pictures are (CLIP, on this computer). A picture far less like the
others of the same one is flagged as "may look different": a measurement to
look at, never a verdict. Without the model it makes the sheet only."""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

PICTURE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def cast_of(sc: dict) -> list[str]:
    c = sc.get("cast") or []
    return [str(x).strip() for x in ([c] if isinstance(c, str) else c) if str(x).strip()]


def frame_of(path: Path, size: int = 224) -> np.ndarray | None:
    """The picture, or the middle frame of a clip, as RGB."""
    from PIL import Image

    try:
        if path.suffix.lower() in PICTURE_EXT:
            im = Image.open(path).convert("RGB")
        else:
            from .media import duration

            mid = max(0.0, duration(path) / 2)
            raw = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-ss", f"{mid:.2f}", "-i", str(path), "-frames:v", "1",
                                  "-vf", f"scale={size * 2}:-2", "-f", "image2pipe", "-vcodec", "png", "-"],
                                 capture_output=True, check=True).stdout
            import io

            im = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception:
        return None
    return np.asarray(im)


def shots(sb: dict) -> dict[str, list[tuple[int, Path]]]:
    """name -> [(scene number, picture file)] for every scene tagged with that name."""
    out: dict[str, list[tuple[int, Path]]] = {}
    for i, sc in enumerate(sb.get("scenes") or [], 1):
        f = sc.get("file")
        if not f or not Path(str(f)).exists():
            continue
        for name in cast_of(sc):
            out.setdefault(name, []).append((i, Path(str(f))))
    return out


def odd_ones(emb: np.ndarray, margin: float = 0.07, floor: float = 0.88) -> list[tuple[int, float]]:
    """(index, likeness) for pictures much less like the rest of the group than they are like each other."""
    n = len(emb)
    if n < 3:
        if n == 2 and float(emb[0] @ emb[1]) < floor - 0.13:
            return [(1, round(float(emb[0] @ emb[1]), 2))]
        return []
    sim = emb @ emb.T
    like = (sim.sum(axis=1) - 1) / (n - 1)
    med = float(np.median(like))
    return [(k, round(float(like[k]), 2)) for k in range(n) if like[k] < med - margin and like[k] < floor]


def embed(images: list[np.ndarray]) -> np.ndarray | None:
    try:
        from PIL import Image

        from . import footage

        if not (footage.model_dir() / "vision_model_quantized.onnx").exists():
            footage.fetch()
        arr = np.stack([np.asarray(Image.fromarray(im).resize((224, 224), Image.BICUBIC)) for im in images])
        return footage.embed_frames(arr)
    except Exception:
        return None


def check(sb: dict, sheet_path: Path | None = None, measure: bool = True) -> tuple[list[str], dict]:
    """Plain notes, and {name: [{"scene", "likeness", "odd"}]} for the AI."""
    groups = shots(sb)
    notes: list[str] = []
    data: dict[str, list[dict]] = {}
    pics: dict[str, list[np.ndarray | None]] = {}
    for name, items in groups.items():
        ims = [frame_of(p) for _, p in items]
        pics[name] = ims
        rows = [{"scene": s, "file": str(p), "likeness": None, "odd": False} for s, p in items]
        ok = [k for k, im in enumerate(ims) if im is not None]
        if measure and len(ok) >= 2:
            emb = embed([ims[k] for k in ok])
            if emb is not None:
                sim = emb @ emb.T
                for j, k in enumerate(ok):
                    rows[k]["likeness"] = round(float((sim[j].sum() - 1) / (len(ok) - 1)), 2)
                for j, lk in odd_ones(emb):
                    rows[ok[j]]["odd"] = True
                    others = ", ".join(str(r["scene"]) for r in rows if r is not rows[ok[j]])
                    notes.append(f"\"{name}\" in scene {rows[ok[j]]['scene']} may look different from scenes {others} "
                                 f"(likeness {lk:.2f}); look at the sheet and swap the picture if it is not the same {name}")
        data[name] = rows
    if sheet_path is not None and groups:
        draw_sheet(groups, pics, data, sheet_path)
    if not groups:
        notes.append("no scene says who is in its picture: add \"cast\": [\"name\", ...] to each scene with a person or a key object")
    return notes, data


def draw_sheet(groups, pics, data, out: Path, th: int = 180) -> None:
    from PIL import Image, ImageDraw

    from .read import _font

    names = list(groups)
    cols = max(len(v) for v in groups.values())
    lab = 220
    W, H = lab + cols * (th + 12) + 12, len(names) * (th + 40) + 20
    sheet = Image.new("RGB", (W, H), (245, 243, 238))
    d = ImageDraw.Draw(sheet)
    f, fs = _font(20), _font(15)
    for r, name in enumerate(names):
        y = 10 + r * (th + 40)
        d.text((12, y + th // 2 - 10), name[:20], font=f, fill=(20, 20, 20))
        for c, (im, row) in enumerate(zip(pics[name], data[name])):
            x = lab + 12 + c * (th + 12)
            if im is not None:
                t = Image.fromarray(im)
                t.thumbnail((th, th))
                sheet.paste(t, (x, y))
                if row["odd"]:
                    d.rectangle([x - 3, y - 3, x + t.width + 2, y + t.height + 2], outline=(200, 40, 40), width=4)
            tag = f"scene {row['scene']}" + (f"  {row['likeness']:.2f}" if row["likeness"] is not None else "")
            d.text((x, y + th + 6), tag, font=fs, fill=(200, 40, 40) if row["odd"] else (60, 60, 60))
    sheet.save(out, quality=88)
