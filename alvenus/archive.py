"""Pictures for archive documentaries (from the Venus board, 21 Nov):

  - an archive scene: an old photograph in a thin print border floating over a
    dark desk of faded documents, ruled lines and a rust-red glow, the desk and
    the print drifting at different speeds so the still feels filmed;
  - frames around any picture: drifting clouds (white, for quotes and memory)
    or ink blots (dark sepia, for film openers), the picture showing through
    the middle.

Everything is drawn here with PIL (no downloads), once per scene, then moved
by FFmpeg. The words on top (year, red tag, note) are drawn later in genre.py.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .media import run

FRAMES = ("cloud", "ink")


def _noise(w: int, h: int, rng, octaves=((8, 1.0), (24, 0.5), (70, 0.25))) -> np.ndarray:
    """Smooth 0..1 noise, made from a few blurred random fields."""
    out = np.zeros((h, w), np.float32)
    for cells, amp in octaves:
        small = Image.fromarray((rng.random((max(2, cells * h // w), cells)) * 255).astype(np.uint8))
        out += amp * np.asarray(small.resize((w, h), Image.BICUBIC), np.float32) / 255
    out -= out.min()
    return out / max(1e-6, out.max())


def desk(w: int, h: int, k: int, accent: str = "#C0392B") -> Image.Image:
    """The dark layered background of an archive scene: charcoal, scraps of
    faded typed paper at angles, fine ruled lines, a rust glow in one corner."""
    rng = np.random.default_rng(1000 + k)
    y = np.linspace(0, 1, h)[:, None]
    x = np.linspace(0, 1, w)[None, :]
    base = 30 + 18 * (1 - np.hypot(x - 0.5, y - 0.5))
    img = Image.fromarray(np.stack([base * 1.02, base * 0.98, base * 0.96], -1).clip(0, 255).astype(np.uint8)).convert("RGBA")
    u = min(w, h)
    for _ in range(6):  # paper scraps with lines of "type"
        pw, ph = int(u * rng.uniform(0.35, 0.7)), int(u * rng.uniform(0.3, 0.6))
        scrap = Image.new("RGBA", (pw, ph), (205, 200, 188, int(rng.uniform(26, 48))))
        d = ImageDraw.Draw(scrap)
        lh = max(6, int(u * 0.016))
        for row in range(int(ph * 0.12), ph - lh, lh):
            if rng.random() < 0.85:
                d.rectangle([int(pw * 0.08), row, int(pw * rng.uniform(0.45, 0.92)), row + max(2, lh // 3)], fill=(20, 20, 20, 70))
        scrap = scrap.rotate(rng.uniform(-8, 8), expand=True, resample=Image.BICUBIC)
        img.alpha_composite(scrap, (int(rng.uniform(-0.1, 0.85) * w), int(rng.uniform(-0.1, 0.8) * h)))
    d = ImageDraw.Draw(img)
    line = (235, 235, 230, 40)
    for fx in (0.08, 0.92):
        d.line([(int(w * fx), 0), (int(w * fx), h)], fill=line, width=1)
    for fy in (0.1, 0.9):
        d.line([(0, int(h * fy)), (w, int(h * fy))], fill=line, width=1)
    for i in range(0, w, max(8, u // 60)):  # a small ruler along the bottom line
        tick = 8 if i % (5 * max(8, u // 60)) == 0 else 4
        d.line([(i, int(h * 0.9)), (i, int(h * 0.9) + tick)], fill=line, width=1)
    r, g, b = (int(accent.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    cx, cy = (0.95, 0.15) if k % 2 == 0 else (0.05, 0.85)
    glow = np.exp(-((x - cx) ** 2 + ((y - cy) * h / w) ** 2) / 0.09)[..., None] * 0.55
    rust = np.array([r * 0.8 + 50, g * 0.5 + 20, b * 0.4 + 10], np.float32)
    arr = np.asarray(img.convert("RGB"), np.float32)
    arr = arr * (1 - glow) + rust * glow
    grain = rng.normal(0, 5, (h, w, 1))
    return Image.fromarray((arr + grain).clip(0, 255).astype(np.uint8))


def print_of(photo: str | Path, box_w: int, box_h: int) -> Image.Image:
    """The photograph as a print: fitted in the box, a thin warm-white border,
    a soft shadow under it. (First frame of a video is used for footage.)"""
    p = Path(photo)
    if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}:
        im = Image.open(p).convert("RGB")
    else:
        tmp = p.with_name(f".{p.stem}.first.png")
        run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(p), "-frames:v", "1", str(tmp)])
        im = Image.open(tmp).convert("RGB")
        tmp.unlink()
    im.thumbnail((box_w, box_h), Image.LANCZOS)
    bdr = max(4, round(min(im.size) * 0.018))
    pad = bdr * 6
    out = Image.new("RGBA", (im.width + 2 * bdr + 2 * pad, im.height + 2 * bdr + 2 * pad), (0, 0, 0, 0))
    sh = Image.new("RGBA", out.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rectangle([pad + bdr, pad + bdr * 3, pad + im.width + bdr * 3, pad + im.height + bdr * 4], fill=(0, 0, 0, 170))
    out.alpha_composite(sh.filter(ImageFilter.GaussianBlur(pad * 0.45)))
    ImageDraw.Draw(out).rectangle([pad, pad, pad + im.width + 2 * bdr - 1, pad + im.height + 2 * bdr - 1], fill=(232, 228, 218, 255))
    out.paste(im, (pad + bdr, pad + bdr))
    return out


def frame_overlay(kind: str, w: int, h: int, k: int) -> Image.Image:
    """A frame that drifts round the picture: soft white clouds, or ragged
    dark sepia ink. Transparent in the middle (an RGBA picture, a little larger
    than the frame so it can drift)."""
    rng = np.random.default_rng(77 + k)
    W, H = round(w * 1.1) // 2 * 2, round(h * 1.1) // 2 * 2
    y = np.linspace(-1, 1, H)[:, None]
    x = np.linspace(-1, 1, W)[None, :]
    edge = np.maximum(np.abs(x) ** 2.2 * 0.9, np.abs(y) ** 2.2) + 0.25 * (x * x * y * y)
    n = _noise(W // 4, H // 4, rng)
    n = np.asarray(Image.fromarray((n * 255).astype(np.uint8)).resize((W, H), Image.BICUBIC), np.float32) / 255
    if kind == "cloud":
        a = np.clip((edge + 0.55 * (n - 0.5) - 0.42) * 2.6, 0, 1) ** 1.3
        shade = 225 + 30 * n  # billows: brighter on the noise's high points
        rgb = np.stack([shade, shade * 0.995, shade * 0.985], -1)
    else:
        a = np.clip((edge + 0.7 * (n - 0.5) - 0.38) * 6, 0, 1)
        a = np.asarray(Image.fromarray((a * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(2)), np.float32) / 255
        rgb = np.stack([np.full_like(n, 34 + 18 * n), np.full_like(n, 26 + 12 * n), np.full_like(n, 20 + 8 * n)], -1)
    img = np.concatenate([rgb, (a * 255)[..., None]], -1).clip(0, 255).astype(np.uint8)
    return Image.fromarray(img, "RGBA")


def scene_video(sc: dict, d: float, w: int, h: int, fps: float, out: Path, k: int, accent: str) -> None:
    """Render an archive scene: the print drifts and grows slowly over the desk,
    which drifts the other way (parallax)."""
    work = out.with_suffix("")
    work.mkdir(parents=True, exist_ok=True)
    try:
        bw, bh = round(w * 1.08) // 2 * 2, round(h * 1.08) // 2 * 2
        desk(bw, bh, k, accent).save(work / "desk.png")
        vertical = h > w
        box = (round(w * 0.8), round(h * 0.52)) if vertical else (round(w * 0.56), round(h * 0.7))
        pr = print_of(sc["file"], *box)
        pr.save(work / "print.png")
        side = -1 if k % 2 == 0 else 1  # the print sits off centre, away from the year
        px = (w - pr.width) // 2 + (0 if vertical else round(side * w * 0.08))
        py = (h - pr.height) // 2 - (round(h * 0.04) if vertical else 0)
        n = max(1, round(d * fps))
        grow = float(sc.get("push", 0.06))
        g = (f"[0:v]fps={fps:g},crop={w}:{h}:x='(iw-ow)/2+{side}*(iw-ow)/2*0.8*(2*min(t/{d:.3f},1)-1)':y='(ih-oh)/2',setsar=1[bg];"
             f"[1:v]fps={fps:g},format=rgba,scale='trunc(iw*(1+{grow:.3f}*min(n/{n},1))/2)*2':'trunc(ih*(1+{grow:.3f}*min(n/{n},1))/2)*2':eval=frame[pr];"
             f"[bg][pr]overlay=x='{px}-(w-{pr.width})/2-{side}*{round(w * 0.012)}*min(t/{d:.3f},1)':y='{py}-(h-{pr.height})/2':eval=frame,format=yuv420p[v]")
        run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-loop", "1", "-t", f"{d + 0.2:.3f}", "-i", str(work / "desk.png"),
             "-loop", "1", "-t", f"{d + 0.2:.3f}", "-i", str(work / "print.png"), "-filter_complex", g, "-map", "[v]",
             "-t", f"{d:.3f}", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "14", "-pix_fmt", "yuv420p", "-r", f"{fps:g}", str(out)])
    finally:
        for f in work.glob("*"):
            f.unlink()
        work.rmdir()


def add_frame(video: Path, kind: str, d: float, w: int, h: int, fps: float, k: int) -> None:
    """Lay a drifting cloud or ink frame over a finished scene picture, in place."""
    png = video.with_name(video.stem + f".{kind}.png")
    ov = frame_overlay(kind, w, h, k)
    ov.save(png)
    ow, oh = ov.size
    raw = video.with_name(video.stem + ".noframe.mp4")
    video.rename(raw)
    try:
        dx = 1 if k % 2 == 0 else -1
        run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(raw), "-loop", "1", "-t", f"{d + 0.2:.3f}", "-i", str(png),
             "-filter_complex", f"[1:v]fps={fps:g},format=rgba[o];[0:v][o]overlay=x='-{(ow - w) // 2}+{dx}*{(ow - w) // 2}*0.9*(2*min(t/{d:.3f},1)-1)'"
             f":y='-{(oh - h) // 2}':eval=frame,format=yuv420p[v]", "-map", "[v]", "-t", f"{d:.3f}", "-an", "-c:v", "libx264",
             "-preset", "veryfast", "-crf", "14", "-pix_fmt", "yuv420p", str(video)])
    finally:
        raw.unlink(missing_ok=True)
        png.unlink(missing_ok=True)
