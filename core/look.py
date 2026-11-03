"""Generic page background + kinetic caption, drawn from a theme's theme.json `style` block.

The Frameditor app draws the background and captions itself from the same `style` block (docs/FORMAT.md), so a theme that
uses these helpers for its previews gets previews that match the app. Supported:
  style.background.type: solid {color} | gradient {top, bottom} | blooms {color, blooms: [[rgb, x, y, r, speed]...], vignette}
  style.caption.type:    kinetic {y, sizes, row, max_width, font, emph_font, emph_scale, colors{ink, emph, emph_blue, highlight}}
"""
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from .util import W, H, ease, font

_GW, _GH = 135, 240
_yy, _xx = np.mgrid[0:_GH, 0:_GW]; _xx = _xx / _GW; _yy = _yy / _GH * (16 / 9)


def background(style, t):
    b = style["background"]; kind = b.get("type", "solid")
    if kind == "solid": return Image.new("RGBA", (W, H), (*b["color"], 255))
    if kind == "gradient":
        top, bot = np.array(b["top"], float), np.array(b["bottom"], float); k = np.linspace(0, 1, _GH)[:, None, None]
        img = np.broadcast_to(top + (bot - top) * k, (_GH, _GW, 3))
        return Image.fromarray(img.astype(np.uint8)).resize((W, H), Image.BICUBIC).convert("RGBA")
    if kind == "blooms":
        img = np.broadcast_to(np.array(b["color"], float), (_GH, _GW, 3)).copy()
        for k, (col, bx, by, r, sp) in enumerate(b.get("blooms", [])):
            cx = bx + .06 * math.sin(t * sp * 2.1 + k * 1.7); cy = (by + .05 * math.cos(t * sp * 1.7 + k)) * (16 / 9)
            m = np.exp(-(((_xx - cx) ** 2 + (_yy - cy) ** 2) / (2 * (r * .62) ** 2)))[..., None] * .55
            img = img + (np.array(col, float) - img) * m
        vg = 1 - b.get("vignette", 0) * (((_xx - .5) ** 2) * 2 + ((_yy / (16 / 9) - .5) ** 2) * 2)[..., None]
        return Image.fromarray(np.clip(img * vg, 0, 255).astype(np.uint8)).resize((W, H), Image.BICUBIC).convert("RGBA")
    raise SystemExit(f"style.background.type '{kind}' is not supported (solid | gradient | blooms)")


def _norm(w, chars=".,!?\"'…:;"): return w.lower().strip(chars)


def _sty(l, w):
    k = _norm(w)
    if k in [_norm(x) for x in l.get("emph_blue", [])]: return "blue"
    if k in [_norm(x) for x in l.get("emph", [])]: return "emph"
    return "ink"


class Caption:
    """kinetic caption: the spoken words blur + rise in one by one; pages of max 2 rows; boom words slam big."""

    def __init__(self, style, R):
        self.c = c = style["caption"]; self.R = R
        if c.get("type", "kinetic") != "kinetic": raise SystemExit(f"style.caption.type '{c.get('type')}' is not supported (kinetic)")
        self.cols = {k: tuple(c["colors"][x]) for k, x in (("ink", "ink"), ("emph", "emph"), ("blue", "emph_blue"))}
        self.hl = tuple(c["colors"].get("highlight", (255, 218, 200))); self.pages = self._pages()

    def _font(self, sty, size):
        c = self.c
        return font(c.get("emph_font", c["font"]), size * c.get("emph_scale", 1.0)) if sty == "emph" else font(c["font"], size)

    def _rows(self, li, idx, size, d):
        R = self.R; rows = [[]]; roww = 0; sp = d.textlength(" ", font=self._font("ink", size))
        for j in idx:
            w = R.words[j][0]; sty = _sty(R.spec["lines"][li], w); ww = d.textlength(w, font=self._font(sty, size))
            need = ww if not rows[-1] else roww + sp + ww
            if need > self.c["max_width"]: rows.append([]); need = ww
            rows[-1].append((j, w, sty, ww)); roww = need
        return rows

    def _pages(self):
        R = self.R; d = ImageDraw.Draw(Image.new("L", (1, 1))); pages = []; sizes = self.c["sizes"]
        for li in range(len(R.lines)):
            idx = [j for j, w in enumerate(R.words) if w[3] == li]
            if not idx: continue
            for size in sizes:
                rows = self._rows(li, idx, size, d)
                if len(rows) <= 2: pages.append((size, rows)); break
            else:
                rows = self._rows(li, idx, sizes[0], d)
                for k in range(0, len(rows), 2): pages.append((sizes[0], rows[k:k + 2]))
        out = [[R.words[rows[0][0][0]][1] - .08, None, rows, size] for size, rows in pages]
        for k in range(len(out)): out[k][1] = out[k + 1][0] if k + 1 < len(out) else R.END + 1
        return out

    def draw(self, f, t, shake=(0, 0)):
        R = self.R; ROW = self.c["row"]
        for a, b, rows, size in self.pages:
            if not (a - .05 <= t < b + .28): continue
            out = ease((t - b) / .28) if t >= b else 0.0
            L = Image.new("RGBA", (W, ROW * 2 + 80), (0, 0, 0, 0)); y0 = 40 + (ROW * (2 - len(rows))) / 2
            for r, row in enumerate(rows):
                sp = ImageDraw.Draw(L).textlength(" ", font=self._font("ink", size)); tw = sum(x[3] for x in row) + sp * (len(row) - 1); x = (W - tw) / 2
                for j, w, sty, ww in row:
                    wa = R.words[j][1] - .06; u = (t - wa) / .32
                    if u <= 0: x += ww + sp; continue
                    e = ease(u); l = R.spec["lines"][R.words[j][3]]
                    wi = Image.new("RGBA", (int(ww + 60), ROW + 50), (0, 0, 0, 0)); wd = ImageDraw.Draw(wi)
                    if _norm(w) in [_norm(h) for h in l.get("highlight", [])]:
                        hp = ease((t - wa - .15) / .35); wd.rounded_rectangle((22, 30 + size * .52, 22 + (ww + 16) * hp, 30 + size * 1.08), radius=10, fill=(*self.hl, 230))
                    wd.text((30, 30 + (-size * .06 if sty == "emph" else 0)), w, font=self._font(sty, size), fill=(*self.cols[sty], 255))
                    if 9 * (1 - e) > .4: wi = wi.filter(ImageFilter.GaussianBlur(float(9 * (1 - e))))
                    bw = l.get("boom"); bws = [bw] if isinstance(bw, (str, int, float)) else (bw or []); xo = yo = 0
                    if any(_norm(w).startswith(str(q).lower()) for q in bws) and u < 1.2:
                        k = 1 + .55 * (1 - _spring(u * .32)); nw, nh = int(wi.width * k), int(wi.height * k)
                        xo, yo = (nw - wi.width) / 2, (nh - wi.height) / 2; wi = wi.resize((nw, nh), Image.BICUBIC)
                    al = min(1, u * 2.2)
                    if al < 1: wi.putalpha(wi.getchannel("A").point(lambda v: int(v * al)))
                    L.alpha_composite(wi, (int(x - 30 - xo), int(y0 + r * ROW - 30 + 20 * (1 - e) - yo))); x += ww + sp
            if out > 0:
                L = L.filter(ImageFilter.GaussianBlur(float(10 * out))); L.putalpha(L.getchannel("A").point(lambda v: int(v * (1 - out))))
            f.alpha_composite(L, (int(shake[0] * .5), int(self.c["y"] - ROW - 40 - 30 * out + shake[1] * .5)))


def _spring(u, zeta=.45, w=14):
    if u <= 0: return 0.0
    wd = w * math.sqrt(1 - zeta * zeta)
    return 1 - math.exp(-zeta * w * u) * (math.cos(wd * u) + zeta * w / wd * math.sin(wd * u))
