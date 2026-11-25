"""Captions that follow the voice.

When a video has a voiceover, each caption word should appear when it is
said, not spread evenly across its scene. Two ways to know when:

- word times given with the storyboard (`"voice_words"`: a list of
  [start, end, word], seconds into the voiceover, or a JSON file of them;
  `"voice_words_at"` says where on the video the voiceover's 0 sits). Any
  transcriber's word times work. The caption words are matched to the
  spoken words in order, so a caption may leave words out or add some;
- otherwise, listened for: the voice under each scene is read for its
  syllables and the caption's words are laid onto them (wordtime.py), good
  to about a tenth of a second on a clean voice. A voice mixed with loud
  music is read less well, so give word times when you have them.

A scene may also set its own `"caption_times"`: one start per word, seconds
from the scene's start. Those always win."""

from __future__ import annotations

import json
from difflib import SequenceMatcher
from pathlib import Path

from .match import words as norm
from .wordtime import Word, analyse, place, syllables

SR = 16000


def given_words(sb: dict) -> list[tuple[float, float, str]] | None:
    """The storyboard's word times, moved onto the video's timeline."""
    vw = sb.get("voice_words")
    if not vw:
        return None
    if isinstance(vw, str):
        vw = json.loads(Path(vw).read_text(encoding="utf-8"))
    if isinstance(vw, dict):
        vw = vw.get("words") or []
    at = float(sb.get("voice_words_at", 0.0) or 0.0)
    out = []
    for x in vw:
        if isinstance(x, dict):
            a, b, t = x.get("start"), x.get("end"), x.get("word") or x.get("text")
        else:
            a, b, t = x[0], x[1], x[2]
        out.append((float(a) + at, float(b) + at, str(t)))
    return out


def _key(token: str) -> str:
    return " ".join(norm(token))


def from_given(caps: list[tuple[int, str, float, float]], spoken: list[tuple[float, float, str]]) -> dict[int, list[Word]]:
    """Match every caption word to a spoken word, in order across the whole video."""
    toks = [(i, k, w) for i, text, _, _ in caps for k, w in enumerate(text.split())]
    a = [_key(w) for _, _, w in toks]
    b = [_key(w) for _, _, w in spoken]
    when: dict[int, tuple[float, float]] = {}
    for blk in SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
        for d in range(blk.size):
            if a[blk.a + d]:
                s = spoken[blk.b + d]
                when[blk.a + d] = (s[0], s[1])
    out: dict[int, list[Word]] = {}
    n = 0
    for i, text, t0, t1 in caps:
        ws = text.split()
        idx = list(range(n, n + len(ws)))
        n += len(ws)
        known = [j for j in idx if j in when and t0 - 1.0 <= when[j][0] <= t1 + 0.5]
        if not known:
            continue  # nothing of this caption is heard during its scene: leave it to the even spread
        starts = []
        for j in idx:
            if j in when and j in known:
                starts.append(when[j][0])
                continue
            # a word the voice doesn't say (or said elsewhere): between its neighbours
            before = [x for x in known if x < j]
            after = [x for x in known if x > j]
            lo = when[before[-1]][1] if before else t0 + 0.05
            hi = when[after[0]][0] if after else min(t1 - 0.05, lo + 0.3)
            starts.append(lo + (hi - lo) * 0.5)
        out[i] = _words(ws, starts, i, t0, t1, ends=[when[j][1] if j in known else None for j in idx])
    return out


def _words(ws: list[str], starts: list[float], line: int, t0: float, t1: float, ends=None) -> list[Word]:
    out: list[Word] = []
    for k, w in enumerate(ws):
        s = min(max(starts[k], t0 + 0.02), t1 - 0.1)
        if out:
            s = max(s, out[-1].start + 0.06)
        out.append(Word(w, round(s, 3), 0.0, line))
    for k, x in enumerate(out):  # a word lasts until the next one starts; the last holds the card to the cut
        x.end = round(out[k + 1].start if k + 1 < len(out) else max(x.start + 0.06, t1 - 0.02), 3)
    return out


def from_voice(caps: list[tuple[int, str, float, float]], voiceover: str) -> dict[int, list[Word]]:
    """Listen to the voice under each captioned scene and lay its words on the syllables."""
    from .media import load_audio

    audio = load_audio(voiceover, SR)
    out: dict[int, list[Word]] = {}
    for i, text, t0, t1 in caps:
        ws = text.split()
        clip = audio[int(max(0.0, t0) * SR) : int(t1 * SR)]
        peaks, on, off, dips = analyse(clip, SR)
        if not ws or len(peaks) < 2 or off - on < 0.25:
            continue  # no voice heard in this scene: keep the even spread
        need = sum(syllables(w) for w in ws)
        if len(peaks) > need * 1.3:  # more beats than the words have syllables: music or a pause after the line
            keep = [p for p in peaks if p <= on + need * 0.32] or peaks[: need + 1]
            peaks = keep[: need + 2]
            dips = [d for d in dips if d[0] <= peaks[-1]]
            off = min(off, peaks[-1] + 0.3)
        placed = place(ws, [t0 + p for p in peaks], t0 + on, t0 + off, [(t0 + t, d) for t, d in dips])
        out[i] = _words(ws, [x.start for x in placed], i, t0, t1)
    return out


def timed(caps: list[tuple[int, str, float, float]], sb: dict, scenes: list[dict]) -> tuple[dict[int, list[Word]], str]:
    """Caption words timed to the voice, by scene index, and how they were timed
    ("given", "heard" or "" when the voice wasn't used). Scenes not in the
    answer keep the even spread."""
    out: dict[int, list[Word]] = {}
    how = ""
    rest = []
    for c in caps:
        own = scenes[c[0]].get("caption_times")
        ws = c[1].split()
        if isinstance(own, list) and len(own) == len(ws):
            out[c[0]] = _words(ws, [c[2] + float(x) for x in own], c[0], c[2], c[3])
        else:
            rest.append(c)
    if not rest or sb.get("caption_sync") is False:
        return out, how
    try:
        spoken = given_words(sb)
    except (OSError, ValueError, TypeError, IndexError, KeyError) as e:
        raise SystemExit(f"voice_words: can't read the word times ({e})")
    if spoken:
        out.update(from_given(rest, spoken))
        how = "given"
    elif sb.get("voiceover"):
        out.update(from_voice(rest, sb["voiceover"]))
        how = "heard"
    return out, how
