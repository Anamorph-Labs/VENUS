"""Make a fake "shoot" for testing: one recording holding 2-3 takes per line,
with flubs, false starts and chatter, like a real creator's raw footage.

The voice is Flite, built into many FFmpeg builds (free, offline). The picture
is a plain background with a small slate in the corner saying which take is
on screen, so you can check by eye which take the cut used.

    python examples/night1/make_takes.py examples/night1/out
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

# (line number or None for chatter, what is said, expected to be chosen?)
SHOOT = [
    (1, "Every night at three, Mara unlocks the bakery on Jupiter Street.", False),
    (None, "Sorry. Juniper. Going again.", False),
    (1, "Every night at three, Mara unlocks the bakery on Juniper Street.", True),
    (2, "She starts the", False),
    (2, "She starts the ovens before the city wakes.", False),
    (2, "She starts the ovens before the city wakes up.", True),
    (3, "The first loaf is always for the bus driver on the early route.", True),
    (3, "The first loaf is always for the, um, the bus driver on the early route.", False),
    (4, "Nobody asked her to do it, and she never says why.", True),
    (4, "Nobody told her to do it, and she never said why.", False),
    (5, "But if you are up before dawn, follow the smell of bread.", True),
    (5, "But if you're up before dawn, just follow the smell of fresh bread.", False),
    (None, "Okay, that is a wrap.", False),
]

GAP = 1.2  # seconds of room tone between takes
SR = 22050


def sh(args):
    p = subprocess.run(args, capture_output=True, text=True)
    if p.returncode:
        raise SystemExit(p.stderr[-1500:])
    return p.stdout


def esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:").replace(",", "\\,")


def main(out_dir: str) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp())
    pieces, slates, t = [], [], 0.0
    take_no: dict[int, int] = {}
    for i, (line, text, _) in enumerate(SHOOT):
        wav = tmp / f"{i:02d}.wav"
        sh(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"flite=text='{esc(text)}':voice=slt",
            "-ar", str(SR), "-ac", "1", str(wav)])
        d = float(sh(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(wav)]))
        if line is None:
            label = "chatter"
        else:
            take_no[line] = take_no.get(line, 0) + 1
            label = f"line {line} take {take_no[line]}"
        slates.append({"label": label, "start": round(t + GAP, 3), "end": round(t + GAP + d, 3), "said": text})
        pieces += [f"gap{i}", str(wav)]
        t += GAP + d
    t += GAP

    # Stitch: room tone, take, room tone, take ...
    gap = tmp / "gap.wav"
    sh(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"anoisesrc=c=pink:a=0.002:r={SR}:d={GAP}", "-ac", "1", str(gap)])
    tail = tmp / "tail.wav"
    sh(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"anoisesrc=c=pink:a=0.002:r={SR}:d={GAP}", "-ac", "1", str(tail)])
    lst = tmp / "list.txt"
    lst.write_text("".join(f"file '{gap if p.startswith('gap') else p}'\n" for p in pieces) + f"file '{tail}'\n")
    audio = tmp / "audio.wav"
    sh(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "pcm_s16le", str(audio)])

    font = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    draws = [
        f"drawtext=fontfile={font}:text='{esc(s['label'].upper())}':x=40:y=40:fontsize=34:fontcolor=white:"
        f"box=1:boxcolor=black@0.5:boxborderw=12:enable='between(t,{s['start'] - GAP / 2:.2f},{s['end'] + GAP / 2:.2f})'"
        for s in slates
    ]
    draws.append(f"drawtext=fontfile={font}:text='SOURCE %{{pts\\:hms}}':x=w-tw-40:y=40:fontsize=26:fontcolor=white@0.8")
    video = out / "raw_takes.mp4"
    sh(["ffmpeg", "-v", "error", "-y",
        "-f", "lavfi", "-i", f"gradients=s=1280x720:c0=0x1d3557:c1=0x6b2d5c:speed=0.02:d={t:.2f}:r=30",
        "-i", str(audio), "-vf", ",".join(draws), "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(video)])

    expected = {str(l): f"line {l} take {sum(1 for x in SHOOT[: k + 1] if x[0] == l)}"
                for k, (l, _, good) in enumerate(SHOOT) if good}
    (out / "shoot_log.json").write_text(json.dumps({"slates": slates, "expected_picks": expected}, indent=2))
    print(f"wrote {video} ({t:.1f}s, {len(SHOOT)} takes)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "examples/night1/out")
