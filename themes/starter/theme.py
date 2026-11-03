"""starter — the minimal free theme, and the template for your own theme pack (copy this folder, rename, change it).

Look: soft gradient page (theme.json style.background), white rounded cards / images in the top area that pop in on
their cue word and fade out at the scene end, kinetic caption at the bottom (style.caption, drawn by core/look.py here
and by the app on the phone). No character (kind: faceless).

Scene (one per line that starts a new visual):
  scene: {type: cards, title: "Short heading", layout: column | row | grid,
          items: [{text: "Write the script", cue: script}, {image: photo.jpg, cue: photo}, ...]}   # max 4 items

Engine contract (docs/THEMES.md): setup(R), frame(R, t, i) -> RGBA preview frame, record(R, rec) -> .frame data, check(spec).
"""
import json, math, os
from PIL import Image, ImageDraw
from core import look, media
from core.util import FPS, W, ease, font

HERE = os.path.dirname(os.path.abspath(__file__))
STYLE = json.load(open(os.path.join(HERE, "theme.json")))["style"]
PAL = {k: tuple(v) for k, v in STYLE["palette"].items()}
DEFAULT_SCENE = {"type": "cards", "items": []}
SS = 2                                  # sprites are drawn at 2x for crisp edges
TOP, BOTTOM = 300, 1300                 # content area (captions own the bottom; keep 90 px side margins)
MAX_ITEMS = 4


# ------------------------------------------------------------------ sprites (drawn once, at SS x)
def _card(text, w=760):
    f = font("Manrope-Bold.ttf", 54 * SS); d = ImageDraw.Draw(Image.new("L", (1, 1)))
    words, rows = str(text).split(), [[]]
    for wd in words:                                             # wrap to the card width
        if rows[-1] and d.textlength(" ".join(rows[-1] + [wd]), font=f) > (w - 96) * SS: rows.append([])
        rows[-1].append(wd)
    rows = [" ".join(r) for r in rows][:3]; lh = 70 * SS; h = (len(rows) * 70 + 80) * SS
    im = Image.new("RGBA", (w * SS, h), (0, 0, 0, 0)); g = ImageDraw.Draw(im)
    g.rounded_rectangle((0, 0, w * SS - 1, h - 1), radius=36 * SS, fill=(*PAL["card"], 255), outline=(*PAL["line"], 255), width=2 * SS)
    for k, r in enumerate(rows): g.text((w * SS / 2, 40 * SS + lh * k + lh / 2), r, font=f, fill=(*PAL["ink"], 255), anchor="mm")
    return im


def _title(text):
    f = font("Manrope-ExtraBold.ttf", 76 * SS); d = ImageDraw.Draw(Image.new("L", (1, 1))); tw = int(d.textlength(str(text), font=f))
    im = Image.new("RGBA", (tw + 40 * SS, 110 * SS), (0, 0, 0, 0)); ImageDraw.Draw(im).text((20 * SS, 55 * SS), str(text), font=f, fill=(*PAL["accent"], 255), anchor="lm")
    return im


def _image(src, box=420):
    im = media.load(src); k = box * SS / max(im.size)
    im = im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.LANCZOS)
    m = Image.new("L", im.size, 0); ImageDraw.Draw(m).rounded_rectangle((0, 0, im.width - 1, im.height - 1), radius=28 * SS, fill=255)
    out = Image.new("RGBA", im.size, (0, 0, 0, 0)); out.paste(im, (0, 0), m); return out


# ------------------------------------------------------------------ layout: every prop gets a sprite, a centre and a cue time
def _layout(n, layout):
    if layout == "row": return [(W / (n + 1) * (k + 1), 800) for k in range(n)]
    if layout == "grid": return [(330 + 420 * (k % 2), 640 + 380 * (k // 2)) for k in range(n)]
    gap = min(300, (BOTTOM - TOP - 200) / max(1, n)); y0 = 820 - gap * (n - 1) / 2
    return [(W / 2, y0 + gap * k) for k in range(n)]


def setup(R):
    R._cap = look.Caption(STYLE, R); R._props = []
    for k, (st, en, S, ctx) in enumerate(R.mainb):
        S = S or {}; items = (S.get("items") or [])[:MAX_ITEMS]; props = []
        if S.get("title"): props.append(dict(id="title", kind="title", spr=_title(S["title"]), x=W / 2, y=TOP + 60, t0=st + .05))
        lay = S.get("layout", "row" if len(items) >= 3 and all("image" in it for it in items) else "column")
        for j, ((x, y), it) in enumerate(zip(_layout(len(items), lay), items)):
            spr = _image(it["image"], 300 if lay != "column" else 420) if it.get("image") else _card(it.get("text", ""), 420 if lay != "column" else 760)
            props.append(dict(id=f"item{j}", kind="image" if it.get("image") else "card", spr=spr, x=x, y=y, t0=ctx.cue(it.get("cue"), j, default=st + .2 + .25 * j)))
        for p in props: R.sfx.add((round(p["t0"], 1), "pop"))
        R._props.append((st, en, props))


def _pose(p, t, en):
    """spring pop-in at the cue (scale .6 -> 1, rise 40 px), fade + shrink out over the last .25 s of the scene."""
    u = (t - p["t0"]) / .45
    if u <= 0: return None
    e = 1 - math.exp(-6 * u) * math.cos(7 * u) if u < 1.6 else 1.0
    a = min(1.0, u * 2.5); s = .6 + .4 * e; dy = 40 * (1 - ease(u))
    if t > en - .25: q = (t - (en - .25)) / .25; a *= 1 - q; s *= 1 - .1 * q
    return p["x"], p["y"] + dy, s, a


def _active(R, t):
    for st, en, props in R._props:
        if st <= t < en: return en, props
    return None, []


def frame(R, t, i):
    f = look.background(STYLE, t); en, props = _active(R, t)
    for p in props:
        q = _pose(p, t, en)
        if not q: continue
        x, y, s, a = q; im = p["spr"]; w, h = max(1, int(im.width / SS * s)), max(1, int(im.height / SS * s))
        im = im.resize((w, h), Image.LANCZOS)
        if a < 1: im.putalpha(im.getchannel("A").point(lambda v: int(v * a)))
        f.alpha_composite(im, (int(x - w / 2), int(y - h / 2)))
    R._cap.draw(f, t); return f


def record(R, rec):
    for k, (st, en, props) in enumerate(R._props):
        a, b = R.main[k][0], R.main[k][1]
        rec.scenes.append(dict(index=k, start=round(st, 2), end=round(en, 2), compose="cards", lines=[a, b],
                               label=R.spec["lines"][a]["say"][:48], overlays={}, anchor_sizes={}))
    for i in range(R.N):
        rec.frame = i; t = i / FPS; en, props = _active(R, t)
        k = R.scene_index(t)
        for p in props:
            q = _pose(p, t, en)
            if not q: continue
            tr = rec.track(f"{k}:{p['id']}", k, p["id"], p["kind"], label=f"{p['kind']}: {p['id']}")
            rec.row(tr, rec.sid(p["spr"], SS), q[0], q[1], s=q[2], a=q[3])


def check(spec):
    out = []
    for i, l in enumerate(spec.get("lines", [])):
        S = l.get("scene")
        if not isinstance(S, dict): continue
        if S.get("type", "cards") != "cards": out.append(f"lines[{i}].scene.type must be 'cards' in the starter theme")
        if len(S.get("items", []) or []) > MAX_ITEMS: out.append(f"lines[{i}]: max {MAX_ITEMS} items per scene (extra items are dropped)")
    return out
