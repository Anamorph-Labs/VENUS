"""Venus by Anamorph Labs: a video editor that tells a story."""

import os as _os

__version__ = "0.9.0"

# Homebrew's plain ffmpeg on macOS has no libass, so it cannot draw words on video.
# install.sh adds ffmpeg-full (kept apart by Homebrew); use it first when it is there.
for _d in ("/opt/homebrew/opt/ffmpeg-full/bin", "/usr/local/opt/ffmpeg-full/bin"):
    if _os.path.isfile(_os.path.join(_d, "ffmpeg")) and _d not in _os.environ.get("PATH", "").split(":"):
        _os.environ["PATH"] = _d + ":" + _os.environ.get("PATH", "")
        break
