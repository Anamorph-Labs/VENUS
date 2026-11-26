# What's new in Venus

Each release, newest first, in plain words. `alvenus update --check` reads this file,
so keep the heading shape: `## VERSION (DATE)` and one `-` line per change.

## Coming in the next release
- Pages move like a designed film: words land as the voice says them, pages meet with a clean move instead of a dissolve, and a gentle camera looks at what is circled or stamped.
- Titles over footage take the page's serif in a video of pages, and shrink into the next page's card.
- A clip that would open on a stray frame of the shot before now starts at the cut.
- `alvenus stills` also makes a short moving preview of each scene.
- A plain cut followed by a blend no longer stops a build.
- `alvenus stills`: a finished still of every scene and one sheet, before anything is made.
- A light editorial page: serif words with one stressed word in the accent colour, a small label, and the picture as a card with a soft shadow.
- Prints that drop onto the page on the beat and pile up.
- A plain cut on any one scene, cropping a picture or clip, a font per scene, and music that cuts dead at a chosen moment.
- Terminal clips hide private text: the home folder, the account and computer names, and anything you name.
- Terminal recordings become sharp video clips: `alvenus terminal` reads a Mac `script -r` recording, an asciinema file or a Linux `script --timing` pair and draws the terminal at its real timing, long waits cut short.
- Installing Venus no longer prints licence warnings.
- Stamps, words crossed out and rewritten, and hand-drawn notes (underlines, circles, arrows) over any scene.
- A still print scanned by a line of light that lifts into a full-screen moving shot; a clip as a tilted card beside its words, shrinking in from full screen.
- Stills come alive: rain, snow, mist, drifting clouds, moving water and a slow 3D camera move.
- Light-trail cuts (`"transition": "trail"`), and music that starts muffled and opens out at the moment you choose (`"music_open"`).
- Venus never tells you how long something will take: it says what it is doing, and when it is done.
- Captions in time with the voice: in a video with a voiceover, each caption word appears when it is said (exactly, when you give word times with `"voice_words"`).
- A clean mix, measured on every line: the voice always sits at least 10 dB over the music, and Venus says how close the closest line came (`--voice-gap`, 0 to switch it off).
- Sound effects: fewer and varied. Never two stacked together, a sound used again is slightly retuned, and quiet ones are lifted until they're heard.
- A song shorter than the video now repeats on a bar line with a short blend, instead of jumping back to its start.
- Captions are short cards of 2 to 6 words that follow the voice, never leaving one word alone (`--caption-words` to choose).
- Each caption card sits where the picture leaves room, away from faces and busy detail, and moves when the shot changes (`--fixed-captions` to keep it at the bottom). On tall videos it stays clear of the app's buttons and caption area.
- Your own fonts in the brand kit, used for every title, caption, label and chart (`alvenus brand set --heading-font FILE --body-font FILE`).
- New checks: the same shot used twice close together, a picture that may not show what is said over it (`alvenus fit`), and captions that aren't clean (alone words, uneven rows, outside the safe area).
- What you approved stays as it was: a fix changes only what you asked for, and Venus lists every other change to an approved part.
- How-to videos: a camera that follows the cursor and typing on screen recordings, steps that slide on, a clear label for another way to do a step, and checks for mock-ups and for skipping the viewer's real path.
- A clip that ends before its scene does now holds its last frame instead of cutting the video short.
- Start by talking to your AI: open it in the Venus folder and tell it the video you want. Venus's visual editor (Studio) is resting in preview for now.
- Stack captions: the small rows hug the big word and stay within its width, and the row above and the row below can each be moved on their own.
- A new caption look, "stack": one big word with the rest of the line in small bold type above or below it, all on one edge (`caption_style: stack`, `caption_big` to choose the big word).

## 0.9.0 (24 Nov 2026)
- Trailers: credit words that slam in huge over old newsprint or red paint, settle small and are wiped off by a brush stroke, and a date card over red smoke, with booms, risers and a deep braam (`make --template trailer`).
- Video essays: a key word whose letters scramble and glitch before landing on what it really means (TAXES becomes F€$Y£).
- Interviews: big red words on the wall behind the speaker, who stays in front (`cut --behind`), plus two caption looks: one small [word] at a time, or the key word in large gold serif.
- Data explainers: a second line to compare, a shaded slope with its question, notes pinned to points, and a map pin that keeps pulsing.
- The wide band: your film as a thin cinematic strip across black, even on a vertical video, with words spread across it and a closing card.
- A free sound-effects pack: 11 sounds made by Venus, `alvenus sfx` writes them all as WAV files.
- Venus keeps itself up to date: `alvenus update` installs a new version with one yes, backs up the one you have, and puts it back on its own if anything goes wrong. Studio shows a note when a new version is ready.
- Pictures without footage: every scene can show a drawing in your video's own look, from 5,491 free icons (one icon, an icon with a badge, steps with arrows, one against the other) or 19 small drawn scenes (a city, a desk, the night sky...). Nothing is downloaded or generated by a paid AI.
- Describe your video in Studio: type the idea on the welcome page, Venus lays the story out at once, your AI writes each scene while you watch, and nothing is made until you press Render.
- Three directions for every idea: your look, the opposite energy and a tighter cut, each with frames and its story check, to pick from before anything is made (`alvenus directions`, or the 3 directions button in Studio).
- A sharper story check: does the hook pull you in, does any scene say two things, is the ending short and given time to land. The board opens with the story at a glance.
- The Venus craft guide (CRAFT.md): your AI reads a cut the way a good editor does, asks one question that unlocks the edit, points to the exact moment and lets you decide.
- The story check reads like an editor: the promise in one line, up to 3 better openings when the first 3 seconds are weak, an opening the ending never answers, "3 reasons" with only 2 given, cuts mid-sentence, a point made twice, the same shot held too long.
- Venus learns your taste on your computer: advice you keep setting aside goes quiet, openings come in the order you pick them (`alvenus taste`). Facts are always checked.
- Easier first steps: the installer ends with `alvenus studio`, and `alvenus` on its own shows where to start.
