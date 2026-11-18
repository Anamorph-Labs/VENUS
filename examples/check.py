"""Automatic quality check of a cut made from a fake shoot.

    python examples/check.py SHOOT_DIR CUT.mp4

Checks: every line got the take the shoot says should win; picture and
sound are the same length; the sound never drops to dead silence; the
captions file has one entry per line in the cut. Exits non-zero on failure."""

import json
import subprocess
import sys
from pathlib import Path

import numpy as np


def probe(path: Path, stream: str) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", f"{stream}:0", "-show_entries", "stream=duration",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout.strip()
    return float(out or 0)


def main(shoot: Path, cut: Path) -> int:
    log = json.loads((shoot / "shoot_log.json").read_text())
    dec = json.loads(cut.with_suffix(".decisions.json").read_text())
    problems, right = [], 0
    for l in dec["lines"]:
        want = log["expected_picks"].get(str(l["line"]))
        got = None
        for c in l["candidates"]:
            if c["take"] == l["chosen_take"]:
                for s in log["slates"]:
                    if ("file" not in s or f"clip{s['file']:02d}" in c["file"]) and s["start"] - 0.6 <= c["start"] <= s["end"]:  # a restart trim starts later
                        got = s["label"]
        if got == want or (want is None and l["chosen_take"] is None):
            right += 1
        else:
            problems.append(f"line {l['line']}: expected {want}, got {got}")
    v, a = probe(cut, "v"), probe(cut, "a")
    if abs(v - a) > 0.1:
        problems.append(f"picture {v:.2f}s and sound {a:.2f}s differ")
    pcm = np.frombuffer(subprocess.run(["ffmpeg", "-v", "error", "-i", str(cut), "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
                                       capture_output=True).stdout, np.int16).astype(float)
    win = pcm[: len(pcm) // 400 * 400].reshape(-1, 400)
    floor = 20 * np.log10(np.sqrt((win ** 2).mean(1)) / 32768 + 1e-9).min()
    if floor < -85:
        problems.append(f"dead silence in the sound (floor {floor:.0f} dBFS)")
    srt = cut.with_suffix(".srt")
    in_cut = sum(1 for l in dec["lines"] if l["chosen_take"] is not None)
    if srt.exists():
        n = srt.read_text().count(" --> ")
        if n != in_cut:
            problems.append(f"captions have {n} entries for {in_cut} lines")
    print(f"picks: {right}/{len(dec['lines'])} right | picture {v:.1f}s, sound {a:.1f}s | quietest moment {floor:.0f} dBFS")
    for p in problems:
        print("  PROBLEM: " + p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]), Path(sys.argv[2])))
