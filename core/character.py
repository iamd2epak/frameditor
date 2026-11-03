"""Sprite characters: ONE fixed PNG (e.g. a cartoon head); only the eyes, brows and mouth move.

A theme with a character declares it in theme.json (one character per theme, see docs/THEMES.md):
  "character": {"name": "Max", "style": "sprite", "image": "character/max.png", "skin": [254,214,182], "ink": [18,18,20],
                "eyes":  [[x0,y0,x1,y1], [x0,y0,x1,y1]],   # rectangles around each eye (inside any glasses rim)
                "brows": [[x0,y0,x1,y1], [x0,y0,x1,y1]],
                "mouth": [x0,y0,x1,y1]}                    # rectangle around the drawn (closed) mouth
Coordinates are pixels in the PNG. The original eyes/mouth are kept for the "open"/"closed" states; blinking, talking and
brow moves are drawn on top in the same ink style. The .frame exporter ships this rig so the app animates the face live.

Motion: mouth follows loudness (shape follows brightness: ee -> wide, oo -> round), blink every ~3 s, brows by `expr`
(neutral | happy | surprised | thinking | sad | angry | wink).
"""
import math, os
from functools import lru_cache
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage

SS = 3   # supersampling for drawn parts

def _box(b): return tuple(int(v) for v in b)

class Rig:
    def __init__(self, cfg):
        self.cfg = cfg
        src = Image.open(cfg["image"]).convert("RGBA")       # absolute path (set by core/theme.py)
        self.skin = tuple(cfg.get("skin", (254, 214, 182))); self.ink = tuple(cfg.get("ink", (18, 18, 20)))
        self.src = src
        base = src.copy(); a = np.array(base)
        # brows: ink mask (dark pixels) inside each brow box -> erased to skin, kept as movable sprites
        self.brows = []
        for b in cfg.get("brows", []):
            x0, y0, x1, y1 = _box(b); reg = a[y0:y1, x0:x1, :3].astype(int)
            m = reg.max(axis=2) < 150; m = ndimage.binary_dilation(m, iterations=3)
            mi = Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.2))
            spr = Image.new("RGBA", (x1 - x0, y1 - y0), (*self.ink, 0)); spr.paste(src.crop((x0, y0, x1, y1)), (0, 0), mi)
            self.brows.append(((x0, y0), spr, mi))
            mm = ndimage.binary_dilation(m, iterations=3)
            sub = a[y0:y1, x0:x1]; sub[mm, :3] = self.skin
        # eyes + mouth: whole rectangles are kept as "open"/"closed" crops, then erased to skin
        self.eyes = [(_box(b), src.crop(_box(b))) for b in cfg.get("eyes", [])]
        mb = _box(cfg["mouth"]); self.mouth_box = mb; self.mouth_orig = src.crop(mb)
        for (x0, y0, x1, y1), _ in self.eyes: a[y0:y1, x0:x1, :3] = self.skin
        x0, y0, x1, y1 = mb; a[y0:y1, x0:x1, :3] = self.skin
        self.clean = Image.fromarray(a)
        # mouth geometry from the original line: endpoints + lowest point
        mo = np.array(self.mouth_orig)[..., :3].max(axis=2) < 120
        ys, xs = np.nonzero(mo)
        self.m_l, self.m_r = x0 + xs.min(), x0 + xs.max()
        self.m_top = y0 + ys[xs <= xs.min() + 6].mean() if len(ys) else (y0 + y1) / 2
        self.m_bot = y0 + ys.max()
        self.lw = max(6, int((x1 - x0) * .028))

    # ---------- parts ----------
    def _eye(self, im, k, state):
        (x0, y0, x1, y1), crop = self.eyes[k]
        if state == "open": im.alpha_composite(crop, (x0, y0)); return
        w, h = x1 - x0, y1 - y0; cy = y0 + h * .55
        if state == "half":
            sq = crop.resize((w, max(2, int(h * .45))), Image.LANCZOS); im.alpha_composite(sq, (x0, int(cy - sq.height / 2)))
            L = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0)); d = ImageDraw.Draw(L)
            yy = (cy - sq.height / 2 - y0) * SS
            d.line([(6 * SS, yy + 4 * SS), (w * SS / 2, yy - 2 * SS), (w * SS - 6 * SS, yy + 4 * SS)], fill=self.ink, width=self.lw * SS, joint="curve")
            im.alpha_composite(L.resize((w, h), Image.LANCZOS), (x0, y0)); return
        L = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0)); d = ImageDraw.Draw(L)
        if state == "happy":      # ^ ^ smiling eye
            pts = [(w * SS * (.12 + .76 * u), (h * .62 - math.sin(math.pi * u) * h * .3) * SS) for u in np.linspace(0, 1, 24)]
        else:                     # closed (blink): lid curve bending down
            pts = [(w * SS * (.1 + .8 * u), (h * .5 + math.sin(math.pi * u) * h * .14) * SS) for u in np.linspace(0, 1, 24)]
        d.line(pts, fill=self.ink, width=int(self.lw * 1.15 * SS), joint="curve")
        for p in (pts[0], pts[-1]): r = self.lw * .58 * SS; d.ellipse((p[0] - r, p[1] - r, p[0] + r, p[1] + r), fill=self.ink)
        im.alpha_composite(L.resize((w, h), Image.LANCZOS), (x0, y0))

    def _brows(self, im, expr, tdy=0.0):
        for k, ((x0, y0), spr, _) in enumerate(self.brows):
            dy, rot = {"surprised": (-16, 0), "happy": (-6, 0), "angry": (8, (-9 if k == 0 else 9)), "sad": (-6, (8 if k == 0 else -8)),
                       "thinking": ((-14, 4) if k == 1 else (4, 0)), "wink": (-4, 0)}.get(expr, (0, 0))
            dy += tdy
            s = spr.rotate(rot, resample=Image.BICUBIC, expand=False) if rot else spr
            im.alpha_composite(s, (x0, int(y0 + dy)))

    def _mouth(self, im, lv, wide, rnd, expr):
        x0, y0, x1, y1 = self.mouth_box
        if lv < .07 and expr not in ("surprised", "sad", "angry"):
            im.alpha_composite(self.mouth_orig, (x0, y0)); return
        cx = (self.m_l + self.m_r) / 2; hw0 = (self.m_r - self.m_l) / 2
        pad = 140; ox, oy = int(cx - hw0 - pad), int(self.m_top - pad)
        Wd, Hd = int(2 * hw0 + 2 * pad), int(pad * 2 + 220)
        L = Image.new("RGBA", (Wd * SS, Hd * SS), (0, 0, 0, 0)); d = ImageDraw.Draw(L)
        X = lambda x: (x - ox) * SS; Y = lambda y: (y - oy) * SS
        ink = self.ink; lw = self.lw * SS
        if lv < .07:
            if expr == "surprised": lv, rnd = .35, 1.0
            else:   # sad / angry: flat, slightly down-turned line
                pts = [(X(cx - hw0 * .55 + 2 * hw0 * .55 * u), Y(self.m_top + 22 - math.sin(math.pi * u) * 10)) for u in np.linspace(0, 1, 20)]
                d.line(pts, fill=ink, width=lw, joint="curve")
                for p in (pts[0], pts[-1]): r = lw * .5; d.ellipse((p[0] - r, p[1] - r, p[0] + r, p[1] + r), fill=ink)
                im.alpha_composite(L.resize((Wd, Hd), Image.LANCZOS), (ox, oy)); return
        smile = self.m_bot - self.m_top
        hw = hw0 * (.62 + .22 * wide - .30 * rnd + (.08 if expr in ("happy", "wink") else 0))
        top = self.m_top + smile * .25; dep = smile * .55 + 16 + 72 * lv + 10 * rnd
        up = [(cx - hw + 2 * hw * u, top + smile * .5 * math.sin(math.pi * u) * (1 - .6 * rnd)) for u in np.linspace(0, 1, 30)]
        lo = [(cx + hw - 2 * hw * u, top + dep * math.sin(math.pi * u) ** (.8 + .6 * rnd)) for u in np.linspace(0, 1, 30)]
        poly = [(X(x), Y(y)) for x, y in up + lo]
        d.polygon(poly, fill=(92, 30, 36))
        M = Image.new("L", L.size, 0); ImageDraw.Draw(M).polygon(poly, fill=255)
        part = Image.new("RGBA", L.size, (0, 0, 0, 0)); pd = ImageDraw.Draw(part)
        pd.ellipse((X(cx - hw * .62), Y(top + dep * .62), X(cx + hw * .62), Y(top + dep * 1.25)), fill=(238, 112, 118))   # tongue
        tw = [(X(x), Y(y)) for x, y in up] + [(X(x), Y(y + 8 + 12 * lv)) for x, y in reversed(up)]
        pd.polygon(tw, fill=(255, 255, 255))                                                                    # top teeth
        Lp = Image.new("RGBA", L.size, (0, 0, 0, 0)); Lp.paste(part, (0, 0), Image.fromarray(np.minimum(np.array(part.getchannel("A")), np.array(M))))
        L.alpha_composite(Lp)
        d.line(poly + [poly[0]], fill=ink, width=lw, joint="curve")
        for p in (poly[0], poly[len(up) - 1]):
            r = lw * .55; d.ellipse((p[0] - r, p[1] - r, p[0] + r, p[1] + r), fill=ink)
        im.alpha_composite(L.resize((Wd, Hd), Image.LANCZOS), (ox, oy))

    def face(self, lv=0.0, wide=.5, rnd=0.0, expr="neutral", blink=0, brow_dy=0.0, smile_eyes=True):
        """full-res RGBA head. blink: 0 open, 1 half, 2 closed. smile_eyes=False keeps the eyes open on happy/wink."""
        im = self.clean.copy()
        self._brows(im, expr, brow_dy)
        for k in range(len(self.eyes)):
            st = "closed" if blink == 2 else "half" if blink == 1 else ("happy" if smile_eyes and (expr == "happy" or (expr == "wink" and k == 1)) else "open")
            if expr == "angry" and blink == 0: st = "half"
            self._eye(im, k, st)
        self._mouth(im, lv, wide, rnd, expr)
        return im.crop(self.src.getbbox())

CHARS = {}          # name -> config (registered by core/theme.py from the theme's theme.json)
_RIGS = {}
def get_rig(name, cfg=None):
    if name not in _RIGS: _RIGS[name] = Rig(cfg or CHARS[name])
    return _RIGS[name]

@lru_cache(maxsize=2048)
def _face_cached(name, lv, wide, rnd, expr, blink, bdy, smile_eyes):
    return get_rig(name).face(lv / 10, wide / 4, rnd / 4, expr, blink, bdy, smile_eyes)

def face(name, lv, wide, rnd, expr, blink, brow_dy=0, smile_eyes=True):
    return _face_cached(name, int(round(min(1, lv) * 10)), int(round(wide * 4)), int(round(min(1, rnd) * 4)), expr, int(blink), int(brow_dy), bool(smile_eyes))

SMILE_EYES_MAX = {"happy": 1.8, "wink": 1.3}   # closed/smiling eyes only briefly, then open while talking
EXPRESSIONS = ("neutral", "happy", "surprised", "thinking", "sad", "angry", "wink")
