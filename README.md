# AL-VENUS (working name)

A free, local video agent. Phase 1: **script-to-cut**. Give it your script and
the raw recording with all your takes; it finds each take, works out which
script line it is, picks the best take per line and cuts the video.

Everything runs on your own computer. No accounts, no API keys, no uploads.

## Try it

You need Python 3.10+ and [FFmpeg](https://ffmpeg.org/download.html).

```sh
pip install -r requirements.txt
python -m alvenus fetch-models          # one-time ~290 MB download of Whisper base.en
python examples/night1/make_takes.py examples/night1/out   # fake test shoot (needs FFmpeg with Flite)
python -m alvenus cut --script examples/night1/script.txt \
  --takes examples/night1/out/raw_takes.mp4 --out examples/night1/out/cut.mp4 --captions
```

Next to the MP4 you get `cut.srt` (captions) and `cut.decisions.json`: for every
line, every take that was heard, what Whisper heard, and why one was chosen.

## How it decides

1. **Find takes**: split the recording at pauses (FFmpeg `silencedetect`).
2. **Hear them**: transcribe each take with Whisper, run locally with onnxruntime.
3. **Match**: compare each take's words with every script line. Takes that match
   nothing (chatter like "sorry, again") are left out. Takes that start a line and
   stop are marked as false starts.
4. **Choose** per line: says the line exactly > closest wording > fewer "um"s >
   no hidden hesitation (same words but noticeably slower) > the later take.
5. **Cut**: trim each chosen take with a little breathing room, short audio fades,
   loudness levelled to -16 LUFS, H.264/AAC MP4.

## Parts and licences

| Part | Licence | How we use it |
|---|---|---|
| Our code | MIT | this repo |
| FFmpeg | LGPL/GPL | separate program the user installs |
| Whisper base.en weights (OpenAI), ONNX export by onnx-community | MIT | downloaded by the user at first run |
| onnxruntime, numpy | MIT, BSD | pip packages |
| Flite (test voice only, inside FFmpeg) | BSD-style | only for making test takes |
