""".frame writer: ONE portable project file `<slug>.frame` that the Frameditor app opens (preview, edit, MP4 export).

The theme does not draw pixels for the app. Its record(R, rec) runs the reel frame by frame and tells the Recorder,
for every frame, which sprite is where (3D pose), plus overlays, flashes and shakes. Sprites are baked once (WebP); the
character face is exported as a rig so the app animates it live; voice, music bed and SFX samples are stored separately
so the app can mix them. Captions are re-drawn by the app from the words + the theme's caption style.
File layout + every field: docs/FORMAT.md.
"""
import hashlib, io, json, os, subprocess, time, zipfile
import numpy as np, soundfile as sf
from PIL import Image
from . import audio, character as charmod
from .util import ROOT, W, H, FPS

FORMAT_VERSION = 1                 # bump only for breaking layout changes (the app refuses files newer than it knows)
EXT = ".frame"
TEXT_KINDS = ("pill", "sticker", "word", "heading")      # props whose text the app can re-draw after an edit


def r2(v): return round(float(v), 2)


class Recorder:
    """collects what the theme puts on screen, frame by frame. Themes set rec.frame = i before drawing frame i."""

    def __init__(self, ss=2):
        self.ss = ss                  # sprite supersampling: sprite pixels per frame pixel
        self.frame = 0
        self.sprites = {}             # sid -> (Image, logical w, logical h, ss)
        self._obj = {}                # id(image) -> (image, sid): keeps objects alive so ids stay unique
        self.tracks = {}              # key -> {key, scene, pid, kind, label, shadow, glow, rows, [text], [expr]}
        self.anchors = {}             # "scene:pid" -> rows [frame, x, y, s, a] (overlays follow these)
        self.flash, self.shake, self.cracks = [], [], []
        self.scenes = []              # [{index, start, end, label, lines, compose, overlays, anchor_sizes}]
        self.shatters = []            # [{scene, pid, t}]
        self.camera = dict(focal=1500.0, cx=W / 2, cy=H / 2)

    def sid(self, im, ss=None):
        hit = self._obj.get(id(im))
        if hit and hit[0] is im: return hit[1]
        sid = hashlib.md5(im.tobytes() + str(im.size).encode()).hexdigest()[:14]
        self._obj[id(im)] = (im, sid); k = ss or self.ss
        if sid not in self.sprites: self.sprites[sid] = (im, im.width / k, im.height / k, k)
        return sid

    def track(self, key, scene, pid, kind, label=None, shadow=False, **extra):
        tr = self.tracks.get(key)
        if tr is None:
            tr = self.tracks[key] = dict(key=key, scene=scene, pid=pid, kind=kind, shadow=bool(shadow), glow=None, label=label or kind, rows=[], **extra)
        return tr

    def row(self, tr, sid, x, y, z=0, rx=0, ry=0, rz=0, s=1, a=1, blur=0, mx=0, my=0, glint=-1):
        """one frame of a track: pose (page px, depth z, tilt degrees, scale, alpha, blur px) + screen motion (mx, my) for motion blur."""
        tr["rows"].append([self.frame, sid, r2(x), r2(y), r2(z), r2(rx), r2(ry), r2(rz), round(s, 4), round(a, 3), r2(blur), r2(mx), r2(my),
                           round(glint, 3) if glint is not None and 0 < glint < 1 else -1])

    def anchor(self, key, x, y, s, a): self.anchors.setdefault(key, []).append([self.frame, r2(x), r2(y), round(s, 4), round(a, 3)])
    def add_flash(self, v): self.flash.append([self.frame, round(v, 3)])
    def add_shake(self, sx, sy): self.shake.append([self.frame, r2(sx), r2(sy)])
    def add_crack(self, x, y, u): self.cracks.append([self.frame, r2(x), r2(y), round(u, 3)])


# ------------------------------------------------------------------ helpers
def _webp(im):
    b = io.BytesIO(); im.save(b, "WEBP", quality=92, method=4); return b.getvalue()     # keeps alpha, ~3x smaller than PNG


def _png(im):
    b = io.BytesIO(); im.save(b, "PNG", compress_level=6); return b.getvalue()


def _jpg(im):
    b = io.BytesIO(); im.convert("RGB").save(b, "JPEG", quality=85); return b.getvalue()


def _wav(a):
    b = io.BytesIO(); sf.write(b, np.clip(a, -1, 1), audio.SR, format="WAV", subtype="PCM_16"); return b.getvalue()


def _git_version():
    try: return subprocess.run(["git", "-C", ROOT, "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip() or "dev"
    except Exception: return "dev"


def identity(slug, ids_file):
    """stable id + revision per reel (local file, never committed): every new export of the same spec is the next version of
    the same project in the app (v1, v2, ...), even if the title changes."""
    import uuid
    try: db = json.load(open(ids_file))
    except Exception: db = {}
    e = db.get(slug) or dict(id=uuid.uuid4().hex[:16], rev=0)
    e["rev"] = int(e.get("rev", 0)) + 1; db[slug] = e
    os.makedirs(os.path.dirname(ids_file), exist_ok=True); json.dump(db, open(ids_file, "w"), indent=1)
    return e["id"], e["rev"]


def rig(name, max_side=800):
    """character face rig: clean head + movable parts (eyes, brows, mouth), scaled so the head is <= max_side px."""
    cfg = charmod.CHARS[name]; R = charmod.get_rig(name); bb = R.src.getbbox(); k = min(1.0, max_side / max(bb[2] - bb[0], bb[3] - bb[1]))
    def box(b): return [r2((b[0] - bb[0]) * k), r2((b[1] - bb[1]) * k), r2((b[2] - bb[0]) * k), r2((b[3] - bb[1]) * k)]
    def img(im): return im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.LANCZOS)
    files = {"character/clean.png": img(R.clean.crop(bb)), "character/mouth.png": img(R.mouth_orig)}
    meta = dict(name=name, style=cfg.get("style", "sprite"), version=1, size=[r2((bb[2] - bb[0]) * k), r2((bb[3] - bb[1]) * k)],
                ink=list(R.ink), skin=list(R.skin), lw=r2(R.lw * k), eyes=[], brows=[],
                mouth=dict(box=box(R.mouth_box), file="character/mouth.png", l=r2((R.m_l - bb[0]) * k), r=r2((R.m_r - bb[0]) * k),
                           top=r2((R.m_top - bb[1]) * k), bot=r2((R.m_bot - bb[1]) * k), scale=r2(k)),
                smile_eyes_max=charmod.SMILE_EYES_MAX)
    for j, (b, crop) in enumerate(R.eyes):
        f = f"character/eye{j}.png"; files[f] = img(crop); meta["eyes"].append(dict(box=box(b), file=f))
    for j, ((x0, y0), spr, _) in enumerate(R.brows):
        f = f"character/brow{j}.png"; files[f] = img(spr); meta["brows"].append(dict(box=box((x0, y0, x0 + spr.width, y0 + spr.height)), file=f))
    return meta, files


def _audio(R):
    """voice, ducked music bed, one sample per SFX kind + the event list (the app mixes them with its own volumes)."""
    n = int(R.END * audio.SR) + audio.SR; V = np.zeros(n); V[:len(R.voice)] = R.voice[:n]; rng = np.random.default_rng(1)
    events = audio.soft_events(R.sfx)
    kinds = sorted({k for _, k in events}); samples = {k: audio._sfx_soft(k, rng) for k in kinds}
    duck = audio.voice_duck(V, n); mood = R.mood; mus = audio.music_soft(n, R.END, mood, duck, rng)
    A = np.zeros(n)
    for t, k in events:
        s0 = max(0, int(t * audio.SR)); sg = samples[k]; e0 = min(n, s0 + len(sg)); A[s0:e0] += sg[:e0 - s0]
    end = int(R.END * audio.SR); A = A * (1 - .25 * duck) + mus + V * .95; peak = float(np.abs(A[:end]).max() + 1e-9)
    files = {"audio/voice.wav": _wav(V[:end])}
    if mood != "none": files["audio/music.wav"] = _wav(mus[:end])
    for k, sg in samples.items(): files[f"audio/sfx/{k}.wav"] = _wav(sg)
    meta = dict(sample_rate=audio.SR, voice=dict(file="audio/voice.wav", gain=.95),
                music=dict(file="audio/music.wav", gain=1.0, mood=mood) if mood != "none" else None,
                sfx=dict(gain=.85, samples={k: f"audio/sfx/{k}.wav" for k in kinds}, events=[[round(t, 3), k] for t, k in events]),
                master=dict(peak=round(peak, 4), drive=1.15, ceiling=.93))
    return meta, files


# ------------------------------------------------------------------ export
def export(R, out, ids_file):
    t0 = time.time(); slug = os.path.splitext(os.path.basename(out))[0]; th = R.theme; files = {}
    tp = min(R.END - .1, R.SS[1] + .6 if len(R.SS) > 1 else 1.0)
    files["poster.jpg"] = _jpg(R.frame(int(tp * FPS)).resize((360, 640)))        # real theme render for the app's project list
    rec = Recorder()
    R.T.record(R, rec)
    if not rec.scenes: raise SystemExit(f"theme '{th.id}': record() produced no scenes")
    # sprites: props that change look every frame (live charts, HUD) update at 15 fps and are stored at 1x
    lowres = set()
    for tr in rec.tracks.values():
        sids = {r[1] for r in tr["rows"]}
        if len(sids) > 24 and len(sids) > .5 * len(tr["rows"]):
            for j in range(1, len(tr["rows"])):
                a, b = tr["rows"][j - 1], tr["rows"][j]
                if b[0] % 2 and a[0] == b[0] - 1: b[1] = a[1]
            lowres |= {r[1] for r in tr["rows"]}
    used = {r[1] for tr in rec.tracks.values() for r in tr["rows"]}; sprites = {}
    for sid, (im, w, h, ss) in rec.sprites.items():
        if sid not in used: continue
        lo = sid in lowres and im.width > 64 and ss > 1
        if lo: im = im.resize((max(1, im.width // ss), max(1, im.height // ss)), Image.LANCZOS)
        fn = f"sprites/{sid}.webp"; files[fn] = _webp(im); sprites[sid] = dict(file=fn, w=r2(w), h=r2(h), ss=1 if lo else ss)
    char = None
    if R.char:
        char, rf = rig(R.char)
        for fn, im in rf.items(): files[fn] = _png(im)
    am, af = _audio(R); files.update(af)
    for fn in th.meta["fonts"]: files[f"fonts/{fn}"] = open(th.path("fonts", fn), "rb").read()
    L = R.spec["lines"]
    def ws(l, k):
        v = l.get(k, []) or []; return [str(x) for x in ([v] if isinstance(v, (str, int, float)) else v)]
    lines = [dict(say=str(l["say"]), expr=l.get("expr", "neutral"), emph=ws(l, "emph"), emph_blue=ws(l, "emph_blue"),
                  highlight=ws(l, "highlight"), boom=ws(l, "boom"), start=r2(R.SS[i]), end=r2(R.SE[i])) for i, l in enumerate(L)]
    timeline = dict(
        fps=FPS, frames=R.N, width=W, height=H, duration=r2(R.END), camera=rec.camera, style=th.meta["style"],
        lines=lines, words=[[w, round(a, 3), round(b, 3), li] for w, a, b, li in R.words],
        levels=[round(float(v), 3) for v in R.lvl], bright=[round(float(v), 3) for v in R.bri],
        scenes=rec.scenes, shatters=rec.shatters, sprites=sprites, tracks=list(rec.tracks.values()), anchors=rec.anchors,
        fx=dict(flash=rec.flash, shake=rec.shake, cracks=rec.cracks), character=char, audio=am)
    reel_id, rev = identity(slug, ids_file)
    manifest = dict(format="frame", formatVersion=FORMAT_VERSION, slug=slug, reelId=reel_id, revision=rev, title=R.spec.get("title", slug),
                    createdAt=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    generator=dict(name="frameditor", version=_git_version()),
                    theme=dict(id=th.id, name=th.meta["name"], version=th.meta["version"], kind=th.meta["kind"]),
                    character=dict(name=R.char, style="sprite", version=1) if R.char else None,
                    canvas=dict(width=W, height=H, fps=FPS), frames=R.N, duration=r2(R.END), poster="poster.jpg")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True); tmp = out + ".part"
    with zipfile.ZipFile(tmp, "w") as z:
        z.writestr("manifest.json", json.dumps(manifest, indent=1), compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("timeline.json", json.dumps(timeline, separators=(",", ":"), ensure_ascii=False), compress_type=zipfile.ZIP_DEFLATED)
        for fn, data in sorted(files.items()):                     # PNG/JPG/WebP are already compressed: store them
            z.writestr(fn, data, compress_type=zipfile.ZIP_STORED if fn.endswith((".png", ".jpg", ".webp")) else zipfile.ZIP_DEFLATED)
    os.replace(tmp, out)
    mb = os.path.getsize(out) / 1e6
    print(f"frame: {out}  ({mb:.1f} MB, {R.END:.1f}s, {len(sprites)} sprites, {len(rec.tracks)} tracks, {len(am['sfx']['events'])} sfx) "
          f"v{rev} in {time.time() - t0:.0f}s")
    if mb > 60: print("frame WARNING: file is large; check for props that change every frame (live charts) or very big photos")
    return out
