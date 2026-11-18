"""Starter storyboards: four proven shapes of short video, ready to fill in.

Each one opens on a hook that lands inside the first two seconds (a bold
claim, a number or a promise), because that is where viewers decide to stay.
The words are an invented example on purpose: the person's own AI swaps them
for the real subject and keeps the shape. They need no footage, so each one
renders as it is; clips and photos can replace any scene later."""

from __future__ import annotations

TEMPLATES: dict[str, dict] = {
    "explainer": {
        "_about": "Explain one idea in about 30 seconds: a surprising claim, the question, three reasons, the proof, the takeaway.",
        "aspect": "16:9", "style": "explainer", "end_card": "Follow for the next one",
        "scenes": [
            {"type": "text", "text": "Your battery is lying.", "big_words": ["lying"], "seconds": 2, "_hook": "a short, bold claim; 5 words or fewer"},
            {"type": "title", "text": "How battery percentage really works", "seconds": 3},
            {"type": "list", "title": "It guesses from three things", "items": ["Voltage, which sags under load", "Heat, which hides charge", "Age, which shrinks the tank"], "seconds": 7},
            {"type": "compare", "left": {"title": "What it shows", "points": ["1% left", "About to die"]},
             "right": {"title": "What is there", "points": ["Often 5% more", "A safety margin"]}, "seconds": 6},
            {"type": "line_chart", "points": [["New", 100], ["1 year", 92], ["2 years", 83], ["3 years", 75]], "title": "Real capacity over time", "seconds": 5},
            {"type": "text", "text": "Charge to 80%. It lasts years longer.", "big_words": ["80%"], "seconds": 4},
        ],
    },
    "story": {
        "_about": "Tell a small true story: start in the middle of the moment, go back to how it began, rise, then land on what it meant.",
        "aspect": "16:9", "style": "cinematic-doc", "end_card": "Thanks for watching",
        "scenes": [
            {"type": "text", "text": "The first night, nobody came.", "big_words": ["nobody"], "seconds": 2.2, "_hook": "drop the viewer into the hardest moment"},
            {"type": "title", "text": "The Lantern Stall", "seconds": 3},
            {"type": "timeline", "items": [["1998", "One table, one lamp"], ["2005", "Ten regulars"], ["2024", "A queue every night"]], "title": "How it grew", "seconds": 6},
            {"type": "quote", "text": "I kept the lamp on anyway. Someone had to see it.", "who": "Mei, the owner", "seconds": 5},
            {"type": "stat", "value": "26", "label": "years, never a night off", "seconds": 3.5},
            {"type": "text", "text": "Keep the light on.", "big_words": ["light"], "seconds": 3},
        ],
    },
    "list": {
        "_about": "A top-5 countdown for vertical feeds: promise the payoff, count down from 5, recap all five at the end.",
        "aspect": "9:16", "style": "reels-punchy", "end_card": "Save this for later",
        "scenes": [
            {"type": "text", "text": "5 habits. #1 takes 10 seconds.", "big_words": ["10 seconds"], "seconds": 2.6, "_hook": "promise the best item so they wait for it"},
            {"type": "stat", "value": "#5", "label": "Lay out tomorrow's clothes", "seconds": 2.5},
            {"type": "stat", "value": "#4", "label": "Water before coffee", "seconds": 2.5},
            {"type": "stat", "value": "#3", "label": "Phone stays in another room", "seconds": 2.5},
            {"type": "stat", "value": "#2", "label": "Ten minutes of daylight", "seconds": 2.5},
            {"type": "stat", "value": "#1", "label": "Make the bed", "seconds": 2.5},
            {"type": "list", "title": "All five", "items": ["Make the bed", "Daylight", "Phone away", "Water first", "Clothes ready"], "seconds": 5},
        ],
    },
    "ad": {
        "_about": "A product ad: name the pain, show the product as the fix, prove it, give one clear action.",
        "aspect": "9:16", "style": "hype", "end_card": "Order today",
        "scenes": [
            {"type": "text", "text": "Cold coffee by 9 AM?", "big_words": ["Cold"], "seconds": 2, "_hook": "the viewer's own problem, as a question"},
            {"type": "title", "text": "Meet Glowmug", "seconds": 2.5},
            {"type": "compare", "left": {"title": "Any mug", "points": ["Cold in 20 min", "Reheat, again"]},
             "right": {"title": "Glowmug", "points": ["Hot for 3 hours", "Set it and forget it"]}, "seconds": 5},
            {"type": "stat", "value": "3 hrs", "label": "at your perfect temperature", "seconds": 3},
            {"type": "list", "title": "Why people love it", "items": ["One-tap temperature", "Charges on its coaster", "Dishwasher safe"], "seconds": 5},
            {"type": "text", "text": "Every sip, still hot.", "big_words": ["hot"], "seconds": 2.5},
        ],
    },
}


def describe() -> str:
    return "\n".join(f"  {k:10} {v['_about']}" for k, v in TEMPLATES.items())
