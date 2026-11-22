"""The add-on rules, run on every community proposal (and by hand).

    python tools/addon_guard.py BASE_REF            # checks the files changed since BASE_REF

A proposal passes when:
  - it only adds or changes files under alvenus/addons/ (styles/*.json, recipes/*.json, README.md),
  - each add-on file is valid and every value is one Venus knows (the same check Venus runs at start),
  - nothing in it looks private or secret (emails, keys, tokens, home folder paths),
  - nothing in it carries someone else's licence or copyright.

Anything else (a code change to Venus itself) is not refused as an idea, but it
can't pass as an add-on: Anamorph Labs reads it as a sketch and builds the idea
itself. Prints a plain report; exits 1 when a rule is broken.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ALLOWED = re.compile(r"^alvenus/addons/(styles|recipes)/[a-z0-9][a-z0-9-]{1,30}\.json$|^alvenus/addons/README\.md$")
FOREIGN = re.compile(r"(GNU (Affero )?General Public License|GPL-?[23]|AGPL|Creative Commons|All rights reserved|proprietary and confidential)", re.I)


def changed(base: str) -> list[tuple[str, str]]:
    out = subprocess.run(["git", "diff", "--name-status", f"{base}...HEAD"], capture_output=True, text=True, cwd=ROOT, check=True).stdout
    return [(ln.split("\t")[0][0], ln.split("\t")[-1]) for ln in out.splitlines() if ln.strip()]


def main(base: str) -> int:
    from alvenus import community as cm

    files = changed(base)
    broken, notes = [], []
    if not files:
        print("No files changed.")
        return 0
    for status, f in files:
        if status == "D":
            broken.append(f"{f}: removes a file; community proposals only add")
            continue
        if not ALLOWED.match(f):
            broken.append(f"{f}: outside the add-on folder. Code changes are read as a sketch of the idea; "
                          "Anamorph Labs builds the idea itself (see CONTRIBUTING.md)")
            continue
        p = ROOT / f
        before = len(broken)
        text = p.read_text(encoding="utf-8", errors="replace")
        for what in cm.private_bits(text):
            broken.append(f"{f}: contains {what}")
        if FOREIGN.search(text):
            broken.append(f"{f}: mentions another licence or copyright; add-ons must be your own work under MIT")
        if f.endswith(".json"):
            try:
                data = json.loads(text)
            except ValueError as e:
                broken.append(f"{f}: not valid JSON ({e})")
                continue
            kind = f.split("/")[2]
            why = (cm.recipe_problems if kind == "recipes" else cm.style_problems)(p.stem, data) if isinstance(data, dict) else ["not a JSON object"]
            broken += [f"{f}: {w}" for w in why]
            if len(broken) == before:
                notes.append(f"{f}: a valid {kind[:-1]} add-on by {data.get('by')}")
    print("Add-on rules\n")
    for n in notes:
        print("  ok   " + n)
    for b in broken:
        print("  no   " + b)
    print("\n" + ("Passed." if not broken else f"{len(broken)} rule{'s' if len(broken) > 1 else ''} broken."))
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "origin/main"))
