# Venus add-ons

Add-ons let anyone add something new to Venus without touching its core. They are
**data files, never code**: Venus reads them, checks every value against what it
already knows, and skips a bad one with a note (`alvenus suggest --addons`).

- `styles/NAME.json`: a style pack, used like any other (`make --style NAME`,
  `cut --preset NAME`). Example: [examples/addon-style.json](../../examples/addon-style.json).
  Keys: `about` and `by` (required), and any of aspect, look, accent, transition,
  transition_seconds, title_style, background, design, captions, caption_style,
  letterbox, lower_third_style, quote_style, max_pause, beat, scene_beat, music_lufs, voice.
- `recipes/NAME.json`: a story recipe for `alvenus storyboard` (a new kind of
  video). Example: [examples/addon-recipe.json](../../examples/addon-recipe.json).
  `beats` is a list of `[beat, share of the length, [scene forms], what it must do]`,
  starting with a `hook` and ending with a `payoff`.

How add-ons reach Venus: see [How ideas become Venus features](../../CONTRIBUTING.md).
Share one with `alvenus suggest`, or a pull request that only adds a file here.
Anamorph Labs reviews it, the automatic checks run on it, and it is credited to
the name in `"by"` when it ships.
