"""Starting styles. A preset is a bundle of settings an editor would reach for
on a given kind of video; anything typed on the command line or set in a
plan still wins. They are first drafts, to be tuned on real reference videos."""

from __future__ import annotations

PRESETS: dict[str, dict] = {
    "reels-punchy": {
        "about": "Reels / TikTok / Shorts: vertical, tight pauses, word-pop captions, punchy colour, whip into new scenes.",
        "aspect": "9:16", "captions": True, "caption_style": "pop", "max_pause": 0.35, "beat": 0.12,
        "scene_beat": 0.45, "look": "punchy", "transition": "whip", "transition_seconds": 0.3, "music_lufs": -20.0,
    },
    "cinematic-doc": {
        "about": "Short documentary / brand film: wide, room to breathe, filmic grade, dips to black between scenes.",
        "aspect": "16:9", "captions": True, "caption_style": "classic", "max_pause": 1.0, "beat": 0.45,
        "scene_beat": 1.4, "look": "film", "transition": "dip", "transition_seconds": 0.8, "music_lufs": -24.0,
    },
    "explainer": {
        "about": "Explainer (Vox-like): wide, brisk but clear, word-pop captions, clean grade, crossfades between ideas.",
        "aspect": "16:9", "captions": True, "caption_style": "pop", "max_pause": 0.5, "beat": 0.2,
        "scene_beat": 0.7, "look": "natural", "transition": "crossfade", "transition_seconds": 0.4, "music_lufs": -25.0,
    },
    "podcast-clip": {
        "about": "Podcast or interview clip for social: vertical, natural pauses kept short, warm grade, straight cuts.",
        "aspect": "9:16", "captions": True, "caption_style": "pop", "max_pause": 0.6, "beat": 0.2,
        "scene_beat": 0.6, "look": "warm", "transition": "cut", "music_lufs": -26.0,
    },
    "calm-story": {
        "about": "Calm personal story for the Instagram feed: 4:5, reflective pauses kept, cool grade, slow crossfades.",
        "aspect": "4:5", "captions": True, "caption_style": "classic", "keep_pauses": True, "beat": 0.5,
        "scene_beat": 1.6, "look": "cool", "transition": "crossfade", "transition_seconds": 1.0, "music_lufs": -24.0,
    },
}


def defaults(name: str) -> dict:
    if name not in PRESETS:
        raise SystemExit(f"--preset {name!r}: choose one of {', '.join(PRESETS)}")
    return {k: v for k, v in PRESETS[name].items() if k != "about"}


def describe() -> str:
    return "\n".join(f"  {n:14} {p['about']}" for n, p in PRESETS.items())
