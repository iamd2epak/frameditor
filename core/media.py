"""Images (local path or URL, cached) and brand logos (theme pack logos/ first, then auto-download to .cache/logos/)."""
import hashlib, json, os, subprocess
from PIL import Image, ImageDraw
from .util import CACHE

IMG_CACHE = os.path.join(CACHE, "media"); os.makedirs(IMG_CACHE, exist_ok=True)
SEARCH = []          # extra folders for relative image paths (the spec's folder, the theme folder) — set by core/reel.py
LOGO_DIRS = [os.path.join(CACHE, "logos")]       # the active theme inserts its logos/ folder in front
MISSING = []         # images that could not be loaded (the CLI asks the user to attach them)
_IM = {}


def load(src):
    """src: absolute path, path relative to the spec / theme folder, or http(s) URL (downloaded once)."""
    if src in _IM: return _IM[src]
    path = str(src)
    if path.startswith("http"):
        path = os.path.join(IMG_CACHE, hashlib.md5(path.encode()).hexdigest() + os.path.splitext(path.split("?")[0])[1][:5])
        if not os.path.exists(path): subprocess.run(["curl", "-sL", "-m", "60", "-o", path, src], check=False)
    elif not os.path.isabs(path):
        for base in SEARCH + [os.getcwd()]:
            if os.path.exists(os.path.join(base, path)): path = os.path.join(base, path); break
    try: im = Image.open(path).convert("RGBA")
    except Exception:
        MISSING.append(str(src))
        im = Image.new("RGBA", (540, 960), (60, 60, 70, 255)); ImageDraw.Draw(im).text((20, 20), "missing image", fill=(255, 255, 255))
    _IM[src] = im; return im


def fitcrop(im, w, h, zoom=1.0, fx=0.5, fy=0.5):
    w, h = max(1, int(w)), max(1, int(h))
    s = max(w / im.width, h / im.height) * zoom
    r = im.resize((int(im.width * s) + 1, int(im.height * s) + 1), Image.LANCZOS)
    x = int((r.width - w) * fx); y = int((r.height - h) * fy); return r.crop((x, y, x + w, y + h))


# ---------- brand logos: <slug>.png = white glyph + brands.json {slug: "RRGGBB"} ----------
BRAND = {"tiktok": (0, 0, 0), "youtube": (255, 0, 0), "youtubeshorts": (255, 0, 0), "github": (24, 23, 23),
         "googlegemini": (70, 90, 200), "openai": (16, 163, 127), "claude": (217, 119, 87), "ollama": (40, 40, 44), "pexels": (5, 160, 129)}
_TRIED = set()


def reload_brands():
    for d in reversed(LOGO_DIRS):
        p = os.path.join(d, "brands.json")
        if os.path.exists(p):
            for k, v in json.load(open(p)).items(): BRAND[k] = tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))


def is_img(slug): return isinstance(slug, str) and slug.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))


def logo_path(slug):
    for d in LOGO_DIRS:
        p = os.path.join(d, f"{slug}.png")
        if os.path.exists(p): return p
    return None


def has_logo(slug):
    """True if a logo PNG exists for slug; downloads it once (core/logos.py) if missing. An image path counts as a full-colour tile."""
    if is_img(slug): return True
    if not logo_path(slug) and slug and slug not in _TRIED:
        _TRIED.add(slug)
        try:
            from . import logos
            got = logos.get([slug], quiet=True)
            if got.get(slug) and got[slug] != slug:          # resolved to another slug (e.g. "google drive" -> googledrive)
                import shutil; shutil.copy(os.path.join(logos.LOGOS, got[slug] + ".png"), os.path.join(logos.LOGOS, f"{slug}.png"))
            reload_brands()
            if got.get(slug) and got[slug] in BRAND: BRAND[slug] = BRAND[got[slug]]
        except Exception as e: print("logo fetch failed:", slug, e)
    return logo_path(slug) is not None
