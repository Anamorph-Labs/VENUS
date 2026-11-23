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

When they have several references of one kind (about five of their favourite
explainers, trailers...), turn them into a style pack of their own:

```sh
alvenus study refs/ --as my-vox
```

Venus measures shape, pace, cuts versus dissolves, colour (saturation, contrast,
warmth, shadow and highlight tint, lifted blacks, vignette) and the accent colour
that keeps coming back, writes `my-vox.style.md` explaining it, and saves a pack
usable as `cut --preset my-vox`, `montage --style my-vox`, `make --style my-vox`.
Its grade is fitted to each piece of footage when used (it grades a few frames,
measures, corrects), so their clips land on the references' colour. Nothing from
the references is copied into the video.

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

### A produced talking head (`--talk`, preset `talk-studio`)

For a person talking to camera that should feel like a produced show, not a
webcam recording, add `--talk`. Some lines open up into a designed set: the
speaker moves into a framed window on one side, and the other side holds the
line's words, arriving as they are said (key words in a serif italic, in the
accent colour), or the line's graphic (`--stat`, `--chart`, `--line-chart`,
`--quote`, `--timeline`). The face never leaves the screen, so a number no
longer interrupts the person. 9:16 and 4:5 stack the window over the words.

Venus directs it: graphics and marked lines (`--highlight`, `--kinetic`)
open up; the hook and the last line stay on the face; a long run of the face
(about 5 s) gets a words panel to reset attention. It writes `cut.layout.md`
with the reason for every line. Overrule one with `--layout 3=side` or
`--layout 3=full`; `--chapter "3=How it works"` names a chapter on the set's
header (with a running "02 / 03"). Use it when the story has parts. Keep the
hook and the payoff full frame unless the payoff *is* a number.

### Documentary and travel

- **Documentary** (preset `documentary`): cinema bars (`--letterbox`, 2.39 by
  default, captions sit in the bar like cinema subtitles), a muted filmic grade
  (`--look doc`), serif name tags (`--lower-third-style doc`, use with
  `--lower-third`), chapter titles (`--title-style chapter`, text
  `"Part one|The night shift"`), and place-and-time stamps typed out as a line
  starts (`--place "2=Juniper Street, 3:12 AM"`). In a storyboard: `"letterbox"`,
  `"lower_third_style"`, and a scene's `"place"`.
- **Travel** (preset `travel-reel`, best with `montage`): a warm sunny grade
  (`--look travel`), arrival titles when a place first appears
  (`montage --place "lisbon.mp4=Lisbon|Portugal|38.72 N, 9.14 W"`: the place in
  huge condensed capitals, the country written by hand across it, the
  coordinates typed below; in a storyboard a scene's `"arrive"`), and a
  camcorder date in the corner (`--datestamp "NOV 21 2026"`). Use
  `--title-style place` for an opening title in the same family. Only put real
  places and dates the creator gave you.

### Archive documentary, sepia openers and match cuts

- **Archive documentary** (preset `archive-doc`, with `make`): black and white
  with one red accent. An `"archive"` scene floats an old photograph as a print
  on a dark desk of documents, the desk and print drifting apart, with its
  `"year"` large in serif, a red `"tag"` (one word) and a small typed `"detail"`
  on the side away from the print. Use for a life, a company or a place told
  through old photos: one photo per scene, in date order. Only use years and
  facts the creator gave you.
- **Quote cards** (`"quote_style": "verse"`, on in both presets): the quote in
  centred serif over the scene's own picture, the source (`"who"`) in a small
  red tag. Give the quote scene a `"file"` to sit on.
- **Frames** (any scene, `"frame": "cloud"` or `"ink"`): drifting white clouds
  (memory, faith, dreams) or ragged sepia ink (film openers) round the picture.
- **Reveals** between scenes: `bloom` (ink blots spreading), `cloud` (billows
  and white mist), `tear` (a torn paper edge crossing), `tiles` (squares
  flipping in a scattered order). Set storyboard `"transition"` or a scene's own.
- **Sepia film opening** (preset `sepia-film`): brown old-photograph grade,
  ink frames, and opening credits: storyboard `"credits": [["Directed by",
  "Name"], ...]`, one per scene from the start (or a scene's `"credit":
  "Role|Name"`), set in small spaced capitals in a different corner each time.
  Only real names the creator gave you.
- **Looks**: `sepia`, `archive` (both with `--look` or `"look"`).
- **Match cuts** (`montage --match-cut`): shots that share a framing (an eye in
  the same spot, a figure on the same horizon, one object) are put one after
  another and lined up, the later shot pushed in and moved so the subject
  stays put. Suggest it when the clips repeat a subject: faces, eyes, hands,
  silhouettes, the same object in many places.
- **Creative edit** (preset `creative-edit`, or `montage --creative`): the
  surreal fast reel. A cut every half beat; silhouettes (a black figure on a
  rim of red light, glowing yellow figures with copies popping in), light
  strobes, bursts, lightning, a photo flickering with its sketch or
  blueprint, negative and x-ray frames, cut-outs on a colour that flips
  every two frames, and an ending that turns to dots and strobes. Stills and
  AI pictures work as clips. `--in-order` keeps the clips in the order given
  (seed, sprout, plant; stone, wheel, tyre: a thing changing step by step).
  `--words "HIGHS AND LOWS"` sets words behind the subject of one shot;
  `--shape infinity` (or heart, circle, any short text) is what the final
  dots gather into. Every shot's effects are in the plan (`fx`, `fxo`): read
  `alvenus fx --list`, change them, and render again with `--plan`. It
  flashes a lot: tell the creator to add a flashing-lights warning when they
  post it. One shot alone: `alvenus fx clip.mp4 --fx glow --opt copies=3
  --out x.mp4`; a subject lifted off its background for any editor:
  `alvenus cutout clip.mp4 --out subject.mov` (person, object or plain
  background; free models fetched once, run on the computer).

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
and how long it is, what needs a reshoot and why, and where the files are. If they
want to finish the edit by hand, point them at the `.xml` timeline: Premiere Pro
(File > Import) and DaVinci Resolve (File > Import > Timeline) open it with the
media linked, the unused takes on switched-off tracks above each line, and a
marker per line saying which take was picked and why (the `.edl` is the plain
fallback).

To find a shot in their footage by what is in it, ask it:
`alvenus find "someone laughing" clips/` lists the best moments with times and a
picture of them (it looks at every clip once with a free local model, then answers
in a second). Use the result as `--broll LINE=FILE@SECONDS` or a storyboard clip.

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
storyboard and Venus builds it. **Venus never makes a video straight from an
idea: the storyboard is shown to the creator first, and built only after they
say yes.** The path is always brief, storyboard, check, the creator's yes, make:

    alvenus brief "their idea, word for word" brief.json   # the questions to settle
    alvenus brief brief.json                                # is it complete?
    alvenus storyboard brief.json sb.json                   # beats laid out by the recipe
    (you write the words and pick the pictures, scene by scene)
    alvenus check sb.json                                   # the story check + sb.board.md
    (show the creator sb.board.md; change what they ask; check again)
    alvenus approve sb.json --by "their name"               # only on their yes
    alvenus make sb.json --draft --out draft.mp4            # then the full build

`make` refuses a storyboard that is not approved, or that changed after it was
approved (the approval is a fingerprint of its content, in sb.approved.json).
A change after approval means showing it and approving again: say what changed
in one line, then approve on their yes. In Venus Studio, the creator pressing
Render or a scene's play button is their approval of what is on screen.

**The brief.** Fill every field of brief.json from what they said; ask only what
you cannot tell (usually the one point and the length). `point` is the ONE thing
to remember, one sentence. `facts` lists every number, date and name the video
may state, each with its source; the story check refuses a number on screen that
is not there. Never make one up to fill a stat scene: ask, or use another form.

**The recipe.** `alvenus storyboard` lays out one scene per beat for the kind
(`explainer`, `travel`, `story`, `list`, `ad`), with its length and its job
(`_job`). Write each scene for its job. You may change a scene's form to one in
`_other_forms`, split a beat in two, or add a scene, but keep the beats in order:
- explainer: hook (a claim or number under 3 s), question, two steps (one idea
  each, different forms), turn (what people get wrong: "but", "actually", a
  compare), proof (one fact from the brief), payoff (the point, echoing the hook).
- travel: hook (the best shot, before any words), place (name, country, date, or a
  map), arrival, three moments (people, a close detail, the place at its best),
  one quiet longer shot, payoff (a closing line: what it felt like, not what it was).
  Use `alvenus find` on their clip folders to find each shot.

**The story check** (`alvenus check`) reads the storyboard as an editor would and
refuses it ("weak") when the hook is a greeting, too long or too wordy; a scene
says two things or has too little time to be read; nothing turns in the middle;
the ending doesn't say the point; a number isn't in the facts; the length is far
from the brief; a scene runs over 8 s; or a scene is still empty. "Notes" are
advice and never block. Fix the weak points scene by scene and check again; when
the creator wants it as it is anyway, `approve --anyway "their reason"`.
It writes `sb.board.md`: the brief, then one row per scene (beat, time, what is on
screen). Show that board to the creator, not the JSON.

Templates still work for a quick start (`alvenus make --template explainer|story|
list|ad sb.json` writes a filled example of the shape); they go through the same
check and approval. `alvenus make --example sb.json` writes every scene type.

1. Settle the brief (above).
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
   - `list`: up to 6 short points that arrive one by one with numbered badges.
   - `compare`: `left` and `right`, each `{"title", "points"}`, with a "vs" badge.
   - Any clip or image scene can add `"callout": {"x", "y", "label"}` (0 to 1 across
     and down the picture) to point at something with a ring, a line and a label.
   Vary the forms; don't put two graphic scenes in a row more than once or twice.
   Scenes of 2.5 to 5 seconds; graphics need about a second more than pictures.
4. Settings: `aspect`, `look`, `accent`, `music`, `voiceover` (a narration file
   if they recorded one), `style` (a style pack), `transition`, `title_style`,
   `cut_on_beat` (scene changes snap to the music's beat), `captions`, `progress`,
   `end_card`, `background` (aurora, orbs, grid, ink, spotlight, dark; also per
   scene). With no footage at all, a storyboard of title, text, stat, chart,
   timeline and quote scenes on a background is a complete video. Footage-free
   scenes drift with a slow camera move (type over a background that moves less,
   for depth); `"camera": false` keeps them still.
   **Designed looks** (`"style": "mono-editorial"` or `"vox-paper"`, or `"design":
   "mono"` / `"paper"`): the scenes become a designed page instead of footage on a
   background. "mono" is a greyscale editorial reel: grey grid paper with print
   details (header, scene number, crop marks, barcode, small columns of the scene's
   own words), black-and-white photos as prints, one accent shape, words arriving
   one at a time in mixed type. "paper" is a Vox-style collage: crumpled paper,
   torn photo prints with tape, a paint blob or flat colour circle behind, heavy
   caps with a highlighter, red hand-drawn arrows and loops. Pictures (`image` or
   `clip`) become prints beside or under the words; give each scene a `caption`
   (or `text` for a words-only scene). Mark words up for the type to change:
   `*word*` elegant serif italic (the feeling word), `_word_` small and light (the
   filler words), `==word==` highlighted (the one fact), and `big_words` for the
   huge ones. Use one or two marks per line, not more: the contrast is the point.
   A `title` scene takes `subtitle` too. Extra: `"label"` (the figure caption under
   a print, mono), `"note"` (a handwritten note by the arrow, paper), `"dark": true`
   (a dark page for a change of mood, mono). Stats, charts, lists and other graphic
   scenes sit on a dark page in these looks. A new graphic lands about every
   0.8 s, near the pace of the references these were learned from; `alvenus study`
   reports `seconds_per_graphic_beat` for any video, to compare pace.
5. After the creator's yes, `alvenus make sb.json --draft --out draft.mp4` first: it takes seconds. Look at
   `draft.sheet.jpg` (one frame per scene), fix what is weak, repeat; then build
   without `--draft`. Venus reviews the result itself and fixes reading time,
   faint text and flashing on its own; read what it changed (printed, and the
   saved `.storyboard.json`) and what it could not fix (in the output).
6. Changing one thing keeps the rest: edit that scene in the storyboard and build
   again; only scenes whose picture changed are redrawn (words, titles and sound
   are always fresh). `--scene 3` builds scene 3 alone in seconds, to check a
   change. `video.why.md` explains every scene's length and change of scene, so the
   creator can disagree with something specific.
7. When the creator is unsure of the feel, `--versions` builds three quick drafts
   side by side (their style, the opposite energy, a tighter pace), with
   `video-versions.jpg` to compare and `video-versions.md` with why each exists.
   They pick one; build it in full from its saved `.storyboard.json`.

### Nodes: precise control (`alvenus nodes`)

For anything past a first draft, work on a node file instead of the storyboard.
It is the same video cut into named nodes, so every change names exactly what it
touches, and nothing else moves.

1. `alvenus nodes init sb.json` writes `sb.nodes.json` (nothing is lost; `nodes
   export FILE --out sb.json` goes back). Nodes: `settings`, `sound`, one `sceneN`
   per scene, and under each scene its parts: `sceneN.in` (its transition),
   `.words`, `.picture`, `.mark` (callout, note) and `.graphic` (the number, chart,
   list, map or comparison). Ids are names, not positions: a moved scene keeps its id.
2. `alvenus nodes show FILE` prints the map in a few lines: read it before every
   change, not the JSON. `nodes guide` lists what each node can hold.
3. Change with `alvenus nodes set FILE NODE.PARAM=VALUE ...`, for example
   `scene3.words.size=1.3 scene3.picture.shape=none scene5.in.transition=whip`
   (`null` removes a setting; a missing part is created). A wrong name is refused
   with the nearest right one, and nothing is saved until everything checks out.
   Controls in the designed looks: words `size`, `speed` (seconds between words),
   `delay`, `align`, `caps`; picture `size`, `shape` (circle, block, blob, none),
   `shape_colour`, `angle` (tilt of a still), `photo` (grey, colour, warm),
   `darken`, `push`; mark `colour`, `show` (false hides the automatic label or arrow).
4. **Lock what the creator likes**: `alvenus nodes lock FILE scene3` (a scene lock
   covers its parts and the styles it uses). A locked node refuses `set`, the
   self-review leaves it alone, and a build stops if it was edited by hand. When
   the creator says "keep that one", lock it before changing anything else.
5. **Shared styles**: `alvenus nodes use FILE calm scene2 scene5`, then
   `nodes set FILE calm.words.size=0.9 calm.picture.shape=none`. Every scene using
   the style follows it; a scene's own setting still wins. Use one for a recurring
   kind of beat (all quotes, all close-ups) instead of repeating settings.
6. Order: `nodes move FILE scene5 --after scene2` (or `--before`, `--first`),
   `nodes copy FILE scene2 [--as id]`, `nodes remove FILE scene4`.
7. Build with `alvenus make FILE --out video.mp4` as usual. It prints which nodes
   changed since the last build and which scenes it redrew; words, marks and
   timing never redraw a scene. `--scene scene3` builds one scene by its id.
8. `alvenus nodes view FILE` writes `FILE.html`: the node map as boxes and wires,
   with a frame of each scene from the last build, locks, and what changed. Send
   it to the creator so they can point at a node ("scene4.words feels slow").

### The Venus editor: the creator edits, you help (`alvenus studio`)

`alvenus studio FILE.nodes.json` opens a node editor in the creator's browser, on
their computer: a viewer with a live frame of the selected scene, the scenes
along the bottom, the scene's node graph in the middle, and sliders, colours and
lists on the right. Every change is saved to the node file at once, and what you
change in the file shows up in Studio within a second, outlined in blue, so the
two of you work on the same video side by side.

The graph is built like a compositing page. The **paper** runs along the bottom
(the trunk). Each layer comes down into it along its own **branch** and is laid
on top by a **Merge**, in order: by default shape, then picture (Picture ->
Look), then words, then marks. After the last Merge come the output tools, then
**In** (the transition) and **Output**. Style nodes are wired (dashed) into the
nodes they set. The creator can drag a branch onto another Merge to restack, and
add **tool nodes** anywhere (right-click, or on a wire): blur, glow, grade,
vignette. You do the same from the command line:

- `alvenus nodes layers FILE scene3 shape words picture marks` sets what sits over
  what, bottom to top (here the words go behind the print, for a collage feel).
  Anything left out keeps its place. Putting a layer over the words, or any
  output tool, draws that scene's words into the scene itself.
- `alvenus nodes add FILE scene3 glow amount=0.6 --on words` puts a tool on a
  branch: `background` (the paper), `picture`, `words`, `marks`, or `output`
  (everything merged above it). `--before scene3.blur` puts it ahead of another
  tool. Tools are nodes like any other: `nodes set FILE scene3.glow.amount=0.3`,
  `nodes off FILE scene3.glow`, `nodes remove FILE scene3.glow`.
- Use them with taste, as an editor would: a blurred paper pushes the print
  forward; a soft glow lifts the one line that matters; a vignette closes in on
  a quiet moment; a grade on the picture alone (`grade --on picture`) matches a
  photo to the page. One or two tools a scene, not a stack.
- In scenes that are not designed pages (stats, charts, maps...), tools on the
  paper, picture or output work on the whole picture, and the order is fixed.

The creator can **describe what they want in any node's box** ("warmer and
slower", "make this feel like the moment it breaks"). Plain asks Venus does at
once; every description stays on the node for you:

1. `alvenus nodes listen FILE` waits (up to 10 minutes; `--timeout`) until the
   creator writes something, then prints each description with its node, what
   Venus already did, what is left for you, and the node's settings now.
   `alvenus nodes asks FILE` prints them without waiting.
2. Read it as a storyteller: what does the creator feel is missing in that
   moment? Make the change with `nodes set` (look at the scene with `nodes show
   FILE sceneN` first). Check or refine what Venus already did.
3. Answer in a few plain words, which the creator sees under their description:
   `alvenus nodes answer FILE scene4.words "slowed the words so 'broken' lands last"`.
4. Run `listen` again while Studio is open, so the creator never waits on you.

Stages can be switched off to compare, as in a finishing app: `alvenus nodes off
FILE scene3 shape` (look, shape, words, marks), `nodes on` to bring it back; a
tool switches off by its id (`nodes off FILE scene3.glow`). Descriptions can
change the graph too: "words behind the picture", "soft glow on the words",
"blur the paper", "more contrast", "no vignette" are done by Venus at once. A
description can also be written from the command line: `nodes describe FILE
scene3.words "bigger"`.

## 10. Ideas for Venus itself (`alvenus suggest`)

Venus is started by Anamorph Labs and grows with its users. When the creator
wishes Venus could do something it can't, or you notice a missing feature while
working, offer to write it up as a suggestion. **Tell them how it works first:**
ideas are welcome; code is never added to Venus directly; every proposal is
scanned and reviewed, and Anamorph Labs builds the good ones itself; when an idea
ships, its author is thanked and credited by name (CONTRIBUTING.md has the detail).

1. `alvenus suggest "the idea in their words" idea.json` writes the form to fill.
2. Fill it with them: what Venus would do, why it makes videos better, one concrete
   example, and the name they want credited ("anonymous" is fine). Code is optional
   and only explains the idea.
3. `alvenus suggest idea.json` checks it is complete and carries nothing private
   (emails, keys, paths from their computer), then prints a link to a filled-in
   GitHub form. **Give them the link; they read it and press Submit themselves.**
   Never submit, post or email anything for them.
4. A new style pack or story recipe can be shared as an add-on: a JSON data file
   (see `examples/addon-style.json`, `examples/addon-recipe.json` and
   `alvenus/addons/README.md`), with `"kind": "add-on"` and `"addon_file"` in the
   suggestion. Venus checks every value before it is sent. `alvenus suggest --addons`
   lists the add-ons this Venus has.

## Rules

- Everything stays on the creator's computer. Never upload their footage or script.
- Never invent or reword script lines; captions show the script as written.
- Never send a suggestion, email or post for the creator: give them the link and let them submit it.
- No video before the creator has seen the storyboard and said yes (`alvenus approve`).
- Say what you are unsure about. A confident wrong cut costs the creator more than
  a question.
