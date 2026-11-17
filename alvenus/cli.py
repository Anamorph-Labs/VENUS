"""Command line: `python -m alvenus cut --script script.txt --takes clips/ --out cut.mp4`."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from . import asr
from .cut import Clip, render, take_clips, write_srt
from .match import Take, assign, choose, join_paused
from .media import duration, frame_rate, has_video, load_audio, need_ffmpeg, speech_regions
from .timeline import write_edl

SR = asr.SAMPLE_RATE
EDGE = 0.1  # sound this close to a file's start or end means the take is clipped
MEDIA = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".mts", ".wav", ".mp3", ".m4a", ".aac", ".flac"}


def read_script(path: Path) -> list[str]:
    lines = [l.strip() for l in path.read_text(encoding="utf-8").splitlines()]
    return [l for l in lines if l and not l.startswith("#")]


def find_sources(items: list[str]) -> list[Path]:
    """Files and folders, in name order (phones name clips in shooting order)."""
    out: list[Path] = []
    for it in items:
        p = Path(it)
        if p.is_dir():
            out += sorted(f for f in p.iterdir() if f.suffix.lower() in MEDIA)
        else:
            out.append(p)
    if not out:
        raise SystemExit("no media files found in --takes")
    return out


def cmd_cut(a: argparse.Namespace) -> None:
    need_ffmpeg()
    t0 = time.time()
    script = read_script(Path(a.script))
    sources = find_sources(a.takes)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    print(f"1/5 finding takes in {len(sources)} file(s)")
    pieces: list[tuple[int, float, float]] = []
    lengths = [duration(src) for src in sources]
    for k, src in enumerate(sources):
        pieces += [(k, s, e) for s, e in speech_regions(src, a.noise_db, a.min_silence)]

    print(f"2/5 transcribing {len(pieces)} pieces on this computer (Whisper {a.model})")
    model = asr.Whisper(a.models, name=a.model)
    takes: list[Take] = []
    audio_cache: dict[int, object] = {}
    for i, (k, s, e) in enumerate(pieces):
        if k not in audio_cache:
            audio_cache.clear()
            audio_cache[k] = load_audio(sources[k], SR)
        audio = audio_cache[k]
        clip = audio[int(max(0, s - 0.1) * SR) : int((e + 0.1) * SR)]
        if e - s > 29:
            print(f"   warning: piece {i + 1} is {e - s:.0f}s long; only the first 30s are read")
        tr = model.transcribe(clip)
        takes.append(Take(i + 1, s, e, tr.text, tr.avg_logprob, source=k))
        print(f"   {i + 1:>2} {sources[k].name[:18]:18} {s:7.2f}-{e:7.2f}  {tr.text}")

    print("3/5 matching takes to script lines")
    takes = join_paused(takes, script)
    for t in takes:
        t.clipped = t.start < EDGE or t.end > lengths[t.source] - EDGE
    assign(takes, script)
    choices = choose(takes, script)
    picked = [c for c in choices if c.take]

    print("4/5 trimming" + ("" if a.keep_pauses else " (long pauses inside takes shortened)"))
    clips: list[Clip] = []
    for c in picked:
        t = c.take
        clips += take_clips(sources[t.source], t.source, c.line, t.start, t.end, lengths[t.source],
                            max_pause=None if a.keep_pauses else a.max_pause)

    print("5/5 cutting")
    srt = out.with_suffix(".srt")
    write_srt(srt, clips, script)
    vids = [s for s in sources if has_video(s)]
    fps = frame_rate(vids[0]) if vids else 30.0
    render(sources, clips, out, srt if a.captions else None, fps=fps)
    write_edl(out.with_suffix(".edl"), out.stem, sources, clips, script, fps)

    report = {
        "sources": [str(s) for s in sources],
        "output": str(out),
        "seconds_taken": round(time.time() - t0, 1),
        "lines": [
            {
                "line": c.line + 1,
                "script": script[c.line],
                "chosen_take": c.take.index if c.take else None,
                "reason": c.reason,
                "candidates": [
                    {
                        "take": t.index, "file": sources[t.source].name, "start": round(t.start, 2), "end": round(t.end, 2),
                        "heard": t.text, "match": round(t.score, 3), "notes": t.notes,
                    }
                    for t in c.candidates
                ],
            }
            for c in choices
        ],
        "unused": [
            {"take": t.index, "file": sources[t.source].name, "start": round(t.start, 2), "end": round(t.end, 2),
             "heard": t.text, "notes": t.notes}
            for t in takes if t.line is None
        ],
    }
    out.with_suffix(".decisions.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print()
    for c in choices:
        pick = f"take {c.take.index} ({sources[c.take.source].name})" if c.take else "MISSING"
        print(f"line {c.line + 1}: {pick:28}  {c.reason}")
    print(f"\nwrote {out} ({sum(c.length for c in clips):.1f}s) + .edl timeline in {report['seconds_taken']}s")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="alvenus", description="Cut a video from a script and your takes.")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("cut", help="pick the best take per script line and build the cut")
    c.add_argument("--script", required=True, help="text file, one spoken line per row")
    c.add_argument("--takes", required=True, nargs="+", help="recording(s) or folder(s) of clips, video or audio")
    c.add_argument("--out", required=True, help="output MP4 (an .edl timeline and .srt captions are written beside it)")
    c.add_argument("--captions", action="store_true", help="burn the script lines in as captions")
    c.add_argument("--model", default=asr.DEFAULT_MODEL, choices=sorted(asr.MODELS), help="Whisper size (small.en hears better, is slower)")
    c.add_argument("--models", help="Whisper model folder (default ~/.cache/al-venus/whisper-<model>)")
    c.add_argument("--noise-db", type=float, default=-35.0, help="silence threshold in dB")
    c.add_argument("--min-silence", type=float, default=0.35, help="shortest pause that splits pieces, seconds")
    c.add_argument("--max-pause", type=float, default=0.6, help="pauses inside a take longer than this are shortened")
    c.add_argument("--keep-pauses", action="store_true", help="never shorten pauses inside a take")
    c.set_defaults(func=cmd_cut)

    f = sub.add_parser("fetch-models", help="download the free Whisper model once")
    f.add_argument("--model", default=asr.DEFAULT_MODEL, choices=sorted(asr.MODELS))
    f.add_argument("--models")
    f.set_defaults(func=lambda a: print(asr.fetch_models(a.models, a.model)))

    a = p.parse_args(argv)
    a.func(a)
