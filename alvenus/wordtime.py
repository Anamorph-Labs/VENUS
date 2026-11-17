"""When each word of the script is spoken in the cut.

Whisper (as we run it) gives text, not word times. Instead we listen for
syllables: every syllable has a burst of energy in the voice band, so the
peaks of that energy mark syllable centres. The script tells us how many
syllables each word has, so the words can be laid onto those peaks. Good to
a tenth of a second or so, which is what animated captions need."""

from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np

from .match import words as norm_words


@dataclass
class Word:
    text: str  # as written in the script, punctuation kept
    start: float  # seconds on the cut's timeline
    end: float


def syllables(word: str) -> int:
    n = 0
    for w in norm_words(word) or [word.lower()]:
        groups = re.findall(r"[aeiouy]+", w)
        k = len(groups)
        if w.endswith("e") and not w.endswith(("le", "ee")) and k > 1:
            k -= 1
        n += max(1, k)
    return n


PROMINENCE, GAP, LEAD = 1.0, 8, 0.12  # tuned on test speech with known word times


def nuclei(audio: np.ndarray, sr: int) -> tuple[list[float], float, float]:
    """Syllable centres (seconds into `audio`), plus where the voice starts and stops."""
    p, on, off, _ = analyse(audio, sr)
    return p, on, off


def analyse(audio: np.ndarray, sr: int):
    """As nuclei(), plus the dips between syllables as (time, depth in dB):
    word boundaries usually sit in the deeper dips."""
    hop, win = int(0.01 * sr), int(0.03 * sr)
    if len(audio) < win * 2:
        return [], 0.0, len(audio) / sr, []
    frames = np.lib.stride_tricks.sliding_window_view(audio, win)[::hop] * np.hanning(win)
    spec = np.abs(np.fft.rfft(frames, axis=1)) ** 2
    f = np.fft.rfftfreq(win, 1 / sr)
    band = spec[:, (f > 300) & (f < 2500)].sum(1)
    db = 10 * np.log10(band + 1e-10)
    db = np.convolve(db, np.ones(5) / 5, mode="same")  # 50 ms smoothing
    top = np.percentile(db, 95)
    voiced = db > top - 30
    if not voiced.any():
        return [], 0.0, len(audio) / sr, []
    on, off = np.argmax(voiced), len(voiced) - np.argmax(voiced[::-1])
    peaks = []
    for i in range(1, len(db) - 1):
        if db[i] < top - 22 or db[i] < db[i - 1] or db[i] < db[i + 1]:
            continue
        lo = db[max(0, i - 12) : i].min(initial=db[i])
        hi = db[i + 1 : i + 13].min(initial=db[i])
        if db[i] - max(lo, hi) < PROMINENCE:  # needs a dip on both sides to be its own syllable
            continue
        if peaks and i - peaks[-1] < GAP:  # syllables are at least ~90 ms apart
            if db[i] > db[peaks[-1]]:
                peaks[-1] = i
            continue
        peaks.append(i)
    t = lambda i: (i * hop + win / 2) / sr
    dips = []
    for a, b in zip(peaks, peaks[1:]):
        j = a + int(np.argmin(db[a : b + 1]))
        dips.append((t(j), float(min(db[a], db[b]) - db[j])))
    return [t(i) for i in peaks], t(on), t(off), dips


DIP_PULL, DIP_DEPTH = 0.3, 1.0


def snap_to_dips(starts: list[float], dips: list[tuple[float, float]]) -> list[float]:
    """Move each word start (after the first) onto a dip between syllables,
    choosing in order, near where it was expected, preferring deep dips."""
    n, m = len(starts) - 1, len(dips)
    if n <= 0 or m < n:
        return starts
    top = max(d for _, d in dips) or 1.0
    cost = lambda j, k: abs(dips[k][0] - starts[j + 1]) / DIP_PULL - DIP_DEPTH * dips[k][1] / top
    INF = float("inf")
    best = [[INF] * m for _ in range(n)]
    back = [[-1] * m for _ in range(n)]
    for k in range(m):
        best[0][k] = cost(0, k)
    for j in range(1, n):
        run_min, arg = INF, -1
        for k in range(m):
            if k >= 1 and best[j - 1][k - 1] < run_min:
                run_min, arg = best[j - 1][k - 1], k - 1
            if arg >= 0:
                best[j][k] = run_min + cost(j, k)
                back[j][k] = arg
    k = min(range(m), key=lambda k: best[n - 1][k])
    if best[n - 1][k] == INF:
        return starts
    picks = [k]
    for j in range(n - 1, 0, -1):
        k = back[j][k]
        picks.append(k)
    picks.reverse()
    return [starts[0]] + [dips[k][0] for k in picks]


def place(tokens: list[str], peaks: list[float], start: float, end: float,
          dips: list[tuple[float, float]] | None = None) -> list[Word]:
    """Lay words onto syllable peaks; fall back to an even spread by syllables."""
    counts = [syllables(w) for w in tokens]
    total = sum(counts)
    if not tokens:
        return []
    k = 0
    starts = []
    use_peaks = len(peaks) >= max(2, total // 2)
    for c in counts:
        if use_peaks:
            pos = k * len(peaks) / total  # this word's first syllable, as a fractional peak index
            i = int(pos)
            a = peaks[min(i, len(peaks) - 1)]
            b = peaks[min(i + 1, len(peaks) - 1)]
            s = a + (b - a) * (pos - i) - LEAD  # a syllable starts a little before its peak
        else:
            s = start + (end - start) * k / total
        starts.append(s)
        k += c
    starts[0] = start
    if dips:
        starts = snap_to_dips(starts, dips)
    out = []
    for i, w in enumerate(tokens):
        s = max(starts[i], out[-1].start + 0.06 if out else start)
        e = starts[i + 1] if i + 1 < len(tokens) else end
        out.append(Word(w, round(s, 3), round(max(e, s + 0.06), 3)))
    return out


def timed_words(clips, script: list[str], audio_of, sr: int) -> list[Word]:
    """Word times on the cut's timeline for every line in the cut.
    `audio_of(source)` returns that file's audio at `sr`."""
    out: list[Word] = []
    t, i = 0.0, 0
    while i < len(clips):
        line = clips[i].line
        peaks: list[float] = []
        dips: list[tuple[float, float]] = []
        on = off = None
        line_start = t
        while i < len(clips) and clips[i].line == line:
            c = clips[i]
            a = audio_of(c.source)[int(c.start * sr) : int(c.end * sr)]
            p, s, e, d = analyse(a, sr)
            peaks += [t + x for x in p]
            dips += [(t + x, depth) for x, depth in d]
            on = t + s if on is None else on
            off = t + e
            t += c.length
            i += 1
        out += place(script[line].split(), peaks, on if on is not None else line_start, off if off is not None else t, dips)
    return out
