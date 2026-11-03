"""Brand logos on demand: white glyph PNG + brand colour from simple-icons (CC0, 3000+ brands), saved to .cache/logos/.
core/media.py calls this automatically when a spec names a logo that neither the theme pack nor the cache has."""
import json, os, re, subprocess, sys, glob, tarfile, urllib.request
from .util import CACHE as _C
LOGOS = os.path.join(_C, "logos"); BRANDS = os.path.join(LOGOS, "brands.json"); os.makedirs(LOGOS, exist_ok=True)
CACHE = os.path.join(_C, "simple-icons")
RAW = "https://raw.githubusercontent.com/simple-icons/simple-icons/develop/"

ALIASES = {"chatgpt": "openai", "gpt": "openai", "gemini": "googlegemini", "twitter": "x", "vscode": "visualstudiocode",
           "ytshorts": "youtubeshorts", "insta": "instagram", "fb": "facebook", "gmail": "gmail", "claudeai": "claude"}
def _norm(s): return re.sub(r"[^a-z0-9]", "", s.lower().replace("+", "plus").replace("&", "and").replace(".", "dot"))

def _package():
    pkg = os.path.join(CACHE, "package")
    if os.path.isdir(pkg): return pkg
    os.makedirs(CACHE, exist_ok=True)
    try:
        out = subprocess.run(["npm", "pack", "simple-icons", "--silent"], cwd=CACHE, capture_output=True, text=True, timeout=180).stdout.strip().splitlines()
        tgz = os.path.join(CACHE, out[-1]); tarfile.open(tgz).extractall(CACHE, filter="data"); os.remove(tgz); return pkg
    except Exception: return None

def _data(pkg):
    if pkg:
        f = (glob.glob(os.path.join(pkg, "_data", "simple-icons.json")) + glob.glob(os.path.join(pkg, "data", "simple-icons.json")))
        if f:
            d = json.load(open(f[0])); return d["icons"] if isinstance(d, dict) else d
    for p in ("data/simple-icons.json", "_data/simple-icons.json"):
        try:
            d = json.loads(urllib.request.urlopen(RAW + p, timeout=30).read()); return d["icons"] if isinstance(d, dict) else d
        except Exception: pass
    return []

def _svg(pkg, slug):
    if pkg and os.path.exists(os.path.join(pkg, "icons", slug + ".svg")): return open(os.path.join(pkg, "icons", slug + ".svg")).read()
    try: return urllib.request.urlopen(RAW + f"icons/{slug}.svg", timeout=30).read().decode()
    except Exception: return None

def get(names, quiet=False):
    import cairosvg
    pkg = _package(); icons = _data(pkg); brands = json.load(open(BRANDS)) if os.path.exists(BRANDS) else {}
    by = {}
    for ic in icons:
        slug = ic.get("slug") or _norm(ic["title"]); by[_norm(ic["title"])] = (slug, ic); by.setdefault(slug, (slug, ic))
        for a in (ic.get("aliases", {}) or {}).get("aka", []): by.setdefault(_norm(a), (slug, ic))
    got = {}
    for name in names:
        key = _norm(name); key = ALIASES.get(key, key); hit = by.get(key)
        if not hit and os.path.exists(os.path.join(LOGOS, key + ".png")):
            got[name] = key; continue                      # already cached (e.g. chatgpt -> openai)
        if not hit:
            if not quiet: print(f"  ✗ {name}: not in simple-icons (use a lettered tile or ask the user for a PNG)")
            continue
        slug, ic = hit; svg = _svg(pkg, slug)
        if not svg: print(f"  ✗ {name}: download failed"); continue
        svg = svg.replace("<svg ", '<svg fill="#FFFFFF" ', 1)
        cairosvg.svg2png(bytestring=svg.encode(), write_to=os.path.join(LOGOS, slug + ".png"), output_width=256, output_height=256)
        brands[slug] = ic.get("hex", "444444"); got[name] = slug
        if not quiet: print(f"  ✓ {name} → .cache/logos/{slug}.png  (#{brands[slug]})")
    json.dump(brands, open(BRANDS, "w"), indent=1, sort_keys=True)
    return got
