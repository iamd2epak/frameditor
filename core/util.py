"""Shared helpers: frame size, paths, easing, fonts, layers."""
import os
from PIL import Image, ImageFont

W, H, FPS = 1080, 1920, 30                      # every .frame is portrait 1080x1920 @ 30 fps (format v1)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, ".cache")            # downloads, voice cache, auto-fetched logos (git-ignored)
MODELS = os.path.join(ROOT, "models")           # TTS / ASR models (git-ignored, setup.sh)
os.makedirs(CACHE, exist_ok=True)


def ease(x):
    x = min(1, max(0, x)); return 1 - (1 - x) ** 3


def back(x):
    x = min(1, max(0, x)); c = 1.70158; return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2


def prog(t, a, d=0.35):
    return min(1, max(0, (t - a) / d))


def layer(): return Image.new("RGBA", (W, H), (0, 0, 0, 0))


def fade(L, a):
    if a >= 1: return L
    L = L.copy(); L.putalpha(L.getchannel("A").point(lambda v: int(v * max(0, a)))); return L


# ---------- fonts: a theme registers its fonts/ folder; DejaVu is the fallback ----------
FONT_DIRS = []
_FC = {}


def font_file(name):
    for d in FONT_DIRS:
        p = os.path.join(d, name)
        if os.path.exists(p): return p
    return None


def font(name, size):
    """name = a font file in the active theme's fonts/ folder (e.g. "Manrope-Bold.ttf")."""
    key = (name, int(size))
    if key not in _FC:
        p = font_file(name)
        try: _FC[key] = ImageFont.truetype(p or "DejaVuSans-Bold.ttf", max(6, int(size)))
        except OSError: _FC[key] = ImageFont.load_default()
    return _FC[key]
