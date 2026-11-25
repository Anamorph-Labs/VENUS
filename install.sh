#!/usr/bin/env bash
# Venus in one step, on macOS or Linux:   bash install.sh
#
# 1. checks for Python 3.10+ and FFmpeg (and offers to install FFmpeg with
#    Homebrew or apt when it is missing);
# 2. puts Venus in its own folder (~/.venus) so nothing else on the computer
#    changes, and links the `alvenus` command into ~/.local/bin;
# 3. downloads the free models once (Whisper to hear; add --find for footage search);
# 4. runs `alvenus doctor` to show that everything works.
#
# Nothing is uploaded. Run it again any time to update.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOME_DIR="${VENUS_HOME:-$HOME/.venus}"
BIN_DIR="${VENUS_BIN:-$HOME/.local/bin}"
MODEL="small.en"
EXTRA=()
for arg in "$@"; do
  case "$arg" in
    --small) MODEL="base.en" ;;           # a smaller, quicker listener (~290 MB instead of ~1.5 GB)
    --find) EXTRA+=(--find) ;;            # also the footage-search model (~150 MB)
    --no-models) MODEL="" ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg (try --help)"; exit 2 ;;
  esac
done

say() { printf '\n== %s\n' "$*"; }

say "Python"
PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
    PY="$(command -v "$c")"; break
  fi
done
if [ -z "$PY" ]; then
  echo "Venus needs Python 3.10 or newer: https://www.python.org/downloads/ (then run this again)"
  exit 1
fi
echo "using $("$PY" --version) at $PY"

say "FFmpeg"
if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    echo "FFmpeg is missing; installing it with Homebrew"; brew install ffmpeg
  elif command -v apt-get >/dev/null 2>&1; then
    echo "FFmpeg is missing; installing it with apt (asks for your password)"; sudo apt-get update && sudo apt-get install -y ffmpeg
  else
    echo "Please install FFmpeg (https://ffmpeg.org/download.html), then run this again."; exit 1
  fi
fi
if ! ffmpeg -hide_banner -filters 2>/dev/null | grep -q " subtitles "; then
  # Venus draws its words with libass; Homebrew's plain ffmpeg is built without it
  if command -v brew >/dev/null 2>&1; then
    echo "This FFmpeg can't draw words on video; adding Homebrew's ffmpeg-full (Venus uses it on its own)"
    brew install ffmpeg-full && export PATH="$(brew --prefix ffmpeg-full)/bin:$PATH"
  else
    echo "Note: this FFmpeg has no libass, so words can't be drawn on video. Install a full FFmpeg build."
  fi
fi
ffmpeg -version | head -1

say "Venus"
if [ ! -x "$HOME_DIR/bin/python" ]; then
  "$PY" -m venv "$HOME_DIR"
fi
"$HOME_DIR/bin/python" -m pip install --quiet --upgrade pip
"$HOME_DIR/bin/python" -m pip install --quiet --upgrade "$HERE"
mkdir -p "$BIN_DIR"
ln -sf "$HOME_DIR/bin/alvenus" "$BIN_DIR/alvenus"
echo "the alvenus command is in $BIN_DIR"
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) echo "add this line to your shell profile so the command is found:  export PATH=\"$BIN_DIR:\$PATH\"" ;;
esac

if [ -n "$MODEL" ]; then
  say "Models (once)"
  "$HOME_DIR/bin/alvenus" fetch-models --model "$MODEL" ${EXTRA[@]+"${EXTRA[@]}"}
fi

say "Check"
"$HOME_DIR/bin/alvenus" doctor || true
echo
echo "Done. Open your AI (Claude Code, Codex...) in the Venus folder and tell it: Make a video about ..."
