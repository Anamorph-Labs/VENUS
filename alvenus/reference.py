"""Study a reference video ("make it feel like this one").

People describe style loosely ("snappy", "like that reel"). This measures the
reference itself, so the AI driving the tool works from facts: frame shape,
length, how often it cuts, how fast people talk, how long the pauses are,
how loud it is, and when the first words land. It also saves a contact sheet
of frames so an AI that can see images can judge framing, colour and captions.
"""

from __future__ import annotations

import json
import re
import statistics
from pathlib import Path

from .media import duration, frame_rate, has_video, load_audio, run, speech_regions, video_size

SHAPES = {"16:9": 16 / 9, "9:16": 9 / 16, "1:1": 1.0, "4:5": 4 / 5}


def _shape(w: int, h: int) -> str:
    return min(SHAPES, key=lambda k: abs(SHAPES[k] - w / h))


def _cuts(path: Path, threshold: float = 0.3) -> list[float]:
    err = run([
        "ffmpeg", "-nostdin", "-i", str(path), "-an",
        "-vf", f"scale=320:-2,select='gt(scene,{threshold})',showinfo", "-f", "null", "-",
    ]).stderr
    return [float(x) for x in re.findall(r"pts_time:([\d.]+)", err)]


def _loudness(path: Path) -> float | None:
    err = run(["ffmpeg", "-nostdin", "-i", str(path), "-vn", "-af", "ebur128", "-f", "null", "-"]).stderr
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", err)
    return float(m[-1]) if m else None


def _sheet(path: Path, out: Path, length: float, n: int = 12) -> None:
    step = max(length / n, 0.04)
    run([
        "ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(path),
        "-vf", f"fps=1/{step:.3f},scale=320:-2,tile=4x3:padding=4:color=black", "-frames:v", "1", str(out),
    ])


def study(path: Path, out_dir: Path, listen: bool = True, model_name: str = "base.en") -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    length = duration(path)
    style: dict = {"file": path.name, "seconds": round(length, 1)}

    if has_video(path):
        w, h = video_size(path) or (0, 0)
        style["frame"] = {"size": f"{w}x{h}", "shape": _shape(w, h), "fps": round(frame_rate(path), 2)}
        cuts = _cuts(path)
        shots = len(cuts) + 1
        style["editing"] = {
            "shots": shots,
            "cuts_per_minute": round(len(cuts) / length * 60, 1) if length else 0,
            "average_shot_seconds": round(length / shots, 2),
        }
        sheet = out_dir / f"{path.stem}.sheet.png"
        _sheet(path, sheet, length)
        style["contact_sheet"] = str(sheet)

    speech = speech_regions(path)
    pauses = [b0 - a1 for (_, a1), (b0, _) in zip(speech, speech[1:])]
    talk = sum(e - s for s, e in speech)
    audio: dict = {"loudness_lufs": _loudness(path)}
    if len(speech) <= 1 and talk > 0.9 * length:
        audio["note"] = "sound never drops to silence (likely music or ambience under the voice), so pauses can't be measured"
    else:
        audio["sound_share"] = round(talk / length, 2) if length else 0
        audio["first_sound_at"] = round(speech[0][0], 2) if speech else None
        if pauses:
            audio["median_pause_seconds"] = round(statistics.median(pauses), 2)
            audio["longest_pause_seconds"] = round(max(pauses), 2)
    style["audio"] = audio

    if listen and speech:
        from . import asr

        model = asr.Whisper(name=model_name)
        sr = asr.SAMPLE_RATE
        wav = load_audio(path, sr)
        texts, n_words = [], 0
        for s, e in speech:
            for c0 in range(int(s * sr), int(e * sr), 28 * sr):  # Whisper reads up to 30 s at a time
                text = model.transcribe(wav[c0 : min(int(e * sr), c0 + 28 * sr)]).text
                texts.append(text)
                n_words += len(text.split())
        style["speech"] = {
            "words_per_minute": round(n_words / talk * 60) if talk else 0,
            "opening_words": texts[0] if texts else "",
            "transcript": " ".join(texts),
        }

    style["suggested_settings"] = suggest(style)
    (out_dir / f"{path.stem}.style.json").write_text(json.dumps(style, indent=2), encoding="utf-8")
    return style


def suggest(style: dict) -> list[str]:
    flags = []
    shape = style.get("frame", {}).get("shape")
    if shape:
        flags.append(f"--aspect {shape}")
    pause = style.get("audio", {}).get("median_pause_seconds")
    if pause is not None:
        if pause < 0.35:
            flags.append("--max-pause 0.4")
        elif pause > 0.8:
            flags.append("--keep-pauses")
    return flags


def describe(style: dict) -> str:
    """The same facts in plain sentences."""
    lines = [f"{style['file']}: {style['seconds']} seconds."]
    f = style.get("frame")
    if f:
        lines.append(f"Frame: {f['shape']} ({f['size']}, {f['fps']} fps).")
    ed = style.get("editing")
    if ed:
        lines.append(
            f"Editing: {ed['shots']} shot(s), a cut every {ed['average_shot_seconds']} s on average "
            f"({ed['cuts_per_minute']} cuts a minute)."
        )
    au = style.get("audio", {})
    if au.get("note"):
        lines.append(f"Sound: {au['note']}.")
    elif "median_pause_seconds" in au:
        lines.append(
            f"Pauses: usually {au['median_pause_seconds']} s, longest {au['longest_pause_seconds']} s; "
            f"first sound at {au['first_sound_at']} s."
        )
    if au.get("loudness_lufs") is not None:
        lines.append(f"Loudness: {au['loudness_lufs']} LUFS.")
    sp = style.get("speech")
    if sp:
        lines.append(f"Speech: about {sp['words_per_minute']} words a minute. Opens with: \"{sp['opening_words']}\"")
    if style.get("contact_sheet"):
        lines.append(f"Frames to look at: {style['contact_sheet']}")
    if style.get("suggested_settings"):
        lines.append("Suggested: " + " ".join(style["suggested_settings"]))
    return "\n".join(lines)
