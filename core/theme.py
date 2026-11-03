"""Theme packs: find, validate, install and load them.

A theme pack is ONE folder (or a .zip of it) that holds everything one look needs: theme.json, theme.py, RULES.md,
fonts/, optional character/, logos/, stickers/, examples/. The engine core never contains a theme. Contract: docs/THEMES.md.
"""
import importlib.util, json, os, re, shutil, sys, tempfile, zipfile
from . import media, util, character

THEMES_DIR = os.path.join(util.ROOT, "themes")
KINDS = ("character", "faceless", "face")        # face = the user's own video (planned: not in format v1 yet)
SUPPORTED_KINDS = ("character", "faceless")
LICENSES = ("free", "paid", "private")
FORMAT = 1                                         # .frame format this engine writes
REQUIRED = ("id", "name", "version", "format", "kind", "license", "fonts", "style")
ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")


class ThemeError(SystemExit):
    pass


def dirs():
    """theme search path: ./themes, plus every folder in $FRAME_THEMES (os.pathsep separated)."""
    out = [THEMES_DIR] + [p for p in os.environ.get("FRAME_THEMES", "").split(os.pathsep) if p]
    return [d for d in out if os.path.isdir(d)]


def installed():
    found = {}
    for d in dirs():
        for name in sorted(os.listdir(d)):
            p = os.path.join(d, name)
            if os.path.isfile(os.path.join(p, "theme.json")): found.setdefault(name, p)
    return found


def find(theme_id):
    p = installed().get(theme_id)
    if not p:
        have = ", ".join(installed()) or "none"
        raise ThemeError(f"theme '{theme_id}' is not installed (installed: {have}).\n"
                         f"  Install its pack first: python frame.py install <{theme_id}.zip | folder | URL>")
    return p


def read_json(path):
    try: return json.load(open(os.path.join(path, "theme.json")))
    except FileNotFoundError: raise ThemeError(f"{path}: no theme.json (not a theme pack)")
    except json.JSONDecodeError as e: raise ThemeError(f"{path}/theme.json is not valid JSON: {e}")


def validate(path):
    """list of problems with a theme pack folder (empty = valid)."""
    errs = []
    try: m = read_json(path)
    except ThemeError as e: return [str(e)]
    for k in REQUIRED:
        if k not in m: errs.append(f"theme.json: missing '{k}'")
    tid = m.get("id", "")
    if tid and not ID_RE.match(tid): errs.append("theme.json: id must be lowercase letters/digits/_ (2-32 chars, starts with a letter)")
    if tid and os.path.basename(os.path.normpath(path)) != tid: errs.append(f"folder name must equal the theme id ('{tid}')")
    if not isinstance(m.get("version"), int) or m.get("version", 0) < 1: errs.append("theme.json: version must be an integer >= 1")
    if m.get("format") != FORMAT: errs.append(f"theme.json: format must be {FORMAT} (this engine writes .frame format {FORMAT})")
    if m.get("kind") not in KINDS: errs.append(f"theme.json: kind must be one of {', '.join(KINDS)}")
    elif m["kind"] not in SUPPORTED_KINDS: errs.append(f"kind '{m['kind']}' is not supported by .frame format {FORMAT} yet")
    if m.get("license") not in LICENSES: errs.append(f"theme.json: license must be one of {', '.join(LICENSES)}")
    for f in ("theme.py", "RULES.md"):
        if not os.path.isfile(os.path.join(path, f)): errs.append(f"missing {f}")
    for f in m.get("fonts", []):
        if not os.path.isfile(os.path.join(path, "fonts", f)): errs.append(f"fonts/{f} listed in theme.json but missing")
    c = m.get("character")
    if m.get("kind") == "character":
        if not isinstance(c, dict): errs.append("kind 'character' needs a 'character' block (name, style: sprite, image, eyes, brows, mouth)")
        else:
            for k in ("name", "style", "image", "eyes", "mouth"):
                if k not in c: errs.append(f"character: missing '{k}'")
            if c.get("style") != "sprite": errs.append("character.style must be 'sprite' (format 1)")
            if c.get("image") and not os.path.isfile(os.path.join(path, c["image"])): errs.append(f"character image {c['image']} missing")
            if c.get("name") and not re.match(r"^[A-Z][A-Za-z]{1,15}$", c["name"]): errs.append("character.name: one simple word, capitalised (e.g. Max)")
    elif c: errs.append(f"kind '{m.get('kind')}' must not have a character")
    st = m.get("style", {})
    for k in ("background", "caption", "palette"):
        if k not in st: errs.append(f"style: missing '{k}' (the app draws it, see docs/FORMAT.md)")
    if not os.path.isdir(os.path.join(path, "examples")) or not [f for f in os.listdir(os.path.join(path, "examples")) if f.endswith(".yaml")]:
        errs.append("examples/: add at least one example spec (.yaml)")
    return errs


def install(src, force=False):
    """install a pack from a folder, a .zip or an http(s) URL into ./themes/<id>/."""
    tmp = tempfile.mkdtemp(prefix="theme_")
    try:
        if src.startswith(("http://", "https://")):
            import urllib.request
            z = os.path.join(tmp, "pack.zip"); urllib.request.urlretrieve(src, z); src = z
        if os.path.isfile(src):
            if not zipfile.is_zipfile(src): raise ThemeError(f"{src}: not a .zip theme pack")
            with zipfile.ZipFile(src) as zf:
                for n in zf.namelist():
                    if n.startswith("/") or ".." in n.split("/"): raise ThemeError(f"unsafe path in zip: {n}")
                zf.extractall(os.path.join(tmp, "x"))
            root = os.path.join(tmp, "x"); subs = [d for d in os.listdir(root) if not d.startswith((".", "__"))]
            src = os.path.join(root, subs[0]) if len(subs) == 1 and os.path.isdir(os.path.join(root, subs[0])) else root
        if not os.path.isdir(src): raise ThemeError(f"{src}: not found")
        m = read_json(src); tid = m.get("id", "")
        if not ID_RE.match(tid): raise ThemeError("theme.json: bad or missing id")
        stage = os.path.join(tmp, tid)
        if os.path.normpath(src) != os.path.normpath(stage): shutil.copytree(src, stage, ignore=shutil.ignore_patterns("__pycache__", ".git"))
        errs = validate(stage)
        if errs: raise ThemeError("theme pack is not valid:\n  " + "\n  ".join(errs))
        dst = os.path.join(THEMES_DIR, tid)
        if os.path.exists(dst):
            if not force: raise ThemeError(f"theme '{tid}' is already installed (use --force to replace it)")
            shutil.rmtree(dst)
        os.makedirs(THEMES_DIR, exist_ok=True); shutil.copytree(stage, dst)
        return tid, m
    finally: shutil.rmtree(tmp, ignore_errors=True)


def pack(path, out_dir):
    """zip a theme pack folder into <out_dir>/<id>.zip after validating it."""
    errs = validate(path)
    if errs: raise ThemeError("theme pack is not valid:\n  " + "\n  ".join(errs))
    m = read_json(path); os.makedirs(out_dir, exist_ok=True); out = os.path.join(out_dir, f"{m['id']}.zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for base, ds, fs in os.walk(path):
            ds[:] = [d for d in ds if d not in ("__pycache__", ".git")]
            for f in sorted(fs):
                if f.endswith((".pyc", ".DS_Store")): continue
                p = os.path.join(base, f); z.write(p, os.path.join(m["id"], os.path.relpath(p, path)))
    return out


class Theme:
    """a loaded theme: .meta (theme.json), .dir, .mod (theme.py module), .character (name or None)."""

    def __init__(self, theme_id):
        self.dir = find(theme_id)
        errs = validate(self.dir)
        if errs: raise ThemeError(f"theme '{theme_id}' is broken:\n  " + "\n  ".join(errs))
        self.meta = m = read_json(self.dir); self.id = m["id"]
        util.FONT_DIRS[:0] = [os.path.join(self.dir, "fonts")]
        if os.path.isdir(os.path.join(self.dir, "logos")): media.LOGO_DIRS.insert(0, os.path.join(self.dir, "logos"))
        media.SEARCH.append(self.dir); media.reload_brands()
        c = m.get("character")
        self.character = c["name"] if c else None
        if c: character.CHARS[c["name"]] = dict(c, image=os.path.join(self.dir, c["image"]))
        name = f"frametheme_{self.id}"
        spec = importlib.util.spec_from_file_location(name, os.path.join(self.dir, "theme.py"), submodule_search_locations=[self.dir])
        mod = importlib.util.module_from_spec(spec); sys.modules[name] = mod; spec.loader.exec_module(mod)
        for fn in ("frame", "record"):
            if not callable(getattr(mod, fn, None)): raise ThemeError(f"theme '{self.id}': theme.py must define {fn}() (docs/THEMES.md)")
        self.mod = mod

    def path(self, *p): return os.path.join(self.dir, *p)
