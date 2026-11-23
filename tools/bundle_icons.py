"""Bundle the Tabler outline icons (MIT) into alvenus/icons/tabler.json.gz.

    python tools/bundle_icons.py PATH/TO/@tabler/icons/package

Keeps each icon's path data, category and search tags; drops the invisible
bounding-box path every Tabler icon starts with."""

import gzip
import json
import shutil
import sys
from pathlib import Path

src = Path(sys.argv[1])
nodes = json.loads((src / "tabler-nodes-outline.json").read_text())
meta = json.loads((src / "icons.json").read_text())
out = {}
for name, elems in sorted(nodes.items()):
    ds = [a["d"] for tag, a in elems if tag == "path" and a.get("d") and a.get("d") != "M0 0h24v24H0z"]
    m = meta.get(name, {})
    out[name] = [m.get("category", ""), " ".join(str(t) for t in m.get("tags", [])), ds]
dest = Path(__file__).resolve().parent.parent / "alvenus" / "icons"
dest.mkdir(exist_ok=True)
with gzip.open(dest / "tabler.json.gz", "wt", encoding="utf-8", compresslevel=9) as f:
    json.dump({"version": json.loads((src / "package.json").read_text())["version"], "icons": out}, f, separators=(",", ":"))
shutil.copy(src / "LICENSE", dest / "TABLER-LICENSE.txt")
print(f"{len(out)} icons -> {dest / 'tabler.json.gz'}")
