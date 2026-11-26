"""Stills of every scene, before anything is made.

The creator should see every card before saying yes. `alvenus stills FILE`
draws the storyboard exactly as `make` would (pictures, words, captions,
stamps, notes, cards, drops), takes one finished frame from each scene once
everything in it has arrived, and lays them on one sheet. The working video it
draws them from is deleted: no video is delivered, and the storyboard does
not need to be approved yet."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .style import FONTS

IVORY = (244, 241, 234)
INK = (27, 27, 31)
MUTED = (118, 114, 106)


def settled(sc: dict, t0: float, t1: float) -> float:
    """The moment a scene is complete: after its last stamp, note, strike, drop or page line, before it ends."""
    L = t1 - t0
    last = 0.0
    for k in ("stamp", "strike"):
        if isinstance(sc.get(k), dict):
            last = max(last, float(sc[k].get("at", 0.4)) + 0.6)
    for n in sc.get("notes") or []:
        if isinstance(n, dict):
            last = max(last, float(n.get("at", 0.2)) + 0.9)
    if sc.get("_drop"):
        last = max(last, sc["_drop"]["at"] + 0.6)
    if isinstance(sc.get("page"), dict):
        last = max(last, 1.6)
    if isinstance(sc.get("card"), dict) and sc["card"].get("from_full"):
        last = max(last, 1.6)
    at = max(L * 0.8, last)
    return t0 + max(0.0, min(at, L - 0.12))


def grab(video: Path, at: float, dst: Path) -> None:
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", f"{max(0.0, at):.3f}", "-i", str(video), "-frames:v", "1",
                    "-q:v", "2", str(dst)], check=True)


def sheet(frames: list[tuple[Path, str]], dst: Path, cols: int = 3) -> None:
    """One page: every scene's still, numbered, on ivory."""
    ims = [Image.open(f).convert("RGB") for f, _ in frames]
    if not ims:
        return
    tw = 640
    th = round(tw * ims[0].height / ims[0].width)
    gap, cap = 28, 44
    rows = (len(ims) + cols - 1) // cols
    page = Image.new("RGB", (gap + cols * (tw + gap), gap + rows * (th + cap + gap)), IVORY)
    d = ImageDraw.Draw(page)
    try:
        f = ImageFont.truetype(str(FONTS / "Inter-SemiBold.otf"), 18)
    except OSError:
        f = ImageFont.load_default()
    for k, (im, (_, label)) in enumerate(zip(ims, frames)):
        x = gap + (k % cols) * (tw + gap)
        y = gap + (k // cols) * (th + cap + gap)
        page.paste(im.resize((tw, th), Image.LANCZOS), (x, y))
        d.rectangle([x, y, x + tw - 1, y + th - 1], outline=(214, 209, 199))
        d.text((x, y + th + 12), label, font=f, fill=INK)
    page.save(dst, quality=90)


def make(sb: dict, size: str, out_dir: Path, build) -> list[Path]:
    """Draw the storyboard, keep one still per scene in out_dir, delete the working video."""
    out_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="venus-stills-", dir=out_dir))
    try:
        video = work / "stills.mp4"
        build(sb, video, size)
        files = []
        for i, sc in enumerate(sb["scenes"]):
            t0, t1 = sb["_spans"][i]
            at = settled(sc, t0, t1)
            dst = out_dir / f"scene-{i + 1:02d}.jpg"
            grab(video, at, dst)
            files.append((dst, f"{i + 1}  {sc['type']}  {t1 - t0:.1f} s  (frame at {at - t0:.1f} s)"))
        sheet(files, out_dir / "stills.jpg")
        return [f for f, _ in files] + [out_dir / "stills.jpg"]
    finally:
        shutil.rmtree(work, ignore_errors=True)  # no video is kept: these are stills to approve
