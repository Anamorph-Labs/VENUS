"""The second reader: looks over the finished cut the way a careful editor
would, and writes plain notes for the creator. What to reshoot, which picks
were close calls worth a look, and anything that seems off.

It only reports; it never changes the cut.
"""

from __future__ import annotations

from difflib import SequenceMatcher
from pathlib import Path

from .match import FILLERS, Choice, Take, _snap, words

UNSURE = -0.6  # Whisper's mean log-probability below this: it was guessing


def _at(t: Take, sources: list[Path]) -> str:
    m, s = divmod(int(t.start), 60)
    return f"{sources[t.source].name} at {m}:{s:02d}"


def word_diff(line: str, heard: str) -> tuple[list[str], list[str]]:
    """Words of the line that were not said, and said words not in the line."""
    lw = words(line)
    said = _snap(lw, [w for w in words(heard) if w not in FILLERS])
    missing, extra = [], []
    for op, a0, a1, b0, b1 in SequenceMatcher(a=lw, b=said, autojunk=False).get_opcodes():
        if op in ("delete", "replace"):
            missing += lw[a0:a1]
        if op in ("insert", "replace"):
            extra += said[b0:b1]
    return missing, extra


def notes(script: list[str], choices: list[Choice], takes: list[Take], sources: list[Path], length: float) -> str:
    reshoot, check, fyi = [], [], []
    for c in choices:
        n = c.line + 1
        if c.take is None:
            tried = f" ({len(c.candidates)} attempt(s), none complete)" if c.candidates else " (never recorded)"
            reshoot.append(f"**Line {n}** has no usable take{tried}: \"{script[c.line]}\"")
            continue
        t = c.take
        missing, extra = word_diff(script[c.line], t.text)
        if missing or extra:
            bits = []
            if missing:
                bits.append("missing \"" + " ".join(missing) + "\"")
            if extra:
                bits.append("heard \"" + " ".join(extra) + "\" instead")
            check.append(
                f"**Line {n}**: the best take still differs from the script ({'; '.join(bits)}). "
                f"Listen at {_at(t, sources)}. If it really was said that way, reshoot the line."
            )
        if t.clipped:
            check.append(f"**Line {n}**: the only good take is cut off at the edge of its clip ({_at(t, sources)}). A reshoot would be safer.")
        if t.confidence < UNSURE:
            check.append(f"**Line {n}**: speech recognition was unsure about this take ({_at(t, sources)}). Give it a listen.")
        rivals = [
            o for o in c.candidates
            if o is not t and o.recall >= 0.6 and not o.clipped and abs(o.score - t.score) <= 0.02
        ]
        if rivals and "picked the later take" in c.reason:
            others = ", ".join(_at(o, sources) for o in rivals)
            fyi.append(f"Line {n}: a close call. Takes read the same, so I used the later one ({_at(t, sources)}). The other is at {others}, if you prefer its delivery.")
        if any("restarted inside the take" in x for x in t.notes):
            fyi.append(f"Line {n}: you restarted mid-take; I kept the last full attempt ({_at(t, sources)}).")
        if any("slower than an equal take" in x for o in c.candidates for x in o.notes):
            fyi.append(f"Line {n}: one take sounded the same but ran slower, likely a hidden pause or \"um\". I used the tighter one.")

    chatter = [t for t in takes if t.line is None]
    covered = sum(1 for c in choices if c.take)
    out = [
        "# Second reader notes",
        "",
        f"{covered} of {len(script)} lines cut, {length:.1f} seconds long, from {len(sources)} file(s). "
        f"{len(chatter)} bit(s) of chatter or slates were left out.",
        "",
    ]
    if reshoot:
        out += ["## Reshoot", ""] + [f"- {x}" for x in reshoot] + [""]
    if check:
        out += ["## Check these", ""] + [f"- {x}" for x in check] + [""]
    if fyi:
        out += ["## For your information", ""] + [f"- {x}" for x in fyi] + [""]
    if not (reshoot or check):
        out += ["Nothing needs a reshoot. Every line has a take that matches the script.", ""]
    return "\n".join(out)
