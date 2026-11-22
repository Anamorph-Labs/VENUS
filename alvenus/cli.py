"""Command line: `python -m alvenus cut --script script.txt --takes clips/ --out cut.mp4`."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

from . import asr
from .cut import TRANSITIONS, Clip, hide_jump_cuts, positions, push_in, render, take_clips, total_length, write_srt
from .match import Take, as_said, assign, choose, edge_word_heard, join_paused
from .review import notes as review_notes
from .delivery import judge, measure
from .finish import auto_broll, finish, line_spans, parse_broll
from . import plan as plan_file
from .style import LOOKS, TITLE_STYLES
from .presets import PRESETS, defaults as preset_defaults, describe as describe_presets, pack
from .wordtime import timed_words
from .graphics import (mark as mark_words, parse_charts, parse_highlights, parse_line_charts, parse_lines, parse_lower_thirds,
                       parse_maps, parse_quotes, parse_stats, parse_timelines)
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


def write_sheet(out: Path, marks: list[tuple[float, str]]) -> None:
    """A one-page sheet with a frame from every scene, beside the video."""
    try:
        from .draft import sheet

        if len(marks) > 24:
            marks = [marks[round(i * (len(marks) - 1) / 23)] for i in range(24)]
        sheet(out, marks, out.with_suffix(".sheet.jpg"))
        print(f"   scene sheet: {out.with_suffix('.sheet.jpg')}")
    except Exception as e:  # a sheet must never cost the video
        print(f"   (no scene sheet: {e})")


def draft_mode(a: argparse.Namespace) -> None:
    if getattr(a, "draft", False):
        from .draft import enable

        enable(ASPECTS)
        print("draft: a third of the size, quickest settings; look, change, then render without --draft")


def extras_of(a, spans: dict, n_lines: int) -> dict:
    """The documentary and travel touches asked for on the command line (or by a preset)."""
    ex: dict = {}
    lb = getattr(a, "letterbox", None)
    if lb:
        ex["letterbox"] = True if lb in (True, "true", "on", "") else float(lb)
    if getattr(a, "datestamp", None):
        ex["datestamp"] = a.datestamp
    if getattr(a, "lower_third_style", None):
        ex["lower_third_style"] = a.lower_third_style
    places = []
    for it in getattr(a, "place", None) or []:
        line, _, text = it.partition("=")
        if not line.strip().isdigit() or not 0 < int(line) <= n_lines or not text.strip():
            raise SystemExit(f"--place {it!r}: use LINE=TEXT, e.g. --place \"2=Juniper Street, 3:12 AM\"")
        if int(line) - 1 in spans:
            t0, t1 = spans[int(line) - 1]
            places.append((text.strip(), t0 + 0.2, max(t1, t0 + 3.5)))
    if places:
        ex["places"] = places
    return ex


def cmd_cut(a: argparse.Namespace) -> None:
    need_ffmpeg()
    draft_mode(a)
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
    line_charts = parse_line_charts(getattr(a, "line_chart", None) or [], len(script))
    quotes = parse_quotes(getattr(a, "quote", None) or [], script)
    maps = parse_maps(getattr(a, "map", None) or [], len(script))
    for mc in maps:
        if not Path(mc.image).exists():
            raise SystemExit(f"--map: {mc.image} not found")
    timelines = parse_timelines(getattr(a, "timeline", None) or [], len(script))
    from .talk import parse_chapters, parse_layouts

    layouts = parse_layouts(getattr(a, "layout", None) or [], len(script))
    chapters = parse_chapters(getattr(a, "chapter", None) or [], len(script))
    talk_on = bool(getattr(a, "talk", False) or layouts)
    kinetic = []
    for k in getattr(a, "kinetic", None) or []:
        line, _, emph = k.partition("=")
        if not line.strip().isdigit() or not 0 < int(line) <= len(script):
            raise SystemExit(f"--kinetic {k!r}: use LINE or LINE=word, word (the words to make big)")
        kinetic.append((int(line) - 1, {x.strip().lower() for x in emph.split(",") if x.strip()}))
    if getattr(a, "broll_dir", None):
        taken = ({c.line for c in cutaways} | set(card_lines) | {x.line for x in stats} | {x.line for x in charts}
                 | {x.line for x in line_charts} | {x.line for x in quotes} | {x.line for x in maps}
                 | {x.line for x in timelines} | {n for n, _ in kinetic})
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
    assign(takes, script)
    for t in takes:
        # Sound running into the very start or end of a file only matters when
        # a word there was lost; a take that starts the instant recording does
        # is fine as long as its first word is all there.
        t.clipped = (t.start < EDGE and not edge_word_heard(t, script, first=True)) or \
                    (t.end > lengths[t.source] - EDGE and not edge_word_heard(t, script, first=False))
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
    if not a.keep_fillers:
        # Whisper tidies "um" out of what it hears, so two takes can read the
        # same when one hesitates. Where a line has rival takes, listen for
        # fillers in each: the clean take should win, and pace is measured
        # without the hesitation.
        by_line: dict[int, list] = {}
        for t in takes:
            if t.line is not None:
                by_line.setdefault(t.line, []).append(t)
        rivals = [t for group in by_line.values() if len(group) > 1
                  for t in group if t.score >= max(o.score for o in group) - 0.05]
        for k in sorted({t.source for t in rivals}):
            wav = load_audio(sources[k], SR)
            for t in rivals:
                if t.source == k:
                    t.filler_spans = find_fillers(t, sources[k], wav, model, SR, a.noise_db, script[t.line])
                    if t.filler_spans and t.delivery is not None:
                        t.fillers = max(t.fillers, len(t.filler_spans))
                        spoken = t.length - sum(e - s for s, e in t.filler_spans)
                        t.delivery.words_per_sec = round(len(t.text.split()) / max(spoken, 0.1), 2)
    judge(takes)
    choices = choose(takes, script)
    apply_picks(choices, takes, a.pick or [], len(script))
    picked = [c for c in choices if c.take]

    print("4/5 trimming" + ("" if a.keep_pauses else " (long pauses inside takes shortened)"))
    breaks = scene_breaks(Path(a.script))
    clips: list[Clip] = []
    room_end: dict[int, float] = {}  # clip index -> where the next sound starts in its file
    fillers_cut = 0
    for c in picked:
        t = c.take
        at_break = c.line in breaks
        if a.keep_fillers:
            remove = []
        elif getattr(t, "filler_spans", None) is not None:  # already listened for while comparing takes
            remove = t.filler_spans
        else:
            remove = find_fillers(t, sources[t.source], load_audio(sources[t.source], SR), model, SR, a.noise_db, script[c.line])
        if remove:
            fillers_cut += len(remove)
            t.notes.append(f"{len(remove)} filler sound(s) cut out")
        room = quiet_around(t, pieces)
        clips += take_clips(sources[t.source], t.source, c.line, t.start, t.end, lengths[t.source],
                            tail=a.scene_beat if at_break else a.beat,
                            max_pause=None if a.keep_pauses else a.max_pause,
                            room=room, hold_short=at_break, remove=remove)
        room_end[len(clips) - 1] = room[1] if room else lengths[t.source]
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
    pushed = {int(x) - 1 for x in getattr(a, "push_in", None) or [] if str(x).isdigit()} | {line for line, _ in highlights}
    if pushed and not getattr(a, "no_push_in", False):
        print(f"   slow push-in on {push_in(clips, pushed)} line(s)")
    if TRANSITIONS.get(a.transition):
        # The first clip of each line that follows a blank line comes in with the transition.
        for prev, c in zip(clips, clips[1:]):
            if prev.line != c.line and prev.line in breaks:
                c.transition, c.tdur = a.transition, a.transition_seconds
    if music is not None and not getattr(a, "no_beat_sync", False) and clips:
        from .beats import beats_of, sync

        starts = {i for i in range(1, len(clips)) if clips[i - 1].line != clips[i].line and clips[i - 1].line in breaks}
        for n in sync(clips, beats_of(music, total_length(clips) + 2), starts, room_end):
            print("   " + n)
    room_tone = find_room_tone(pieces, picked[0].take.source, lengths[picked[0].take.source]) if picked else None

    print("5/5 cutting")
    srt = out.with_suffix(".srt")
    # Captions show what was actually said in each chosen take, not the script.
    spoken = list(script)
    for c in picked:
        spoken[c.line] = as_said(script[c.line], c.take.text)
    write_srt(srt, clips, spoken)
    vids = [s for s in sources if has_video(s)]
    fps = frame_rate(vids[0]) if vids else 30.0
    finish_notes: list[str] = []
    pop = a.captions and a.caption_style == "pop"
    graphics_wanted = talk_on or bool(getattr(a, "letterbox", None) or getattr(a, "place", None) or getattr(a, "datestamp", None)) or bool(lower_thirds or card_lines or highlights or stats or charts or line_charts or quotes or maps or timelines or kinetic or getattr(a, "progress", False))
    sfx = None
    if not getattr(a, "no_sfx", False):
        sfx = [(t + c.tdur / 2, "whoosh") for c, t in zip(clips, positions(clips)) 
               if c.transition in ("whip", "slide", "zoom", "flash", "circle", "glitch") and c.tdur > 0]  # dissolves and dips stay silent
    if sfx or cutaways or music or a.title or a.end_card or pop or a.look != "natural" or graphics_wanted:
        # Cut first (at higher quality), then grade and lay B-roll, music and
        # titles on top; captions go on last.
        base = out.with_name(out.stem + ".base.mp4")
        render(sources, clips, base, None, size=ASPECTS[a.aspect], fps=fps, room_tone=room_tone, crf=14, voice=a.voice)
        words = None
        if pop or card_lines or highlights or kinetic or talk_on:
            loaded: dict[int, object] = {}
            def audio_of(k: int):
                if k not in loaded:
                    loaded.clear()
                    loaded[k] = load_audio(sources[k], SR)
                return loaded[k]
            words = timed_words(clips, spoken, audio_of, SR)
            mark_words(words, highlights)
        talk = None
        if talk_on:
            from .talk import direct, why

            spans_ = line_spans(clips)
            graphic = {x.line for x in list(stats) + list(charts) + list(line_charts) + list(quotes) + list(timelines)}
            wordish = {n for n, _ in highlights} | {n for n, _ in kinetic}
            kinds = direct(spans_, graphic, wordish, set(card_lines) | {m.line for m in maps} | {c.line for c in cutaways}, layouts)
            emphasis = {n: e for n, e in kinetic if e}
            for n, ws in highlights:
                emphasis.setdefault(n, set()).update(re.sub(r"[^\w%']", "", x.lower()) for x in ws)
            talk = {"kinds": kinds, "emphasis": emphasis, "chapters": chapters, "label": a.title or "", "breaks": breaks,
                    "set": getattr(a, "talk_set", None) or "dark"}
            order = sorted(spans_)
            opened = [n for n in order if kinds[n] != "full"]
            print(f"   talk layout: {len(opened)} of {len(order)} line(s) open up beside the speaker")
            (out.with_suffix(".layout.md")).write_text(
                "# Layout of each line\n\nChange one with `--layout LINE=full` or `--layout LINE=side`.\n\n"
                + "".join(f"- Line {n + 1}: **{'full frame' if kinds[n] == 'full' else 'beside its ' + ('graphic' if kinds[n] == 'graphic' else 'words')}**, "
                          f"{why(kinds[n], n, graphic, wordish, layouts, i == 0, i == len(order) - 1)}\n" for i, n in enumerate(order)),
                encoding="utf-8")
        from . import genre

        genre.EXTRAS = extras_of(a, line_spans(clips), len(script))
        finish_notes = finish(base, out, ASPECTS[a.aspect], fps, line_spans(clips), cutaways, music, a.music_lufs,
                              a.title, a.end_card, srt=srt if a.captions and not pop else None,
                              words=words if pop else None, look=a.look, accent=a.accent,
                              lower_thirds=lower_thirds, card_lines=card_lines, all_words=words,
                              stats=stats, charts=charts, sfx=sfx, line_charts=line_charts, quotes=quotes,
                              progress=getattr(a, "progress", False), maps=maps, timelines=timelines, kinetic_lines=kinetic,
                              title_style=getattr(a, "title_style", "track"), talk=talk,
                              titles=[] if talk_on else [(chapters[n], line_spans(clips)[n][0], min(line_spans(clips)[n][1], line_spans(clips)[n][0] + 3.4))
                                                         for n in sorted(chapters) if n in line_spans(clips)],
                              scene_marks=[t for i, t in enumerate(positions(clips))
                                           if i and clips[i - 1].line != clips[i].line and clips[i - 1].line in breaks])
        genre.EXTRAS = {}
        thumb_from = base
    else:
        thumb_from = None
        render(sources, clips, out, srt if a.captions else None, size=ASPECTS[a.aspect], fps=fps, room_tone=room_tone, voice=a.voice)
    try:
        from .thumb import make as make_thumb, pick_moment

        covered = (set(card_lines) | {x.line for x in list(stats) + list(charts) + list(line_charts) + list(quotes) + maps + timelines}
                   | {n for n, _ in kinetic}
                   | {c.line for c in cutaways})
        tw, th = (int(x) for x in ASPECTS[a.aspect].split("x"))
        make_thumb(thumb_from or out, pick_moment(line_spans(clips), covered, pushed), out.with_suffix(".thumb.jpg"),
                   a.title or script[0], tw, th, a.accent, a.look if thumb_from else "natural")
    except Exception as e:  # a thumbnail must never cost the cut
        print(f"   (no thumbnail: {e})")
    if thumb_from is not None:
        base.unlink()
        for n in finish_notes:
            print("   " + n)
    write_edl(out.with_suffix(".edl"), out.stem, sources, clips, script, fps)
    try:
        from .handoff import write_xml

        alts = write_xml(out.with_suffix(".xml"), out.stem, sources, clips, script, fps, ASPECTS[a.aspect], choices, music)
        print(f"   timeline for Premiere / Resolve: {out.with_suffix('.xml').name}"
              + (f" ({alts} unused take(s) on switched-off tracks, ready to swap in)" if alts else ""))
    except Exception as e:  # the hand-off must never cost the cut
        print(f"   (no XML timeline: {e})")
    write_sheet(out, [((a0 + a1) / 2, f"line {n + 1}") for n, (a0, a1) in sorted(line_spans(clips).items())])

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
    review += self_review(out, script)
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
    if a.as_pack:
        from .learnstyle import learn

        pack_, path, report = learn(a.reference, a.as_pack)
        where = Path(a.out_dir) if a.out_dir else (Path(a.reference[0]) if Path(a.reference[0]).is_dir() else Path(a.reference[0]).parent)
        (where / f"{a.as_pack}.style.md").write_text(report, encoding="utf-8")
        print(pack_["about"])
        print(f"saved the style pack as {path}; what was measured: {where / (a.as_pack + '.style.md')}")
        print(f"use it: alvenus cut ... --preset {a.as_pack}  |  alvenus montage ... --style {a.as_pack}  |  alvenus make sb.json --style {a.as_pack}")
        return
    for ref in a.reference:
        path = Path(ref)
        style = study(path, Path(a.out_dir) if a.out_dir else path.parent, listen=not a.no_listen)
        print(describe(style) + "\n")


def by_place(shots, places: list[str]):
    """A travel reel visits its places one after another: shots of clips with
    no place come first (the opening), then each place's shots in the order
    the places were given. Shot lengths stay whole beats, so every cut still
    lands on the beat."""
    keys = [p.partition("=")[0].strip().lower() for p in places]

    def rank(s) -> int:
        n = Path(s.clip).name.lower()
        for i, k in enumerate(keys):
            if k in (n, Path(n).stem):
                return i + 1
        return 0

    return sorted(shots, key=rank)  # stable: the musical order inside each group stays


def montage_extras(a, shots) -> dict:
    """Arrival titles (--place CLIP=TEXT, shown when that clip first comes on),
    the camcorder date and the cinema bars, for a montage."""
    ex: dict = {}
    if getattr(a, "letterbox", None):
        ex["letterbox"] = float(a.letterbox)
    if getattr(a, "datestamp", None):
        ex["datestamp"] = a.datestamp
    pos = [sum(x.length for x in shots[:k]) for k in range(len(shots))]
    total = sum(x.length for x in shots)
    arrivals = []
    for it in getattr(a, "place", None) or []:
        clip, _, text = it.partition("=")
        key = clip.strip().lower()
        hit = next((p for p, s in zip(pos, shots) if key in (Path(s.clip).name.lower(), Path(s.clip).stem.lower())), None)
        if hit is None or not text.strip():
            raise SystemExit(f"--place {it!r}: use CLIP=Place|Country|coordinates, with CLIP a clip's file name in the montage")
        start = max(hit + 0.05, 3.1 if a.title else 0.0)  # never on top of the opening title
        arrivals.append((text.strip(), start, min(total - 0.3, start + 2.8)))
    if arrivals:
        ex["arrivals"] = arrivals
    return ex


def cmd_montage(a: argparse.Namespace) -> None:
    from . import montage as mt

    need_ffmpeg()
    draft_mode(a)
    t0 = time.time()
    settings: dict = {}
    if a.plan:
        shots, settings = mt.load_plan(Path(a.plan))
        for k in ("music", "aspect", "look", "title", "accent", "out", "title_style"):
            if getattr(a, k) is None:  # flags typed now win over the plan
                setattr(a, k, settings.get(k))
    sty = pack(a.style, "aspect", "look", "accent", "title_style")
    a.aspect, a.look, a.accent = a.aspect or sty.get("aspect", "9:16"), a.look or sty.get("look", "punchy"), a.accent or sty.get("accent", "#FFD23F")
    if not a.music or not a.out or not (a.plan or a.clips):
        raise SystemExit("montage needs --clips, --music and --out (or --plan)")
    music, out = Path(a.music), Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if not a.plan:
        files = mt.find_clips(a.clips)
        if not files:
            raise SystemExit("no video clips found")
        print(f"1/3 looking at {len(files)} clip(s)")
        infos = [mt.analyse(f) for f in files]
        print("2/3 listening to the music")
        beats, energy, down = mt.song_map(music)
        total = min(a.length or duration(music), duration(music))
        tempo = 60 / (beats[1] - beats[0]) if len(beats) > 1 else 0
        print(f"   {tempo:.0f} beats a minute, {len(beats)} beats; quiet parts {sum(e < 0.4 for e in energy)}, loud {sum(e >= 0.75 for e in energy)}")
        shots = mt.plan(infos, beats, energy, down, total, seed=a.seed)
        if getattr(a, "match_cut", False):
            from .matchcut import order_shots

            aw, ah = (int(x) for x in ASPECTS[a.aspect].split("x"))
            shots, groups = order_shots(shots, aw / ah)
            linked = [g for g in groups if len(g) > 1]
            print(f"   match cuts: {sum(len(g) for g in linked)} shots in {len(linked)} run(s) of the same framing, lined up shot to shot")
        if getattr(a, "place", None):
            shots = by_place(shots, a.place)
            print(f"   shots grouped by place, in the order given: {', '.join(p.partition('=')[2].split('|')[0] for p in a.place)}")
    from . import genre

    for k in ("place", "datestamp", "letterbox"):
        if getattr(a, k, None) in (None, []) and settings.get(k) not in (None, []):
            setattr(a, k, settings[k])
    genre.EXTRAS = montage_extras(a, shots)
    print(f"3/3 cutting {len(shots)} shots")
    mt.render(shots, music, out, ASPECTS[a.aspect], look=a.look, title=a.title, accent=a.accent,
              title_style=a.title_style or sty.get("title_style", "stamp"))
    if not a.draft:  # flashing found? calm the shots there (no white flash, no zoom kick) and cut again
        try:
            from .selfcheck import review

            hot = [t for f in review(out) if getattr(f, "kind", "") == "flash" for t in f.times]
        except Exception:
            hot = []
        pos = [sum(x.length for x in shots[:k]) for k in range(len(shots))]
        calm = [k for k, (p, s) in enumerate(zip(pos, shots)) if any(p - 1.0 < t < p + s.length + 1.0 for t in hot) and (s.flash or s.pulse)]
        if calm:
            for k in calm:
                shots[k].flash, shots[k].pulse = False, 0.0
            print(f"self-review: too much flashing; calmed shot(s) {', '.join(str(k + 1) for k in calm)} and cutting again")
            mt.render(shots, music, out, ASPECTS[a.aspect], look=a.look, title=a.title, accent=a.accent,
                      title_style=a.title_style or sty.get("title_style", "stamp"))
    plan_path = out.with_suffix(".montage.json")
    mt.save_plan(plan_path, shots, {"music": str(music.resolve()), "out": str(out.resolve()), "aspect": a.aspect,
                                    "look": a.look, "title": a.title, "accent": a.accent,
                                    "title_style": a.title_style or sty.get("title_style", "stamp"),
                                    "place": a.place or [], "datestamp": a.datestamp, "letterbox": a.letterbox})
    genre.EXTRAS = {}
    for k, s in enumerate(shots):
        print(f"   {k + 1:>2} {Path(s.clip).name[:22]:22} {s.start:6.2f}s  {s.length:4.2f}s on screen  {s.why}")
    pos = [sum(x.length for x in shots[:k]) for k in range(len(shots))]
    write_sheet(out, [(p + s.length / 2, f"{k + 1} {Path(s.clip).stem[:18]}") for k, (p, s) in enumerate(zip(pos, shots))])
    print(self_review(out).strip())
    print(f"wrote {out} ({sum(s.length for s in shots):.1f}s) in {time.time() - t0:.0f}s")
    print(f"to change it, edit {plan_path} and run: alvenus montage --plan {plan_path}")


def self_review(out: Path, spoken=()) -> str:
    """Venus watches the finished video once more; never fails the run."""
    try:
        from .selfcheck import review

        notes = review(out, spoken=spoken)
    except Exception as e:
        return f"\n## Self-review\n\n- could not run: {e}\n"
    if not notes:
        return "\n## Self-review\n\nAll clear: text readable and on long enough, no stray black, no flashing, sound and picture in step.\n"
    return "\n## Self-review\n\n" + "".join(f"- {n}\n" for n in notes)


def cmd_review(a: argparse.Namespace) -> None:
    need_ffmpeg()
    print(self_review(Path(a.video)).strip())


def cmd_make(a: argparse.Namespace) -> None:
    from . import story

    if a.example:
        Path(a.example).write_text(json.dumps(story.EXAMPLE, indent=2), encoding="utf-8")
        print(f"wrote an example storyboard to {a.example}; every scene type is in it")
        return
    if a.template:
        from .templates import TEMPLATES

        if not a.storyboard:
            raise SystemExit("--template needs a file name to write the starter storyboard to")
        p = Path(a.storyboard)
        if p.exists():
            raise SystemExit(f"{p} already exists; give a new file name for the starter storyboard")
        p.write_text(json.dumps(TEMPLATES[a.template], indent=2), encoding="utf-8")
        print(f"wrote the {a.template} starter to {p}: swap the words for your subject, keep the shape, then: "
              f"alvenus check {p}, show the creator, alvenus approve {p} --by NAME, alvenus make {p} --out video.mp4")
        return
    if not a.storyboard or not a.out:
        raise SystemExit("make needs a storyboard file and --out (or --example FILE to see one)")
    from .approval import require

    print(f"storyboard {require(Path(a.storyboard))}")
    need_ffmpeg()
    draft_mode(a)
    t0 = time.time()
    from . import nodes as nd

    src = Path(a.storyboard)
    doc = nd.read(src) if nd.is_nodes(src) else None
    if doc is not None:  # a node file: check the nodes and locks, then build its storyboard
        problems = nd.check(doc)
        if problems:
            raise SystemExit("node file problems:\n  " + "\n  ".join(problems))
        changed = nd.changes(doc, nd.read_last(src))
        if changed:
            print("changed since the last build: " + ", ".join(c if not c.startswith("-") else f"{c[1:]} (removed)" for c in changed))
        sb = story.load(src, nd.to_storyboard(doc))
    else:
        sb = story.load(src)
    style = a.style or sb.get("style")
    sb = {**pack(style, "aspect", "look", "accent", "transition", "transition_seconds", "title_style", "background", "design", "letterbox", "lower_third_style", "quote_style"), **sb}
    aspect = a.aspect or sb.get("aspect", "16:9")
    if aspect not in ASPECTS:
        raise SystemExit(f"aspect {aspect!r}: choose from {', '.join(sorted(ASPECTS))}")
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if a.scene:
        ids = [x["id"] for x in nd.scenes_of(doc)] if doc else []
        n = ids.index(a.scene) + 1 if a.scene in ids else int(a.scene) if a.scene.isdigit() else 0
        if not 1 <= n <= len(sb["scenes"]):
            raise SystemExit(f"--scene {a.scene}: the storyboard has scenes 1 to {len(sb['scenes'])}"
                             + (f" ({', '.join(ids)})" if ids else ""))
        one = {**sb, "scenes": [sb["scenes"][n - 1]], "end_card": None, "music": None, "progress": False,
               "_place": (n - 1, len(sb["scenes"]))}
        first = next((x for x in sb["scenes"] if x["type"] == "title" and x.get("text")), None)
        if first and not sb.get("label"):  # the page header names the whole video, as in the full build
            from .paper import plain

            one["label"] = plain(first["text"])
        print(f"scene {n} on its own, to check it quickly")
        story.build(one, out, ASPECTS[aspect])
        print(f"wrote {out} ({duration(out):.1f}s) in {time.time() - t0:.0f}s")
        return
    if a.versions:
        return make_versions(sb, style, aspect, out, t0)
    print(f"building {len(sb['scenes'])} scenes at {aspect}")
    for n in story.build(sb, out, ASPECTS[aspect]):
        print("   " + n)
    fixed: list[str] = []
    asked = [dict(x) for x in sb["scenes"]], sb.get("end_card_seconds")
    for _ in range(2 if not (a.no_fix or a.draft) else 0):  # watch, fix, build again; twice at most
        try:
            from .selfcheck import review

            changes = story.autofix(sb, review(out), nd.frozen(doc) if doc else frozenset())
        except Exception as e:
            print(f"   (self-review could not run: {e})")
            break
        if not changes:
            break
        fixed += changes
        print("self-review: fixing " + "; ".join(changes) + ". Building again.")
        story.build(sb, out, ASPECTS[aspect])
    if fixed and doc is not None:  # the fixes go back on the nodes they belong to, in a copy beside the video
        fixed_doc = json.loads(json.dumps(doc))
        ids = [x["id"] for x in nd.scenes_of(fixed_doc)]
        for i, (before, sc) in enumerate(zip(asked[0], sb["scenes"])):
            for key in ("seconds", "darken", "transition"):
                if sc.get(key) != before.get(key):
                    nd.set_scene_key(fixed_doc, ids[i], key, sc[key])
        if sb.get("end_card_seconds") != asked[1]:
            nd.find(fixed_doc, "settings")["params"]["end_card_seconds"] = sb["end_card_seconds"]
        if out.parent.resolve() != src.parent.resolve():
            nd.absolute_files(fixed_doc, src.parent)
        nd.relock(fixed_doc)
        nd.write(out.with_suffix(".nodes.json"), fixed_doc)
        print(f"   fixed nodes saved as {out.with_suffix('.nodes.json')} (locked nodes were left as they are)")
    elif fixed:
        keep = {k: v for k, v in sb.items() if not k.startswith("_")}
        keep["scenes"] = [{k: v for k, v in sc.items() if not k.startswith("_")} for sc in sb["scenes"]]
        out.with_suffix(".storyboard.json").write_text(json.dumps(keep, indent=2), encoding="utf-8")
        print(f"   fixed storyboard saved as {out.with_suffix('.storyboard.json')}")
    write_sheet(out, [(a0 + (a1 - a0) * 0.6, f"{i + 1} {sb['scenes'][i]['type']}") for i, (a0, a1) in sorted(sb["_spans"].items())])
    out.with_suffix(".why.md").write_text(story.explain(sb), encoding="utf-8")
    redrawn = sb.get("_redrawn")
    if doc is not None:
        ids = [x["id"] for x in nd.scenes_of(doc)]
        nd.save_last(src, doc, out, sb["_spans"], [ids[i] for i in redrawn or []])
        if redrawn is not None and len(redrawn) < len(ids):
            print(f"   redrew {', '.join(ids[i] for i in redrawn) or 'no scenes'} ({len(redrawn)} of {len(ids)}); "
                  "the rest were kept from the last build")
    elif redrawn is not None and len(redrawn) < len(sb["scenes"]):
        print(f"   redrew {len(redrawn)} of {len(sb['scenes'])} scenes; the rest were kept from the last build")
    print(self_review(out).strip())
    print(f"wrote {out} ({duration(out):.1f}s) in {time.time() - t0:.0f}s; why it is cut this way: {out.with_suffix('.why.md')}")


def cmd_brief(a: argparse.Namespace) -> None:
    from . import brief

    p = Path(a.file)
    if a.idea is None:  # check a filled brief
        b = brief.read(p)
        probs = brief.problems(b)
        if probs:
            raise SystemExit("the brief still needs:\n  " + "\n  ".join(probs))
        print(f"brief ready: a {b['seconds']} s {brief.NAMES[b['kind']]} for {b['audience']}; the point: {b['point']}\n"
              f"next: alvenus storyboard {p} sb.json")
        return
    if p.exists() and not a.force:
        raise SystemExit(f"{p} already exists; give a new file name (or --force to start it again)")
    p.write_text(json.dumps(brief.new(a.idea), indent=2), encoding="utf-8")
    print(f"wrote a brief to {p}. Fill in every field (ask the creator what you can't tell from the idea), "
          f"then: alvenus brief {p}")


def cmd_storyboard(a: argparse.Namespace) -> None:
    from . import brief

    b = brief.read(Path(a.brief))
    probs = brief.problems(b)
    if probs:
        raise SystemExit("finish the brief first:\n  " + "\n  ".join(probs))
    out = Path(a.out)
    if out.exists() and not a.force:
        raise SystemExit(f"{out} already exists; give a new file name (or --force to lay it out again)")
    sb = brief.skeleton(b)
    out.write_text(json.dumps(sb, indent=2), encoding="utf-8")
    r = brief.RECIPES[b["kind"]]
    print(f"laid out {'an' if b['kind'][0] in 'aeiou' else 'a'} {brief.NAMES[b['kind']]} storyboard in {out}: {len(sb['scenes'])} beats, {r['about']}")
    for i, sc in enumerate(sb["scenes"], 1):
        print(f"  {i}. {sc['beat']:9} {sc['seconds']:>4.1f} s  {sc['type']:10} {sc['_job']}")
    print(f"write each scene's words for its beat, then: alvenus check {out}")


def cmd_check(a: argparse.Namespace) -> None:
    from . import storycheck
    from .approval import content, status

    p = Path(a.storyboard)
    sb = content(p)
    findings = storycheck.check(sb)
    try:
        from . import story

        story.load(p, json.loads(json.dumps(sb)))
    except SystemExit as e:  # the storyboard can't be built as written: that is weak too
        for line in str(e).splitlines()[1:]:
            findings.insert(0, storycheck.Finding("weak", 0, "", line.strip(), "fix the storyboard file"))
    page = storycheck.board(sb, findings)
    bp = p.with_name((p.name[:-5] if p.name.endswith(".json") else p.name) + ".board.md")
    bp.write_text(page, encoding="utf-8")
    print(page)
    w = storycheck.weak(findings)
    ok, why = status(p)
    print(f"board saved as {bp}; show it to the creator.")
    if w:
        raise SystemExit(f"not ready: fix the {len(w)} weak point{'s' if len(w) > 1 else ''} above, then check again")
    print(f"story check passed ({why}). When the creator says yes: alvenus approve {p} --by NAME")


def cmd_approve(a: argparse.Namespace) -> None:
    from . import storycheck
    from .approval import approve, content

    p = Path(a.storyboard)
    w = storycheck.weak(storycheck.check(content(p)))
    if w and not a.anyway:
        raise SystemExit(f"the story check still finds {len(w)} weak point{'s' if len(w) > 1 else ''} (alvenus check {p}). "
                         "Fix them, or if the creator wants it as it is: approve --anyway \"their reason\"")
    rec = approve(p, a.by, a.anyway or "")
    print(f"approved by {rec['approved_by']} at {rec['at']}. Now: alvenus make {p} --out video.mp4 "
          "(any change to the storyboard needs a new approval)")


def cmd_suggest(a: argparse.Namespace) -> None:
    from . import community as cm

    if a.addons:
        from .brief import RECIPES
        from .presets import PRESETS

        st = [f"  style  {n:16} {p['about']}" for n, p in PRESETS.items() if p.get("addon")]
        rc = [f"  recipe {n:16} {r['about']}" for n, r in RECIPES.items() if r.get("addon")]
        print("Add-ons from the community:\n" + ("\n".join(st + rc) or "  none yet"))
        if cm.NOTES:
            print("Skipped:\n  " + "\n  ".join(cm.NOTES))
        return
    if not a.idea:
        raise SystemExit('give an idea in quotes to start one (alvenus suggest "your idea" idea.json), or a suggestion file to check it')
    p = Path(a.idea)
    if p.suffix == ".json" and p.exists() and a.file is None:
        try:
            s = json.loads(p.read_text(encoding="utf-8"))
        except ValueError as e:
            raise SystemExit(f"{p}: can't read it ({e})")
        if not isinstance(s, dict) or "venus_suggestion" not in s:
            raise SystemExit(f"{p}: not a Venus suggestion")
        probs = cm.suggestion_problems(s)
        if probs:
            raise SystemExit("before it can be sent:\n  " + "\n  ".join(probs))
        url, paste = cm.form_link(s)
        md = p.with_suffix(".md")
        md.write_text(f"# {s['title']}\n\n{paste}\n", encoding="utf-8")
        print(cm.HOW_IT_WORKS + "\n")
        print("Ready. Open this link, read it over, and press Submit yourself (Venus never sends anything for you):\n" + url)
        if len(url) > 7000:
            print(f"\nThe link is long; if the form opens empty, paste the text from {md} into it.")
        print("\nWant a thank-you by email? Send it to Anamorph Labs privately (see the form); never put it in the public form.")
        return
    out = Path(a.file or "idea.json")
    if out.exists() and not a.force:
        raise SystemExit(f"{out} already exists; give a new file name (or --force)")
    out.write_text(json.dumps(cm.new_suggestion(a.idea), indent=2), encoding="utf-8")
    print(f"wrote {out}. Fill it in with the person (what, why, one example, the name to credit), then: alvenus suggest {out}\n\n"
          + cm.HOW_IT_WORKS)


def cmd_nodes(a: argparse.Namespace) -> None:
    """Work on a node file: the video as named nodes you can show, set, lock and move."""
    from . import nodes as nd
    from . import story

    f = Path(a.file)
    if a.action == "init":
        try:
            sb = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise SystemExit(f"{f}: can't read the storyboard ({e})")
        if "venus_nodes" in sb:
            raise SystemExit(f"{f} is already a node file")
        out = Path(a.out) if a.out else f.with_name((f.name[:-5] if f.name.endswith(".json") else f.name) + ".nodes.json")
        if out.exists() and not a.force:
            raise SystemExit(f"{out} already exists; add --force to replace it")
        doc = nd.to_nodes(sb)
        if nd.to_storyboard(doc) != sb:  # never lose anything on the way
            raise SystemExit("this storyboard didn't survive the round trip into nodes; please report it")
        nd.write(out, doc)
        print(f"wrote {out}: {len(nd.scenes_of(doc))} scenes as {len(doc['nodes'])} nodes\n")
        print(nd.show(doc))
        return
    if a.action == "guide":
        print(nd.guide())
        return
    doc = nd.read(f)
    if a.action == "show":
        print(nd.show(doc, nd.read_last(f), a.ids or None))
        problems = nd.check(doc)
        if problems:
            print("\nproblems:\n  " + "\n  ".join(problems))
        return
    if a.action in ("asks", "listen"):
        import time as _time

        end = _time.time() + (a.timeout or 0)
        while a.action == "listen" and not nd.asks(doc) and _time.time() < end:
            _time.sleep(1.0)  # wait for the person to describe something in Studio
            doc = nd.read(f)
        print(nd.asks_text(doc, str(f)))
        return
    if a.action == "check":
        problems = nd.check(doc)
        if not problems:
            try:
                story.load(f, nd.to_storyboard(doc))
            except SystemExit as e:
                problems = str(e).splitlines()[1:] or [str(e)]
        print("\n".join(["problems:"] + ["  " + x.strip() for x in problems]) if problems else "all good")
        return
    if a.action == "export":
        if not a.out:
            raise SystemExit("export needs --out FILE for the storyboard")
        Path(a.out).write_text(json.dumps(nd.to_storyboard(doc), indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"wrote the storyboard to {a.out}")
        return
    if a.action == "view":
        from .nodeview import write_view

        out = Path(a.out) if a.out else f.with_name((f.name[:-5] if f.name.endswith(".json") else f.name) + ".html")
        write_view(f, doc, out)
        print(f"wrote {out}: open it in a browser to see the node map")
        return
    ids = a.ids or []
    if a.action == "set":
        if not ids:
            raise SystemExit("set needs NODE.PARAM=VALUE, like scene3.words.size=1.3 (null removes a setting)")
        done = []
        for item in ids:
            target, eq, raw = item.partition("=")
            if not eq:
                raise SystemExit(f"{item}: write it as NODE.PARAM=VALUE")
            nd.set_param(doc, target.strip(), nd.parse_value(raw), a.force)
            done.append(f"{target.strip()} = {raw}")
    elif a.action in ("lock", "unlock"):
        done = nd.lock(doc, ids, a.action == "lock")
        done = [f"{a.action}ed {x}" for x in done]
    elif a.action == "move":
        if len(ids) != 1:
            raise SystemExit("move one scene: alvenus nodes move FILE scene4 --after scene1")
        nd.move(doc, ids[0], a.after, a.before, a.first)
        done = [f"moved {ids[0]}"]
    elif a.action == "copy":
        if len(ids) != 1:
            raise SystemExit("copy one scene: alvenus nodes copy FILE scene2 [--as scene2b]")
        new = nd.copy_scene(doc, ids[0], a.as_id)
        if a.after or a.before or a.first:
            nd.move(doc, new, a.after, a.before, a.first)
        done = [f"copied {ids[0]} as {new}"]
    elif a.action == "remove":
        done = [f"removed {x}" for nid in ids for x in nd.remove(doc, nid, a.force)]
    elif a.action == "describe":
        if len(ids) < 2:
            raise SystemExit('describe a node in plain words: alvenus nodes describe FILE scene3.words "bigger and slower"')
        got = nd.describe(doc, ids[0], " ".join(ids[1:]))
        ask = (nd.find(doc, ids[0]) or {}).get("ask") or {}
        done = [f"did: {'; '.join(got)}" if got else "nothing Venus could do on its own"]
        if ask.get("left"):
            done.append(f"left for your AI: {'; '.join(ask['left'])}")
    elif a.action == "answer":
        if len(ids) < 2:
            raise SystemExit('answer a description: alvenus nodes answer FILE scene3.words "made the words bigger and slower"')
        nd.answer(doc, ids[0], " ".join(ids[1:]))
        done = [f"answered {ids[0]}"]
    elif a.action in ("off", "on") and len(ids) == 1 and (nd.find(doc, ids[0]) or {}).get("kind") == "tool":
        nd.toggle_tool(doc, ids[0], a.action == "on", a.force)
        done = [f"{ids[0]} {a.action}"]
    elif a.action == "add":
        if len(ids) < 2 or not a.on:
            raise SystemExit("add a tool: alvenus nodes add FILE scene3 blur amount=0.4 --on background  (see: alvenus nodes guide)")
        params = {}
        for item in ids[2:]:
            k, eq, raw = item.partition("=")
            if not eq:
                raise SystemExit(f"{item}: write tool settings as NAME=VALUE")
            params[k.strip()] = nd.parse_value(raw)
        new = nd.add_tool(doc, ids[0], ids[1], a.on, a.force, **params)
        if a.before:
            nd.move_tool(doc, new, before=a.before, force=a.force)
        done = [f"added {new} on the {a.on}"]
    elif a.action == "layers":
        if len(ids) < 2:
            raise SystemExit("say the layers bottom to top: alvenus nodes layers FILE scene3 shape words picture marks")
        done = ["layers, bottom to top: " + ", ".join(nd.set_layers(doc, ids[0], ids[1:], a.force))]
    elif a.action in ("off", "on"):
        if len(ids) != 2:
            raise SystemExit(f"switch a stage of a scene {a.action}: alvenus nodes {a.action} FILE scene3 shape (look, shape, words, marks)")
        done = [nd.switch(doc, ids[0], ids[1], a.action == "on", a.force)]
    elif a.action in ("use", "unuse"):
        if len(ids) < 2:
            raise SystemExit(f"{a.action} a style on scenes: alvenus nodes {a.action} FILE STYLE scene2 scene4")
        got = nd.use(doc, ids[0], ids[1:], a.action == "use", a.force)
        done = [f"{', '.join(got)} {'now use' if a.action == 'use' else 'no longer use'} {ids[0]}"
                + (f"; give it settings with: alvenus nodes set {f} {ids[0]}.words.size=1.2" if a.action == "use"
                   and not (nd.find(doc, ids[0]).get("params")) else "")]
    else:
        raise SystemExit(f"unknown action {a.action}")
    problems = nd.check(doc)
    if not problems:
        try:
            story.load(f, nd.to_storyboard(doc))
        except SystemExit as e:
            problems = [x.strip() for x in str(e).splitlines()[1:]] or [str(e)]
    if problems:
        raise SystemExit("not saved, because:\n  " + "\n  ".join(problems))
    nd.write(f, doc)
    print("; ".join(done))
    touched = {x.split(" = ")[0].rsplit(".", 1)[0] for x in done if " = " in x}
    if touched:
        print(nd.show(doc, nd.read_last(f), sorted({t.split(".")[0] for t in touched} | touched)))


ENERGETIC = {"reels-punchy", "hype"}


def make_versions(sb: dict, style: str | None, aspect: str, out: Path, t0: float) -> None:
    """Three takes on the same storyboard, side by side, each with the reason it
    exists, so choosing is a glance instead of a guess. Quick drafts: pick one,
    then build it in full from its saved storyboard."""
    from PIL import Image, ImageDraw

    from . import story
    from .draft import enable
    from .selfcheck import review

    vertical = aspect in ("9:16", "4:5")
    own = style or ("reels-punchy" if vertical else "explainer")
    other = ("editorial" if not vertical else "calm-story") if own in ENERGETIC else ("hype" if vertical else "reels-punchy")
    plans = [
        ("A", own, 1.0, "as you wrote it" + (f", in the {own} style" if style else f", in the {own} style (a fit for {aspect})")),
        ("B", other, 1.0, ("calmer: slower scene changes, softer titles, a warmer look" if own in ENERGETIC
                           else "punchier: quicker, bolder scene changes and titles that land hard")
                          + f" ({other} style), to see if the idea plays better that way"),
        ("C", own, 0.85, "the same style, every scene 15% shorter, for feeds where attention is short "
                         "(scenes with words stay long enough to read)"),
    ]
    enable(ASPECTS)
    rows, sheets = [], []
    for tag, pk, pace, reason in plans:
        keys = ("look", "accent", "transition", "transition_seconds", "title_style", "background")
        mine = {k: v for k, v in sb.items() if k not in keys or pk == own}
        v = {**pack(pk, *keys), **mine, "style": pk, "aspect": aspect}
        v["scenes"] = [{k: x for k, x in sc.items() if not k.startswith("_")} for sc in sb["scenes"]]
        if pace != 1.0:
            for sc in v["scenes"]:
                sc["seconds"] = round(max(1.6, float(sc.get("seconds", 3.0)) * pace), 2)
        o = out.with_name(f"{out.stem}-{tag}{out.suffix}")
        print(f"version {tag}: {reason}")
        story.build(v, o, ASPECTS[aspect])
        changes = story.autofix(v, review(o))
        if changes:
            print("   self-review: " + "; ".join(changes) + ". Building again.")
            story.build(v, o, ASPECTS[aspect])
        write_sheet(o, [(a0 + (a1 - a0) * 0.6, f"{i + 1} {v['scenes'][i]['type']}") for i, (a0, a1) in sorted(v["_spans"].items())])
        keep = {k: x for k, x in v.items() if not k.startswith("_")}
        keep["scenes"] = [{k: x for k, x in sc.items() if not k.startswith("_")} for sc in v["scenes"]]
        o.with_suffix(".storyboard.json").write_text(json.dumps(keep, indent=2), encoding="utf-8")
        rows.append(f"| {tag} | {o.name} | {pk} | {duration(o):.1f} s | {reason} |")
        sheets.append((tag, o.with_suffix(".sheet.jpg")))
    imgs = [(t, Image.open(p)) for t, p in sheets if p.exists()]
    if imgs:
        wmax = max(im.width for _, im in imgs)
        band = 70
        page = Image.new("RGB", (wmax, sum(im.height + band for _, im in imgs)), (18, 18, 20))
        d, y = ImageDraw.Draw(page), 0
        from .style import FONTS
        from PIL import ImageFont

        try:
            font = ImageFont.truetype(str(Path(FONTS) / "InterDisplay-Black.otf"), 44)
        except OSError:
            font = ImageFont.load_default()
        for (t, im), r in zip(imgs, rows):
            d.text((20, y + 12), f"{t}   {r.split('|')[3].strip()}   {r.split('|')[4].strip()}", fill=(255, 255, 255), font=font)
            page.paste(im, (0, y + band))
            y += im.height + band
        page.save(out.with_name(f"{out.stem}-versions.jpg"), quality=88)
    md = ["# Three versions", "", "Quick drafts of the same storyboard. Pick one, then build it in full:",
          f"`alvenus make {out.stem}-B.storyboard.json --out final.mp4` (or A, or C).", "",
          "| | file | style | length | why this version |", "|---|---|---|---|---|"] + rows
    out.with_name(f"{out.stem}-versions.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"wrote 3 versions, {out.stem}-versions.jpg to compare them and {out.stem}-versions.md with the reasons, in {time.time() - t0:.0f}s")


def cmd_scan(a: argparse.Namespace) -> None:
    from .scan import scan

    need_ffmpeg()
    r = scan(a.clips, Path(a.out_dir) if a.out_dir else None)
    for c in r["clips"]:
        sound = "has sound" if c["own_sound"] else "silent"
        print(f"{Path(c['file']).name}: {c['seconds']}s, {c['shape']} ({c['size']}), {sound}, "
              f"{len(c['cuts_inside_at'])} cut(s) inside")
    print("frames to look at: " + ", ".join(r["contact_sheets"]))


def cmd_find(a: argparse.Namespace) -> None:
    from .footage import SHEET, find, sheet

    need_ffmpeg()
    hits = find(a.query, a.clips, a.top)
    if not hits:
        print("nothing found")
        return
    print(f'moments that look like "{a.query}" (best first):')
    for i, h in enumerate(hits, 1):
        print(f"  {i}. {h['file']}  {h['from']:.1f}s to {h['to']:.1f}s  (match {h['match']})")
    out = Path(a.sheet) if a.sheet else Path(a.clips[0] if Path(a.clips[0]).is_dir() else Path(a.clips[0]).parent) / f"{SHEET}.jpg"
    try:
        sheet(hits, a.query, out)
        print(f"frames side by side: {out}")
    except Exception as e:
        print(f"   (no picture of the results: {e})")
    best = hits[0]
    print(f"use it as a cutaway: --broll LINE={best['file']}@{best['from']:g}, or in a storyboard: "
          f'{{"type": "clip", "file": "{best["file"]}", "from": {best["from"]:g}}}')


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
    for mod in ("numpy", "onnxruntime", "PIL"):
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
    from .footage import FILES, model_dir

    clip = all((model_dir() / Path(f).name).exists() for f in FILES)
    print(f"  {'OK ' if clip else '-- '} footage search model {'downloaded' if clip else 'not downloaded (optional: alvenus fetch-models --find, or it downloads the first time you use alvenus find)'}")
    print("\nAll set." if ok else "\nFix the NO lines above, then run this again.")
    raise SystemExit(0 if ok else 1)


def main(argv: list[str] | None = None) -> None:
    from .community import load_addons

    load_addons()  # community style packs and story recipes (data only, each one checked)
    p = argparse.ArgumentParser(prog="alvenus", description="Cut a video from a script and your takes.")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("cut", help="pick the best take per script line and build the cut")
    c.add_argument("--preset", help="starting style: " + ", ".join(PRESETS) + " (see: alvenus presets)")
    c.add_argument("--plan", help="edit plan JSON (each cut writes one beside its output); flags typed here win over it")
    c.add_argument("--script", help="text file, one spoken line per row")
    c.add_argument("--takes", nargs="+", help="recording(s) or folder(s) of clips, video or audio")
    c.add_argument("--draft", action="store_true", help="quick look: a third of the size, fastest settings, plus a sheet of every scene")
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
    c.add_argument("--voice", choices=["studio", "clean", "off"], default="studio", help="voice treatment: studio (cleaned, warm, even; default), clean (noise and harsh s removed only), off")
    c.add_argument("--no-beat-sync", action="store_true", help="with --music, don't move scene changes onto the music's beat")
    c.add_argument("--line-chart", action="append", metavar="LINE=LABEL N, ...|TITLE", help="turn a line into a line chart that draws itself, e.g. --line-chart \"3=2019 4, 2021 6, 2023 11|Stalls per night\" (repeatable)")
    c.add_argument("--quote", action="append", metavar="LINE[=WHO]", help="show a line as a pull-quote card, e.g. --quote \"4=Mara Ilić\" (repeatable)")
    c.add_argument("--map", action="append", metavar="LINE=IMAGE|x,y Label; ...", help="lay a map (any image) over a line; pins drop in order and a route joins them; x and y from 0 to 1, e.g. --map \"3=city.png|0.3,0.6 Old port; 0.7,0.4 Market\"")
    c.add_argument("--timeline", action="append", metavar="LINE=WHEN what, ...|TITLE", help="a timeline that draws itself, e.g. --timeline \"2=1990 First stall, 2005 Market opens, 2024 500 stalls|How it grew\"")
    c.add_argument("--kinetic", action="append", metavar="LINE[=word, word]", help="the line as big kinetic type, words slamming in as said; listed words (or long ones) big and in accent")
    c.add_argument("--letterbox", nargs="?", const="2.39", metavar="RATIO", help="cinema bars on a wide frame (2.39 by default, or e.g. 2.0)")
    c.add_argument("--place", action="append", metavar="LINE=TEXT", help="a place-and-time stamp typed out low on the left as the line starts, e.g. --place \"2=Juniper Street, 3:12 AM\"")
    c.add_argument("--datestamp", metavar="TEXT", help="a camcorder date in the corner, e.g. --datestamp \"NOV 21 2026\"")
    c.add_argument("--lower-third-style", choices=["bar", "doc"], help="name tags: bar (accent bar, bold) or doc (hairline, serif name, spaced role)")
    c.add_argument("--talk", action="store_true", help="produced-show layout: some lines open up into a designed set, the speaker in a window beside the line's words or graphic (stacked in tall frames)")
    c.add_argument("--talk-set", choices=["dark", "paper"], help="the talk layout's set: dark (ink, default) or paper (light grey editorial paper, ink type)")
    c.add_argument("--layout", action="append", metavar="LINE=full|side", help="overrule the talk layout of one line, e.g. --layout 3=side (turns --talk on)")
    c.add_argument("--chapter", action="append", metavar="LINE=TITLE", help="a chapter starts at this line: its name and number sit on the talk set's header, e.g. --chapter \"3=How it works\"")
    c.add_argument("--progress", action="store_true", help="a thin bar along the bottom that fills as the video plays, notched at each new scene")
    c.add_argument("--push-in", action="append", metavar="LINE", help="a slow camera push-in across this line (repeatable); highlighted lines get one automatically")
    c.add_argument("--no-push-in", action="store_true", help="no slow push-ins at all")
    c.add_argument("--formats", metavar="A,B,...", help="make several shapes in one go, e.g. --formats 9:16,16:9,1:1 (files are named out-9x16.mp4 and so on)")
    c.add_argument("--no-sfx", action="store_true", help="no sound effects (by default soft whooshes and pops sit under transitions and graphics)")
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
    c.add_argument("--title-style", default="track", choices=list(TITLE_STYLES), help="how the opening title and end card animate in")
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

    mo = sub.add_parser("montage", help="cut a folder of clips to a song: on the beat, calm or punchy with the music")
    mo.add_argument("--clips", nargs="+", help="clip files or folders")
    mo.add_argument("--music", help="the song")
    mo.add_argument("--draft", action="store_true", help="quick look: a third of the size, fastest settings, plus a sheet of every scene")
    mo.add_argument("--out", help="output MP4")
    mo.add_argument("--plan", help="a .montage.json from an earlier run, edited or not")
    mo.add_argument("--aspect", choices=sorted(ASPECTS), help="default 9:16")
    mo.add_argument("--length", type=float, help="seconds (default: the whole song)")
    mo.add_argument("--look", choices=sorted(LOOKS), help="default punchy")
    mo.add_argument("--title", help="opening title")
    mo.add_argument("--place", action="append", metavar="CLIP=PLACE|COUNTRY|COORDS", help="an arrival title when this clip first comes on, e.g. --place \"lisbon.mp4=Lisbon|Portugal|38.72 N, 9.14 W\" (repeatable)")
    mo.add_argument("--datestamp", metavar="TEXT", help="a camcorder date in the corner, e.g. --datestamp \"NOV 21 2026\"")
    mo.add_argument("--letterbox", nargs="?", const="2.39", metavar="RATIO", help="cinema bars on a wide frame")
    mo.add_argument("--accent", help="#RRGGBB for the title bar")
    mo.add_argument("--title-style", choices=list(TITLE_STYLES), help="how the title animates in (default stamp)")
    mo.add_argument("--style", choices=list(PRESETS), help="a style pack: sets aspect, look, title animation and colour (flags still win)")
    mo.add_argument("--match-cut", action="store_true", help="put shots with the same framing (an eye, a figure on the horizon, "
                    "one object) one after another and line them up, so the cut matches")
    mo.add_argument("--seed", type=int, default=0, help="a different number gives a different edit of the same material")
    mo.set_defaults(func=cmd_montage)

    mk = sub.add_parser("make", help="build a video from a storyboard (scenes of clips, images, titles, numbers, charts, maps...)")
    mk.add_argument("storyboard", nargs="?", help="storyboard JSON or node file (see: alvenus make --example sb.json; alvenus nodes init)")
    mk.add_argument("--draft", action="store_true", help="quick look: a third of the size, fastest settings, plus a sheet of every scene")
    mk.add_argument("--out", help="output MP4")
    mk.add_argument("--aspect", choices=sorted(ASPECTS), help="overrides the storyboard's aspect")
    mk.add_argument("--style", choices=list(PRESETS), help="a style pack: look, colour, transitions and titles (the storyboard's own settings still win)")
    mk.add_argument("--scene", metavar="N", help="build only scene N (or a node file's scene id, like scene3), in seconds, "
                    "to check a change before building it all")
    mk.add_argument("--versions", action="store_true", help="three quick versions side by side (your style, the opposite energy, "
                    "tighter pace), each with the reason it exists")
    mk.add_argument("--no-fix", action="store_true", help="only report what the self-review finds; don't change and rebuild")
    mk.add_argument("--example", metavar="FILE", help="write an example storyboard with every scene type, then stop")
    from .templates import TEMPLATES

    mk.add_argument("--template", choices=list(TEMPLATES), help="start from a proven shape with a hook in the first 2 seconds: "
                    "explainer, story, list (top-5) or ad; writes it to the storyboard file to fill in, check and approve")
    mk.set_defaults(func=cmd_make)

    sg = sub.add_parser("suggest", help="suggest an idea or an add-on for Venus: written up by you or your AI, checked for "
                        "anything private, sent by you through a GitHub form. Anamorph Labs reviews it and builds the good ones")
    sg.add_argument("idea", nargs="?", help="the idea in quotes (starts a suggestion file), or a suggestion file to check")
    sg.add_argument("file", nargs="?", help="where to write the suggestion (default idea.json)")
    sg.add_argument("--force", action="store_true")
    sg.add_argument("--addons", action="store_true", help="list the community add-ons this Venus has, and any it skipped")
    sg.set_defaults(func=cmd_suggest)

    br = sub.add_parser("brief", help="start a video from an idea: write the brief (who, the one point, length, kind, mood...), "
                        "or check a filled one")
    br.add_argument("idea", nargs="?", help="the idea in the creator's words (leave out to check FILE)")
    br.add_argument("file", nargs="?", default="brief.json", help="the brief file (default brief.json)")
    br.add_argument("--force", action="store_true", help="start the brief again over an existing file")

    def brief_args(a):
        if a.idea and not a.idea.strip().startswith("{") and a.file == "brief.json" and Path(a.idea).suffix == ".json" and Path(a.idea).exists():
            a.idea, a.file = None, a.idea  # "alvenus brief my.json": check it
        cmd_brief(a)

    br.set_defaults(func=brief_args)
    sk = sub.add_parser("storyboard", help="lay out a storyboard from a filled brief, by the story recipe for its kind")
    sk.add_argument("brief")
    sk.add_argument("out", nargs="?", default="sb.json")
    sk.add_argument("--force", action="store_true")
    sk.set_defaults(func=cmd_storyboard)
    ck = sub.add_parser("check", help="the story check: hook, one idea per scene, turn, payoff, facts, pace; writes a board to show the creator")
    ck.add_argument("storyboard")
    ck.set_defaults(func=cmd_check)
    ap = sub.add_parser("approve", help="record the creator's yes to a storyboard; videos are made only from approved storyboards")
    ap.add_argument("storyboard")
    ap.add_argument("--by", required=True, help="who said yes (the creator's name)")
    ap.add_argument("--anyway", metavar="REASON", help="approve although the story check finds weak points, with the creator's reason")
    ap.set_defaults(func=cmd_approve)

    nd = sub.add_parser("nodes", help="the video as named nodes your AI can point at: show, set, lock, move, and a map to look at",
                        description="Actions: init (storyboard -> node file), show, guide, set NODE.PARAM=VALUE..., lock ID..., "
                                    "unlock ID..., move SCENE, copy SCENE, remove ID..., use STYLE SCENE... (wire scenes to a shared style), "
                                    "unuse STYLE SCENE..., check, view (an HTML map), export --out sb.json, describe NODE TEXT, "
                                    "asks (descriptions waiting for your AI), listen (wait for the next one), answer NODE NOTE, "
                                    "off/on SCENE STAGE (switch look, shape, words or marks off to compare) or off/on TOOL, "
                                    "add SCENE TOOL [p=v...] --on BRANCH (blur, glow, grade, vignette), layers SCENE LAYER... (bottom to top)")
    nd.add_argument("action", choices=["init", "show", "guide", "set", "lock", "unlock", "move", "copy", "remove", "use", "unuse", "check", "view",
                                       "export", "describe", "asks", "listen", "answer", "off", "on", "add", "layers"])
    nd.add_argument("file", nargs="?", default="", help="the node file (for init: the storyboard)")
    nd.add_argument("ids", nargs="*", help="node ids, or NODE.PARAM=VALUE for set")
    nd.add_argument("--out", "-o", help="where to write (init, view, export)")
    nd.add_argument("--force", action="store_true", help="change a locked node anyway (it stays locked), or replace a file")
    nd.add_argument("--after", metavar="SCENE")
    nd.add_argument("--before", metavar="ID", help="move: the scene to go before; add: the tool to go before")
    nd.add_argument("--on", metavar="BRANCH", help="add: background, picture, words, marks or output")
    nd.add_argument("--first", action="store_true")
    nd.add_argument("--as", dest="as_id", metavar="ID", help="copy: the new scene's id")
    nd.add_argument("--timeout", type=float, default=600, help="listen: seconds to wait for a description (default 600)")

    def run_nodes(a: argparse.Namespace) -> None:
        if a.action != "guide" and not a.file:
            raise SystemExit(f"nodes {a.action} needs a file")
        cmd_nodes(a)

    nd.set_defaults(func=run_nodes)

    so = sub.add_parser("studio", help="open Venus in your browser: a node editor for a node file, in your browser, on this computer")
    so.add_argument("file", help="a node file (make one with: alvenus nodes init storyboard.json)")
    so.add_argument("--port", type=int, default=8765)
    so.add_argument("--no-open", action="store_true", help="don't open the browser")

    def run_studio(a: argparse.Namespace) -> None:
        from .studio import serve

        need_ffmpeg()
        serve(Path(a.file), a.port, not a.no_open)

    so.set_defaults(func=run_studio)

    rv = sub.add_parser("review", help="check a finished video: reading time, contrast, black frames, flashing, sound and picture")
    rv.add_argument("video")
    rv.set_defaults(func=cmd_review)

    ps = sub.add_parser("presets", help="list the style packs")
    ps.set_defaults(func=lambda a: print("Style packs (use with: alvenus cut --preset NAME, montage --style NAME, make --style NAME):\n" + describe_presets()))

    f = sub.add_parser("fetch-models", help="download the free models once (Whisper to hear; with --find, CLIP to search footage)")
    f.add_argument("--model", default=asr.DEFAULT_MODEL, choices=sorted(asr.MODELS))
    f.add_argument("--models")
    f.add_argument("--find", action="store_true", help="also the footage-search model (about 150 MB)")

    def fetch_all(a: argparse.Namespace) -> None:
        print(asr.fetch_models(a.models, a.model))
        if a.find:
            from .footage import fetch

            print(fetch())

    f.set_defaults(func=fetch_all)

    r = sub.add_parser("study", help="measure the style of a reference video (shape, cut rhythm, pace, pauses)")
    r.add_argument("reference", nargs="+", help="reference video file(s) on this computer")
    r.add_argument("--out-dir", help="where to write .style.json and .sheet.png (default: beside the reference)")
    r.add_argument("--no-listen", action="store_true", help="skip transcribing (faster; no words-per-minute)")
    r.add_argument("--as", dest="as_pack", metavar="NAME", help="learn a style pack from these references (a folder of about 5 "
                   "videos of one kind) and save it as NAME, to use like any pack: cut --preset NAME, make --style NAME")
    r.set_defaults(func=cmd_study)

    fd = sub.add_parser("find", help='ask your footage: find the moment you describe ("someone laughing") in a folder of clips')
    fd.add_argument("query", help="what you are looking for, in plain words")
    fd.add_argument("clips", nargs="+", help="clip folders or files")
    fd.add_argument("--top", type=int, default=5, help="how many moments to show (default 5)")
    fd.add_argument("--sheet", help="where to save the picture of the results (default venus-found.jpg in the folder)")
    fd.set_defaults(func=cmd_find)

    b = sub.add_parser("scan", help="look through cutaway clips (B-roll): length, shape, and a contact sheet of frames with times")
    b.add_argument("clips", nargs="+", help="B-roll folder(s) or file(s)")
    b.add_argument("--out-dir", help="where to write broll.json and the sheets (default: the folder scanned)")
    b.set_defaults(func=cmd_scan)

    d = sub.add_parser("doctor", help="check that FFmpeg, Python packages and models are ready")
    d.set_defaults(func=cmd_doctor)

    a = p.parse_args(args)
    if a.cmd == "cut" and getattr(a, "formats", None):
        # One cut in several shapes. What was heard is remembered, so each
        # extra shape costs only the trimming and rendering.
        shapes = [x.strip() for x in a.formats.split(",") if x.strip()]
        bad = [x for x in shapes if x not in ASPECTS]
        if bad or not a.out:
            raise SystemExit(f"--formats: choose from {', '.join(sorted(ASPECTS))}" if bad else "--formats needs --out")
        base_out = Path(a.out)
        for shape in shapes:
            one = argparse.Namespace(**vars(a))
            one.aspect, one.formats = shape, None
            one.out = str(base_out.with_name(f"{base_out.stem}-{shape.replace(':', 'x')}{base_out.suffix}"))
            print(f"=== {shape} ===")
            cmd_cut(one)
        return
    a.func(a)
