"""The node map: one HTML page that shows a node file as boxes and wires.

Scenes run left to right, each with its parts stacked under it; the wires
between scenes carry their transitions; style nodes wire down to the scenes
that use them. Locked nodes show a lock, nodes changed since the last build
are outlined, and a click shows a node's settings with the command that
changes them. The page is self-contained (frames from the last build are
embedded), so it opens anywhere and can be sent to someone."""

from __future__ import annotations

import base64
import html
import json
import subprocess
from pathlib import Path

from . import nodes as nd


def _frame(video: str, t: float, width: int = 240) -> str | None:
    try:
        raw = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-ss", f"{t:.2f}", "-i", video, "-frames:v", "1",
                              "-vf", f"scale={width}:-2", "-q:v", "5", "-f", "image2pipe", "-vcodec", "mjpeg", "-"],
                             capture_output=True, check=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return "data:image/jpeg;base64," + base64.b64encode(raw).decode() if raw else None


def view_data(path: Path, doc: dict) -> dict:
    last = nd.read_last(path)
    changed = set(nd.changes(doc, last))
    sb = nd.effective(nd.to_storyboard(doc))
    video = last.get("video")
    have_video = bool(video and Path(video).exists())
    spans = last.get("spans") or {}
    redrawn = set(last.get("redrawn") or [])

    def node(n: dict) -> dict:
        return {"id": n["id"], "kind": n["kind"], "params": n.get("params") or {}, "locked": bool(n.get("locked")),
                "changed": n["id"] in changed, "what": nd.WHAT.get(n["kind"], ""),
                "can": nd.part_params(n["kind"]) if n["kind"] in nd.PARTS else []}

    scenes = []
    trans = sb.get("transition", "crossfade")
    for k, sn in enumerate(nd.scenes_of(doc)):
        p = sn.get("params") or {}
        parts = nd.parts_of(doc, sn["id"])
        inn = next((x for x in parts if x["kind"] == "in"), None)
        thumb = None
        if have_video and sn["id"] in spans:
            a, b = spans[sn["id"]]
            thumb = _frame(video, a + (b - a) * 0.6)
        scenes.append({**node(sn), "n": k + 1, "type": p.get("type", "?"), "seconds": p.get("seconds"),
                       "use": sn.get("use") or [], "thumb": thumb, "redrawn": sn["id"] in redrawn,
                       "trans": ((inn or {}).get("params") or {}).get("transition") or trans,
                       "parts": [node(x) for x in parts if x["kind"] != "in"] + [node(t) for t in nd.tools_of(doc, sn["id"])],
                       "inNode": node(inn) if inn else None})
    top = []
    for n in nd.tidy(doc)["nodes"]:
        if n["kind"] in ("settings", "sound", "style"):
            top.append({**node(n), "users": [s["id"] for s in nd.scenes_of(doc) if n["id"] in (s.get("use") or [])]})
    gone = [c[1:] for c in changed if c.startswith("-")]
    total = sum(float(s.get("seconds", 3.0)) for s in sb["scenes"])
    return {"file": path.name, "built": last.get("built"), "total": round(total, 1), "design": sb.get("design"),
            "aspect": sb.get("aspect", "16:9"), "scenes": scenes, "top": top, "gone": gone,
            "problems": nd.check(doc), "changedCount": len([c for c in changed if not c.startswith("-")])}


def write_view(path: Path, doc: dict, out: Path) -> None:
    data = view_data(path, doc)
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    out.write_text(PAGE.replace("__TITLE__", html.escape(path.name)).replace("__DATA__", blob), encoding="utf-8")


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Node map</title>
<style>
:root{--bg:#f4f2ee;--panel:#fffdf9;--ink:#1b1a18;--soft:#6c6860;--line:#d9d4ca;--wire:#a39d92;--accent:#c8412f;
--chip:#ece8e0;--scene:#1b1a18;--sceneInk:#fffdf9;--lock:#2f6f8f;--shadow:0 1px 2px rgba(0,0,0,.06),0 4px 14px rgba(0,0,0,.05)}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#161514;--panel:#201f1d;--ink:#eeeae2;--soft:#a29d94;
--line:#383531;--wire:#6d685f;--accent:#f06a52;--chip:#2c2a27;--scene:#eeeae2;--sceneInk:#161514;--lock:#7cc0de;--shadow:none}}
:root[data-theme="dark"]{--bg:#161514;--panel:#201f1d;--ink:#eeeae2;--soft:#a29d94;--line:#383531;--wire:#6d685f;--accent:#f06a52;
--chip:#2c2a27;--scene:#eeeae2;--sceneInk:#161514;--lock:#7cc0de;--shadow:none}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
header{padding:20px 24px 8px;display:flex;flex-wrap:wrap;gap:8px 20px;align-items:baseline}
h1{font-size:20px;margin:0;font-weight:700;letter-spacing:-.01em}
.meta{color:var(--soft);font-size:13px}
.legend{display:flex;gap:14px;flex-wrap:wrap;color:var(--soft);font-size:12px;padding:0 24px 8px}
.legend span{display:inline-flex;gap:6px;align-items:center}
.sw{width:12px;height:12px;border-radius:3px;border:1.5px solid var(--line);display:inline-block}
.sw.ch{border-color:var(--accent)}
.problems{margin:6px 24px;padding:10px 14px;border-left:3px solid var(--accent);background:var(--panel);font-size:13px}
.wrap{overflow:auto;padding:8px 24px 32px}
.canvas{position:relative;width:max-content;padding:4px 0 0}
svg.wires{position:absolute;inset:0;pointer-events:none;overflow:visible}
.lane{display:flex;gap:18px;align-items:flex-start;position:relative;z-index:1}
.lane.top{margin-bottom:64px}
.lane.scenes{gap:72px}
.col{display:flex;flex-direction:column;gap:14px;width:212px}
.box{background:var(--panel);border:1.5px solid var(--line);border-radius:10px;padding:9px 11px;cursor:pointer;box-shadow:var(--shadow);
width:212px;position:relative;text-align:left;color:inherit;font:inherit}
.box:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.box.sel{outline:2.5px solid var(--accent);outline-offset:3px}
.box.changed{border-color:var(--accent);border-width:2px}
.k{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--soft);display:flex;gap:6px;align-items:center}
.id{font-weight:650;font-size:13.5px;margin:1px 0 3px;word-break:break-all}
.p{font-size:12px;color:var(--soft);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.p b{color:var(--ink);font-weight:500}
.scene{background:var(--scene);color:var(--sceneInk);border-color:var(--scene)}
.scene .k,.scene .p{color:color-mix(in srgb,var(--sceneInk) 65%,transparent)}
.scene .p b{color:var(--sceneInk)}
.scene.changed{border-color:var(--accent)}
.thumb{display:block;width:100%;max-height:150px;object-fit:contain;border-radius:6px;margin:6px 0 4px;background:#0003}
.chips{display:flex;gap:4px;flex-wrap:wrap;margin-top:4px}
.chip{font-size:10.5px;padding:1px 7px;border-radius:99px;background:var(--chip);color:var(--ink)}
.scene .chip{background:color-mix(in srgb,var(--sceneInk) 16%,transparent);color:var(--sceneInk)}
.chip.ch{background:var(--accent);color:#fff}
.lock{color:var(--lock);font-size:12px}
.scene .lock{color:inherit}
.tr{position:absolute;z-index:2;font-size:11px;padding:2px 8px;border-radius:99px;background:var(--bg);border:1px solid var(--wire);
color:var(--soft);transform:translate(-50%,-50%);cursor:pointer;white-space:nowrap}
.tr.own{color:var(--ink);border-color:var(--ink)}
.tr.changed{border-color:var(--accent);color:var(--accent)}
aside{position:fixed;right:16px;bottom:16px;width:min(380px,calc(100vw - 32px));max-height:min(70vh,560px);overflow:auto;
background:var(--panel);border:1.5px solid var(--line);border-radius:12px;padding:14px 16px;box-shadow:0 8px 30px rgba(0,0,0,.18);display:none;z-index:5}
aside.on{display:block}
aside h2{font-size:15px;margin:0 0 2px;word-break:break-all}
aside .what{color:var(--soft);font-size:12.5px;margin-bottom:10px}
aside table{border-collapse:collapse;width:100%;font-size:12.5px}
aside td{border-top:1px solid var(--line);padding:5px 4px;vertical-align:top}
aside td:first-child{color:var(--soft);white-space:nowrap;padding-right:10px}
aside td:last-child{word-break:break-word}
aside code,aside pre{font:12px/1.4 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
aside pre{background:var(--chip);padding:8px 10px;border-radius:8px;white-space:pre-wrap;word-break:break-all;margin:10px 0 0}
aside .can{color:var(--soft);font-size:12px;margin-top:8px}
.x{position:absolute;right:10px;top:8px;border:0;background:none;color:var(--soft);font-size:18px;cursor:pointer}
.theme{margin-left:auto;border:1.5px solid var(--line);background:var(--panel);color:var(--ink);border-radius:99px;padding:3px 12px;font:inherit;font-size:12px;cursor:pointer}
@media (max-width:600px){header{padding:16px 16px 6px}.wrap{padding:8px 16px 120px}.legend{padding:0 16px 8px}.problems{margin:6px 16px}}
</style></head><body>
<header><h1>__TITLE__</h1><span class="meta" id="meta"></span><button class="theme" id="theme" type="button">Theme</button></header>
<div class="legend"><span><i class="sw"></i>node</span><span><i class="sw ch"></i>changed since the last build</span>
<span><span class="lock">&#128274;</span>locked</span><span>click any node for its settings</span></div>
<div id="problems"></div>
<div class="wrap"><div class="canvas" id="canvas"><svg class="wires" id="wires"></svg>
<div class="lane top" id="top"></div><div class="lane scenes" id="scenes"></div></div></div>
<aside id="panel" aria-live="polite"><button class="x" id="close" aria-label="Close">&times;</button><div id="pbody"></div></aside>
<script>
const D = __DATA__;
const $ = s => document.querySelector(s);
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const short = v => { let s = typeof v === 'string' ? v : JSON.stringify(v); if (typeof v === 'string' && /[\/\\]/.test(v) && /\.\w+$/.test(v)) s = v.split(/[\/\\]/).pop(); return s.length > 40 ? s.slice(0, 38) + '…' : s; };
const byId = {};
$('#meta').textContent = `${D.scenes.length} scenes · about ${D.total} s · ${D.aspect}` + (D.design ? ` · design ${D.design}` : '')
  + (D.built ? ` · last built ${D.built}` + (D.changedCount ? `, ${D.changedCount} node${D.changedCount > 1 ? 's' : ''} changed since then` : ', nothing changed since') : ' · not built yet');
if (D.problems.length || D.gone.length) $('#problems').innerHTML = '<div class="problems">' + D.problems.map(esc).join('<br>')
  + (D.gone.length ? (D.problems.length ? '<br>' : '') + 'Removed since the last build: ' + D.gone.map(esc).join(', ') : '') + '</div>';
function params(p, n) {
  return Object.entries(p).slice(0, n).map(([k, v]) => `<div class="p">${esc(k)} <b>${esc(short(v))}</b></div>`).join('')
    + (Object.keys(p).length > n ? `<div class="p">+ ${Object.keys(p).length - n} more</div>` : '');
}
function box(n, cls, inner) {
  byId[n.id] = n;
  return `<button type="button" class="box ${cls} ${n.changed ? 'changed' : ''}" data-id="${esc(n.id)}" id="b-${esc(n.id)}">${inner}</button>`;
}
const lock = n => n.locked ? '<span class="lock" title="locked">&#128274;</span>' : '';
$('#top').innerHTML = D.top.map(n => box(n, '', `<div class="k">${esc(n.kind)}${lock(n)}</div><div class="id">${esc(n.id)}</div>`
  + (Object.keys(n.params).length ? params(n.params, 5) : '<div class="p">empty</div>')
  + (n.users.length ? `<div class="chips">${n.users.map(u => `<span class="chip">→ ${esc(u)}</span>`).join('')}</div>` : ''))).join('');
$('#scenes').innerHTML = D.scenes.map(s => {
  const own = Object.fromEntries(Object.entries(s.params).filter(([k]) => k !== 'type' && k !== 'seconds'));
  const chips = s.use.map(u => `<span class="chip">uses ${esc(u)}</span>`).join('') + (s.changed ? '<span class="chip ch">changed</span>' : '')
    + (s.redrawn ? '<span class="chip">redrawn last build</span>' : '');
  const head = box(s, 'scene', `<div class="k">#${s.n} · ${esc(s.type)}${s.seconds != null ? ' · ' + esc(s.seconds) + ' s' : ''}${lock(s)}</div>`
    + `<div class="id">${esc(s.id)}</div>` + (s.thumb ? `<img class="thumb" alt="frame of ${esc(s.id)}" src="${s.thumb}">` : '')
    + params(own, 3) + (chips ? `<div class="chips">${chips}</div>` : ''));
  return `<div class="col" data-scene="${esc(s.id)}">` + head + s.parts.map(p => box(p, 'part',
    `<div class="k">${esc(p.kind)}${lock(p)}</div><div class="id">${esc(p.id)}</div>` + params(p.params, 4))).join('') + '</div>';
}).join('');
D.scenes.forEach(s => { if (s.inNode) byId[s.inNode.id] = s.inNode; });
function wires() {
  const c = $('#canvas'), r0 = c.getBoundingClientRect(), svg = $('#wires');
  svg.setAttribute('width', c.scrollWidth); svg.setAttribute('height', c.scrollHeight);
  c.querySelectorAll('.tr').forEach(e => e.remove());
  const R = el => { const r = el.getBoundingClientRect(); return {x: r.left - r0.left, y: r.top - r0.top, w: r.width, h: r.height}; };
  let out = '<defs><marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
    + '<path d="M0 0L10 5L0 10z" fill="var(--wire)"/></marker></defs>';
  D.scenes.forEach((s, i) => {
    const col = c.querySelector(`[data-scene="${CSS.escape(s.id)}"]`), sb = R(col.firstElementChild);
    // a scene's parts hang off it on a spine at its left
    const parts = [...col.children].slice(1);
    if (parts.length) {
      const last = R(parts[parts.length - 1]), x = sb.x - 9;
      out += `<path d="M${sb.x} ${sb.y + 18} H${x} V${last.y + 18}" fill="none" stroke="var(--wire)" stroke-width="1.5"/>`;
      parts.forEach(p => { const b = R(p); out += `<path d="M${x} ${b.y + 18} H${b.x}" stroke="var(--wire)" stroke-width="1.5"/>`; });
    }
    if (i + 1 < D.scenes.length) {
      const nb = R(c.querySelector(`[data-scene="${CSS.escape(D.scenes[i + 1].id)}"]`).firstElementChild);
      const y = sb.y + 22;
      out += `<path d="M${sb.x + sb.w} ${y} H${nb.x - 2}" stroke="var(--wire)" stroke-width="2" marker-end="url(#ar)"/>`;
      const nx = D.scenes[i + 1], t = document.createElement('div');
      t.className = 'tr' + (nx.inNode ? ' own' : '') + (nx.inNode && nx.inNode.changed ? ' changed' : '');
      t.textContent = nx.trans; t.style.left = (sb.x + sb.w + nb.x) / 2 + 'px'; t.style.top = y + 'px';
      t.title = nx.inNode ? `${nx.inNode.id}: this scene's own way in` : 'the video\'s transition (set settings.transition, or ' + nx.id + '.in.transition)';
      if (nx.inNode) t.onclick = () => pick(nx.inNode.id);
      c.appendChild(t);
    }
  });
  D.top.filter(n => n.users.length).forEach(n => {
    const a = R($('#b-' + CSS.escape(n.id)));
    n.users.forEach(u => {
      const b = R($('#b-' + CSS.escape(u))), x1 = a.x + a.w / 2, y1 = a.y + a.h, x2 = b.x + b.w / 2, y2 = b.y - 2, m = (y1 + y2) / 2;
      out += `<path d="M${x1} ${y1} C${x1} ${m} ${x2} ${m} ${x2} ${y2}" fill="none" stroke="var(--wire)" stroke-width="1.5" stroke-dasharray="5 4" marker-end="url(#ar)"/>`;
    });
  });
  svg.innerHTML = out;
}
function pick(id) {
  const n = byId[id]; if (!n) return;
  document.querySelectorAll('.box.sel').forEach(e => e.classList.remove('sel'));
  const el = document.getElementById('b-' + id); if (el) el.classList.add('sel');
  const rows = Object.entries(n.params).map(([k, v]) => `<tr><td>${esc(k)}</td><td><code>${esc(typeof v === 'string' ? v : JSON.stringify(v))}</code></td></tr>`).join('');
  const ex = Object.keys(n.params).find(k => k !== 'type') || (n.can[0] || 'param');
  $('#pbody').innerHTML = `<h2>${esc(n.id)} ${lock(n)}</h2><div class="what">${esc(n.kind)}: ${esc(n.what)}${n.changed ? ' · <b>changed since the last build</b>' : ''}</div>`
    + (rows ? `<table>${rows}</table>` : '<div class="what">No settings yet.</div>')
    + (n.can.length ? `<div class="can">Can hold: ${n.can.map(esc).join(', ')}</div>` : '')
    + `<pre>alvenus nodes set ${esc(D.file)} ${esc(n.id)}.${esc(ex)}=…\nalvenus nodes ${n.locked ? 'unlock' : 'lock'} ${esc(D.file)} ${esc(n.id)}</pre>`;
  $('#panel').classList.add('on');
}
document.addEventListener('click', e => { const b = e.target.closest('.box'); if (b) pick(b.dataset.id); });
$('#close').onclick = () => { $('#panel').classList.remove('on'); document.querySelectorAll('.box.sel').forEach(e => e.classList.remove('sel')); };
$('#theme').onclick = () => { const r = document.documentElement, dark = r.dataset.theme ? r.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
  r.dataset.theme = dark ? 'light' : 'dark'; };
window.addEventListener('resize', wires);
document.querySelectorAll('img').forEach(i => i.addEventListener('load', wires));
wires();
</script></body></html>
"""
