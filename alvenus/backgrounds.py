"""Backgrounds made from nothing: slow, living colour fields for scenes that
have no footage (titles, numbers, charts, quotes), so an idea alone can become
a finished-looking video.

Each one is drawn small (a few thousand pixels) with FFmpeg's expression
filter, then scaled up smoothly, which is quick and naturally soft; a little
moving film grain on top keeps it from looking like flat computer colour.
They stay dark so white type always reads on them."""

from __future__ import annotations

KINDS = {
    "dark": "a plain deep gradient (the default)",
    "aurora": "slow ribbons of the accent colour drifting across the dark",
    "orbs": "soft blurred lights floating, like out-of-focus city lights",
    "grid": "a faint grid gliding past with a glow behind it, for tech and data",
    "ink": "warm dark paper with a soft stain of colour and grain, for essays",
    "spotlight": "a pool of light that breathes in the middle, for one big idea",
}


def _rgb(hex_rgb: str) -> tuple[int, int, int]:
    h = hex_rgb.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _partner(r: int, g: int, b: int) -> tuple[int, int, int]:
    """A second light that sits well with the accent: its opposite on the
    colour wheel, a little deeper (orange finds a deep blue, teal a rose)."""
    import colorsys

    hh, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    r2, g2, b2 = colorsys.hsv_to_rgb((hh + 0.5) % 1.0, min(0.85, s * 0.9 + 0.1), 0.75)
    return round(r2 * 255), round(g2 * 255), round(b2 * 255)


def _channel(base: int, a: int, b: int, fa: str, fb: str) -> str:
    """One colour channel: a dark base plus two lights, clipped to 0..255."""
    return f"clip({base}+{a}*({fa})+{b}*({fb}),0,255)"


def source(kind: str, w: int, h: int, fps: float, d: float, accent: str = "#FFD23F") -> tuple[str, str]:
    """(lavfi input, filter chain) for a background `d` seconds long."""
    if kind not in KINDS:
        raise ValueError(f"background {kind!r}: choose one of {', '.join(KINDS)}")
    ar, ag, ab = _rgb(accent)
    br, bg, bb = _partner(ar, ag, ab)
    sw, sh = (192, 108) if w >= h else (108, 192)
    n = f"nullsrc=s={sw}x{sh}:r={fps:g}:d={d:.3f},format=gbrp"
    grain = f"scale={w}:{h}:flags=bicubic,noise=alls=7:allf=t,format=yuv420p"
    if kind == "dark":
        return (f"gradients=s={w}x{h}:r={fps:g}:c0=0x15171c:c1=0x23262e:x0=0:y0=0:x1={w}:y1={h}:speed=0.002:d={d:.3f}",
                "format=yuv420p")
    if kind == "aurora":
        fa = "0.8*pow(0.5+0.5*sin(X/W*3.1+T*0.5+1.8*sin(Y/H*2.2+T*0.33)),2)*(1.15-Y/H)"
        fb = "0.85*pow(0.5+0.5*sin(X/W*2.3-T*0.37+1.4*sin(Y/H*2.9-T*0.21)+2),2)*(0.35+0.8*Y/H)"
        base = (16, 17, 26)
    elif kind == "orbs":
        def orb(cx: str, cy: str, r: float) -> str:
            return f"exp(-(pow(X/W-({cx}),2)*1.8+pow(Y/H-({cy}),2))/{r})"
        fa = "0.7*(" + orb("0.3+0.18*sin(T*0.31)", "0.4+0.15*sin(T*0.23+1)", 0.025) + "+" + orb("0.75+0.12*sin(T*0.27+2)", "0.65+0.1*sin(T*0.19)", 0.018) + ")"
        fb = "0.55*(" + orb("0.55+0.25*sin(T*0.17+4)", "0.25+0.12*sin(T*0.29+3)", 0.02) + "+" + orb("0.15+0.1*sin(T*0.21+5)", "0.8+0.08*sin(T*0.33)", 0.012) + ")"
        base = (10, 11, 16)
    elif kind == "spotlight":
        fa = "0.5*(0.85+0.15*sin(T*1.1))*exp(-(pow(X/W-0.5,2)*1.6+pow(Y/H-0.46,2))/0.06)"
        fb = "0.18*exp(-(pow(X/W-0.5,2)+pow(Y/H-0.5,2))/0.3)"
        base = (9, 9, 12)
    elif kind == "ink":
        fa = "0.3*pow(0.5+0.5*sin(X/W*2.3+Y/H*1.7+T*0.12+sin(Y/H*5.1+T*0.07)),2)*(1-0.6*Y/H)"
        fb = "0.12*(0.5+0.5*sin(X/W*7.1-Y/H*3.3+T*0.09))"
        base = (30, 24, 20)
        br, bg, bb = 120, 90, 60  # the paper's warmth, not a second hue
    else:  # grid: lines gliding past over a soft glow
        glow = "0.45*exp(-(pow(X/W-0.5,2)+pow(Y/H-0.55,2)*1.5)/0.08)"
        glow2 = "0.35*exp(-(pow(X/W-0.15,2)+pow(Y/H-0.1,2))/0.12)"
        e = [_channel(c0, c1, c2, glow, glow2) for c0, c1, c2 in ((12, ar, br), (13, ag, bg), (18, ab, bb))]
        step = max(40, round(min(w, h) / 9))
        return (f"{n},geq=r='{e[0]}':g='{e[1]}':b='{e[2]}'",
                f"scale={w + step}:{h + step}:flags=bicubic,"
                f"drawgrid=w={step}:h={step}:t=1:c=white@0.09,"
                f"crop={w}:{h}:x='mod(t*{step / 6:.1f},{step})':y='mod(t*{step / 10:.1f},{step})',"
                f"noise=alls=5:allf=t,format=yuv420p")
    e = [_channel(base[0], ar, br, fa, fb), _channel(base[1], ag, bg, fa, fb), _channel(base[2], ab, bb, fa, fb)]
    return f"{n},geq=r='{e[0]}':g='{e[1]}':b='{e[2]}'", f"{grain},vignette=PI/5"
