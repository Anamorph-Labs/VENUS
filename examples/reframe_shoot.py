"""Make a wide (16:9) test shoot for auto-reframe: a stand-in "person" (a
skin-toned head whose mouth moves while the voice speaks) stands on the
right, then walks to the left. A busy, static bookshelf pattern sits at the
far left to check that still detail doesn't pull the framing.

    python examples/reframe_shoot.py VOICE.mp4 OUT.mp4
The voice comes from any existing clip (e.g. a fakeshoot clip)."""

import subprocess
import sys

import numpy as np

W, H, FPS = 960, 540, 25


def main(voice: str, out: str) -> None:
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", voice],
                               capture_output=True, text=True).stdout)
    pcm = np.frombuffer(subprocess.run(["ffmpeg", "-v", "error", "-i", voice, "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
                                       capture_output=True).stdout, np.int16).astype(np.float32)
    env = np.abs(pcm)
    yy, xx = np.mgrid[0:H, 0:W]
    bg = np.zeros((H, W, 3), np.float32)
    bg[...] = (40 + 30 * yy / H)[..., None] * np.array([0.8, 0.9, 1.2])
    shelf = ((xx < 150) & ((yy // 30 + xx // 12) % 2 == 0))
    bg[shelf] = (200, 180, 120)
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
                          "-i", "-", "-i", voice, "-map", "0:v", "-map", "1:a", "-vf", "scale=1920:1080", "-c:v", "libx264",
                          "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", out], stdin=subprocess.PIPE)
    n = int(dur * FPS)
    for i in range(n):
        t = i / FPS
        # right third until 45% of the clip, walk across over 2 s, then left third
        k = min(max((t - 0.45 * dur) / 2.0, 0.0), 1.0)
        cx = W * (0.75 - 0.5 * (3 * k * k - 2 * k ** 3))
        cy = H * 0.45
        f = bg.copy()
        body = ((xx - cx) / 120) ** 2 + ((yy - H) / 200) ** 2 < 1
        f[body] = (60, 70, 90)
        head = ((xx - cx) / 70) ** 2 + ((yy - cy) / 90) ** 2 < 1
        f[head] = (224, 172, 140)
        a = env[int(t * 8000): int(t * 8000) + 320]
        open_ = min(1.0, (a.mean() if len(a) else 0) / 3000)
        mouth = ((xx - cx) / 28) ** 2 + ((yy - cy - 45) / (3 + 14 * open_)) ** 2 < 1
        f[mouth] = (90, 30, 30)
        p.stdin.write(f.clip(0, 255).astype(np.uint8).tobytes())
    p.stdin.close()
    p.wait()


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
