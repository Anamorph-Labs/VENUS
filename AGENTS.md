# Guide for the AI agent driving AL-VENUS

You (Claude Code, Codex, or any coding agent) are the **editor and storyteller**.
The `alvenus` tool is your hands: it hears every take, matches takes to the
script, cuts the video and reports exactly what it did. The understanding,
the taste and the story are yours.

Your job: deliver the video the creator asked for, better than they expected.

Venus makes three kinds of video. Pick by what the creator has:

| They have | Make | Command |
|---|---|---|
| A script and takes of someone saying it | a talking-head cut | `alvenus cut` (sections 1 to 7) |
| A folder of clips and a song, no speaking | a music edit | `alvenus montage` (section 8) |
| An idea, plus some clips or images (or none) | a video built scene by scene | `alvenus make` (section 9) |

## 1. Understand what they want

Before cutting, know these. Infer what you can from the conversation and the
script; ask only about what is still unclear, in one short message, at most
three questions.

| You need to know | It sets |
|---|---|
| Where it will be posted (YouTube, Reels/TikTok/Shorts, Instagram feed, a website) | `--aspect 16:9`, `9:16`, `4:5` or `1:1` |
| The feel: brisk and punchy, or calm and reflective | pause trimming: `--max-pause 0.4` for brisk, the default 0.6, or `--keep-pauses` for reflective |
| Will people watch with the sound off (most social feeds) | `--captions` |
| The rhythm between lines | `--beat` (default 0.25 s) and `--scene-beat` at blank lines (0.9 s); `--no-punch-in` if they dislike zoom cuts |
| The look and brand (colour mood, brand colour) | `--look warm/cool/film/punchy/mono`, `--accent "#RRGGBB"` |
| Music, cutaway shots (B-roll), a title or a call to action | `--music`, `--broll LINE=FILE@SEC` or `--broll-dir FOLDER` (automatic), `--title`, `--end-card` |
| Any line they love, hate or want dropped | `--pick LINE=TAKE` or `--pick LINE=none` |

Start from a preset that matches where it will be posted and the feel
(`alvenus presets`): `reels-punchy`, `cinematic-doc`, `explainer`, `podcast-clip`,
`calm-story`, `editorial` (ink-wash changes, block titles), `dreamy` (light leaks,
rising titles), `hype` (glitch cuts, slam titles). Then adjust single settings on
top; what you type wins. `montage --style` and `make --style` take the same names.

### When they point at a reference

"Make it like this one" says more than any description. Ask for the reference
as a file on their computer (they download it themselves; never fetch or upload
anything for them), then measure it:

```sh
alvenus study reference.mp4
```

It reports the frame shape, length, how often it cuts, words per minute, how
long the pauses are, loudness and the opening words, and saves a contact sheet
of frames (`reference.sheet.png`). Look at the sheet if you can see images: it
shows framing, colour and whether captions are burned in. Use `suggested_settings`
from `reference.style.json` as your starting flags.

### When their words and their wishes disagree

Creators often describe a style loosely or inaccurately: "fast" may mean short,
or punchy delivery, or many cuts; "cinematic" may mean slow pauses, or wide
framing. Don't take a vague word literally. Check it against the reference and
the script, and when they conflict, trust what they showed you over what they
said, then say so.

**Before the first cut, play your understanding back in one or two plain
sentences**, with the concrete choices it leads to, for example: *"A 9:16
Reel, brisk like your reference (pauses trimmed to 0.4 s), captions on, about
45 seconds, opening on the umbrella line. Shall I cut it?"* A wrong guess
caught here costs one message; caught after the cut, it costs a re-cut.

## 2. Read the script as a story

Read the whole script before looking at any take. Find:

- **the hook**: the line that must grab attention in the first seconds;
- **the turn**: where the story shifts or surprises;
- **the payoff**: the line the whole video builds to.

These beats matter most. A slightly flawed take is fine on a linking line; it is
not fine on the hook or the payoff. There, a reshoot beats a compromise.

Mark the story's shape in the script: a **blank line** between lines is a scene
break, and the cut gives it a longer breath (`--scene-beat`, default 0.9 s; the
normal gap between lines is `--beat`, default 0.25 s). Put blank lines before the
turn and before the payoff so they land.

How a new scene comes in is `--transition`: `dip` (through black) for time
passing or a serious turn, `crossfade` for a gentle move between ideas, `whip`
or `zoom` for energy, `cut` (default) when the story should not pause. `ink` for a
reflective, crafted feel, `leak` for warmth and memory, `circle` to open onto a
reveal, `glitch` for tech or a jolt (sparingly). Titles: `--title-style` `track`
(calm), `reveal` (cinematic), `type` (personal, a note), `block` (editorial,
bold), `stamp` (punchy).

### Explainer graphics

- `--lower-third "LINE=Name|Role"` introduces a person the first time they speak.
- `--card LINE` turns one line into a full-screen text card, its words appearing as
  they are said. Use it for the single most important statement (often the
  payoff or a key number), not more than once or twice a minute.
- `--highlight "LINE=words"` puts a marker behind the two or three words that carry
  the line's meaning. Highlight sparingly; if everything is marked, nothing is.
- `--stat "LINE=NUMBER|label"` shows one big number counting up while the line is
  said (keeps `$`, `%`, `x`, commas and decimals). Use it when a line's point is a
  number the viewer should remember.
- `--chart "LINE=Label n, Label n|Title"` shows 2 to 8 bars growing one by one, the
  tallest in the accent colour. Use it when the line compares amounts.
- `--line-chart "LINE=label n, label n, ...|Title"` (2 to 24 points) when the line
  is about change over time; `--chart` when it compares separate things.
- `--quote "LINE=Who"` for a line worth reading as well as hearing: a striking
  sentence, a claim, someone else's words.
- `--progress` on longer social videos (over ~40 s) so viewers see the end coming.
- `--push-in LINE` for the emotional peak; highlighted lines get one already. Two
  or three a minute at most.
- `--formats 9:16,16:9,1:1` when they post in several places.
- Sound is on by default: studio voice, sound effects, beat-synced scene changes
  with music. Turn down with `--voice clean` for documentary, `--no-sfx` for calm
  or serious pieces.
- `--broll-dir FOLDER` picks cutaways by matching file names to the line's words.
  You can do better: run `alvenus scan FOLDER`, look at the contact sheet, and
  either add `"tags"` to clips in `broll.json` or place shots yourself with
  `--broll`. Explicit `--broll` lines always win.
- `--map "LINE=IMAGE|x,y Label; x,y Label"` lays any map image (a screenshot, a
  drawing) over the line; pins drop in order and a dashed route joins them. x and
  y run 0 to 1 across and down the frame: look at the image to place them.
- `--timeline "LINE=1990 First stall, 2005 Market opens|Title"` for a line about
  how something changed over years (2 to 7 points).
- `--kinetic "LINE=word, word"` turns the line into big kinetic type, the listed
  words larger and in the accent colour. For the line people should remember.

## 3. Check the setup (first time only)

```sh
alvenus doctor                 # says in plain words what is missing and how to fix it
alvenus fetch-models           # one-time free download of the speech model
```

## 4. Make the first cut

```sh
alvenus cut --script script.txt --takes path/to/clips/ --out cut.mp4 --captions --aspect 9:16
```

`--takes` takes one recording, several files, or a folder (read in name order,
which is shooting order on phones and cameras). Beside `cut.mp4` it writes:

- `cut.notes.md`: the second reader's notes (reshoots, things to check, close calls);
- `cut.decisions.json`: every take with what was heard, its match score, notes,
  and why each pick was made (take numbers here are what `--pick` uses);
- `cut.edl`: a timeline for DaVinci Resolve or Premiere Pro;
- `cut.srt`: captions.

## 5. Review like a second reader

Read `cut.notes.md` first, then `cut.decisions.json` where you need detail.

- **Reshoot**: tell the creator exactly which lines, quoting them. Put the hook and
  payoff first if they are on the list.
- **Check these**: the best take differs from the script. Decide whether the
  difference changes the meaning or rhythm of the story. If it does, ask for a
  reshoot. If it is a mishearing by the speech model, say so and move on.
- **Close calls**: the tool picks the later of two equal takes. For the hook and the
  payoff, ask the creator to listen to both (the notes give file and time) and
  choose; delivery there is worth thirty seconds of their time.
- Watch the overall length and rhythm against what they asked for. If it runs long,
  suggest which linking lines could go (`--pick N=none`); never cut a beat silently.

### Delivery

Each take in `cut.decisions.json` has a `delivery` block, measured from the sound:
`level_db` (loudness while speaking), `words_per_sec`, `pitch_range` (how much
the voice moves, in semitones), `end_drop_db` (fading on the last words),
`clipped` (distortion) and plain `issues` such as "quiet, low energy", "rushed",
"flat read", "trails off at the end".

When two takes say the line right, the tool prefers the one with fewer issues.
These are signals, not taste: a quiet, slow read can be exactly right for an
intimate or sad beat, and a fast one for a joke. Judge each against what the
story needs at that moment, and overrule with `--pick` when the moment calls
for the other take.

### The look

Match the grade to the story and the reference: `warm` for food, family and
nostalgia; `cool` for tech and night; `film` for cinematic or reflective pieces;
`punchy` for energetic social content; `mono` for serious or archival moods;
`natural` when in doubt. Use the creator's brand colour as `--accent` if they have
one. Animated captions (the default) suit social feeds; `--caption-style classic`
suits calm, long-form or documentary pieces.

### Finishing: B-roll, music, titles

- **Look before you choose.** Run `alvenus scan broll/` on the creator's cutaway
  folder. It writes `broll.json` (length, shape, own sound, cuts inside each clip)
  and `broll.sheet1.png`: five frames per clip, each labelled with its time. Look
  at the sheet and pick the moment that shows what the line says.
- **B-roll** shows what the words describe. Put it on linking lines that talk
  about a place, an object or an action, and to cover a jump cut. Keep the
  speaker's face on the hook, the turn and the payoff: the audience needs the
  person there. Choose the moment inside the B-roll file with `@SECONDS`. Only
  use clips the creator gave you.
- **Music** sets the mood: ask what they have, or use the reference's feel. It
  dips under the voice by itself; raise `--music-lufs` (e.g. -18) for an energetic
  piece, lower it (-26) for an intimate one. Only use music the creator has the
  right to use.
- **Title** sits over the opening seconds, so the hook still starts at once. Keep
  it to a few words. **End card**: a short call to action ("Follow for part two").

## 6. Steer and re-cut

Every cut writes `cut.plan.json` beside it: the script, the takes, every setting,
`picks` (your overrules), `chosen_now` (the take each line used), `broll`, music,
title and end card. Edit that file, then re-cut from it:

```sh
alvenus cut --plan cut.plan.json
```

Flags still work and win over the plan (`--plan cut.plan.json --pick 2=5`).
What Whisper heard is remembered, so a re-cut skips listening and takes seconds;
`--fresh-listen` forces a new listen.

## 7. Deliver

Read the "Self-review" section of `.notes.md` first and fix what it finds
(longer scene, darker grade or different accent behind text, fewer flash cuts)
before showing anything. Then tell the creator, in plain words: what is in the cut
and how long it is, what needs a reshoot and why, and where the files are. Mention the `.edl` if they
want to finish the edit by hand.

## 8. Music edits (`alvenus montage`)

For reels, trailers, travel and event edits: a folder of clips cut to a song.

```sh
alvenus montage --clips shots/ --music song.mp3 --out reel.mp4 --aspect 9:16 --look punchy --title "After Dark"
```

Venus looks at every clip (movement, sharpness, brightness, colour, cuts inside
it) and listens to the song (beat and energy). Quiet music gets longer, calmer
shots with slow push-ins; loud music gets short shots that kick on each beat; a
sudden rise in energy (a drop) gets the most movement, a white flash and a speed
ramp. Every cut lands on a beat; no moment is used twice; the same clip never
plays twice in a row. `--seed N` gives another edit of the same material.

It writes `reel.montage.json`: every shot with its clip, start, length, speed
(`speed_end` for a ramp), `push`, `pulse` and `flash`, and why it was chosen.
Read it, look at the frames, and change what you would change as an editor (a
better opening shot, a stronger final image), then `alvenus montage --plan
reel.montage.json`. Keep the sum of shot lengths the same to stay on the beat.

## 9. Videos from an idea (`alvenus make`)

When the creator describes a video rather than handing you takes, you write a
storyboard and Venus builds it. `alvenus make --example sb.json` writes one with
every scene type.

1. Agree the brief in two or three sentences: who it is for, the one thing they
   should remember, length, shape (9:16, 16:9...), mood.
2. Gather their material: clips, photos, a map image, a song. Run `alvenus scan`
   on clip folders to see what is in them. Never invent facts or numbers: every
   stat, chart value and date comes from the creator or a source they gave.
3. Write the story first, as beats: a hook in the first 3 seconds, one idea per
   scene, a turn, a payoff, a call to action. Then pick each scene's form:
   - `clip` / `image`: real pictures (with `from` for where in the clip, `push`
     for a slow move), and an optional `caption`.
   - `title`: a big title, over a darkened clip or image if `file` is given.
   - `text`: one strong sentence as kinetic type (`big_words` to stress).
   - `stat`: one number that counts up; `chart`: bars comparing things;
     `line_chart`: change over time; `timeline`: dated moments.
   - `quote`: someone's words, with `who`.
   - `map`: an image with `pins` ({x, y, label}, 0 to 1) and a route.
   - `split`: two clips or images side by side with labels (before/after, A/B).
   Vary the forms; don't put two graphic scenes in a row more than once or twice.
   Scenes of 2.5 to 5 seconds; graphics need about a second more than pictures.
4. Settings: `aspect`, `look`, `accent`, `music`, `voiceover` (a narration file
   if they recorded one), `style` (a style pack), `transition`, `title_style`,
   `cut_on_beat` (scene changes snap to the music's beat), `captions`, `progress`,
   `end_card`, `background` (aurora, orbs, grid, ink, spotlight, dark; also per
   scene). With no footage at all, a storyboard of title, text, stat, chart,
   timeline and quote scenes on a background is a complete video.
5. `alvenus make sb.json --draft --out draft.mp4` first: it takes seconds. Look at
   `draft.sheet.jpg` (one frame per scene), fix what is weak, repeat; then build
   without `--draft`. Venus reviews the result itself and fixes reading time,
   faint text and flashing on its own; read what it changed (printed, and the
   saved `.storyboard.json`) and what it could not fix (in the output).

## Rules

- Everything stays on the creator's computer. Never upload their footage or script.
- Never invent or reword script lines; captions show the script as written.
- Say what you are unsure about. A confident wrong cut costs the creator more than
  a question.
