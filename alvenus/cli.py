"""Command line: `python -m alvenus cut --script script.txt --takes clips/ --out cut.mp4`."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import asr
from .cut import TRANSITIONS, Clip, hide_jump_cuts, render, take_clips, total_length, write_srt
from .match import Take, assign, choose, join_paused
from .review import notes as review_notes
from .delivery import judge, measure
from .finish import auto_broll, finish, line_spans, parse_broll
from . import plan as plan_file
from .style import LOOKS
from .presets import PRESETS, defaults as preset_defaults, describe as describe_presets
from .wordtime import timed_words
from .graphics import mark as mark_words, parse_charts, parse_highlights, parse_lines, parse_lower_thirds, parse_stats
from .refine import find_fillers, has_restart, keep_last_attempt
from .media import duration, frame_rate, has_video, load_audio, need_ffmpeg, speech_regions, video_size
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
    missing = [f"--{k}" for k in ("script", "takes", "out") if not getattr(a, k)]
    if missing:
        raise SystemExit(f"cut needs {', '.join(missing)} (on the command line or in --plan)")
    t0 = time.time()
    script = read_script(Path(a.script))
    sources = find_sources(a.takes)
    cutaways = parse_broll(a.broll or [], len(script))
    lower_thirds = parse_lower_thirds(a.lower_third or [], len(script))
    card_lines = parse_lines(a.card or [], len(script), "--card")
    highlights = parse_highlights(a.highlight or [], script)
    stats = parse_stats(a.stat or [], len(script))
    charts = parse_charts(a.chart or [], len(script))
    if getattr(a, "broll_dir", None):
        taken = {c.line for c in cutaways} | set(card_lines) | {x.line for x in stats} | {x.line for x in charts}
        auto, auto_notes = auto_broll(script, Path(a.broll_dir), taken, {c.path.resolve() for c in cutaways},
                                      {c.line for c in cutaways})
        cutaways = sorted(cutaways + auto, key=lambda c: c.line)
        for n in auto_notes:
            print("   " + n)
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
    model = asr.Remembering(a.models, name=a.model, enabled=not a.fresh_listen)
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

    if model.hits:
        print(f"   {model.hits} of {model.hits + model.misses} pieces already heard in an earlier run; reused")
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
    fillers_cut = 0
    for c in picked:
        t = c.take
        at_break = c.line in breaks
        remove = [] if a.keep_fillers else find_fillers(t, sources[t.source], load_audio(sources[t.source], SR), model, SR, a.noise_db, script[c.line])
        if remove:
            fillers_cut += len(remove)
            t.notes.append(f"{len(remove)} filler sound(s) cut out")
        clips += take_clips(sources[t.source], t.source, c.line, t.start, t.end, lengths[t.source],
                            tail=a.scene_beat if at_break else a.beat,
                            max_pause=None if a.keep_pauses else a.max_pause,
                            room=quiet_around(t, pieces), hold_short=at_break, remove=remove)
    if fillers_cut:
        print(f"   cut out {fillers_cut} filler sound(s) (um, uh) inside the chosen takes")
    if a.reframe == "auto":
        # Wide footage going into a taller frame follows the subject instead of blur-filling.
        from .reframe import track

        tw, th = (int(x) for x in ASPECTS[a.aspect].split("x"))
        for c in clips:
            sz = video_size(sources[c.source]) if has_video(sources[c.source]) else None
            if sz and sz[0] / sz[1] > 1.15 * tw / th:
                c.reframe = track(sources[c.source], c.start, c.end)
        if any(c.reframe for c in clips):
            print(f"   reframed {sum(1 for c in clips if c.reframe)} wide clip(s) to follow the subject")
    if not a.no_punch_in:
        hide_jump_cuts(clips)
    if TRANSITIONS.get(a.transition):
        # The first clip of each line that follows a blank line comes in with the transition.
        for prev, c in zip(clips, clips[1:]):
            if prev.line != c.line and prev.line in breaks:
                c.transition, c.tdur = a.transition, a.transition_seconds
    room_tone = find_room_tone(pieces, picked[0].take.source, lengths[picked[0].take.source]) if picked else None

    print("5/5 cutting")
    srt = out.with_suffix(".srt")
    write_srt(srt, clips, script)
    vids = [s for s in sources if has_video(s)]
    fps = frame_rate(vids[0]) if vids else 30.0
    finish_notes: list[str] = []
    pop = a.captions and a.caption_style == "pop"
    graphics_wanted = bool(lower_thirds or card_lines or highlights or stats or charts)
    if cutaways or music or a.title or a.end_card or pop or a.look != "natural" or graphics_wanted:
        # Cut first (at higher quality), then grade and lay B-roll, music and
        # titles on top; captions go on last.
        base = out.with_name(out.stem + ".base.mp4")
        render(sources, clips, base, None, size=ASPECTS[a.aspect], fps=fps, room_tone=room_tone, crf=14)
        words = None
        if pop or card_lines or highlights:
            loaded: dict[int, object] = {}
            def audio_of(k: int):
                if k not in loaded:
                    loaded.clear()
                    loaded[k] = load_audio(sources[k], SR)
                return loaded[k]
            words = timed_words(clips, script, audio_of, SR)
            mark_words(words, highlights)
        finish_notes = finish(base, out, ASPECTS[a.aspect], fps, line_spans(clips), cutaways, music, a.music_lufs,
                              a.title, a.end_card, srt=srt if a.captions and not pop else None,
                              words=words if pop else None, look=a.look, accent=a.accent,
                              lower_thirds=lower_thirds, card_lines=card_lines, all_words=words,
                              stats=stats, charts=charts)
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
    plan_file.write(out.with_suffix(".plan.json"), a, choices, cutaways)
    out.with_suffix(".decisions.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    review = review_notes(script, choices, takes, sources, total_length(clips))
    if finish_notes:
        review += "\n## Finishing\n\n" + "".join(f"- {n}\n" for n in finish_notes)
    out.with_suffix(".notes.md").write_text(review, encoding="utf-8")
    print()
    for c in choices:
        pick = f"take {c.take.index} ({sources[c.take.source].name})" if c.take else "MISSING"
        print(f"line {c.line + 1}: {pick:28}  {c.reason}")
    print("\n" + review)
    print(f"wrote {out} ({duration(out):.1f}s) + .edl timeline in {report['seconds_taken']}s")
    print(f"to change it, edit {out.with_suffix('.plan.json')} and run: alvenus cut --plan {out.with_suffix('.plan.json')}")


def cmd_study(a: argparse.Namespace) -> None:
    from .reference import describe, study

    need_ffmpeg()
    for ref in a.reference:
        path = Path(ref)
        style = study(path, Path(a.out_dir) if a.out_dir else path.parent, listen=not a.no_listen)
        print(describe(style) + "\n")


def cmd_scan(a: argparse.Namespace) -> None:
    from .scan import scan

    need_ffmpeg()
    r = scan(a.clips, Path(a.out_dir) if a.out_dir else None)
    for c in r["clips"]:
        sound = "has sound" if c["own_sound"] else "silent"
        print(f"{Path(c['file']).name}: {c['seconds']}s, {c['shape']} ({c['size']}), {sound}, "
              f"{len(c['cuts_inside_at'])} cut(s) inside")
    print("frames to look at: " + ", ".join(r["contact_sheets"]))


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
    c.add_argument("--preset", help="starting style: " + ", ".join(PRESETS) + " (see: alvenus presets)")
    c.add_argument("--plan", help="edit plan JSON (each cut writes one beside its output); flags typed here win over it")
    c.add_argument("--script", help="text file, one spoken line per row")
    c.add_argument("--takes", nargs="+", help="recording(s) or folder(s) of clips, video or audio")
    c.add_argument("--out", help="output MP4 (an .edl timeline, .srt captions and .notes.md review are written beside it)")
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
    c.add_argument("--broll-dir", metavar="FOLDER", help="pick cutaway shots from this folder by matching their names (and tags in its broll.json) to the script's words")
    c.add_argument("--broll", action="append", metavar="LINE=FILE[@SEC]", help="lay a cutaway shot over a line, voice kept, e.g. --broll 3=market.mp4@4.5 (repeatable)")
    c.add_argument("--music", help="music file to play under the cut; it dips whenever someone speaks")
    c.add_argument("--music-lufs", type=float, default=-22.0, help="music loudness between lines (voice sits at -16)")
    c.add_argument("--title", help="opening title, shown over the first seconds")
    c.add_argument("--end-card", help="text on a closing card after the last line (e.g. a call to action)")
    c.add_argument("--look", default="natural", choices=sorted(LOOKS), help="colour grade for the whole cut, B-roll included")
    c.add_argument("--caption-style", default="pop", choices=["pop", "classic"], help="pop: short phrases, each word lights up as it is said; classic: one plain line")
    c.add_argument("--accent", default="#FFD23F", help="accent colour for captions, title bar and end card, as #RRGGBB")
    c.add_argument("--transition", default="cut", choices=list(TRANSITIONS), help="how a new scene (after a blank line in the script) comes in")
    c.add_argument("--transition-seconds", type=float, default=0.5, help="length of that transition")
    c.add_argument("--lower-third", action="append", metavar="LINE=NAME|ROLE", help="animated name tag when a line starts, e.g. --lower-third \"1=Mara Ilić|Night baker\"")
    c.add_argument("--card", action="append", metavar="LINE", help="show this line as a full-screen kinetic text card, words appearing as they are said (voice kept)")
    c.add_argument("--highlight", action="append", metavar="LINE=WORDS", help="put a marker highlight behind words, e.g. --highlight \"3=broken clocks\"")
    c.add_argument("--stat", action="append", metavar="LINE=NUMBER|LABEL", help="big-number card over a line, counting up as it is said, e.g. --stat \"3=73%%|of stalls open after midnight\"")
    c.add_argument("--chart", action="append", metavar="LINE=BARS|TITLE", help="animated bar chart over a line, e.g. --chart \"2=Mon 3, Tue 5, Wed 9|Stalls open\"")
    c.add_argument("--no-captions", dest="captions", action="store_false", help="turn captions off (when a preset turns them on)")
    c.add_argument("--reframe", default="auto", choices=["auto", "blur"], help="wide footage in a taller frame: auto follows the subject; blur fits it whole on a blurred copy")
    c.add_argument("--keep-fillers", action="store_true", help="leave filler sounds (um, uh) inside takes instead of cutting them out")
    c.add_argument("--no-punch-in", action="store_true", help="don't zoom in to hide jump cuts between shots from the same camera")
    c.add_argument("--fresh-listen", action="store_true", help="listen to every take again instead of reusing what was heard before")
    c.set_defaults(func=cmd_cut)
    args = list(sys.argv[1:] if argv is None else argv)
    # Settings stack up: preset, then plan, then flags typed now.
    if args and args[0] == "cut":
        from_plan = plan_file.load(Path(args[args.index("--plan") + 1])) if "--plan" in args[:-1] else {}
        preset = args[args.index("--preset") + 1] if "--preset" in args[:-1] else from_plan.get("preset")
        if preset:
            c.set_defaults(preset=preset, **preset_defaults(preset))
        c.set_defaults(**from_plan)

    ps = sub.add_parser("presets", help="list the starting styles")
    ps.set_defaults(func=lambda a: print("Starting styles (use with: alvenus cut --preset NAME ...):\n" + describe_presets()))

    f = sub.add_parser("fetch-models", help="download the free Whisper model once")
    f.add_argument("--model", default=asr.DEFAULT_MODEL, choices=sorted(asr.MODELS))
    f.add_argument("--models")
    f.set_defaults(func=lambda a: print(asr.fetch_models(a.models, a.model)))

    r = sub.add_parser("study", help="measure the style of a reference video (shape, cut rhythm, pace, pauses)")
    r.add_argument("reference", nargs="+", help="reference video file(s) on this computer")
    r.add_argument("--out-dir", help="where to write .style.json and .sheet.png (default: beside the reference)")
    r.add_argument("--no-listen", action="store_true", help="skip transcribing (faster; no words-per-minute)")
    r.set_defaults(func=cmd_study)

    b = sub.add_parser("scan", help="look through cutaway clips (B-roll): length, shape, and a contact sheet of frames with times")
    b.add_argument("clips", nargs="+", help="B-roll folder(s) or file(s)")
    b.add_argument("--out-dir", help="where to write broll.json and the sheets (default: the folder scanned)")
    b.set_defaults(func=cmd_scan)

    d = sub.add_parser("doctor", help="check that FFmpeg, Python packages and models are ready")
    d.set_defaults(func=cmd_doctor)

    a = p.parse_args(args)
    a.func(a)
