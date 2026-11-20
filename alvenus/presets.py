"""Style packs. A pack is a bundle of settings an editor would reach for
on a given kind of video; anything typed on the command line or set in a
plan still wins. They are first drafts, to be tuned on real reference videos."""

from __future__ import annotations

PRESETS: dict[str, dict] = {
    "reels-punchy": {
        "about": "Reels / TikTok / Shorts: vertical, tight pauses, word-pop captions, punchy colour, whip into new scenes.",
        "aspect": "9:16", "captions": True, "caption_style": "pop", "max_pause": 0.35, "beat": 0.12,
        "scene_beat": 0.45, "look": "punchy", "transition": "whip", "transition_seconds": 0.3, "music_lufs": -20.0,
        "background": "orbs", "title_style": "stamp", "accent": "#FFD23F",
    },
    "cinematic-doc": {
        "about": "Short documentary / brand film: wide, room to breathe, filmic grade, dips to black between scenes.",
        "aspect": "16:9", "captions": True, "caption_style": "classic", "max_pause": 1.0, "beat": 0.45,
        "scene_beat": 1.4, "look": "film", "voice": "clean", "transition": "dip", "transition_seconds": 0.8, "music_lufs": -24.0,
        "background": "spotlight", "title_style": "reveal", "accent": "#E8D9B0",
    },
    "explainer": {
        "about": "Explainer (Vox-like): wide, brisk but clear, word-pop captions, clean grade, crossfades between ideas.",
        "aspect": "16:9", "captions": True, "caption_style": "pop", "max_pause": 0.5, "beat": 0.2,
        "scene_beat": 0.7, "look": "natural", "transition": "crossfade", "transition_seconds": 0.4, "music_lufs": -25.0,
        "background": "grid", "title_style": "block", "accent": "#FFD23F",
    },
    "podcast-clip": {
        "about": "Podcast or interview clip for social: vertical, natural pauses kept short, warm grade, straight cuts.",
        "aspect": "9:16", "captions": True, "caption_style": "pop", "max_pause": 0.6, "beat": 0.2,
        "scene_beat": 0.6, "look": "warm", "transition": "cut", "music_lufs": -26.0,
        "background": "dark", "title_style": "type", "accent": "#FF8A5B",
    },
    "calm-story": {
        "about": "Calm personal story for the Instagram feed: 4:5, reflective pauses kept, cool grade, slow crossfades.",
        "aspect": "4:5", "captions": True, "caption_style": "classic", "keep_pauses": True, "beat": 0.5,
        "scene_beat": 1.6, "look": "cool", "voice": "clean", "transition": "crossfade", "transition_seconds": 1.0, "music_lufs": -24.0,
        "background": "aurora", "title_style": "track", "accent": "#9FD3E6",
    },
    "editorial": {
        "about": "Magazine-style essay: wide, measured, warm grade, ink-wash scene changes, titles revealed by an accent block.",
        "aspect": "16:9", "captions": True, "caption_style": "classic", "max_pause": 0.7, "beat": 0.3,
        "scene_beat": 1.0, "look": "warm", "transition": "ink", "transition_seconds": 0.9, "music_lufs": -25.0,
        "background": "ink", "title_style": "block", "accent": "#E4572E",
    },
    "dreamy": {
        "about": "Travel or memory piece: 4:5, slow, filmic grade, light leaks washing between scenes, titles rising into view.",
        "aspect": "4:5", "captions": True, "caption_style": "classic", "keep_pauses": True, "beat": 0.5,
        "scene_beat": 1.5, "look": "film", "transition": "leak", "transition_seconds": 1.1, "music_lufs": -23.0,
        "background": "aurora", "title_style": "reveal", "accent": "#F6C28B",
    },
    "hype": {
        "about": "High-energy promo or drop: vertical, very tight, word-pop captions, glitch cuts, titles that slam in.",
        "aspect": "9:16", "captions": True, "caption_style": "pop", "max_pause": 0.25, "beat": 0.08,
        "scene_beat": 0.3, "look": "punchy", "transition": "glitch", "transition_seconds": 0.35, "music_lufs": -18.0,
        "background": "orbs", "title_style": "stamp", "accent": "#3DF5C8",
    },
    "mono-editorial": {
        "about": "Greyscale editorial reel: grey grid paper, print details, black-and-white photos, one lime accent, words one at a time in mixed type.",
        "aspect": "9:16", "captions": True, "caption_style": "pop", "max_pause": 0.4, "beat": 0.15,
        "scene_beat": 0.5, "look": "natural", "transition": "blur", "transition_seconds": 0.35, "music_lufs": -22.0,
        "background": "dark", "title_style": "track", "accent": "#D4F01E", "design": "mono",
        "learned_from": "reference board, pins 3, 5, 6, 8, 31, 32, 34, 40, 52",
    },
    "vox-paper": {
        "about": "Vox-style paper collage: crumpled paper, torn photo prints with tape, colour shapes and paint, heavy captions with a highlighter.",
        "aspect": "16:9", "captions": True, "caption_style": "pop", "max_pause": 0.5, "beat": 0.2,
        "scene_beat": 0.7, "look": "natural", "transition": "slide", "transition_seconds": 0.3, "music_lufs": -24.0,
        "background": "dark", "title_style": "block", "accent": "#F2C230", "design": "paper",
        "learned_from": "reference board, pins 14, 18, 19, 23, 26, 42, 53, 55, 58, 63",
    },
    "talk-studio": {
        "about": "Talking head as a produced show: dark designed set, the speaker in a window beside the line's words or graphic on chosen lines, full frame for the hook and payoff, word-pop captions.",
        "aspect": "16:9", "captions": True, "caption_style": "pop", "max_pause": 0.45, "beat": 0.18,
        "scene_beat": 0.6, "look": "natural", "transition": "cut", "music_lufs": -25.0,
        "background": "dark", "title_style": "track", "accent": "#7FA7E0", "talk": True,
    },
    "talk-paper": {
        "about": "Talking head as a printed page: light grey editorial paper with a fine grid, the speaker in a window beside the words in ink and serif italic, one accent colour.",
        "aspect": "16:9", "captions": True, "caption_style": "pop", "max_pause": 0.45, "beat": 0.18,
        "scene_beat": 0.6, "look": "natural", "transition": "cut", "music_lufs": -25.0,
        "background": "dark", "title_style": "track", "accent": "#2B4A78", "talk": True, "talk_set": "paper",
    },
    "documentary": {
        "about": "Documentary with interviews: wide cinema bars, muted filmic grade, serif name tags and chapter titles, place-and-time stamps, slow dips between scenes.",
        "aspect": "16:9", "captions": True, "caption_style": "classic", "max_pause": 1.0, "beat": 0.45,
        "scene_beat": 1.4, "look": "doc", "voice": "clean", "transition": "dip", "transition_seconds": 0.9, "music_lufs": -25.0,
        "background": "dark", "title_style": "chapter", "accent": "#C9A86A", "letterbox": "2.39", "lower_third_style": "doc",
    },
    "travel-reel": {
        "about": "Travel reel: vertical, warm sunny grade, cut to the beat, arrival titles in huge condensed capitals with the country written by hand, light leaks, camcorder date.",
        "aspect": "9:16", "captions": True, "caption_style": "pop", "max_pause": 0.35, "beat": 0.12,
        "scene_beat": 0.45, "look": "travel", "transition": "leak", "transition_seconds": 0.6, "music_lufs": -18.0,
        "background": "aurora", "title_style": "place", "accent": "#FFB347",
    },
}


def defaults(name: str) -> dict:
    if name not in PRESETS:
        raise SystemExit(f"--preset {name!r}: choose one of {', '.join(PRESETS)}")
    return {k: v for k, v in PRESETS[name].items() if k not in ("about", "learned_from")}


def pack(name: str | None, *keys: str) -> dict:
    """Just the given settings of a pack (for montage and make, which have
    fewer knobs than cut)."""
    if not name:
        return {}
    d = defaults(name)
    return {k: d[k] for k in keys if k in d}


def describe() -> str:
    return "\n".join(f"  {n:14} {p['about']}" for n, p in PRESETS.items())


def _learned() -> None:
    """Packs learned from the person's own reference videos (alvenus study --as NAME)."""
    try:
        from . import style
        from .learnstyle import load_user_packs

        load_user_packs(PRESETS, style.LOOKS)
    except Exception:  # a broken pack file must never stop Venus starting
        pass


_learned()
