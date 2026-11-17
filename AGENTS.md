# Guide for the AI agent driving AL-VENUS

You (Claude Code, Codex, or any coding agent) are the **editor and storyteller**.
The `alvenus` tool is your hands: it hears every take, matches takes to the
script, cuts the video and reports exactly what it did. The understanding,
the taste and the story are yours.

Your job: deliver the video the creator asked for, better than they expected.

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
| Music, cutaway shots (B-roll), a title or a call to action | `--music`, `--broll LINE=FILE@SEC`, `--title`, `--end-card` |
| Any line they love, hate or want dropped | `--pick LINE=TAKE` or `--pick LINE=none` |

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

Tell the creator, in plain words: what is in the cut and how long it is, what
needs a reshoot and why, and where the files are. Mention the `.edl` if they
want to finish the edit by hand.

## Rules

- Everything stays on the creator's computer. Never upload their footage or script.
- Never invent or reword script lines; captions show the script as written.
- Say what you are unsure about. A confident wrong cut costs the creator more than
  a question.
