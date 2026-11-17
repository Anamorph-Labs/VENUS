"""Command line: `python -m alvenus cut --script script.txt --takes clips/ --out cut.mp4`."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from . import asr
from .cut import Clip, hide_jump_cuts, render, take_clips, write_srt
from .match import Take, assign, choose, join_paused
from .review import notes as review_notes
from .delivery import judge, measure
from .finish import finish, line_spans, parse_broll
from .refine import has_restart, keep_last_attempt
from .media import duration, frame_rate, has_video, load_audio, need_ffmpeg, speech_regions
from .timeline import write_edl

SR = asr.SAMPLE_RATE
EDGE = 0.1  # sound this close to a file's start or end means the take is clipped
MEDIA = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".mts", ".wav", ".mp3", ".m4a", ".aac", ".flac"}


def read_script(path: Path) -> list[str]:
    lines = [l.strip() for l in path.read_text(encoding="utf-8").splitlines()]
    return [l for l in lines if l and not l.startswith("#")]


def scene_breaks(path: Path) -> set[int]:
    """Lines (0-based) followed by a blank line: the end of a beat or scene,
    where the cut should breathe a little longer."""
    breaks, n, blank = set(), -1, False
    for raw in path.read_text(encoding="utf-8").splitlines():
        l = raw.strip()
        if l.startswith("#"):
            continue
        if not l:
            blank = True
            continue
        if blank and n >= 0:
            breaks.add(n)
        n, blank = n + 1, False
    return breaks


def quiet_around(t: Take, pieces: list[tuple[int, float, float]]) -> tuple[float, float]:
    """End of the sound before a take and start of the sound after it, in its file."""
    before = [e for k, s, e in pieces if k == t.source and e <= t.start + 0.01]
    after = [s for k, s, e in pieces if k == t.source and s >= t.end - 0.01]
    lo = max(before, default=0.0)
    if any("restarted inside the take" in n for n in t.notes):
        lo = max(lo, t.start - 0.1)  # don't reach back into the false start
    return lo, min(after, default=float("inf"))


def find_room_tone(pieces: list[tuple[int, float, float]], source: int, length: float) -> tuple[int, float, float] | None:
    """The longest quiet stretch in a file: a clean sample of the room."""
    spans = [(0.0, None)] + [(e, None) for k, s, e in pieces if k == source]
    starts = [s for k, s, e in pieces if k == source] + [length]
    best = max(((s - e, e, s) for (e, _), s in zip(spans, starts)), default=None)
    if not best or best[0] < 0.5:
        return None
    _, a, b = best
    return source, a + 0.1, b - 0.1


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


ASPECTS = {"16:9": "1920x1080", "9:16": "1080x1920", "1:1": "1080x1080", "4:5": "1080x1350"}


def apply_picks(choices, takes: list[Take], picks: list[str], n_lines: int) -> None:
    """Overrules from the person or their AI: "2=5" uses take 5 for line 2,
    "2=none" leaves line 2 out."""
    by_index = {t.index: t for t in takes}
    for p in picks:
        try:
            line_s, take_s = p.split("=")
            line = int(line_s) - 1
            assert 0 <= line < n_lines
        except (ValueError, AssertionError):
            raise SystemExit(f"--pick {p!r}: use LINE=TAKE, e.g. --pick 2=5 (or 2=none)")
        c = choices[line]
        if take_s.strip().lower() == "none":
            c.take, c.reason = None, "left out on request"
            continue
        t = by_index.get(int(take_s))
        if t is None:
            raise SystemExit(f"--pick {p}: there is no take {take_s} (see the take numbers in the decisions file)")
        c.take, c.reason = t, "chosen on request"
        if t not in c.candidates:
            c.candidates.append(t)


def cmd_cut(a: argparse.Namespace) -> None:
    need_ffmpeg()
    t0 = time.time()
    script = read_script(Path(a.script))
    sources = find_sources(a.takes)
    cutaways = parse_broll(a.broll or [], len(script))
    music = Path(a.music) if a.music else None
    if music is not None and not music.exists():
        raise SystemExit(f"--music: {music} not found")
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
    restarts = [t for t in takes if t.line is not None and has_restart(t, script[t.line])]
    if restarts:
        print(f"   {len(restarts)} take(s) restart mid-line; finding the last clean attempt")
        for t in restarts:
            keep_last_attempt(t, script[t.line], sources[t.source], load_audio(sources[t.source], SR), model, SR, a.noise_db)
    print("   measuring delivery (level, pace, pitch, ending)")
    for k in sorted({t.source for t in takes if t.line is not None}):
        wav = load_audio(sources[k], SR)
        for t in takes:
            if t.source == k and t.line is not None:
                t.delivery = measure(wav, t.start, t.end)
                t.delivery.words_per_sec = round(len(t.text.split()) / max(t.length, 0.1), 2)
    judge(takes)
    choices = choose(takes, script)
    apply_picks(choices, takes, a.pick or [], len(script))
    picked = [c for c in choices if c.take]

    print("4/5 trimming" + ("" if a.keep_pauses else " (long pauses inside takes shortened)"))
    breaks = scene_breaks(Path(a.script))
    clips: list[Clip] = []
    for c in picked:
        t = c.take
        at_break = c.line in breaks
        clips += take_clips(sources[t.source], t.source, c.line, t.start, t.end, lengths[t.source],
                            tail=a.scene_beat if at_break else a.beat,
                            max_pause=None if a.keep_pauses else a.max_pause,
                            room=quiet_around(t, pieces), hold_short=at_break)
    if not a.no_punch_in:
        hide_jump_cuts(clips)
    room_tone = find_room_tone(pieces, picked[0].take.source, lengths[picked[0].take.source]) if picked else None

    print("5/5 cutting")
    srt = out.with_suffix(".srt")
    write_srt(srt, clips, script)
    vids = [s for s in sources if has_video(s)]
    fps = frame_rate(vids[0]) if vids else 30.0
    finish_notes: list[str] = []
    if cutaways or music or a.title or a.end_card:
        # Cut first, then lay B-roll, music and titles on top; captions go on last.
        base = out.with_name(out.stem + ".base.mp4")
        render(sources, clips, base, None, size=ASPECTS[a.aspect], fps=fps, room_tone=room_tone)
        finish_notes = finish(base, out, ASPECTS[a.aspect], fps, line_spans(clips), cutaways, music, a.music_lufs,
                              a.title, a.end_card, srt=srt if a.captions else None)
        base.unlink()
        for n in finish_notes:
            print("   " + n)
    else:
        render(sources, clips, out, srt if a.captions else None, size=ASPECTS[a.aspect], fps=fps, room_tone=room_tone)
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
                        "delivery": vars(t.delivery) if t.delivery is not None else None,
                    }
                    for t in c.candidates
                ],
            }
            for c in choices
        ],
        "finishing": {
            "broll": [{"line": c.line + 1, "file": str(c.path), "from_second": c.offset} for c in cutaways],
            "music": str(music) if music else None,
            "title": a.title, "end_card": a.end_card, "notes": finish_notes,
        },
        "unused": [
            {"take": t.index, "file": sources[t.source].name, "start": round(t.start, 2), "end": round(t.end, 2),
             "heard": t.text, "notes": t.notes}
            for t in takes if t.line is None
        ],
    }
    out.with_suffix(".decisions.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    review = review_notes(script, choices, takes, sources, sum(c.length for c in clips))
    if finish_notes:
        review += "\n## Finishing\n\n" + "".join(f"- {n}\n" for n in finish_notes)
    out.with_suffix(".notes.md").write_text(review, encoding="utf-8")
    print()
    for c in choices:
        pick = f"take {c.take.index} ({sources[c.take.source].name})" if c.take else "MISSING"
        print(f"line {c.line + 1}: {pick:28}  {c.reason}")
    print("\n" + review)
    print(f"wrote {out} ({duration(out):.1f}s) + .edl timeline in {report['seconds_taken']}s")


def cmd_study(a: argparse.Namespace) -> None:
    from .reference import describe, study

    need_ffmpeg()
    for ref in a.reference:
        path = Path(ref)
        style = study(path, Path(a.out_dir) if a.out_dir else path.parent, listen=not a.no_listen)
        print(describe(style) + "\n")


def cmd_doctor(a: argparse.Namespace) -> None:
    """Check everything the cutter needs, in plain words."""
    import shutil
    import subprocess
    import sys

    ok = True

    def say(good: bool, what: str, fix: str = "") -> None:
        nonlocal ok
        ok &= good
        print(f"  {'OK ' if good else 'NO '} {what}" + ("" if good else f"\n       fix: {fix}"))

    print("Checking your setup:")
    say(sys.version_info >= (3, 10), f"Python {sys.version.split()[0]}", "install Python 3.10 or newer")
    for mod in ("numpy", "onnxruntime"):
        try:
            __import__(mod)
            say(True, f"{mod} installed")
        except ImportError:
            say(False, f"{mod} missing", f"pip install {mod}")
    ff = shutil.which("ffmpeg")
    say(bool(ff and shutil.which("ffprobe")), "FFmpeg installed", "install FFmpeg from https://ffmpeg.org/download.html")
    if ff:
        enc = subprocess.run([ff, "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
        fil = subprocess.run([ff, "-hide_banner", "-filters"], capture_output=True, text=True).stdout
        say("libx264" in enc, "FFmpeg can write H.264 MP4", "install a full FFmpeg build (with libx264)")
        say(" subtitles " in fil, "FFmpeg can burn captions (only needed for --captions)", "install a full FFmpeg build (with libass)")
        say(" silencedetect " in fil and " loudnorm " in fil, "FFmpeg audio tools present", "install a full FFmpeg build")
    for name in sorted(asr.MODELS):
        d = asr.default_model_dir(name)
        have = all((d / Path(f).name).exists() for f in asr.MODEL_FILES)
        fast = (d / Path(asr.FAST_DECODER).name).exists()
        if name == asr.DEFAULT_MODEL or have:
            say(have, f"Whisper {name} downloaded" + (" (fast decoder too)" if have and fast else ""),
                f"alvenus fetch-models --model {name}")
    print("\nAll set." if ok else "\nFix the NO lines above, then run this again.")
    raise SystemExit(0 if ok else 1)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="alvenus", description="Cut a video from a script and your takes.")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("cut", help="pick the best take per script line and build the cut")
    c.add_argument("--script", required=True, help="text file, one spoken line per row")
    c.add_argument("--takes", required=True, nargs="+", help="recording(s) or folder(s) of clips, video or audio")
    c.add_argument("--out", required=True, help="output MP4 (an .edl timeline, .srt captions and .notes.md review are written beside it)")
    c.add_argument("--captions", action="store_true", help="burn the script lines in as captions")
    c.add_argument("--aspect", default="16:9", choices=sorted(ASPECTS), help="frame shape: 16:9 wide, 9:16 vertical, 1:1 square, 4:5 feed")
    c.add_argument("--pick", action="append", metavar="LINE=TAKE", help="overrule a pick, e.g. --pick 2=5 or --pick 4=none (repeatable)")
    c.add_argument("--model", default=asr.DEFAULT_MODEL, choices=sorted(asr.MODELS), help="Whisper size (small.en hears better, is slower)")
    c.add_argument("--models", help="Whisper model folder (default ~/.cache/al-venus/whisper-<model>)")
    c.add_argument("--noise-db", type=float, default=-35.0, help="silence threshold in dB")
    c.add_argument("--min-silence", type=float, default=0.35, help="shortest pause that splits pieces, seconds")
    c.add_argument("--max-pause", type=float, default=0.6, help="pauses inside a take longer than this are shortened")
    c.add_argument("--keep-pauses", action="store_true", help="never shorten pauses inside a take")
    c.add_argument("--beat", type=float, default=0.25, help="breathing room after each line, seconds")
    c.add_argument("--scene-beat", type=float, default=0.9, help="longer breath after a line followed by a blank line in the script")
    c.add_argument("--broll", action="append", metavar="LINE=FILE[@SEC]", help="lay a cutaway shot over a line, voice kept, e.g. --broll 3=market.mp4@4.5 (repeatable)")
    c.add_argument("--music", help="music file to play under the cut; it dips whenever someone speaks")
    c.add_argument("--music-lufs", type=float, default=-22.0, help="music loudness between lines (voice sits at -16)")
    c.add_argument("--title", help="opening title, shown over the first seconds")
    c.add_argument("--end-card", help="text on a closing card after the last line (e.g. a call to action)")
    c.add_argument("--no-punch-in", action="store_true", help="don't zoom in to hide jump cuts between shots from the same camera")
    c.set_defaults(func=cmd_cut)

    f = sub.add_parser("fetch-models", help="download the free Whisper model once")
    f.add_argument("--model", default=asr.DEFAULT_MODEL, choices=sorted(asr.MODELS))
    f.add_argument("--models")
    f.set_defaults(func=lambda a: print(asr.fetch_models(a.models, a.model)))

    r = sub.add_parser("study", help="measure the style of a reference video (shape, cut rhythm, pace, pauses)")
    r.add_argument("reference", nargs="+", help="reference video file(s) on this computer")
    r.add_argument("--out-dir", help="where to write .style.json and .sheet.png (default: beside the reference)")
    r.add_argument("--no-listen", action="store_true", help="skip transcribing (faster; no words-per-minute)")
    r.set_defaults(func=cmd_study)

    d = sub.add_parser("doctor", help="check that FFmpeg, Python packages and models are ready")
    d.set_defaults(func=cmd_doctor)

    a = p.parse_args(argv)
    a.func(a)
