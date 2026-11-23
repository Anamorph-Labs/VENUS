"""Keep Venus up to date: check for a new version, install it, and roll back on its own if anything breaks.

    alvenus update --check          is there a new version? what is new in it? (add --json for your AI)
    alvenus update                  install it (asks first; --yes to skip the question)
    alvenus update --rollback       go back to the version you had before the last update
    alvenus update --from FOLDER    install from a copy you already have (a folder or a .tar.gz)

How it stays safe:
  * the new version comes only from the official Venus repository on GitHub, over HTTPS;
  * before anything changes, the version you have now is copied to ~/.venus/backups;
  * after installing, Venus starts the new version and checks it; if it does not start,
    the old version is put back on its own and nothing is lost;
  * your videos, node files and settings are never touched, only the program.

Nothing is uploaded and nothing is installed without a yes (from the creator, or --yes).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess  # nosec B404
import sys
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path

from . import __version__

REPO = "Anamorph-Labs/AL-VENUS"
BRANCH = "main"
NOTES_URL = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/CHANGES.md"
CODE_URL = f"https://codeload.github.com/{REPO}/tar.gz/refs/heads/{BRANCH}"
ALLOWED_HOSTS = ("raw.githubusercontent.com", "codeload.github.com")
CHECK_EVERY = 6 * 3600  # seconds between quiet checks (Studio, session start)
KEEP_BACKUPS = 3


def home() -> Path:
    return Path(os.environ.get("VENUS_HOME") or Path.home() / ".venus")


def parse_version(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3]) or (0,)


def newer(a: str, b: str) -> bool:
    """True when version a is newer than version b."""
    return parse_version(a) > parse_version(b)


def read_notes(text: str) -> list[dict]:
    """CHANGES.md -> [{version, date, notes: [...]}, ...], newest first.

    Each release starts with a heading like '## 0.9.0 (24 Nov 2026)'; the bullet lines under it
    are the notes, written for creators in plain words."""
    out: list[dict] = []
    for line in text.splitlines():
        m = re.match(r"^##\s+v?(\d+\.\d+(?:\.\d+)?)\s*(?:\((.*?)\))?", line)
        if m:
            out.append({"version": m.group(1), "date": (m.group(2) or "").strip(), "notes": []})
        elif out and line.strip().startswith(("-", "*")):
            out[-1]["notes"].append(line.strip()[1:].strip())
    return out


def _fetch(url: str, timeout: float = 8.0) -> bytes:
    from urllib.parse import urlparse

    u = urlparse(url)
    if u.scheme != "https" or u.hostname not in ALLOWED_HOSTS:
        raise ValueError(f"Venus only updates from its own repository over HTTPS, not {url}")
    req = urllib.request.Request(url, headers={"User-Agent": f"venus-updater/{__version__}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # nosec B310
        return r.read()


def _source_notes(src: str | None) -> str:
    """The release notes from GitHub, or from a local copy given with --from (or VENUS_UPDATE_FROM)."""
    if src:
        p = Path(src)
        if p.is_dir():
            return (p / "CHANGES.md").read_text(encoding="utf-8")
        with tarfile.open(p) as t:
            for m in t.getmembers():
                if m.name.split("/")[-1] == "CHANGES.md" and m.name.count("/") <= 1:
                    f = t.extractfile(m)
                    return f.read().decode("utf-8") if f else ""
        raise ValueError(f"{src} has no CHANGES.md: is it a copy of Venus?")
    return _fetch(NOTES_URL).decode("utf-8")


def check(src: str | None = None, quiet_cache: bool = False) -> dict:
    """What is installed, what is newest, and what is new since. Never raises for a missing network."""
    src = src or os.environ.get("VENUS_UPDATE_FROM") or None
    cache = home() / "update-check.json"
    if quiet_cache and not src:
        try:
            c = json.loads(cache.read_text())
            if time.time() - c.get("at", 0) < CHECK_EVERY and c.get("installed") == __version__:
                return c
        except (OSError, ValueError):
            pass
    res = {"installed": __version__, "latest": __version__, "update": False, "whats_new": [], "at": time.time()}
    try:
        rel = read_notes(_source_notes(src))
    except Exception as e:  # offline, GitHub down, or the repository not public yet: say so, don't fail
        if src:
            raise SystemExit(f"Could not read {src}: {e}") from None
        res["error"] = f"could not check for updates ({type(e).__name__}); try again later"
        return res
    if rel:
        res["latest"] = rel[0]["version"]
        res["update"] = newer(rel[0]["version"], __version__)
        res["whats_new"] = [{"version": r["version"], "date": r["date"], "notes": r["notes"]}
                            for r in rel if newer(r["version"], __version__)]
    if not src:
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(res))
        except OSError:
            pass
    return res


def say_check(res: dict) -> str:
    if res.get("error"):
        return f"Venus {res['installed']}: {res['error']}."
    if not res["update"]:
        return f"Venus {res['installed']} is the newest version."
    lines = [f"A new Venus is ready: {res['latest']} (you have {res['installed']})."]
    for r in res["whats_new"]:
        for n in r["notes"][:6]:
            lines.append(f"  - {n}")
    lines.append("Install it with: alvenus update   (your current version is backed up and comes back on its own if anything fails)")
    return "\n".join(lines)


# ---------------------------------------------------------------- installing

def installed_files() -> tuple[Path, list[Path]]:
    """The installed package folder and its pip record folders (what a backup must hold)."""
    pkg = Path(__file__).resolve().parent
    site = pkg.parent
    info = sorted(site.glob("alvenus-*.dist-info")) + sorted(site.glob("alvenus-*.egg-info"))
    return pkg, info


def from_source_checkout() -> bool:
    """Running straight from a git folder (a developer copy): updating means git pull there instead."""
    pkg, info = installed_files()
    return (pkg.parent / ".git").exists() or any((p / "direct_url.json").exists() and '"editable": true' in
                                                (p / "direct_url.json").read_text() for p in info if p.suffix == ".dist-info")


def backup() -> Path:
    pkg, info = installed_files()
    dest = home() / "backups" / f"{__version__}-{time.strftime('%Y%m%d-%H%M%S')}"
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copytree(pkg, dest / pkg.name, ignore=shutil.ignore_patterns("__pycache__"))
    for p in info:
        shutil.copytree(p, dest / p.name)
    (dest / "backup.json").write_text(json.dumps({"version": __version__, "site": str(pkg.parent), "at": time.time(),
                                                  "parts": [pkg.name] + [p.name for p in info]}))
    old = sorted((home() / "backups").iterdir())
    for p in old[:-KEEP_BACKUPS]:
        shutil.rmtree(p, ignore_errors=True)
    return dest


def latest_backup() -> Path | None:
    d = home() / "backups"
    found = sorted(p for p in d.iterdir() if (p / "backup.json").exists()) if d.exists() else []
    return found[-1] if found else None


def restore(b: Path) -> str:
    """Put a backed-up version back exactly as it was."""
    meta = json.loads((b / "backup.json").read_text())
    site = Path(meta["site"])
    for p in list(site.glob("alvenus-*.dist-info")) + list(site.glob("alvenus-*.egg-info")) + [site / "alvenus"]:
        if p.is_dir():
            shutil.rmtree(p)
    for part in meta["parts"]:
        shutil.copytree(b / part, site / part)
    return meta["version"]


def _safe_extract(tar_path: Path, into: Path) -> Path:
    with tarfile.open(tar_path) as t:
        root = into.resolve()
        for m in t.getmembers():
            target = (into / m.name).resolve()
            if not str(target).startswith(str(root) + os.sep) or m.issym() or m.islnk() or m.isdev():
                raise ValueError(f"refusing an unsafe path in the download: {m.name}")
        if sys.version_info >= (3, 12):
            t.extractall(into, filter="data")  # nosec B202
        else:
            t.extractall(into)  # nosec B202
    tops = [p for p in into.iterdir() if p.is_dir()]
    if len(tops) == 1 and (tops[0] / "pyproject.toml").exists():
        return tops[0]
    if (into / "pyproject.toml").exists():
        return into
    raise ValueError("the download does not look like Venus (no pyproject.toml)")


def get_source(src: str | None, work: Path) -> Path:
    if src and Path(src).is_dir():
        if not (Path(src) / "pyproject.toml").exists():
            raise ValueError(f"{src} does not look like a copy of Venus")
        clean = work / "src"  # a clean copy: old build folders in a working copy would be installed instead
        shutil.copytree(src, clean, ignore=shutil.ignore_patterns(".git", "build", "*.egg-info", "__pycache__", "*.mp4", "*.mov"))
        return clean
    tar = Path(src) if src else work / "venus.tar.gz"
    if not src:
        tar.write_bytes(_fetch(CODE_URL, timeout=120))
    return _safe_extract(tar, work / "src")


def health(expect: str | None = None) -> tuple[bool, str]:
    """Start the freshly installed Venus in a new Python and make sure it answers."""
    code = "import alvenus, alvenus.cli, alvenus.studio; print(alvenus.__version__)"
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)  # nosec B603
    if r.returncode != 0:
        return False, (r.stderr or r.stdout)[-400:]
    got = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
    r2 = subprocess.run([sys.executable, "-m", "alvenus", "--help"], capture_output=True, text=True, timeout=120)  # nosec B603
    if r2.returncode != 0:
        return False, (r2.stderr or r2.stdout)[-400:]
    if expect and got != expect:
        return False, f"expected version {expect} but {got} started"
    return True, got


def install(src: str | None = None, log=print) -> dict:
    """Back up, install the new version, check it, and roll back on its own if the check fails."""
    src = src or os.environ.get("VENUS_UPDATE_FROM") or None
    if from_source_checkout():
        raise SystemExit("This Venus runs from a developer folder: update it there with git pull.")
    b = backup()
    log(f"Backed up Venus {__version__} to {b}")
    with tempfile.TemporaryDirectory(prefix="venus-update-") as tmp:
        try:
            code = get_source(src, Path(tmp))
        except Exception as e:
            shutil.rmtree(b, ignore_errors=True)
            raise SystemExit(f"Could not get the new version ({e}). Nothing was changed.") from None
        want = None
        m = re.search(r'__version__\s*=\s*"([^"]+)"', (code / "alvenus" / "__init__.py").read_text())
        if m:
            want = m.group(1)
        log(f"Installing Venus {want or '(new)'}...")
        r = subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--upgrade", "--no-input", str(code.resolve())],  # nosec B603
                           capture_output=True, text=True)
        ok, info = (r.returncode == 0, (r.stderr or r.stdout)[-400:])
        if ok:
            ok, info = health(want)
    if not ok:
        back = restore(b)
        shutil.rmtree(b, ignore_errors=True)  # nothing changed, so this backup is not a step back
        ok2, _ = health(back)
        log(f"The new version did not start ({info.strip()}); Venus {back} is back, as it was."
            + ("" if ok2 else " Please run install.sh again."))
        return {"ok": False, "installed": back, "rolled_back": True, "why": info.strip()}
    try:
        (home() / "update-check.json").unlink()
    except OSError:
        pass
    log(f"Venus {info} is installed. Your old version is kept in {b} (alvenus update --rollback brings it back).")
    return {"ok": True, "installed": info, "from": __version__, "backup": str(b)}


def rollback(log=print) -> dict:
    b = latest_backup()
    if not b:
        raise SystemExit("There is no earlier version to go back to.")
    v = restore(b)
    shutil.rmtree(b, ignore_errors=True)  # used: a second --rollback goes one more step back
    ok, got = health(v)
    log(f"Venus {v} is back." if ok else f"Put back Venus {v}, but it did not start ({got}); please run install.sh again.")
    return {"ok": ok, "installed": v}


def cmd_update(a) -> None:
    if a.rollback:
        res = rollback()
        if a.json:
            print(json.dumps(res))
        return
    res = check(a.from_)
    if a.check:
        print(json.dumps(res, indent=1) if a.json else say_check(res))
        return
    if not res["update"] and not a.force:
        print(json.dumps(res) if a.json else say_check(res))
        return
    if not a.json:
        print(say_check(res))
    if not a.yes:
        if not sys.stdin.isatty():
            raise SystemExit("Add --yes to install (ask the creator first).")
        if input("Install it now? [y/N] ").strip().lower() not in ("y", "yes"):
            print("Nothing changed.")
            return
    out = install(a.from_, log=(lambda *_: None) if a.json else print)
    if a.json:
        print(json.dumps(out))
    if not out["ok"]:
        raise SystemExit(1)


def add_parser(sub) -> None:
    up = sub.add_parser("update", help="check for a new Venus and install it, with a backup and automatic roll-back")
    up.add_argument("--check", action="store_true", help="only say whether a new version is ready and what is new")
    up.add_argument("--json", action="store_true", help="answer in JSON (for your AI)")
    up.add_argument("--yes", "-y", action="store_true", help="install without asking (only after the creator said yes)")
    up.add_argument("--rollback", action="store_true", help="go back to the version you had before the last update")
    up.add_argument("--from", dest="from_", metavar="PATH", help="install from a local copy of Venus (a folder or .tar.gz)")
    up.add_argument("--force", action="store_true", help="reinstall even when the version is the same")
    up.set_defaults(func=cmd_update)
