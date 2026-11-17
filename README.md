# AL-VENUS (working name)

A free, local video agent. Phase 1: **script-to-cut**. Give it your script and
your raw footage (one long recording or a folder of clips); it finds each take, works out which
script line it is, picks the best take per line and cuts the video.

Everything runs on your own computer. No accounts, no API keys, no uploads.

It is meant to be driven by your own AI agent (Claude Code, Codex, ...), which
brings the understanding and the storytelling: see [AGENTS.md](AGENTS.md).

## Try it

You need Python 3.10+ and [FFmpeg](https://ffmpeg.org/download.html).

```sh
pip install .                           # gives you the `alvenus` command
alvenus doctor                          # checks FFmpeg, packages and models
alvenus fetch-models                    # one-time ~1.5 GB download of Whisper small.en
python examples/fakeshoot.py night2 examples/out   # fake test shoot: 5 clip files (needs FFmpeg with Flite)
alvenus cut --script examples/night2/script.txt \
  --takes examples/out/clips --out examples/out/cut.mp4 --captions
```

Next to the MP4 you get:

- `cut.edl`: an editable timeline. Import it in DaVinci Resolve (File > Import >
  Timeline) or Premiere Pro (File > Import) and point it at your clips folder.
- `cut.srt`: captions, one per script line.
- `cut.notes.md`: the second reader's notes: what to reshoot, what to check, close calls.
- `cut.decisions.json`: for every line, every take that was heard, what Whisper
  heard, and why one was chosen.

Study a reference video to match its style: `alvenus study reference.mp4` measures
its shape, cut rhythm, pace, pauses and loudness and suggests settings.

Steer it with `--aspect 9:16` (or 16:9, 1:1, 4:5), `--pick 2=5` (use take 5 for
line 2), `--pick 4=none` (drop line 4), `--max-pause` / `--keep-pauses`,
`--beat 0.25` (breath between lines), `--scene-beat 0.9` (longer breath where the
script has a blank line), `--no-punch-in`.
Use `--model base.en` for a faster but less careful listen (~290 MB, about 2.5x faster).

## How it decides

1. **Find takes**: split each file at pauses (FFmpeg `silencedetect`). Files are
   read in name order, which for phones and cameras is shooting order.
2. **Hear them**: transcribe each take with Whisper, run locally with onnxruntime.
3. **Match**: if a take restarts mid-line without a pause ("She starts the... She
   starts the ovens"), keep only the last full attempt. Compare each take's words with every script line. Takes that match
   nothing (chatter like "sorry, again") are left out. Takes that start a line and
   stop are marked as false starts. Two pieces split by a pause mid-line are
   joined back into one take when together they match the line clearly better.
4. **Choose** per line: not cut off at the edge of its clip > says the line
   exactly > closest wording > fewer "um"s > better delivery (not quiet, rushed,
   flat, trailing off or distorted, measured from the sound) > no hidden hesitation (same words but
   noticeably slower) > the later take. Pickup shots recorded out of order are fine.
5. **Cut**: trim each chosen take with a little breathing room; pauses inside a
   take longer than 0.6 s are shortened (`--keep-pauses` turns this off); clips
   of different shapes (say a vertical phone clip) sit on a blurred copy of
   themselves in one 16:9 frame. Editing craft: two lines in a row from the same
   shot alternate with a gentle 12% punch-in so the cut doesn't jump; breathing
   room never reaches into a neighbouring take; a blank line in the script marks
   a scene break and gets a longer breath (holding the last frame if the footage
   runs out); a quiet stretch of the room is looped under the whole cut so the
   sound never drops to dead silence; short audio fades; loudness levelled to
   -16 LUFS; H.264/AAC MP4.

## Parts and licences

| Part | Licence | How we use it |
|---|---|---|
| Our code | MIT | this repo |
| FFmpeg | LGPL/GPL | separate program the user installs |
| Whisper small.en / base.en weights (OpenAI), ONNX export by onnx-community | MIT | downloaded by the user at first run |
| onnxruntime, numpy | MIT, BSD | pip packages |
| Flite (test voice only, inside FFmpeg) | BSD-style | only for making test takes |
