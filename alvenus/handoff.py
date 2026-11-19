"""Hand the cut to a real editor: an XML timeline that Premiere Pro (File >
Import) and DaVinci Resolve (File > Import > Timeline) open with the media
already linked.

What makes it more than a list of cuts:
- every clip points at the original file by its full path, so nothing needs
  relinking on the same computer;
- the takes Venus did not use sit on tracks above, switched off, lined up
  with the line they belong to: swapping a take is a toggle, not a search;
- a marker on each line says which take was picked and why;
- music, when there is any, is on its own audio track.

The format is Final Cut Pro 7 XML (xmeml version 5), which both programs
import. Effects drawn by Venus (titles, captions, grade) stay in the MP4;
the timeline carries the edit."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape

from .cut import Clip


def _rate(fps: float) -> tuple[int, bool]:
    base = int(round(fps))
    return base, abs(fps - base) > 0.01  # 29.97 is "30, NTSC"


def _url(p: Path) -> str:
    s = str(p.resolve()).replace("\\", "/")
    return "file://localhost" + ("" if s.startswith("/") else "/") + quote(s)


class _Sources:
    """Each file is described in full once, then referred to by id."""

    def __init__(self, paths: list[Path], rate: str):
        from .media import duration, video_size

        self.paths, self.rate, self.seen = paths, rate, set()
        self.info = []
        for p in paths:
            try:
                d, size = duration(p), video_size(p)
            except Exception:
                d, size = 0.0, None
            self.info.append((d, size))

    def ref(self, k: int, fps: float) -> str:
        fid = f"file-{k + 1}"
        if fid in self.seen:
            return f'<file id="{fid}"/>'
        self.seen.add(fid)
        d, size = self.info[k]
        p = self.paths[k]
        video = (f"<video><samplecharacteristics><width>{size[0]}</width><height>{size[1]}</height></samplecharacteristics></video>"
                 if size else "")
        return (f'<file id="{fid}"><name>{escape(p.name)}</name><pathurl>{_url(p)}</pathurl>{self.rate}'
                f"<duration>{round(d * fps)}</duration><media>{video}<audio><samplecharacteristics><depth>16</depth>"
                f"<samplerate>48000</samplerate></samplecharacteristics><channelcount>2</channelcount></audio></media></file>")


def _item(cid: str, name: str, src: str, rate: str, start: int, end: int, cin: int, cout: int, on: bool, link: str = "",
          dur: int = 0) -> str:
    return (f'<clipitem id="{cid}"><name>{escape(name)}</name><enabled>{"TRUE" if on else "FALSE"}</enabled>'
            f"<duration>{max(dur, cout)}</duration>{rate}"
            f"<start>{start}</start><end>{end}</end><in>{cin}</in><out>{cout}</out>{src}{link}</clipitem>")


def _link(vid: str, aid: str, k: int) -> str:
    return (f"<link><linkclipref>{vid}</linkclipref><mediatype>video</mediatype><trackindex>1</trackindex><clipindex>{k}</clipindex></link>"
            f"<link><linkclipref>{aid}</linkclipref><mediatype>audio</mediatype><trackindex>1</trackindex><clipindex>{k}</clipindex></link>")


def write_xml(path: Path, title: str, sources: list[Path], clips: list[Clip], script: list[str], fps: float,
              size: str, choices=(), music: Path | None = None) -> int:
    """Write the timeline; returns how many unused takes were laid on the
    tracks above for swapping."""
    base, ntsc = _rate(fps)
    rate = f"<rate><timebase>{base}</timebase><ntsc>{'TRUE' if ntsc else 'FALSE'}</ntsc></rate>"
    w, h = (int(x) for x in size.split("x"))
    src = _Sources(sources, rate)
    f = lambda t: int(round(t * fps))

    v1, a1, markers = [], [], []
    rec, first_at = 0, {}
    for n, c in enumerate(clips, 1):
        length = f(c.end) - f(c.start)
        vid, aid = f"v1-{n}", f"a1-{n}"
        first_at.setdefault(c.line, rec)
        name = f"line {c.line + 1}: {sources[c.source].name}"
        v1.append(_item(vid, name, src.ref(c.source, fps), rate, rec, rec + length, f(c.start), f(c.end), True, _link(vid, aid, n), f(src.info[c.source][0])))
        a1.append(_item(aid, name, src.ref(c.source, fps), rate, rec, rec + length, f(c.start), f(c.end), True, _link(vid, aid, n), f(src.info[c.source][0])))
        rec += length + f(c.hold)
    total = rec

    # Takes not used, on switched-off tracks above, starting where their line starts.
    alt_tracks: list[list[tuple[int, int, str, str]]] = []
    count = 0
    for ch in choices:
        if ch.take is None or ch.line not in first_at:
            continue
        others = sorted((t for t in ch.candidates if t is not ch.take and t.recall >= 0.5), key=lambda t: -t.score)[:2]
        for t in others:
            at, length = first_at[ch.line], f(t.end) - f(t.start)
            row = next((r for r in alt_tracks if all(at >= e or at + length <= s for s, e, _, _ in r)), None)
            if row is None:
                row = []
                alt_tracks.append(row)
            count += 1
            name = f"line {ch.line + 1}, other take {t.index}: {sources[t.source].name}"
            row.append((at, at + length, f"alt-{count}", _item("{id}", name, src.ref(t.source, fps), rate, at, at + length,
                                                                f(t.start), f(t.end), False, "", f(src.info[t.source][0]))))
        why = ch.reason[0].upper() + ch.reason[1:] if ch.reason else ""
        alts = ", ".join(f"take {t.index}" for t in others)
        markers.append(f"<marker><name>Line {ch.line + 1}: take {ch.take.index}</name><comment>{escape(why)}"
                       f"{escape('. Other takes on the tracks above (switched off): ' + alts) if alts else ''}</comment>"
                       f"<in>{first_at[ch.line]}</in><out>-1</out></marker>")

    def track(items: list[str], on: bool = True) -> str:
        return f"<track><enabled>{'TRUE' if on else 'FALSE'}</enabled>{''.join(items)}</track>"

    vtracks = [track(v1)] + [track([x.replace('"{id}"', f'"{cid}v"') for _, _, cid, x in sorted(r)], False) for r in alt_tracks]
    ref_only = lambda x: re.sub(r'<file id="(file-\d+)">.*?</file>', r'<file id="\1"/>', x)
    atracks = [track(a1)] + [track([ref_only(x.replace('"{id}"', f'"{cid}a"')) for _, _, cid, x in sorted(r)], False) for r in alt_tracks]
    if music and Path(music).exists():
        from .media import duration

        mlen = min(total, f(duration(music)))
        msrc = _Sources([Path(music)], rate)
        atracks.append(track([_item("music-1", f"music: {Path(music).name}", msrc.ref(0, fps).replace('"file-1"', '"file-music"'),
                                    rate, 0, mlen, 0, mlen, True)]))
    fmt = (f"<format><samplecharacteristics>{rate}<width>{w}</width><height>{h}</height>"
           f"<pixelaspectratio>square</pixelaspectratio></samplecharacteristics></format>")
    xml = (f'<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n<xmeml version="5"><sequence id="sequence-1">'
           f"<name>{escape(title)}</name><duration>{total}</duration>{rate}"
           f"<timecode>{rate}<string>01:00:00:00</string><frame>{3600 * base}</frame><displayformat>NDF</displayformat></timecode>"
           f"<media><video>{fmt}{''.join(vtracks)}</video><audio>{''.join(atracks)}</audio></media>"
           f"{''.join(markers)}</sequence></xmeml>\n")
    path.write_text(xml, encoding="utf-8")
    return count
