"""Command line: `python -m alvenus cut --script script.txt --takes recording.mp4 --out cut.mp4`."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from . import asr
from .cut import plan_clips, render, write_srt
from .match import Take, assign, choose
from .media import duration, load_audio, need_ffmpeg, speech_regions

SR = asr.SAMPLE_RATE


def read_script(path: Path) -> list[str]:
    lines = [l.strip() for l in path.read_text(encoding="utf-8").splitlines()]
    return [l for l in lines if l and not l.startswith("#")]


def cmd_cut(a: argparse.Namespace) -> None:
    need_ffmpeg()
    t0 = time.time()
    script = read_script(Path(a.script))
    src = Path(a.takes)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    print(f"1/4 finding takes in {src.name}")
    regions = speech_regions(src, a.noise_db, a.min_silence)
    audio = load_audio(src, SR)

    print(f"2/4 transcribing {len(regions)} takes on this computer")
    model = asr.Whisper(a.models)
    takes: list[Take] = []
    for i, (s, e) in enumerate(regions):
        clip = audio[int(max(0, s - 0.1) * SR) : int((e + 0.1) * SR)]
        if e - s > 29:
            print(f"   warning: take {i + 1} is {e - s:.0f}s long; only the first 30s are read")
        tr = model.transcribe(clip)
        takes.append(Take(i + 1, s, e, tr.text, tr.avg_logprob))
        print(f"   {i + 1:>2} {s:7.2f}-{e:7.2f}  {tr.text}")

    print("3/4 matching takes to script lines")
    assign(takes, script)
    choices = choose(takes, script)
    picked = [c for c in choices if c.take]
    spans = [(c.take.start, c.take.end) for c in picked]
    clips = plan_clips(spans, duration(src))

    print("4/4 cutting")
    srt = out.with_suffix(".srt")
    write_srt(srt, clips, [script[c.line] for c in picked])
    render(src, clips, out, srt if a.captions else None)

    report = {
        "source": str(src),
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
                        "take": t.index, "start": round(t.start, 2), "end": round(t.end, 2),
                        "heard": t.text, "match": round(t.score, 3), "notes": t.notes,
                    }
                    for t in c.candidates
                ],
            }
            for c in choices
        ],
        "unused": [
            {"take": t.index, "start": round(t.start, 2), "end": round(t.end, 2), "heard": t.text, "notes": t.notes}
            for t in takes if t.line is None
        ],
    }
    out.with_suffix(".decisions.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print()
    for c in choices:
        pick = f"take {c.take.index}" if c.take else "MISSING"
        print(f"line {c.line + 1}: {pick:8}  {c.reason}")
    print(f"\nwrote {out} ({sum(e - s for s, e in clips):.1f}s) in {report['seconds_taken']}s")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="alvenus", description="Cut a video from a script and your takes.")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("cut", help="pick the best take per script line and build the cut")
    c.add_argument("--script", required=True, help="text file, one spoken line per row")
    c.add_argument("--takes", required=True, help="the recording with all takes (video or audio)")
    c.add_argument("--out", required=True, help="output MP4")
    c.add_argument("--captions", action="store_true", help="burn the script lines in as captions")
    c.add_argument("--models", help="Whisper model folder (default ~/.cache/al-venus/whisper-base.en)")
    c.add_argument("--noise-db", type=float, default=-35.0, help="silence threshold in dB")
    c.add_argument("--min-silence", type=float, default=0.35, help="shortest pause that splits takes, seconds")
    c.set_defaults(func=cmd_cut)

    f = sub.add_parser("fetch-models", help="download the free Whisper model once")
    f.add_argument("--models")
    f.set_defaults(func=lambda a: print(asr.fetch_models(a.models)))

    a = p.parse_args(argv)
    a.func(a)
