"""Credits for the people whose ideas shipped (for Anamorph Labs, not part of Venus).

    python tools/credits.py add --name "Asha R" --idea "Lyric overlay" --issue 42 --version 0.2.0 [--link URL]
    python tools/credits.py build

`add` records a contributor in community/contributors.json. `build` writes:
  CONTRIBUTORS.md                       the list on GitHub
  community/credits.html                a ready-to-paste section for the Anamorph Labs site
  community/thank-you-emails/<n>.txt    a draft thank-you email per new contributor, to read and send
Nothing is sent from here: emails are drafts for a person to send.
"""

from __future__ import annotations

import argparse
import html
import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "community" / "contributors.json"


def load() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8")) if DATA.exists() else {"contributors": []}


def add(a) -> None:
    if a.link and not re.fullmatch(r"https://[^\s\"'<>]+", a.link):
        raise SystemExit("--link must be a plain https:// address")
    d = load()
    d["contributors"].append({"name": a.name, "link": a.link or "", "idea": a.idea, "issue": a.issue,
                              "version": a.version, "date": date.today().isoformat(), "emailed": False})
    DATA.write_text(json.dumps(d, indent=2), encoding="utf-8")
    print(f"added {a.name}; now: python tools/credits.py build")


def build(_a=None) -> None:
    d = load()
    people = d["contributors"]
    md = ["# Contributors", "", "Venus is started by Anamorph Labs and built with ideas from these people. Thank you.", ""]
    for p in people:
        who = f"[{p['name']}]({p['link']})" if p.get("link") else p["name"]
        md.append(f"- {who}: {p['idea']} (Venus {p['version']}, #{p['issue']})")
    if not people:
        md.append("Be the first: see [How ideas become Venus features](CONTRIBUTING.md).")
    (ROOT / "CONTRIBUTORS.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    rows = "\n".join(
        f'    <li><strong>{(f"<a href={chr(34)}{html.escape(p["link"])}{chr(34)} rel={chr(34)}nofollow{chr(34)}>" + html.escape(p["name"]) + "</a>") if p.get("link") else html.escape(p["name"])}</strong>'
        f' &middot; {html.escape(p["idea"])} <span class="venus-v">Venus {html.escape(p["version"])}</span></li>' for p in people)
    (ROOT / "community" / "credits.html").write_text(
        '<section class="venus-contributors">\n  <h2>Built with the Venus community</h2>\n'
        "  <p>Venus is started by Anamorph Labs and grows with the people who use it. These ideas are now part of Venus.</p>\n"
        f"  <ul>\n{rows}\n  </ul>\n</section>\n", encoding="utf-8")

    out = ROOT / "community" / "thank-you-emails"
    out.mkdir(exist_ok=True)
    for p in people:
        if p.get("emailed"):
            continue
        slug = re.sub(r"[^a-z0-9]+", "-", p["name"].lower()).strip("-") or "contributor"
        (out / f"{slug}-{p['issue']}.txt").write_text(
            f"From: creative@anamorphlabs.com\nSubject: Your idea is now part of Venus\n\nHi {p['name']},\n\n"
            f"Thank you for suggesting \"{p['idea']}\". We built it into Venus, and it is out now in version {p['version']}.\n\n"
            "Your name is on the Venus contributors list and on the Anamorph Labs site. Venus is started by Anamorph Labs\n"
            "and grows with people like you, so thank you for helping it get better.\n\n"
            "If you have more ideas, we'd love to hear them.\n\nWarmly,\nAnamorph Labs\n", encoding="utf-8")
    print(f"wrote CONTRIBUTORS.md, community/credits.html and email drafts for {sum(not p.get('emailed') for p in people)} people")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a1 = sub.add_parser("add")
    for k in ("name", "idea", "version"):
        a1.add_argument(f"--{k}", required=True)
    a1.add_argument("--issue", required=True, type=int)
    a1.add_argument("--link")
    a1.set_defaults(func=add)
    sub.add_parser("build").set_defaults(func=build)
    a = ap.parse_args()
    a.func(a)
