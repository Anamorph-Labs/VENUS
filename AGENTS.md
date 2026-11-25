# Guide for the AI agent driving Venus

You (any coding AI agent) are the **editor and storyteller**.
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

**Never assume. Ask.** Use only what the creator said, the files they gave
you and what Venus measured. Do not fill gaps with your own guesses: not the
topic or theme, not who it's for, not the length, the shape, the music, the
look, which part of a reference they mean, or what a shot is about. When
something you need is missing, ask one short question, or offer two or three
choices and recommend one. Keep measured facts (cut times, shot lengths, the
beat, loudness, colour numbers) apart from guesses (what a shot shows, what kind
of shot it is): say which is which, and check a guess against the picture
before you rely on it. If you can't tell, say "I can't tell" and ask.

**Brand kit first.** If the creator has a brand kit (`alvenus brand show`, or
"brand" in the storyboard), every colour comes from it. At the start of a new
video, say once that you'll use their kit and ask if this one should differ;
then don't ask again. Suggest a change only when the kit would hurt the video
(the check says "brand-contrast"). Save a new kit with
`alvenus brand set --colour NAME=#RRGGBB ... --background NAME --text NAME --accent NAME`.
A colour they approve for one video goes in the storyboard's `"brand_exceptions"`.
Their **fonts** go in the kit too (`"fonts": {"heading": "fonts/Their-Heading.ttf",
"body": "fonts/Their-Body.ttf"}`, or `alvenus brand set ... --heading-font FILE
--body-font FILE`): every title, caption, label and chart then uses them. A font
file travels with the kit; a font name only works where it is installed, and Venus
says plainly when it had to fall back to its own.
**No kit?** Ask the creator, once, which colours they'd like for this video
(their own words: "warm and calm", "black, white and one red"). Turn the answer
into colours, show them, and use them; offer to save them as their kit with
`alvenus brand set` so next time nobody has to ask. If they have no preference,
use the chosen look's own colours and skip every brand check.

**Watch every reference before the first draft.** When the creator gives
references, read each one (`alvenus read`, look at its sheet) before you plan
anything, and tell them in a line per reference what you are taking from it
(its rhythm, its opening, its colour...). Never start a draft from a reference
you haven't read.

**On feedback, change only what they flagged.** Keep everything they didn't
mention (pace, voice, music, pictures, timing) exactly as it was. If a fix would
touch something else, say so and ask first. When they say a part is fine, it is
locked.

**Read [CRAFT.md](CRAFT.md) first.** It is the craft guide: how a good editor
reads a cut, gives notes and respects the creator's taste. Everything below is
how Venus helps you follow it.

## 0. At the start of every session: is Venus up to date?

Run `alvenus update --check --json` once, before anything else. It answers in
a second (and quietly says so when it is offline):

- `"update": false` → say nothing and carry on.
- `"update": true` → tell the creator in one line, using the notes in
  `whats_new` ("Venus 0.9.1 is ready: faster previews, a new paper texture.
  Install it now?"). **Install only after they say yes**: `alvenus update --yes --json`.
  Venus backs up the current version first, starts the new one to check it,
  and puts the old one back on its own if it does not start (`"rolled_back": true`
  in the answer: tell them nothing changed). Their videos and node files are never touched.
- They regret it later → `alvenus update --rollback`.

(Studio, which is in preview, shows the same note in its header with an Update button.)

Then run `alvenus taste --json` once: what this creator usually leaves as it is
(`quiet`), the advice they usually take (`takes`) and what they like (`likes`:
styles, kinds, openings). Shape your suggestions by it; don't argue again for
something they keep setting aside. It lives only on their computer.

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

### When they want it cut like one or more references (`alvenus read`, `alvenus blend`)

`study` gives averages. When the person wants the *same* edit (the rhythm of
this reel, the flashes of that one, its ending), read each reference shot by
shot instead:

```sh
alvenus read ref1.mp4 ref2.mp4
```

For each reference it writes three files beside it:

- `ref1.read.md`: the whole clip in one line, its parts in plain words (a
  strobe open of 2-frame shots speeding up, a steady middle, a slowing end), the
  music (tempo, how many cuts land on the beat, half-beat or quarter, the loud
  hits, the silences), the ending, the colour, and a table of every shot: its
  length in frames, what it is (white or black flash, negative of the shot
  before, subject small on a plain colour, line drawing, blueprint, chalk, black
  and white, poster, colour pop, dots, light burst, fade, dissolve), what is in it
  and how close (CLIP, free and local), its light and colours, and how the camera
  moves.
- `ref1.shots.jpg`: every shot as a picture with its number, time, length and
  what it is, under a timeline of the cuts against the beat and loudness. **Look
  at it.** The measurements are good, not perfect: you are the one who checks
  them against what you see, and you correct them in your own words.
- `ref1.read.json`: the same, for a recipe.

With two or more references it also writes `references.compare.md` (side by
side) and `references.recipe.json` (a starting recipe).

What is **measured** (cuts, shot lengths, the beat, light, colour) is exact. What is
**seen** (what kind of shot it is, what's in it) is the model's best guess, shown
with how sure it is; "unclear" means it couldn't tell. Check every guess you use
against the picture, and never build a plan on one you haven't checked.

**Comprehension is the job.** Before proposing anything, tell the person what
you understood, part by part, in their language: "Reference 2 opens with three
seconds of two-frame shots: a tiny figure on white, then its negative on black,
flipping every two frames, with light bursts every half beat. It slows into
four longer shots and ends on a white flash and black." Then say what you
would take from each and why, and ask the one question that matters if their
ask is unclear (which part they love, how long, which comes first). Do not
average references together; take parts.

Then write the recipe (edit the starter):

```json
{"refs": {"A": "ref1.read.json", "B": "ref2.read.json"},
 "parts": [{"ref": "B", "from": 0, "to": 5.3, "take": ["rhythm", "effects", "light", "content"]},
           {"ref": "A", "from": 13.0, "to": 17.8, "take": ["rhythm", "effects"]}],
 "look": "A", "shape": "9:16", "length": null, "on_beat": true}
```

- `parts` play in this order; `from`/`to` are seconds in that reference (use the
  part boundaries from the reading).
- `take`: `rhythm` (shot lengths, counted in the reference's beats and replayed
  on the beats of the new song, doubled or halved to keep the feel at a new
  tempo), `effects` (each shot redone as what it was: flashes, negatives,
  drawings, dots, a small subject on its plain colour...), `light` (bright and
  dark shots in the same places), `content` (picks the moment in their clips
  that shows the same kind of thing: a hand for a hand, stars for stars).
- `look`: whose colour to grade toward (the starter leaves it empty: ask); `length`: squeeze or stretch the whole
  thing to N seconds; `on_beat: false` keeps the reference's own timing exactly.

Plan it, which renders nothing:

```sh
alvenus blend recipe.json --clips their-clips/ --music song.mp3 --out reel.mp4
```

It writes `reel.blend.jpg` (each reference shot above the shot of theirs that
answers it, with the effects already on), `reel.blend.md` (where every shot
comes from and why) and `reel.montage.json`. Look at the sheet, fix what's
wrong in the plan (a better clip for a shot, a part dropped), **show the person
the sheet and wait for their yes**, then render with
`alvenus montage --plan reel.montage.json`.

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

### Trailers, video essays, interviews, data and the wide band

- **Trailer** (preset `trailer`, or `make --template trailer`): storyboard
  `"slam"` cards: a huge credit word slams in cropped by the frame over
  `"texture"` `newsprint`, `red` (paint), `charcoal` or `paper`, a light
  sweeps across, then it settles small under `"small"` ("From the writer
  of"); a black brush stroke wipes it (`"wipe": false` to hold it). End on a
  `"date"` card (a date or line over red smoke, `"small"` under it). Booms,
  risers and a braam come with the cards. Credits are real names the
  creator gave you, never invented ones.
- **Video essay** (preset `video-essay`): a `"scramble"` card shows one key
  word whose letters swap for symbols and glitch, then land on `"to"` in a
  black stamp (TAXES -> F€$Y£, Trust -> Nobody). One per idea that turns;
  more than two in a video wears thin.
- **Interviews** (`cut`): `--caption-style bracket` shows one word at a time
  in small mono brackets at chest height (preset `interview-wall`);
  `--caption-style keyword` sets each phrase small with its key word large in
  gold italic serif above (preset `podcast-gold`; a highlighted word wins,
  else the longest real word). `--behind 3="IDEAL MOMENT"` stacks big red
  condensed words on the wall behind the speaker for line 3: the person is
  cut out and stays in front (a free person model is fetched once). Use it
  on the one line that carries the talk, not every line.
- **Data explainer** (preset `data-explainer`): a `"line_chart"` can carry
  more lines to compare (`"lines": [{"name": "Rent", "values": [...]}]`, one
  value per point, and `"name"` for the first line, shown in a key), a shaded
  rise-over-run (`"slope": {"from": 0, "to": 2, "label": "What is slope?"}`)
  and short notes pinned to points (`"notes": [[3, "same hours"]]`). The last
  map pin keeps pulsing. Only the creator's numbers, never made-up data.
- **The wide band** (preset `wide-band`, or `montage --band`): the film as a
  thin ultra-wide strip across black (4.74:1, even on a vertical frame),
  `--band-words "Speak louder than words.|But it feels so pure."` spreads
  each line word by word across the band through the film, `--band-end
  "Bali|Lives forever in the heart"` closes on a serif card.
- **Sound effects pack**: `alvenus sfx --out folder` writes every sound
  (whoosh, pop, hit, riser, boom, braam, snap, glitch, tick, swell, shutter)
  as a WAV the creator can use anywhere; made by Venus, free to use.

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
- **Music** sets the mood. **Ask for the creator's own music first.** If you
  ever use something they didn't give (a Venus sound, a placeholder), say so
  plainly. Read it before you cut: `alvenus listen song.mp3 --voice voice.wav`
  gives its tempo, bars, sections (where it lifts and drops), hits and the
  moments it stops dead, and where the voice speaks and pauses. Place moments
  on those, never on a guess.
- **Under a voice** the music sits well below it (12 dB down while someone
  speaks; `--music-duck` / storyboard `"music_duck"` only if the creator asks for
  more or less). It eases down before each phrase and back up after it, always in
  a gap, never on a word; a short breath keeps it down. Raise `--music-lufs`
  (e.g. -18) for an energetic piece, lower it (-26) for an intimate one. Only use
  music the creator has the right to use.
- **The mix is measured, line by line.** Before the final mix is written, Venus
  measures every spoken phrase against the music under it. Wherever the voice is
  less than 10 dB over the music, the music goes further down for that stretch
  (`--voice-gap` / `"voice_gap"`, 0 = off). The notes say how close the closest
  line came. When the creator set the music level themselves and Venus had to go
  further down, tell them, and why.
- **Sound effects: fewer, varied, heard.** Venus never stacks two effects within
  half a second (the stronger one stays) and allows at most two small ones
  (pops, ticks, snaps) in two seconds. A sound used again is slightly retuned,
  so a run of them never sounds copied. Each effect is measured against what
  plays under it and lifted until it is heard (never more than 9 dB). Put
  effects on the moments that matter, not on every graphic.
- **Music that has to run longer than the song** repeats on a bar line, with a
  short blend, from the bar whose loudness best matches, never by jumping back
  to the top. The notes list each join and flag any where the level still
  changes; listen to those.
- **Never split joined words.** Inside a phrase the words run together; Venus
  only cuts in real quiet and takes back any cut that would split two words.
  When you place voice pieces yourself, cut only in the gaps `alvenus listen`
  lists.
- **Title** sits over the opening seconds, so the hook still starts at once. Keep
  it to a few words. **End card**: a short call to action ("Follow for part two").

### Captions

- **Short cards that follow the voice.** A caption card holds 2 to 6 words, breaks
  where the voice pauses or punctuation ends a thought, never leaves one word
  alone, and never ends on a joining word ("the", "of"): that word goes with
  what it joins. In the `keyword` style there is one big word and at most one
  small row; the small row gets smaller before it would ever wrap. The creator
  can choose other limits (`--caption-words 3-5`, `"caption_words": "3-5"`).
- **In time with the voice** (`make` with a `"voiceover"`). Each caption word
  appears when it is said, and cards break where the voice pauses. Venus listens
  to the voice under each scene and lays the words on its syllables (about a
  tenth of a second on a clean voice; less sure when loud music is mixed in).
  When you have word times from any transcriber, give them for exact timing:
  `"voice_words": "words.json"` (a list of `[start, end, word]`, seconds into
  the voiceover) and `"voice_words_at": 14.2` (where the voiceover's 0 sits in
  the video). Caption words are matched to the spoken words in order, so a
  caption may drop or add a word. One scene by hand: `"caption_times": [0.2,
  0.6, ...]` (one start per word, seconds from the scene's start).
  `"caption_sync": false` spreads the words evenly as before.
- **Each card sits where the picture leaves room.** Venus reads the frame under
  every card and puts the words where it is calm (little detail, no skin tone),
  so they don't cover a face or the subject. Within a shot the card stays put; it
  moves when the shot changes; when two spots are nearly as good, it picks the
  one the last shot didn't use, so the words don't sit in one place all video.
  It measures detail and skin tone, it does not recognise faces: if a card lands
  badly, set that scene's `"caption_place"` ("top", "bottom-left", ...). For
  captions always at the bottom: `--fixed-captions` / `"caption_placement": "fixed"`.
- **Clean type.** Cards stay inside the safe area (on tall videos: clear of the
  app's caption area at the bottom and its buttons on the right). Rows are even,
  and the small row scales with the big word. The self-review checks every card
  for this after the render.
- In Studio the creator can edit each caption card: its words, the big word
  (`"caption_big"`) and where it sits. What they set always wins.

## 6. Steer and re-cut

**What the creator approved stays as it was.** When they ask for a fix, change
only what they named. Example: they say "the opening repeats a shot", so swap
only the repeated shots for unused clips of the same look. Don't restyle,
rebuild or "improve" anything else. Venus keeps a copy of what was approved.
`alvenus check` lists every approved part that has changed since
(`approved-changed`), and `alvenus approve` lists them again. Put back any
change the creator didn't ask for. If you think something else should change,
ask first.

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

Every finished video (cut, montage, make; never a --draft) ends with a small
"Made with Venus" mark in the bottom corner for its last two seconds. It is on
by default. If the creator asks for it gone, ask whether they mean this video
or every video, then: `--no-mark` on the command, or `"venus_mark": false` in
the storyboard (the Video settings switch in Studio), or `alvenus mark off` for
every video on this computer (`alvenus mark on` brings it back). Never turn it
off unless they ask.

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
in one line, then approve on their yes. (In Studio, which is in preview, the creator
pressing Render or a scene's play button is their approval of what is on screen.)

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

It also reads the cut by the craft guide ([CRAFT.md](CRAFT.md)): an opening
question the ending never answers, "3 reasons" with only 2 delivered, a cut that
lands mid-sentence, a point made twice, a word like "REM" the viewer may not know,
"he" before we know who, the same shot held 8 s or more, a scene that serves
neither the promise nor its neighbours. It also guards the setup: the point
said in the first third before it is earned (`payoff-early`), an answer to a
question the video never asked (`answer-unasked`), and a story that opens on
what happened next (`setup-missing`). A colour that isn't in the brand kit is
weak (`off-brand`). The same shot used again within 8 seconds is weak
(`repeat-shot`): use an unused clip of the same look, or mark a deliberate
callback `"repeat_ok": true`. After the render, the self-review also compares the
shots themselves and flags two that look the same close together.

**Does each picture show what is said over it?** `alvenus fit sb.json` measures
how well every scene's picture matches its words (the same local model as the
footage search) and points out the weakest matches. Once the model is on the
computer, `alvenus check` does this too (`picture-off-line`). It is a measurement
to look at: a deliberate contrast between word and picture can be the point.
Show the creator the flagged scenes; don't swap a picture without their yes.

**The same person looks the same.** In a story, tag who and what is in each
picture: `"cast": ["father", "daughter (young)", "watch"]`. Then
`alvenus cast sb.json` lays each one's pictures side by side on
`sb.cast.jpg` and measures how alike they are; a picture flagged "may look
different" is a measurement to check, not a verdict. Look at the sheet, swap
any picture that is not the same person or object, and show the sheet with the
board. The check asks for tags (`cast-untagged`) when a story follows people.

After every render the self-review also checks **pace**: a lone shot too quick
to take in (under 0.4 s between longer shots), and stretches where a video cut
to the beat drifts off it. Fix those moments only. Every finding names its moment
(`at 0:15-0:18`). The board opens with **The promise** (`brief.promise`, else
`point`) and **One question**: ask the creator that question first, not the
whole list. When the first 3 seconds are weak it lists **up to 3 better
openings** from their own scenes, each with a reason: offer them, let them pick,
then `alvenus taste pick opening-KIND` (number, turn, picture, flash-forward).
The board shows only the 3 notes that matter most (`--all` for every one);
`alvenus check FILE --json` gives you everything, with each finding's `code`.

**Learning their taste.** Venus learns on its own: a note gone at the next check
was taken; notes still standing when they approve were set aside. When the
creator says no to a note in words, record it: `alvenus taste aside CODE --why
"their words"` (or `keep CODE` when they take one). A kind of note set aside at
least twice, more often than taken, goes quiet for this creator. Notes about
facts, empty scenes and missing pictures never go quiet. `alvenus taste forget`
starts over.

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
   timeline and quote scenes on a background is a complete video.
   **Pictures without footage.** Any picture slot (`file` of an image, clip,
   title or text scene, or `left`/`right` of a split) can name a drawing instead
   of a file, drawn in the video's own look (cream on dark, ink on paper with a
   hand-made wobble for vox-paper, archive and sepia, ink on grey grid for mono):
   `"icon:battery"` (one icon on an accent shape), `"icon:device-mobile+snowflake"`
   (a main icon with a badge: the phone, and the cold), `"icon:bulb>pencil>rocket"`
   (steps with arrows), `"icon:car/bike"` (one against the other),
   `"icon:sun,cloud,cloud-rain"` (a row), or `"scene:city"` (a small drawn scene:
   `alvenus icons scenes` lists them). 5,491 free icons are bundled (Tabler, MIT):
   find names with `alvenus icons search WORDS`, look at them with
   `alvenus icons sheet NAMES --out sheet.png`, try one with
   `alvenus picture SPEC --style STYLE --out p.png`. Pick the picture that shows
   the scene's ONE idea literally (a phone and a snowflake, not "technology");
   `alvenus check` draws every one onto `NAME.pictures.jpg`: show it beside the
   board so the creator sees the pictures before saying yes. Footage-free
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

### How-to videos (`"kind": "how-to"`)

A how-to teaches one task. Show the result first, then what the viewer needs,
then each step, and end on it working.

- **Explain what you name.** Each thing the viewer needs (a program, an account,
  a file) also gets what it is and where to get it.
- **Show the real place.** Record or screenshot the actual site, page and button
  the viewer will use. Don't use a mock-up unless the real one doesn't exist yet.
  The check flags stand-ins (`stand-in`).
- **Show the real path.** Go there the way the viewer would: search, the site,
  the menu, the page, the button. Don't cut straight to the last page
  (`no-path`).
- **Keep other ways apart.** If a step can also be done another way ("or ask
  your AI"), give it its own scene with `"alternative": "Another way"`. It gets
  a clear label in the corner, and the main path stays simple
  (`other-way-mixed`).
- **Screen recordings move.** In a how-to every clip is treated as a screen
  recording (`"screen": true` anywhere else, `"screen": false` to turn it off).
  The camera follows the activity: it pushes in on the cursor or the text
  being typed, eases back out when the whole page changes, and holds still when
  nothing happens. Steps slide on instead of dissolving. It follows changes on
  the screen; it does not read what the screen says.

### Three directions, before anything is made (`alvenus directions`)

Once the storyboard passes the check, offer the creator three directions:
`alvenus directions FILE` lays the same story out as **A** their look, **B** the
opposite energy (calm and designed if theirs is punchy, quick and bold if it is
calm) and **C** tighter (each scene only as long as its words need, one
optional scene gone). It writes `NAME.directions.jpg` (frames of the hook, the
middle and the payoff of each, the reason and the story at a glance) and
`NAME.directions.md`. Show them the page, say in one line which you would pick
and why, and use their choice: `alvenus directions FILE --pick B`. The picked
storyboard needs their yes again before it is made. In Studio this is the
**3 directions** button (Undo brings back what they had).

The story check (`alvenus check`) also asks: does the hook pull (a number, a
"but", a question or "you"; not a plain statement), does it give the ending
away, does any caption say two things, is the last line short (8 words or
fewer), and does it sit long enough to land. The board opens with the story at
a glance: hook, one idea per scene, the turn, the ending.

### Ideas typed in Studio (`alvenus ideas`)

> **Studio is in preview and not offered to creators yet.** Work with them through the
> conversation and the commands. Don't open Studio or suggest it unless the creator asks
> for it by name.

The creator can also start in Studio: `alvenus studio` with no file opens a
welcome page with a **Describe your video** box (and kind, length, shape and
look to pick). Venus writes the brief, lays the video out by the story recipe
(one empty scene per beat, its `_job` written on it) in a new folder, opens it
in Studio and puts the idea in an inbox for you:

1. When the creator says "Venus has a new idea for you" (or at session start),
   run `alvenus ideas`. It prints each waiting idea with its files and steps.
   (`alvenus ideas --wait` waits for the next one.)
2. Fill `brief.json` (audience, point, mood; fix kind, seconds, aspect or look
   if the idea says otherwise; ask the creator only what you can't tell), then
   `alvenus ideas start ID`. Studio shows "your AI is writing".
3. Write the scenes **one at a time** with `alvenus nodes set FILE
   sceneN.words.text="..."` (a picture: `sceneN.type=image
   sceneN.picture.file="icon:..."`). Each one appears in the creator's strip
   as you go, so they watch the video take shape.
4. `alvenus check FILE` until it passes, then `alvenus ideas ready ID`, and tell
   the creator it is ready to read. **Never render it yourself**: the creator
   reads it in Studio and presses Render. Render runs the story check first and
   shows anything weak, with "Make it anyway" as their choice.

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

> **Studio is in preview and not offered to creators yet.** Work with them through the
> conversation and the commands. Don't open Studio or suggest it unless the creator asks
> for it by name.

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
   Studio shows the creator whether you are connected (you read the descriptions
   in the last 3 minutes); if not, it offers them a message to paste to you.

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
- Ask one question that unlocks the edit, not ten notes; point to the exact moment;
  suggest a fix and let the creator decide (CRAFT.md).
- Say what you are unsure about. A confident wrong cut costs the creator more than
  a question.
- Brand kit first; watch every reference before the first draft; on feedback change
  only what was flagged; ask for the creator's music before using any other.
- What the creator approved stays locked: a fix changes only what they asked for.
- Every check above is a measurement. Report what it measured and say what it
  can't know (it measures detail, not faces; changes on a screen, not what the
  screen says). Never present a measurement as certain.
- Never assume a topic, theme, audience, length, look or music the creator didn't give.
  Ask, or offer choices. A guess presented as a fact is the worst mistake you can make.
