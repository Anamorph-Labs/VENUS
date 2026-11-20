"""Match recorded takes to script lines and choose the best take for each line.

Every decision is written down with a reason, so a person (or their AI agent)
can see why a take was picked and overrule it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

CONTRACTIONS = {
    "you're": "you are", "we're": "we are", "they're": "they are", "i'm": "i am",
    "it's": "it is", "that's": "that is", "there's": "there is", "he's": "he is",
    "she's": "she is", "don't": "do not", "doesn't": "does not", "didn't": "did not",
    "can't": "cannot", "won't": "will not", "isn't": "is not", "aren't": "are not",
    "wasn't": "was not", "i've": "i have", "we've": "we have", "you've": "you have",
    "i'll": "i will", "you'll": "you will", "we'll": "we will", "let's": "let us",
}
# Whisper writes American spelling; scripts may not. Fold common pairs together.
SPELLING = {
    "colour": "color", "colours": "colors", "favourite": "favorite", "favourites": "favorites",
    "centre": "center", "theatre": "theater", "metre": "meter", "litre": "liter", "grey": "gray",
    "neighbour": "neighbor", "neighbours": "neighbors", "honour": "honor", "humour": "humor",
    "flavour": "flavor", "labour": "labor", "behaviour": "behavior", "realise": "realize",
    "realised": "realized", "organise": "organize", "travelled": "traveled", "travelling": "traveling",
    "mum": "mom", "okay": "ok",
}
FILLERS = {"um", "uh", "erm", "er", "hm", "m", "ah", "uhm"}


def is_filler(w: str) -> bool:
    """"umm", "uhhh" and "hmm" are the same sounds drawn out."""
    return re.sub(r"(.)\1+", r"\1", w) in FILLERS
_ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def _number(n: int) -> list[str]:
    if n < 20:
        return [_ONES[n]]
    if n < 100:
        return [_TENS[n // 10]] + ([_ONES[n % 10]] if n % 10 else [])
    if n < 1000:
        return [_ONES[n // 100], "hundred"] + (_number(n % 100) if n % 100 else [])
    return [str(n)]


def words(text: str) -> list[str]:
    text = text.lower().replace("’", "'")
    out: list[str] = []
    for w in re.findall(r"[a-z0-9']+", text):
        w = w.strip("'")
        if not w:
            continue
        if w.isdigit():
            out.extend(_number(int(w)))
        else:
            out.extend(CONTRACTIONS.get(w, w).split())
    out = [SPELLING.get(w, w) for w in out]
    # "can not" and "cannot" are the same words
    i, merged = 0, []
    while i < len(out):
        if out[i] == "can" and i + 1 < len(out) and out[i + 1] == "not":
            merged.append("cannot")
            i += 2
        else:
            merged.append(out[i])
            i += 1
    return merged


def _snap(line_words: list[str], said: list[str], cutoff: float = 0.75) -> list[str]:
    """Treat a heard word as the script word it nearly spells (speech-to-text
    slips like "ever"/"every"). Real word swaps such as "Jupiter" for
    "Juniper" stay below the cutoff and still count as wrong."""
    vocab = set(line_words)
    out = []
    for w in said:
        if w in vocab or len(w) < 3:
            out.append(w)
            continue
        best, ratio = w, cutoff
        for v in vocab:
            r = SequenceMatcher(a=w, b=v).ratio()
            if r > ratio:
                best, ratio = v, r
        out.append(best)
    return out


@dataclass
class Take:
    index: int
    start: float
    end: float
    text: str
    confidence: float  # Whisper's mean token log-probability
    line: int | None = None  # 0-based script line, None if it matches nothing
    score: float = 0.0  # 0..1, how well the words match the line
    recall: float = 0.0  # share of the line's words that were said
    precision: float = 0.0  # share of said words that belong to the line
    fillers: int = 0
    filler_spans: list | None = None  # where "um"/"uh" sit inside the take, once listened for
    notes: list[str] = field(default_factory=list)
    source: int = 0  # which input file the take is in
    clipped: bool = False  # sound runs into the very start or end of its file
    delivery: object = None  # delivery.Delivery, filled in when the audio is measured

    @property
    def length(self) -> float:
        return self.end - self.start


NEAR_CREDIT = 0.6


def compare(line_words: list[str], said: list[str]) -> tuple[float, float, float]:
    if not line_words or not said:
        return 0.0, 0.0, 0.0
    heard = said
    said = _snap(line_words, said)
    sm = SequenceMatcher(a=line_words, b=said, autojunk=False)
    # A word that only nearly matches ("bride" for "bridge", "ever" for
    # "every") gets part credit: it may be a mishearing, or a real flub.
    matched = sum(
        1.0 if heard[b.b + k] == said[b.b + k] else NEAR_CREDIT
        for b in sm.get_matching_blocks()
        for k in range(b.size)
    )
    recall = matched / len(line_words)
    precision = matched / len(said)
    score = 0.0 if matched == 0 else 2 * recall * precision / (recall + precision)
    return score, recall, precision


def _best(text: str, line_words: list[list[str]]) -> float:
    said = [w for w in words(text) if not is_filler(w)]
    return max((compare(lw, said)[0] for lw in line_words), default=0.0)


def join_paused(takes: list[Take], script: list[str], max_gap: float = 2.0) -> list[Take]:
    """People pause in the middle of a line. A pause splits the recording
    into two pieces that each match the line badly; if the two together match
    clearly better, they are one take."""
    line_words = [words(s) for s in script]
    out: list[Take] = []
    for t in takes:
        prev = out[-1] if out else None
        if prev is not None and prev.source == t.source and t.start - prev.end <= max_gap:
            joined = f"{prev.text} {t.text}"
            if _best(joined, line_words) >= max(_best(prev.text, line_words), _best(t.text, line_words)) + 0.15:
                prev.end = t.end
                prev.text = joined
                prev.confidence = (prev.confidence + t.confidence) / 2
                if "joined across a pause" not in prev.notes:
                    prev.notes.append("joined across a pause")
                continue
        out.append(t)
    for i, t in enumerate(out, 1):
        t.index = i
    return out


def assign(takes: list[Take], script: list[str], min_score: float = 0.45) -> None:
    """Label each take with the script line it is an attempt at (or none)."""
    line_words = [words(s) for s in script]
    for t in takes:
        said_all = words(t.text)
        t.fillers = sum(1 for w in said_all if is_filler(w))
        said = [w for w in said_all if not is_filler(w)]
        best = (0.0, 0.0, 0.0, None)
        for i, lw in enumerate(line_words):
            s, r, p = compare(lw, said)
            if s > best[0]:
                best = (s, r, p, i)
        t.score, t.recall, t.precision, line = best
        # A false start says a few of the line's words and stops: high
        # precision, low recall. Keep it attached to its line so it is
        # reported, but it can never be chosen.
        opener = next(
            (i for i, lw in enumerate(line_words) if len(said) >= 2 and len(said) < len(lw) and said[:2] == lw[:2]),
            None,
        )
        if line is not None and (t.score >= min_score or (t.precision >= 0.8 and len(said) >= 2)):
            t.line = line
        elif opener is not None:
            # Starts like a line, then stops or goes wrong: a false start.
            t.line = opener
            t.score, t.recall, t.precision = compare(line_words[opener], said)
        else:
            t.line = None
            t.notes.append("matches no script line (chatter or slate)")


@dataclass
class Choice:
    line: int
    take: Take | None
    reason: str
    candidates: list[Take]


def choose(takes: list[Take], script: list[str]) -> list[Choice]:
    """Pick the best take per line.

    Ranking, in order: says the whole line with no wrong or extra words;
    then word match score; then fewer filler sounds; then no hidden
    hesitation; then the later take (people usually redo a line until it is
    right); then Whisper's confidence.

    "Hidden hesitation": Whisper often tidies up "um, the" out of its text,
    so two takes can read the same while one is clearly slower. A take that
    runs 12% longer than the fastest take with the same words is marked.
    """
    choices: list[Choice] = []
    for i in range(len(script)):
        cands = [t for t in takes if t.line == i]
        usable = [t for t in cands if t.recall >= 0.6]
        for t in cands:
            if t.recall < 0.6:
                t.notes.append("incomplete (false start or cut off)")
            elif t.recall < 1.0:
                t.notes.append(f"missing words ({t.recall:.0%} of the line said)")
            if t.precision < 1.0 and t.recall >= 0.6:
                t.notes.append("has wrong or extra words")
            if t.fillers:
                t.notes.append(f"{t.fillers} filler sound(s)")
            if t.clipped:
                t.notes.append("cut off at the edge of the clip (recording started late or stopped early)")
        if not usable:
            choices.append(Choice(i, None, "no usable take found", cands))
            continue

        slow: set[int] = set()
        for t in usable:
            same = [
                u for u in usable
                if round(u.score, 2) == round(t.score, 2)
                and not (u.delivery is not None and "rushed" in u.delivery.issues)  # a rushed take is no yardstick
            ] or [t]
            if t.length > 1.12 * min(u.length for u in same):
                slow.add(t.index)
                t.notes.append("slower than an equal take (possible hidden pause or filler)")

        def key(t: Take):
            perfect = t.recall >= 0.999 and t.precision >= 0.999
            issues = len(t.delivery.issues) if t.delivery is not None else 0
            return (not t.clipped, perfect, round(t.score, 2), -t.fillers, -issues, t.index not in slow, t.start, t.confidence)

        ranked = sorted(usable, key=key, reverse=True)
        best = ranked[0]
        if len(ranked) == 1:
            why = "only complete take (the others stop early)" if len(cands) > 1 else "only take of this line"
        else:
            runner = ranked[1]
            kb, kr = key(best), key(runner)
            if kb[0] != kr[0]:
                why = "the other take is cut off at the edge of its clip"
            elif kb[1] != kr[1]:
                why = "only take that says the line exactly"
            elif kb[2] != kr[2]:
                why = f"closest to the script ({best.score:.0%} vs {runner.score:.0%})"
            elif kb[3] != kr[3]:
                why = "fewer filler sounds"
            elif kb[4] != kr[4]:
                why = "same words, better delivery (the other take: " + ", ".join(runner.delivery.issues) + ")"
            elif kb[5] != kr[5]:
                why = "same words, but tighter delivery (the other take hesitates)"
            else:
                why = "equally good; picked the later take"
        choices.append(Choice(i, best, why, cands))
    return choices


def as_said(line: str, heard: str) -> str:
    """The script line as it was actually spoken in the chosen take, for the
    captions: script words the speaker left out are dropped, words they added
    are put in, and every word they did say keeps the script's spelling and
    punctuation (speech-to-text guesses at spelling; the script doesn't)."""
    tokens = line.split()
    flat: list[tuple[int, str]] = [(i, w) for i, tok in enumerate(tokens) for w in words(tok)]
    said = [w for w in words(heard) if not is_filler(w)]
    if not flat or not said:
        return line
    sm = SequenceMatcher(None, [w for _, w in flat], said, autojunk=False)
    keep: set[int] = set()
    added: dict[int, list[str]] = {}  # token index -> heard words to put before it
    for op, a0, a1, b0, b1 in sm.get_opcodes():
        if op == "equal" or op == "replace":
            keep.update(flat[k][0] for k in range(a0, a1))
            if op == "replace" and b1 - b0 > a1 - a0:
                # More was said than written here: add the extra heard words.
                extra = said[b0 + (a1 - a0):b1]
                at = flat[a1][0] if a1 < len(flat) else len(tokens)
                added.setdefault(at, []).extend(extra)
        elif op == "insert":
            at = flat[a0][0] if a0 < len(flat) else len(tokens)
            added.setdefault(at, []).extend(said[b0:b1])
    # A token with no spoken words (a dash, an emoji) stays with its neighbours.
    spoken = {i for i, _ in flat}
    keep |= {i for i in range(len(tokens)) if i not in spoken}
    if not any(i in keep for i in spoken):
        return line
    out: list[str] = []
    def numeric(i: int) -> bool:
        return 0 <= i < len(tokens) and any(ch.isdigit() or ch in "$£€₹%" for ch in tokens[i])

    for i, tok in enumerate(tokens + [""]):
        if not (numeric(i - 1) or numeric(i)):  # "$20" is read out as "twenty dollars": nothing to add
            out += added.get(i, [])
        if i < len(tokens) and i in keep:
            out.append(tok)
    text = " ".join(out)
    first = next((t for t in tokens if any(ch.isalpha() for ch in t)), "")
    if text and first[:1].isupper():
        text = text[0].upper() + text[1:]
    if tokens and tokens[-1][-1:] in ".!?" and text[-1:] not in ".!?":
        text = text.rstrip(",;:") + tokens[-1][-1]
    return text


def edge_word_heard(t: Take, script: list[str], first: bool) -> bool:
    """Whether the take's first (or last) script word was heard whole, so a
    take that runs right up to the edge of its file lost nothing there."""
    if t.line is None:
        return False
    line = [w for w in words(script[t.line]) if not is_filler(w)]
    said = [w for w in words(t.text) if not is_filler(w)]
    if not line or not said:
        return False
    a, b = (line[0], said[0]) if first else (line[-1], said[-1])
    return a == b or SequenceMatcher(None, a, b).ratio() >= 0.75
