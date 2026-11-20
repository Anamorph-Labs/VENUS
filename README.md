# AL-VENUS (working name)

A free, local video agent. Phase 1: **script-to-cut**. Give it your script and
your raw footage (one long recording or a folder of clips); it finds each take, works out which
script line it is, picks the best take per line and cuts the video.

Everything runs on your own computer. No accounts, no API keys, no uploads.

It is meant to be driven by your own AI agent (Claude Code, Codex, ...), which
brings the understanding and the storytelling: see [AGENTS.md](AGENTS.md).

## Try it

One step: `bash install.sh` (macOS, Linux) or `powershell -ExecutionPolicy Bypass
-File install.ps1` (Windows). It checks Python 3.10+, installs FFmpeg if it is
missing (Homebrew, apt or winget), puts Venus in its own folder, downloads the free
models once (`--small` for the lighter listener, `--find` for footage search) and
runs `alvenus doctor`. Or by hand, with Python 3.10+ and [FFmpeg](https://ffmpeg.org/download.html):

```sh
pip install .                           # gives you the `alvenus` command
alvenus doctor                          # checks FFmpeg, packages and models
alvenus fetch-models                    # one-time ~1.5 GB download of Whisper small.en
python examples/fakeshoot.py night2 examples/out   # fake test shoot: 5 clip files (needs FFmpeg with Flite)
alvenus cut --script examples/night2/script.txt \
  --takes examples/out/clips --out examples/out/cut.mp4 --captions
```

Next to the MP4 you get:

- `cut.xml`: the edit, for Premiere Pro (File > Import) or DaVinci Resolve (File >
  Import > Timeline). The media is already linked, the takes Venus did not use sit
  on switched-off tracks above each line (swapping is a toggle), and a marker on
  each line says which take was picked and why. `cut.edl` is the plain fallback.
- `cut.srt`: captions, one per script line.
- `cut.notes.md`: the second reader's notes: what to reshoot, what to check, close calls.
- `cut.decisions.json`: for every line, every take that was heard, what Whisper
  heard, and why one was chosen.

Study a reference video to match its style: `alvenus study reference.mp4` measures
its shape, cut rhythm, pace, pauses and loudness and suggests settings. Give it a
folder of about five of one kind and it learns a style pack of your own:
`alvenus study refs/ --as my-vox`, then `--preset my-vox` (or `--style my-vox`). Its
colour grade is fitted to each of your clips, so they land on the references' look.

Ask your footage: `alvenus find "someone laughing" clips/` finds the moments that
match, with times and a picture of them, using a free model on your computer.

Phone footage works as it comes: sideways-stored portrait video, HEVC `.mov`,
60 fps and variable frame rate.

Steer it with `--aspect 9:16` (or 16:9, 1:1, 4:5), `--pick 2=5` (use take 5 for
line 2), `--pick 4=none` (drop line 4), `--max-pause` / `--keep-pauses`,
`--beat 0.25` (breath between lines), `--scene-beat 0.9` (longer breath where the
script has a blank line), `--no-punch-in`.

Finishing touches: `--broll 3=market.mp4@4.5` lays a cutaway shot over line 3
(from 4.5 s into the file) while the voice keeps playing; `--music song.mp3` plays
music under the cut that dips whenever someone speaks (`--music-lufs` sets how
loud it is between lines); `--title "..."` shows a title over the opening seconds;
`--end-card "..."` adds a closing card. `--broll-dir shots/` picks cutaways by
itself: it matches each clip's file name (and any `tags` you add in that folder's
`broll.json` from `alvenus scan`) to the words of each line, keeps the first and
last lines on the speaker, and uses at most one line in two. Its picks are written
into the plan, so you can change them. Captions always stay on top. The `.edl`
holds the main cut only, not the B-roll or music.

Explainer data: `--stat "4=112|clocks repaired this year"` turns line 4 into a
big number that counts up; `--chart "2=Fruit 4, Lamps 7, Books 5|What the stalls sell"`
turns line 2 into a bar chart whose bars grow one by one, the tallest in the accent
colour.

Sound: the voice gets a studio treatment by default (`--voice studio`: room hiss
lifted out, harsh "s" sounds softened, a little warmth, even loudness; `clean` does
the cleanup only, `off` leaves it as recorded). Soft whooshes and pops, made by
Venus itself, sit under whip/slide/zoom transitions and under graphics as they land
(`--no-sfx` for none). With `--music`, scene changes slide onto the music's beat by
lengthening the quiet breath before them, never by moving speech
(`--no-beat-sync` to keep them where they are).

More explainer graphics: `--line-chart "3=2019 4, 2021 6, 2023 11|Stalls per night"`
draws a line across the screen point by point; `--quote "4=Mara Ilić"` shows a line as
a pull-quote card; `--progress` adds a thin bar along the bottom that fills as the
video plays. `--push-in 5` leans the camera slowly in across line 5 (highlighted lines
get one by themselves; `--no-push-in` for none).

Every format at once: `--formats 9:16,16:9,1:1` makes `out-9x16.mp4`, `out-16x9.mp4`
and `out-1x1.mp4` in one go (listening happens once). Each cut also gets a thumbnail,
`.thumb.jpg`: a strong frame of the speaker with the title set big.

The look: `--captions` are animated by default: short phrases, each word lights
up in the accent colour as it is said (`--caption-style classic` for one plain
line). `--look warm|cool|film|punchy|mono` grades speaker and B-roll alike;
`--accent "#FFD23F"` sets the highlight colour. Titles and end cards are
motion-designed (letters track in, an accent bar draws out underneath; the end
card sits on the last frame, blurred). Text uses the bundled Inter fonts (SIL Open
Font License, see `alvenus/fonts/OFL.txt`), so cuts look the same on every computer.

`alvenus scan broll/` looks through a folder of cutaway clips and makes a contact
sheet with times, so you (or your AI) can choose shots. Every cut also writes a
`.plan.json` holding every choice; edit it and run `alvenus cut --plan cut.plan.json`.
What was heard is remembered, so re-cuts skip listening (`--fresh-listen` to redo it).
Style packs: `alvenus presets` lists them; `--preset reels-punchy`,
`cinematic-doc`, `explainer`, `podcast-clip`, `calm-story`, `editorial`, `dreamy` or
`hype` sets shape, pacing, captions, look, colour, title animation and transitions in
one go (anything you type still wins). The same word works for `montage --style` and
`make --style`.
`--transition dip|crossfade|zoom|whip|flash|slide|blur|circle|ink|leak|glitch` sets how
a new scene comes in after a blank line in the script. `--title-style
track|reveal|type|block|stamp` sets how the title and end card animate in.

Self-review: every cut, montage and storyboard video is watched once more before
it is handed over: text on screen long enough to read and readable against what
is behind it, no stray black, no rapid flashing (a seizure risk), sound and picture
in step, no dead silence, no text running off the frame. Findings go in
`.notes.md`; `alvenus review VIDEO` runs it on any video. For storyboard videos
and music edits Venus also fixes what it can by itself (a longer scene for text
that needs it, a darker picture behind faint text, a dissolve instead of a
flashing cut, calmer shots where a music edit flashes too much) and builds again;
the fixed storyboard is saved beside the video (`--no-fix` to only report).

Drafts: add `--draft` to `cut`, `montage` or `make` for a quick look at a third of
the size with the fastest settings (a 30 s storyboard video in about 30 s). Every
render also writes `.sheet.jpg`, one page with a labelled frame from each scene.

Backgrounds: storyboard scenes without footage (titles, text, numbers, charts,
timelines, quotes) are drawn on a living background made by Venus itself:
`"background": "aurora" | "orbs" | "grid" | "ink" | "spotlight" | "dark"` for the
whole video or per scene, tinted from the accent colour; each style pack picks one.

Explainer graphics: `--lower-third "1=Mara Ilić|Night baker"` (animated name tag),
`--card 4` (line 4 as a full-screen kinetic text card, words appearing as they are
said), `--highlight "3=broken clocks"` (a marker highlight behind those words).

Clean-up and framing: filler sounds ("um", "uh") inside the chosen takes are cut
out (`--keep-fillers` to leave them). Wide footage going into a taller frame
follows the speaker instead of cropping the centre (`--reframe blur` fits it whole
on a blurred copy instead). Clips are rendered one at a time, so memory stays flat
on long shoots (a 4.5-minute, 72-take test shoot cuts in under 3 minutes once heard).

Use `--model base.en` for a faster but less careful listen (~290 MB, about 2.5x faster).

## Music edits and videos from an idea

`alvenus montage --clips shots/ --music song.mp3 --out reel.mp4` cuts a folder of
clips to a song: every cut on a beat, calm shots with slow push-ins in the quiet
parts, short shots that kick on each beat in the loud parts, and the strongest
movement with a flash and a speed ramp on the drop. The shot list is written to
`reel.montage.json`; edit it and run `alvenus montage --plan reel.montage.json`.

`alvenus make storyboard.json --out video.mp4` builds a video scene by scene from
a storyboard your AI writes from your idea: clips, images, titles, kinetic text,
counting numbers, bar and line charts, timelines, quotes, maps with pins and
routes, and side-by-side comparisons, cut on the music's beat.
`alvenus make --example sb.json` writes one with every kind of scene, and
`alvenus make --template explainer|story|list|ad sb.json` writes a starter in one
of four proven shapes, each opening on a hook inside the first two seconds.
Storyboards also have lists that build point by point, side-by-side comparisons,
and callouts (a ring, a line and a label pointing at something in a clip).
Scenes without footage move like a filmed shot: the type drifts slowly over a
background that moves less, for depth (`"camera": false` to keep them still).
Change one scene and build again: only what changed is redrawn (kept in
`.venus-cache` beside the video). `--scene 3` builds one scene alone in seconds;
`--versions` builds three quick drafts side by side with the reason for each; and
`video.why.md` says why every scene is as long as it is.

`alvenus nodes init storyboard.json` turns a storyboard into a node file: the same
video as named nodes (`scene3.words`, `scene3.picture`, `scene5.in`...), so you and
your AI can say exactly what to change (`alvenus nodes set FILE scene3.words.size=1.3`),
lock the parts you like so nothing touches them, share settings between scenes
with style nodes, and rebuild only what changed. `alvenus nodes view FILE` draws
the node map as a page, with a frame of every scene.

`alvenus studio video.nodes.json` opens **Venus** (by Anamorph Labs) in your browser: a node
editor laid out like a compositing app, with a live frame of the scene and its
node graph: the paper along the bottom, each layer (shape, picture, words, marks)
dropping into a Merge from its own branch, and tool nodes (blur, glow, grade,
vignette) you add with a right-click and drag onto any wire. Drag a branch onto
another Merge to restack (words behind the print), pan, zoom, and a map in the
corner. Sliders and colours for each node, switch-off to compare,
a before/after wipe, undo, and one button to render. Describe what you want in
any node's box; Venus does the simple asks at once and keeps every description
on the node for your own AI, whose changes show up in Studio as it makes them.
Nothing leaves your computer.

More explainer graphics for talking-head cuts: `--map "3=city.png|0.3,0.6 Old port;
0.7,0.4 Market"`, `--timeline "2=1990 First stall, 2024 500 stalls|How it grew"`,
`--kinetic "5=lose, track"`.

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
| CLIP ViT-B/32 weights (OpenAI), ONNX export by Xenova | MIT | footage search; downloaded by the user on first use |
| onnxruntime, numpy, Pillow | MIT, BSD, MIT-CMU | pip packages |
| Flite (test voice only, inside FFmpeg) | BSD-style | only for making test takes |
