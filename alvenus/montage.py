"""Music edits: cut a folder of clips to a song, the way an editor builds a
reel. No one needs to speak.

1. Look at every clip a few times a second: how much moves, how sharp it is,
   how bright, how colourful, and where the clip has cuts of its own.
2. Listen to the song: its beat, and how much energy each beat carries, so
   the edit can breathe in the quiet parts and hit hard on the drop.
3. Plan the shots: quiet music gets longer, calmer shots; loud music gets
   short shots with movement in them; a sudden jump in energy (a drop) gets
   the strongest moment, a white flash and a speed ramp. Every cut lands on a
   beat, no moment is used twice, and the same clip never plays twice in a
   row.
4. Give still shots life with a slow push-in or pull-out, even out
   brightness between clips, grade everything with one look, and render.

The plan is written to `<out>.montage.json`; the person or their AI can
change any shot and render again with --plan."""

from __future__ import annotations

import json
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from .media import duration, has_video, run, video_size

SW, SH, AFPS = 96, 54, 4.0  # analysis frame size and samples per second
VIDEO = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".mts"}


# --- 1. Looking at the clips -------------------------------------------------

@dataclass
class ClipInfo:
    path: str
    seconds: float
    size: tuple[int, int]
    motion: list[float]  # per sample, 0..~1
    sharp: list[float]
    luma: list[float]  # 0..255
    colour: list[float]
    cuts: list[float] = field(default_factory=list)  # its own cuts, seconds


def analyse(path: Path) -> ClipInfo:
    import subprocess

    raw = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(path), "-an", "-vf",
                          f"fps={AFPS:g},scale={SW}:{SH}:flags=area", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True).stdout
    n = len(raw) // (SW * SH * 3)
    f = np.frombuffer(raw[: n * SW * SH * 3], np.uint8).reshape(n, SH, SW, 3).astype(np.float32)
    if n == 0:
        return ClipInfo(str(path), duration(path), video_size(path) or (0, 0), [0.0], [0.0], [0.0], [0.0])
    g = f.mean(axis=3)
    diff = np.abs(np.diff(g, axis=0, prepend=g[:1])).mean(axis=(1, 2))
    lap = np.abs(4 * g[:, 1:-1, 1:-1] - g[:, :-2, 1:-1] - g[:, 2:, 1:-1] - g[:, 1:-1, :-2] - g[:, 1:-1, 2:]).mean(axis=(1, 2))
    sat = (f.max(axis=3) - f.min(axis=3)).mean(axis=(1, 2))
    # A jump far above the clip's usual movement is a cut inside the clip.
    med = float(np.median(diff[1:])) if n > 2 else 0.0
    cuts = [round(i / AFPS, 2) for i in range(1, n) if diff[i] > max(25.0, 6 * med + 8)]
    motion = np.where(np.isin(np.arange(n), [int(c * AFPS) for c in cuts]), med, diff)
    return ClipInfo(str(path), round(duration(path), 3), video_size(path) or (0, 0),
                    [round(float(x) / 30, 4) for x in motion], [round(float(x), 2) for x in lap],
                    [round(float(x), 1) for x in g.mean(axis=(1, 2))], [round(float(x), 1) for x in sat], cuts)


def find_clips(items: list[str]) -> list[Path]:
    files: list[Path] = []
    for it in items:
        p = Path(it)
        files += sorted(x for x in p.iterdir() if x.suffix.lower() in VIDEO) if p.is_dir() else [p]
    return [f for f in files if f.exists() and has_video(f)]


# --- 2. Listening to the song -------------------------------------------------

def song_map(music: Path) -> tuple[list[float], list[float], int]:
    """(beat times, energy 0..1 per beat, which beat of four is the downbeat)."""
    from .beats import SR, beat_grid
    from .media import load_audio

    y = load_audio(music, SR)
    period, first, conf = beat_grid(y)
    length = len(y) / SR
    if period <= 0 or conf < 0.1:
        period, first = 0.5, 0.0  # no clear beat: cut on a steady half-second grid
    beats = [float(t) for t in np.arange(first, length, period)]
    rms = []
    for t in beats:
        seg = y[int(t * SR) : int((t + period) * SR)]
        rms.append(float(np.sqrt((seg ** 2).mean())) if len(seg) else 0.0)
    r = np.array(rms)
    r = np.convolve(r, np.ones(3) / 3, "same")  # energy changes over a few beats, not one
    lo, hi = np.percentile(r, 10), np.percentile(r, 95)
    energy = np.clip((r - lo) / ((hi - lo) or 1), 0, 1)
    down = int(np.argmax([np.array(rms)[k::4].mean() if len(rms) > k else 0 for k in range(4)]))
    return beats, [round(float(e), 3) for e in energy], down


# --- 3. Planning the shots ---------------------------------------------------

@dataclass
class Shot:
    clip: str  # file
    start: float  # seconds into the clip
    length: float  # seconds on screen
    speed: float = 1.0  # playback speed; a ramp goes from `speed` to `speed_end`
    speed_end: float | None = None
    push: float = 0.0  # >0 slow push-in, <0 pull-out (zoom change over the shot)
    flash: bool = False  # a white flash as it starts (on a drop)
    gain: float = 0.0  # brightness correction to match the other clips
    why: str = ""
    pulse: float = 0.0  # a quick zoom bump on every beat (loud parts), this much bigger
    beat: float = 0.5  # seconds per beat, for the pulse

    def source_length(self) -> float:
        s1 = self.speed if self.speed_end is None else self.speed_end
        return self.length * (self.speed + s1) / 2


def _quality(ci: ClipInfo, a: int, b: int) -> float:
    sharp = np.array(ci.sharp[a:b]) if b > a else np.array([0.0])
    luma = np.array(ci.luma[a:b]) if b > a else np.array([0.0])
    q = min(1.0, float(np.median(sharp)) / 6.0)
    dark = float(np.mean(luma < 35))  # too dark to read
    blown = float(np.mean(luma > 235))
    return q - 1.2 * dark - 0.8 * blown + 0.2 * min(1.0, float(np.median(np.array(ci.colour[a:b] or [0]))) / 80)


def plan(clips: list[ClipInfo], beats: list[float], energy: list[float], down: int,
         total: float, seed: int = 0) -> list[Shot]:
    rng = np.random.default_rng(seed)
    all_motion = np.concatenate([np.array(c.motion) for c in clips]) if clips else np.array([0.0])
    m_lo, m_hi = np.percentile(all_motion, 10), np.percentile(all_motion, 90)
    lum_target = float(np.median(np.concatenate([np.array(c.luma) for c in clips])))
    used: dict[str, list[tuple[float, float]]] = {c.path: [] for c in clips}
    beats = [b for b in beats if b < total] or [0.0]
    cuts = [0.0] + [b for b in beats if b > 0.25]
    shots: list[Shot] = []
    i, last_clip, last_e = 0, None, energy[0] if energy else 0.5
    while i < len(cuts) - 1 or (i == len(cuts) - 1 and total - cuts[i] > 0.3):
        bi = min(i, len(energy) - 1)
        e = energy[bi] if energy else 0.5
        drop = e - last_e > 0.35 and shots
        # Shot length in beats: calm music lets a shot breathe, loud music moves on.
        n = 4 if e < 0.4 else 2 if e < 0.75 else (1 if (len(shots) % 3 == 2) else 2)
        if n == 4 and (i - down) % 2:  # long shots start on the stronger beats
            n = 3
        if drop:
            n = max(n, 2)
        j = min(i + n, len(cuts) - 1)
        t0 = cuts[i]
        t1 = cuts[j] if j > i else total
        if j == len(cuts) - 1 and total - t1 < 1.2:  # don't leave a sliver at the end
            t1, j = total, len(cuts)
        d = t1 - t0
        speed, speed_end = (0.8, None) if e < 0.4 else (1.0, None)
        if drop:
            speed, speed_end = 1.8, 0.55  # rush in, then hang in slow motion
        want_motion = m_lo + (m_hi - m_lo) * (0.2 + 0.8 * e)
        need = d * ((speed + (speed_end or speed)) / 2)
        best, best_score = None, -1e9
        for ci in clips:
            if ci.path == last_clip and len(clips) > 1:
                continue
            for s in np.arange(0.0, max(0.0, ci.seconds - need) + 1e-6, 0.25):
                e_ = s + need
                if e_ > ci.seconds - 0.05:
                    break
                if any(s < c < e_ for c in ci.cuts):  # never play across the clip's own cut
                    continue
                if any(s < u1 and e_ > u0 for u0, u1 in used[ci.path]):
                    continue
                a, b = int(s * AFPS), max(int(s * AFPS) + 1, int(e_ * AFPS))
                mot = float(np.mean(ci.motion[a:b])) if b <= len(ci.motion) else 0.0
                score = _quality(ci, a, b) - abs(mot - want_motion) / ((m_hi - m_lo) or 1) * 0.8
                score -= 0.35 * len(used[ci.path])  # spread the edit over all the clips
                if drop:
                    score += 0.6 * mot / (m_hi or 1)  # the drop gets the most movement
                score += rng.uniform(0, 0.05)
                if score > best_score:
                    best, best_score = (ci, float(s), mot), score
        if best is None:  # everything used: allow reuse, but still not twice in a row
            for u in used.values():
                u.clear()
            if not any(c.seconds > need + 0.1 for c in clips):
                need = min(need, max(c.seconds for c in clips) - 0.1)
                speed, speed_end = need / d, None
            continue
        ci, s, mot = best
        used[ci.path].append((s, s + need))
        a, b = int(s * AFPS), max(int(s * AFPS) + 1, int((s + need) * AFPS))
        lum = float(np.mean(ci.luma[a:b])) if b <= len(ci.luma) else lum_target
        still = mot < m_lo + 0.25 * (m_hi - m_lo)
        push = (0.07 if len(shots) % 2 == 0 else -0.06) if still else 0.0
        why = ("drop: strongest movement, flash and speed ramp" if drop else
               "calm music: longer shot" if e < 0.4 else "high energy: short shot" if n == 1 else "")
        if still:
            why = (why + "; " if why else "") + ("still shot, slow push-in" if push > 0 else "still shot, slow pull-out")
        period = (beats[1] - beats[0]) if len(beats) > 1 else 0.5
        pulse = 0.035 if e >= 0.75 and not drop else 0.0
        if pulse:
            why = (why + "; " if why else "") + "zoom kick on each beat"
        shots.append(Shot(ci.path, round(s, 3), round(d, 3), speed, speed_end,
                          push, bool(drop), round(float(np.clip((lum_target - lum) / 255 * 0.6, -0.15, 0.15)), 3), why,
                          pulse, round(period, 4)))
        last_clip, last_e = ci.path, e
        i = j
    return shots


# --- 4. Rendering ------------------------------------------------------------

def _shot_filter(sh: Shot, src_size, w: int, h: int, fps: float, look: str, reframe) -> str:
    from .style import LOOKS

    d = sh.length
    if sh.speed_end is None or abs(sh.speed_end - sh.speed) < 1e-3:
        timing = f"setpts=(PTS-STARTPTS)/{sh.speed:.4f}"
    else:
        # Speed changes smoothly from speed to speed_end. Source time T and
        # screen time t: T = s0 t + (s1 - s0) t^2 / 2d, solved for t.
        s0, s1 = sh.speed, sh.speed_end
        acc = (s1 - s0) / d
        timing = f"setpts=((-{s0:.4f}+sqrt({s0 * s0:.5f}+2*({acc:.5f})*(PTS-STARTPTS)*TB))/({acc:.5f}))/TB"
    sw, sh_ = src_size
    if sw and sh_ and abs(sw / sh_ - w / h) > 0.01 and sw / sh_ > w / h and reframe:
        from .reframe import crop_x

        cw = 2 * round(sh_ * w / h / 2)
        fit = f"crop={cw}:{sh_}:x='{crop_x(reframe, sw, cw)}':y=0,scale={w}:{h}"
    else:
        fit = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"
    vf = f"{timing},fps={fps:g},{fit},setsar=1"
    if sh.gain:
        vf += f",eq=brightness={sh.gain:.3f}"
    from .learnstyle import matched

    grade_ = matched(look, sh.clip) or LOOKS.get(look)  # a learned look is matched shot by shot
    if grade_:
        vf += "," + grade_
    if sh.push or sh.pulse:
        z0, z1 = (1.0, 1.0 + sh.push) if sh.push > 0 else (1.0 - sh.push, 1.0)
        n = max(1, round(d * fps))
        z = f"({z0:.4f}+{z1 - z0:.4f}*min(on/{n},1)"
        if sh.pulse:  # each beat kicks the frame in a touch, then it settles
            z += f"+{sh.pulse:.4f}*exp(-mod(on/{fps:g},{sh.beat:.4f})/0.09)"
        z += ")"
        corners = [("W/2-W/2/", "H/2-H/2/"), ("W/2+W/2/", "H/2-H/2/"), ("W/2-W/2/", "H/2+H/2/"), ("W/2+W/2/", "H/2+H/2/")]
        vf += ",perspective=" + ":".join(f"x{i}='{a}{z}':y{i}='{b}{z}'" for i, (a, b) in enumerate(corners)) + ":interpolation=cubic:eval=frame"
    if sh.flash:
        vf += ",eq=brightness='0.9*max(0,1-t/0.12)':eval=frame"
    vf += f",trim=0:{d:.3f},setpts=PTS-STARTPTS,format=yuv420p"
    return vf


def render(shots: list[Shot], music: Path, out: Path, size: str, fps: float = 30.0, look: str = "natural",
           title: str | None = None, accent: str = "#FFD23F", reframe_wide: bool = True,
           title_style: str = "stamp") -> None:
    w, h = (int(x) for x in size.split("x"))
    total = sum(s.length for s in shots)
    tmp = Path(tempfile.mkdtemp(prefix="alvenus-m-", dir=out.parent))
    sizes = {s.clip: video_size(s.clip) or (w, h) for s in shots}

    def one(k: int) -> None:
        sh = shots[k]
        need = sh.source_length() + 0.2
        track = None
        sw, shh = sizes[sh.clip]
        if reframe_wide and sw / max(shh, 1) > 1.15 * w / h:
            from .reframe import track as follow
            track = follow(Path(sh.clip), sh.start, sh.start + need)
        run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", f"{sh.start:.3f}", "-t", f"{need:.3f}", "-i", sh.clip, "-an",
             "-vf", _shot_filter(sh, sizes[sh.clip], w, h, fps, look, track),
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "14", "-pix_fmt", "yuv420p", str(tmp / f"s{k:04d}.mp4")])

    try:
        with ThreadPoolExecutor(max(1, min(3, (os.cpu_count() or 2) - 1))) as pool:
            list(pool.map(one, range(len(shots))))
        lst = tmp / "shots.txt"
        lst.write_text("".join(f"file 's{k:04d}.mp4'\n" for k in range(len(shots))), encoding="utf-8")
        vf = "null"
        from . import genre

        if title or genre.EXTRAS:
            from .style import ass_filter, write_ass

            ass = out.with_suffix(".montage.ass")
            write_ass(ass, w, h, accent, title=title, cut_len=total, title_style=title_style)
            vf = ass_filter(ass)
        fade = min(2.0, total / 4)
        run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-i", str(music),
             "-filter_complex", f"[0:v]{vf},fade=t=out:st={total - 0.4:.3f}:d=0.4[v];"
             f"[1:a]atrim=0:{total:.3f},asetpts=PTS-STARTPTS,afade=t=out:st={total - fade:.3f}:d={fade:.3f}[a]",
             "-map", "[v]", "-map", "[a]", "-t", f"{total:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "19",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)])
    finally:
        for f in tmp.glob("*"):
            f.unlink()
        tmp.rmdir()


def save_plan(path: Path, shots: list[Shot], settings: dict) -> None:
    path.write_text(json.dumps({
        "_how_to_use": "Change any shot (clip, start second, length, speed, speed_end for a ramp, push, flash) or "
                       "the settings, then run: alvenus montage --plan THIS_FILE. Shot lengths follow the music's beat; "
                       "keep their sum the same to stay on the beat.",
        **settings, "shots": [asdict(s) for s in shots]}, indent=2), encoding="utf-8")


def load_plan(path: Path) -> tuple[list[Shot], dict]:
    d = json.loads(path.read_text(encoding="utf-8"))
    shots = [Shot(**s) for s in d.pop("shots")]
    d.pop("_how_to_use", None)
    return shots, d
