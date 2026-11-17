"""Make a fake "shoot" for testing: takes with flubs, false starts, mid-line
pauses and chatter, like a real creator's raw footage.

The voice is Flite, built into many FFmpeg builds (free, offline). The picture
is a plain background with a small slate saying which take is on screen, so
you can check by eye which take the cut used.

    python examples/fakeshoot.py night1 /tmp/night1     # one long recording
    python examples/fakeshoot.py night2 /tmp/night2     # several clip files, mixed sizes
    python examples/fakeshoot.py round3 /tmp/round3     # clipped takes, a vertical pickup shot
    python examples/fakeshoot.py round4 /tmp/round4     # instant restarts inside one take

In a take's text, " | " is a 0.9 s pause in the middle of the line and " / "
a 0.2 s breath before an instant restart.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

# Each take: (file number, script line or None for chatter, what is said, should win?)
SHOOTS = {
    "night1": {
        "script": "night1/script.txt",
        "files": {1: "1280x720"},
        "takes": [
            (1, 1, "Every night at three, Mara unlocks the bakery on Jupiter Street.", False),
            (1, None, "Sorry. Juniper. Going again.", False),
            (1, 1, "Every night at three, Mara unlocks the bakery on Juniper Street.", True),
            (1, 2, "She starts the", False),
            (1, 2, "She starts the ovens before the city wakes.", False),
            (1, 2, "She starts the ovens before the city wakes up.", True),
            (1, 3, "The first loaf is always for the bus driver on the early route.", True),
            (1, 3, "The first loaf is always for the, um, the bus driver on the early route.", False),
            (1, 4, "Nobody asked her to do it, and she never says why.", True),
            (1, 4, "Nobody told her to do it, and she never said why.", False),
            (1, 5, "But if you are up before dawn, follow the smell of bread.", True),
            (1, 5, "But if you're up before dawn, just follow the smell of fresh bread.", False),
            (1, None, "Okay, that is a wrap.", False),
        ],
    },
    "night2": {
        "script": "night2/script.txt",
        # different sizes on purpose: landscape camera clips and one vertical phone clip
        "files": {1: "1280x720", 2: "1280x720", 3: "1920x1080", 4: "720x1280", 5: "1280x720"},
        "takes": [
            (1, 1, "Lost umbrellas have a secret life.", True),
            (1, 1, "Lost umbrellas have a secret wife.", False),
            (2, 2, "Most of them end up | in a small office under the train station.", True),
            (2, None, "Hang on, my phone is buzzing.", False),
            (3, 3, "A man named Theo sorts them by colour.", False),
            (3, 3, "A man named Theo sorts them by colour, then by size.", True),
            (4, 4, "Every Friday, he opens one at random and makes a wish.", True),
            (4, 5, "He says it has worked twice.", True),
            (4, 5, "He says it, uh, it has worked twice.", False),
            (5, 6, "So if you lose yours", False),
            (5, 6, "So if you lose yours, it might be granting wishes now.", True),
            (5, None, "That's it, we're done.", False),
        ],
    },
    "round3": {
        "script": "round3/script.txt",
        "files": {1: "1280x720", 2: "1280x720", 3: "1280x720", 4: "1280x720+cutend", 5: "720x1280+cutstart"},
        "takes": [
            (1, 1, "Our building has a lift that only works on Sundays.", True),
            (1, 2, "Nobody knows who fixed it, | or why it chose that day.", True),
            (2, 3, "Mrs Okafor rides it every week with a flask of tea.", True),
            (3, 4, "She says the view from the fourth floor is worth the wait.", True),
            (3, 5, "We have never checked, because we always take the stairs.", True),
            (4, None, "Let me do the last one once more.", False),
            (4, 5, "We have never checked, because we always take the stairs.", False),  # recording stops too soon
            (5, 3, "Mrs Okafor rides it every week with a flask of tea.", False),  # pickup, recording starts late
        ],
    },
    "round4": {
        "script": "round4/script.txt",
        "files": {1: "1280x720", 2: "1280x720"},
        "takes": [
            (1, 1, "Every spring, the river / Every spring, the river behind our school floods for one week.", True),
            (1, 2, "The younger kids fold paper boats and race them to the bridge.", False),
            (1, 2, "The younger kids fold / The younger kids fold paper boats and race them to the bridge.", True),
            (2, 3, "Nobody has ever seen a boat reach the bridge.", True),
            (2, 3, "Nobody has / Nobody has ever seen a boat reach the bride.", False),
            (2, 4, "But every year, somebody folds one more.", True),
        ],
    },
}

GAP = 1.2  # seconds of room tone between takes
MID_PAUSE = 0.9
RESTART_PAUSE = 0.2
CLIP = 0.06  # how much of the first/last word a clipped recording loses
SR = 22050
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def sh(args):
    p = subprocess.run(args, capture_output=True, text=True)
    if p.returncode:
        raise SystemExit(p.stderr[-1500:])
    return p.stdout


def esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:").replace(",", "\\,")


def dur(path: Path) -> float:
    return float(sh(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)]))


def tone(path: Path, seconds: float) -> Path:
    sh(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"anoisesrc=c=pink:a=0.002:r={SR}:d={seconds}", "-ac", "1", str(path)])
    return path


def speak(text: str, path: Path, tmp: Path) -> Path:
    # " | " = a 0.9 s pause; " / " = a 0.2 s catch of breath (an instant restart)
    parts = [(p.strip(), MID_PAUSE if j else 0) for j, p in enumerate(text.split("|"))]
    parts = [(q.strip(), gap if k == 0 else RESTART_PAUSE) for p, gap in parts for k, q in enumerate(p.split("/"))]
    wavs = []
    for j, (part, gap) in enumerate(parts):
        w = tmp / f"{path.stem}_{j}.wav"
        # trim Flite's own silence at both ends so pauses are exactly as written
        trim = "silenceremove=start_periods=1:start_threshold=-50dB,areverse,silenceremove=start_periods=1:start_threshold=-50dB,areverse"
        sh(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"flite=text='{esc(part)}':voice=slt", "-af", trim,
            "-ar", str(SR), "-ac", "1", str(w)])
        if gap:
            wavs.append(tone(tmp / f"{path.stem}_p{j}.wav", gap))
        wavs.append(w)
    concat(wavs, path, tmp)
    return path


def concat(wavs: list[Path], out: Path, tmp: Path) -> None:
    lst = tmp / f"{out.stem}.txt"
    lst.write_text("".join(f"file '{w}'\n" for w in wavs))
    sh(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "pcm_s16le", str(out)])


def build(name: str, out_dir: str) -> None:
    shoot = SHOOTS[name]
    out = Path(out_dir)
    clips_dir = out / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp())
    gap = tone(tmp / "gap.wav", GAP)
    slates, expected, take_no = [], {}, {}
    files = sorted(shoot["files"])
    for fno in files:
        spec = shoot["files"][fno].split("+")
        size, cut_start, cut_end = spec[0], "cutstart" in spec, "cutend" in spec
        # "cutstart"/"cutend": the recording starts late or stops early, so the
        # first or last take is clipped at the edge of the file.
        wavs, t, file_slates = ([] if cut_start else [gap]), (-CLIP if cut_start else GAP), []
        for i, (f, line, text, good) in enumerate(shoot["takes"]):
            if f != fno:
                continue
            w = speak(text, tmp / f"t{i:02d}.wav", tmp)
            d = dur(w)
            if line is None:
                label = "chatter"
            else:
                take_no[line] = take_no.get(line, 0) + 1
                label = f"line {line} take {take_no[line]}"
                if good:
                    expected[str(line)] = label
            file_slates.append({"file": fno, "label": label, "start": round(t, 3), "end": round(t + d, 3), "said": text})
            wavs += [w, gap]
            t += d + GAP
        if cut_end:
            wavs.pop()
            t -= GAP + CLIP
        audio = tmp / f"file{fno}.wav"
        concat(wavs, audio, tmp)
        if cut_start or cut_end:
            whole = tmp / f"file{fno}_whole.wav"
            audio.rename(whole)
            sh(["ffmpeg", "-v", "error", "-y", "-i", str(whole), "-af",
                f"atrim=start={CLIP if cut_start else 0}:end={dur(whole) - (CLIP if cut_end else 0):.3f}", str(audio)])
        w_, h_ = (int(x) for x in size.split("x"))
        fs = max(24, h_ // 22)
        draws = [
            f"drawtext=fontfile={FONT}:text='{esc(s['label'].upper())}':x=40:y=40:fontsize={fs}:fontcolor=white:"
            f"box=1:boxcolor=black@0.5:boxborderw=12:enable='between(t,{s['start'] - GAP / 2:.2f},{s['end'] + GAP / 2:.2f})'"
            for s in file_slates
        ]
        draws.append(f"drawtext=fontfile={FONT}:text='CLIP {fno:02d} %{{pts\\:hms}}':x=40:y=h-th-40:fontsize={fs * 3 // 4}:fontcolor=white@0.8")
        video = clips_dir / f"clip{fno:02d}.mp4"
        sh(["ffmpeg", "-v", "error", "-y",
            "-f", "lavfi", "-i", f"gradients=s={size}:c0=0x1d3557:c1=0x6b2d5c:speed=0.02:d={t:.2f}:r=30",
            "-i", str(audio), "-vf", ",".join(draws), "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(video)])
        slates += file_slates
    (out / "shoot_log.json").write_text(json.dumps({"slates": slates, "expected_picks": expected}, indent=2))
    print(f"wrote {len(files)} clip file(s) in {clips_dir}, {len(shoot['takes'])} takes")


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else "night1", sys.argv[2] if len(sys.argv) > 2 else "examples/out")
