"""Reel = spec + theme + voice timing. Theme-agnostic: it knows lines, words, scenes and SFX events, never pixels.

Themes read these fields (see docs/THEMES.md):
  R.spec, R.dir (spec folder), R.theme (core.theme.Theme), R.T (theme.py module), R.char (character name or None)
  R.lines (say texts), R.SS / R.SE (line start/end seconds), R.words [(word, start, end, line)], R.END, R.N (frames)
  R.lvl / R.bri (voice loudness / brightness per frame, 0..1, for lip-sync), R.emph_words
  R.main [[first_line, last_line, scene_dict]], R.mainb [(start, end, scene_dict, Ctx)], R.sfx {(t, kind)}
  R.line_at(t), R.scene_index(t), Ctx.cue(word | seconds)
"""
import hashlib, json, os
import soundfile as sf
from . import audio, media, spec as specmod
from .util import CACHE, FPS


class Ctx:
    """timing context of one scene: cue words resolve to the moment they are spoken inside the scene's lines."""

    def __init__(self, R, start, end, lines):
        self.R, self.start, self.end, self.lines = R, start, end, lines

    def cue(self, tok, k=0, default=None):
        if isinstance(tok, (int, float)): return self.start + float(tok)
        if isinstance(tok, str) and tok:
            tl = tok.lower().strip(".,!?'\"…:;।")
            for w, a, b, li in self.R.words:
                if li in self.lines and w.lower().strip(".,!?'\"…:;।").startswith(tl): return a
        return default if default is not None else self.start + .35 + .3 * k

    def sfx(self, t, kind): self.R.sfx.add((round(t, 1), kind))


class Reel:
    def __init__(self, spec, spec_dir, theme):
        self.spec, self.dir, self.theme, self.T = spec, spec_dir, theme, theme.mod
        self.char = theme.character
        media.SEARCH.insert(0, spec_dir)
        self.lines = [str(l["say"]) for l in spec["lines"]]; self.sfx = set()
        self.emph_words = {str(w).lower().strip(".,!?") for l in spec["lines"] for w in l.get("emph", [])}
        self._voice(); self._blocks()
        if hasattr(self.T, "setup"): self.T.setup(self)

    @property
    def mood(self): return self.spec.get("music", self.theme.meta.get("music", "bright"))

    # ---------- voice + timing ----------
    def _voice(self):
        v = self.spec.get("voice", {}) or {}; mode = v.get("mode", "kokoro")
        ovk = {i: l["start"] for i, l in enumerate(self.spec["lines"]) if "start" in l}
        fp = None
        if mode == "file": fp = v["file"] if os.path.isabs(v["file"]) else os.path.join(self.dir, v["file"])
        sig = [self.lines, v, ovk, os.path.getmtime(fp) if fp else 0]
        cache = os.path.join(CACHE, "voice_" + hashlib.md5(json.dumps(sig, sort_keys=True).encode()).hexdigest()[:12])
        words = None
        if mode == "file" and v.get("align", "asr") == "asr":
            # word-level timing from the audio itself (core/align.py); `start:` = hard anchor for lines the ASR can't hear
            wc = cache + ".words.json"
            if os.path.exists(wc) and os.path.exists(cache + ".wav"):
                self.voice, _ = sf.read(cache + ".wav"); words = [tuple(x) for x in json.load(open(wc))]
            else:
                from . import align
                if align.ensure_model():
                    self.voice = audio.load_file(fp); words, m, n = align.word_times(self.voice, self.lines, starts=ovk)
                    print(f"word alignment: {m}/{n} words anchored by ASR, rest interpolated on the voiced audio")
                    sf.write(cache + ".wav", self.voice, audio.SR); json.dump(words, open(wc, "w"))
        if words:
            spans = [[(min(w[1] for w in words if w[3] == li), max(w[2] for w in words if w[3] == li))] for li in range(len(self.lines))]
        elif os.path.exists(cache + ".wav") and os.path.exists(cache + ".json"):
            self.voice, _ = sf.read(cache + ".wav"); spans = json.load(open(cache + ".json"))
        elif mode == "file":
            self.voice = audio.load_file(fp); spans = audio.align_file(self.voice, self.lines, ovk)
            sf.write(cache + ".wav", self.voice, audio.SR); json.dump(spans, open(cache + ".json", "w"))
        else:
            self.voice, spans = audio.kokoro_lines(self.lines, v.get("name", "am_michael"), v.get("speed", 1.07), v.get("lang", "en-us"))
            sf.write(cache + ".wav", self.voice, audio.SR); json.dump(spans, open(cache + ".json", "w"))
        self.spans = [[tuple(s) for s in sp] for sp in spans]
        self.SS = [float(sp[0][0]) for sp in self.spans]; self.SE = [float(sp[-1][1]) for sp in self.spans]
        ws = [tuple(w) for w in words] if words else audio.word_times(self.lines, self.spans)
        self.words = [(w, float(a), float(b), int(li)) for w, a, b, li in ws]       # plain floats (numpy floats break PIL blur radii)
        self.END = max(self.SE[-1] + 1.6, len(self.voice) / audio.SR + .3); self.N = int(self.END * FPS)
        self.lvl = audio.levels(self.voice, self.N, FPS)
        self.bri = audio.brightness(self.voice, self.N, FPS)
        print("line timings:"); [print(f"  {i:2d}  {self.SS[i]:6.2f}-{self.SE[i]:6.2f}  {l[:60]}") for i, l in enumerate(self.lines)]

    def _blocks(self):
        """a scene starts at every line with `scene:` (line 0 always starts one) and runs until the next."""
        L = self.spec["lines"]; self.main = []
        default = getattr(self.T, "DEFAULT_SCENE", {})
        for i, l in enumerate(L):
            if "scene" in l or i == 0: self.main.append([i, i, l.get("scene", default)])
            else: self.main[-1][1] = i
        self.mainb = []
        for a, b, S in self.main:
            st = (self.SS[a] - .15) if a > 0 else 0; en = (self.SS[b + 1] - .15) if b + 1 < len(L) else self.END
            self.mainb.append((st, en, S, Ctx(self, st, en, set(range(a, b + 1)))))
        self.n_scenes = len(self.main)

    # ---------- queries ----------
    def scene_index(self, t): return max(k for k, b in enumerate(self.mainb) if t >= b[0])
    def line_at(self, t): return max([k for k, s in enumerate(self.SS) if t >= s - .15], default=0)

    def frame(self, i):
        """full RGB frame i drawn by the theme (previews + the .frame poster)."""
        return self.T.frame(self, i / FPS, i).convert("RGB")


def open_reel(spec_path, strict=True):
    """load + validate a spec, load its theme, build the Reel. Exits with clear messages on errors."""
    from .theme import Theme
    s = specmod.load(spec_path); d = os.path.dirname(os.path.abspath(spec_path))
    E, Wn = specmod.validate(s)
    if E: raise specmod.SpecError("spec errors:\n  " + "\n  ".join(E))
    th = Theme(s["theme"])
    E, Wn = specmod.validate(s, th, d)
    for w in Wn: print("spec warning:", w)
    if E: raise specmod.SpecError("spec errors:\n  " + "\n  ".join(E))
    return Reel(s, d, th)
