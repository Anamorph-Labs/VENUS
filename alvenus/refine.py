"""Instant restarts: "She starts the... She starts the ovens before..." said
in one breath, with no pause long enough to split it into two takes.

We spot a restart from the words (the line's opening comes round again),
then look for the small breaths inside the take, listen again from each one,
and keep the last attempt that says the line best.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .match import FILLERS, Take, _snap, compare, words
from .media import speech_regions


def _said(text: str) -> list[str]:
    return [w for w in words(text) if w not in FILLERS]


def has_restart(take: Take, line: str) -> bool:
    lw = words(line)
    if len(lw) < 3:
        return False
    said = _snap(lw, _said(take.text))
    opener = lw[:2]
    return any(said[k : k + 2] == opener for k in range(1, len(said) - 1))


def keep_last_attempt(take: Take, line: str, path: Path, audio: np.ndarray, model, sr: int, noise_db: float = -35.0) -> bool:
    """Move the take's start to its last clean restart. Returns True if moved."""
    lw = words(line)
    breaths = speech_regions(path, noise_db, min_silence=0.12, start=take.start, end=take.end)
    if len(breaths) < 2:
        take.notes.append("restarts inside the take, but there is no breath to cut at")
        return False
    best = None
    for s0, _ in breaths[1:]:
        clip = audio[int(max(0.0, s0 - 0.05) * sr) : int((take.end + 0.1) * sr)]
        tr = model.transcribe(clip)
        said = _said(tr.text)
        if _snap(lw, said)[:2] != lw[:2]:
            continue  # this breath is not where the line starts again
        score = compare(lw, said)
        if best is None or score[0] >= best[0][0]:  # ties go to the later restart
            best = (score, s0, tr)
    if best is None or best[0][0] < take.score - 0.05:
        take.notes.append("restarts inside the take; could not find a cleaner restart point")
        return False
    (take.score, take.recall, take.precision), take.start, tr = best
    take.text, take.confidence = tr.text, tr.avg_logprob
    take.fillers = sum(1 for w in words(tr.text) if w in FILLERS)
    take.notes.append("restarted inside the take; kept the last full attempt")
    return True
