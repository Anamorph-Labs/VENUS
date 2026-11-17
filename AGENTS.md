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

## 6. Steer and re-cut

Re-run `alvenus cut` with your changes. Speech is heard again each run, so batch
your changes into one re-cut where you can.

```sh
alvenus cut ... --pick 2=5 --pick 6=none --max-pause 0.4
```

## 7. Deliver

Tell the creator, in plain words: what is in the cut and how long it is, what
needs a reshoot and why, and where the files are. Mention the `.edl` if they
want to finish the edit by hand.

## Rules

- Everything stays on the creator's computer. Never upload their footage or script.
- Never invent or reword script lines; captions show the script as written.
- Say what you are unsure about. A confident wrong cut costs the creator more than
  a question.
