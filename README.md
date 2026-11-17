# AL-VENUS (working name)

A free, local video agent. Phase 1: **script-to-cut**. Give it your script and
your raw footage (one long recording or a folder of clips); it finds each take, works out which
script line it is, picks the best take per line and cuts the video.

Everything runs on your own computer. No accounts, no API keys, no uploads.

## Try it

You need Python 3.10+ and [FFmpeg](https://ffmpeg.org/download.html).

```sh
pip install -r requirements.txt
python -m alvenus fetch-models          # one-time ~1 GB download of Whisper small.en
python examples/fakeshoot.py night2 examples/out   # fake test shoot: 5 clip files (needs FFmpeg with Flite)
python -m alvenus cut --script examples/night2/script.txt \
  --takes examples/out/clips --out examples/out/cut.mp4 --captions
```

Next to the MP4 you get:

- `cut.edl`: an editable timeline. Import it in DaVinci Resolve (File > Import >
  Timeline) or Premiere Pro (File > Import) and point it at your clips folder.
- `cut.srt`: captions, one per script line.
- `cut.decisions.json`: for every line, every take that was heard, what Whisper
  heard, and why one was chosen.

Use `--model base.en` for a faster but less careful listen (~290 MB, about 2.5x faster).

## How it decides

1. **Find takes**: split each file at pauses (FFmpeg `silencedetect`). Files are
   read in name order, which for phones and cameras is shooting order.
2. **Hear them**: transcribe each take with Whisper, run locally with onnxruntime.
3. **Match**: compare each take's words with every script line. Takes that match
   nothing (chatter like "sorry, again") are left out. Takes that start a line and
   stop are marked as false starts. Two pieces split by a pause mid-line are
   joined back into one take when together they match the line clearly better.
4. **Choose** per line: not cut off at the edge of its clip > says the line
   exactly > closest wording > fewer "um"s > no hidden hesitation (same words but
   noticeably slower) > the later take. Pickup shots recorded out of order are fine.
5. **Cut**: trim each chosen take with a little breathing room; pauses inside a
   take longer than 0.6 s are shortened (`--keep-pauses` turns this off); clips
   of different shapes (say a vertical phone clip) sit on a blurred copy of
   themselves in one 16:9 frame; short audio fades; loudness
   levelled to -16 LUFS; H.264/AAC MP4.

## Parts and licences

| Part | Licence | How we use it |
|---|---|---|
| Our code | MIT | this repo |
| FFmpeg | LGPL/GPL | separate program the user installs |
| Whisper small.en / base.en weights (OpenAI), ONNX export by onnx-community | MIT | downloaded by the user at first run |
| onnxruntime, numpy | MIT, BSD | pip packages |
| Flite (test voice only, inside FFmpeg) | BSD-style | only for making test takes |
