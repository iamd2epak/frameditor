"""Voice (Kokoro TTS or the user's own audio file), line/word timings, synthesized SFX samples and the soft music bed.
The app mixes voice + music + SFX itself (the .frame stores them separately), so there is no MP4 mixdown here."""
import os, re, subprocess
import numpy as np, soundfile as sf
from .util import CACHE, MODELS

SR = 24000

# ---------------- Kokoro ----------------
def kokoro_lines(lines, voice="am_michael", speed=1.07, lang="en-us", lead=0.2, gap=0.16):
    from kokoro_onnx import Kokoro
    k = Kokoro(os.path.join(MODELS, "kokoro-v1.0.onnx"), os.path.join(MODELS, "voices-v1.0.bin"))
    out = [np.zeros(int(SR * lead))]; spans = []; t = lead
    for s in lines:
        a, sr = k.create(s, voice=voice, speed=speed, lang=lang)
        if sr != SR: raise RuntimeError("unexpected sample rate")
        spans.append([(t, t + len(a) / SR)]); out.append(a); t += len(a) / SR
        out.append(np.zeros(int(SR * gap))); t += gap
    a = np.concatenate(out); a = a / (np.abs(a).max() + 1e-9) * 0.9
    # trim each span to actual voiced part
    spans = [[_trim(a, s0, s1)] for [(s0, s1)] in spans]
    return a, spans

def _trim(a, s0, s1, th=0.04):
    seg = a[int(s0 * SR):int(s1 * SR)]
    fr = np.array([np.sqrt(np.mean(seg[j:j + 240] ** 2)) for j in range(0, max(1, len(seg) - 240), 240)])
    v = np.where(fr > th)[0]
    if len(v) == 0: return (s0, s1)
    return (s0 + v[0] * 0.01, s0 + (v[-1] + 1) * 0.01)

# ---------------- custom audio ----------------
def load_file(path):
    tmp = os.path.join(CACHE, "voice_in.wav")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", path, "-ac", "1", "-ar", str(SR), tmp], check=True)
    a, _ = sf.read(tmp); return a / (np.abs(a).max() + 1e-9) * 0.9

def speech_segments(a, noise_db=-35, min_sil=0.18):
    tmp = os.path.join(CACHE, "seg.wav"); sf.write(tmp, a, SR)
    out = subprocess.run(["ffmpeg", "-i", tmp, "-af", f"silencedetect=noise={noise_db}dB:d={min_sil}", "-f", "null", "-"], capture_output=True, text=True).stderr
    ss = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", out)]; se = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", out)]
    dur = len(a) / SR; segs = []; cur = 0
    for g0, g1 in zip(ss, se + [dur]):
        if g0 > cur + 0.05: segs.append((cur, g0))
        cur = g1
    if cur < dur - 0.05: segs.append((cur, dur))
    return segs

def align_file(a, lines, overrides=None):
    """Assign speech segments to script lines. Boundaries snap to pauses, preferring long pauses
    near the position predicted by text length. overrides: {line_index: start_seconds}."""
    segs = speech_segments(a); n = len(lines)
    if len(segs) < n:  # not enough pauses: split proportionally inside the biggest segments
        s0, s1 = segs[0][0], segs[-1][1]; segs = [(s0 + (s1 - s0) * k / n, s0 + (s1 - s0) * (k + 1) / n) for k in range(n)]
    seglen = np.array([b - x for x, b in segs]); cum = np.concatenate([[0], np.cumsum(seglen)]); T = cum[-1]
    gapl = np.array([segs[j + 1][0] - segs[j][1] for j in range(len(segs) - 1)] + [0])
    w = np.array([len(re.sub(r"[^\w]", "", l)) + 3 for l in lines], float); tgt = np.cumsum(w)[:-1] / w.sum() * T
    nb, ng = n - 1, len(segs) - 1
    if nb == 0: bounds = [-1, len(segs) - 1]
    else:
        INF = 1e18; D = np.full((nb, ng), INF); B = np.zeros((nb, ng), int)
        cost = lambda i, j: ((cum[j + 1] - tgt[i]) / T) ** 2 * 40 - min(gapl[j], 1.0) * 0.6
        for j in range(ng): D[0, j] = cost(0, j)
        for i in range(1, nb):
            best, bj = INF, -1
            for j in range(ng):
                if j - 1 >= 0 and D[i - 1, j - 1] < best: best, bj = D[i - 1, j - 1], j - 1
                if bj >= 0: D[i, j] = best + cost(i, j); B[i, j] = bj
        j = int(np.argmin(D[-1])); cuts = [j]
        for i in range(nb - 1, 0, -1): j = B[i, j]; cuts.append(j)
        bounds = [-1] + cuts[::-1] + [len(segs) - 1]
    spans = [segs[bounds[i] + 1:bounds[i + 1] + 1] for i in range(n)]
    if overrides:
        starts = [sp[0][0] for sp in spans]
        for i, v in overrides.items(): starts[i] = float(v)
        ends = starts[1:] + [segs[-1][1]]
        spans = [[(max(s, x), min(e, b)) for x, b in segs if b > s and x < e] or [(s, e)] for s, e in zip(starts, ends)]
    return spans

# ---------------- word timings ----------------
def word_times(lines, spans):
    """Return list of (word, start, end, line_index) spread over each line's voiced spans."""
    out = []
    for li, (txt, sp) in enumerate(zip(lines, spans)):
        ml = [b - x for x, b in sp]; mc = np.concatenate([[0], np.cumsum(ml)]); tot = mc[-1]
        def real(v):
            k = min(len(sp) - 1, int(np.searchsorted(mc, v, side="right") - 1)); return sp[k][0] + (v - mc[k])
        ws = txt.split(); L = np.array([len(re.sub(r"[^\w]", "", x)) + 1.4 for x in ws]); c = np.concatenate([[0], np.cumsum(L)]) / L.sum() * tot
        for k, x in enumerate(ws): out.append((x, real(c[k] + 0.005), real(c[k + 1] - 0.005), li))
    return out

# ---------------- SFX samples (synthesized, no sound files needed) ----------------
def _lp(x, cut):
    """one-pole low-pass (cut in Hz, scalar or per-sample array)"""
    a = np.exp(-2 * np.pi * np.broadcast_to(np.asarray(cut, float), x.shape) / SR); y = np.empty_like(x); s = 0.0
    for i in range(len(x)): s = a[i] * s + (1 - a[i]) * x[i]; y[i] = s
    return y

def _sfx_soft(kind, rng):
    """Softer, rounder SFX for the 'soft' sound set: quiet, low-passed, short tails."""
    def T(d): return np.arange(int(d * SR)) / SR
    if kind == "pop":       # bubble blip
        t = T(.11); f = 520 + 900 * (1 - np.exp(-t * 60)); return .085 * np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 38) * np.minimum(1, t * 900)
    if kind == "tick":      # tiny wooden click
        t = T(.05); return .05 * np.sin(2 * np.pi * 1800 * t) * np.exp(-t * 140)
    if kind == "thump":     # soft sub kick
        t = T(.32); f = 48 + 90 * np.exp(-t * 22); return .26 * np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 9) * np.minimum(1, t * 400)
    if kind == "stamp":     # rubber stamp: low thud + short paper slap
        t = T(.28); f = 70 + 60 * np.exp(-t * 30); nz = _lp(rng.standard_normal(len(t)), 2400) * np.exp(-t * 55)
        return .2 * np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 14) + .12 * nz
    if kind in ("ding", "shimmer"):   # soft bell with two partials
        t = T(.9); return .045 * (np.sin(2 * np.pi * 1568 * t) + .45 * np.sin(2 * np.pi * 2349 * t) + .25 * np.sin(2 * np.pi * 3136 * t)) * np.exp(-t * 4.5) * np.minimum(1, t * 300)
    if kind == "whoosh":    # band-limited air sweep, quiet
        t = T(.42); env = np.sin(np.pi * t / t[-1]) ** 2; nz = rng.standard_normal(len(t))
        return .09 * _lp(nz, 500 + 2600 * np.sin(np.pi * t / t[-1])) * env
    if kind == "riser":     # short filtered rise into a hit
        t = T(1.0); env = (t / t[-1]) ** 2; return .05 * _lp(rng.standard_normal(len(t)), 300 + 3500 * t / t[-1]) * env
    if kind == "click":     # mouse click: two tiny plastic ticks
        t = T(.07); c = np.sin(2 * np.pi * 3200 * t) * np.exp(-t * 260); c2 = np.zeros_like(t); k = int(.028 * SR); c2[k:] = c[:len(t) - k] * .7
        return .06 * (c + c2)
    if kind == "hit":       # "haptic" impact: deep sub boom + short soft transient
        t = T(.45); f = 38 + 120 * np.exp(-t * 30); nz = _lp(rng.standard_normal(len(t)), 1800) * np.exp(-t * 70)
        return .32 * np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 7) * np.minimum(1, t * 500) + .06 * nz
    if kind == "drop":      # card falling into a bin: short thud + rattle
        t = T(.25); f = 140 + 80 * np.exp(-t * 40); return .12 * np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 18) + .03 * _lp(rng.standard_normal(len(t)), 3000) * np.exp(-t * 30)
    # ---- depth3d premium set (cinematic, still soft-limited)
    if kind == "impact":    # cinematic hit: sub drop + body thump + airy crack + short room tail
        t = T(1.1); f = 34 + 150 * np.exp(-t * 26); sub = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 4.2) * np.minimum(1, t * 600)
        body = np.sin(2 * np.pi * np.cumsum(90 + 200 * np.exp(-t * 60)) / SR) * np.exp(-t * 22)
        nz = rng.standard_normal(len(t)); crack = _lp(nz, 5200) * np.exp(-t * 48); tail = _lp(nz, 1400) * np.exp(-t * 6) * .25
        return .30 * sub + .12 * body + .07 * crack + .03 * tail
    if kind == "boom":      # deep opener boom (hook start)
        t = T(1.6); f = 30 + 70 * np.exp(-t * 9); return .30 * np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 2.6) * np.minimum(1, t * 300) + .02 * _lp(rng.standard_normal(len(t)), 900) * np.exp(-t * 5)
    if kind == "whip":      # fast whip pan
        t = T(.28); env = np.sin(np.pi * t / t[-1]) ** 3; return .11 * _lp(rng.standard_normal(len(t)), 900 + 5200 * (t / t[-1]) ** 1.5) * env
    if kind == "zip":       # rising zip as items burst out
        t = T(.36); f = 380 + 1700 * (t / t[-1]) ** 2; env = np.sin(np.pi * t / t[-1]) ** 2
        return .035 * np.sin(2 * np.pi * np.cumsum(f) / SR) * env + .05 * _lp(rng.standard_normal(len(t)), 1200 + 3000 * t / t[-1]) * env
    if kind == "sparkle":   # quick glassy arpeggio
        t = T(.7); o = np.zeros(len(t))
        for j, fr in enumerate((1760, 2217, 2637, 3520)):
            k = int(j * .055 * SR); tt = t[:len(t) - k]; o[k:] += np.sin(2 * np.pi * fr * tt) * np.exp(-tt * 9)
        return .03 * o
    if kind == "snap":      # UI snap / selection lock
        t = T(.09); return .07 * np.sin(2 * np.pi * (2400 - 9000 * t) * t) * np.exp(-t * 70) + .02 * _lp(rng.standard_normal(len(t)), 6000) * np.exp(-t * 120)
    if kind == "shatter":   # glass break: sharp crack + bright shards tinkling down
        t = T(1.2); nz = rng.standard_normal(len(t)); crack = (nz - _lp(nz, 2500)) * np.exp(-t * 30) * .16
        thud = np.sin(2 * np.pi * np.cumsum(60 + 120 * np.exp(-t * 40)) / SR) * np.exp(-t * 14) * .14; o = np.zeros(len(t))
        for j in range(9):
            k = int(rng.uniform(.03, .7) * SR); fr = rng.uniform(2600, 6200); tt = t[:len(t) - k]; o[k:] += np.sin(2 * np.pi * fr * tt) * np.exp(-tt * rng.uniform(25, 60)) * .022
        return crack + thud + o
    if kind == "scratch":   # marker scribble: two quick rough strokes
        t = T(.42); nz = _lp(rng.standard_normal(len(t)), 3800) - _lp(rng.standard_normal(len(t)), 700); env = np.zeros(len(t))
        for a0, a1 in ((.0, .17), (.19, .38)): env += np.where((t > a0) & (t < a1), np.sin(np.pi * np.clip((t - a0) / (a1 - a0), 0, 1)), 0)
        return .06 * nz * env * (1 + .4 * np.sin(2 * np.pi * 38 * t))
    if kind == "laser":     # energy shot: charge chirp + bright zap
        t = T(.42); f = 300 + 2600 * (1 - np.exp(-t * 9)); zap = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 7) * np.minimum(1, t * 400)
        nz = _lp(rng.standard_normal(len(t)), 1500 + 4000 * t / t[-1]) * np.sin(np.pi * t / t[-1]) ** 2
        return .06 * zap
    if kind == "data":      # computer HUD: fast tiny bleeps
        t = T(.6); o = np.zeros(len(t))
        for j in range(9):
            k = int(j * .062 * SR); tt = t[:max(0, min(len(t) - k, int(.04 * SR)))]; fr = rng.choice([1800, 2400, 3000, 2100])
            o[k:k + len(tt)] += np.sin(2 * np.pi * fr * tt) * np.exp(-tt * 60)
        return .03 * o
    if kind == "warp":      # time warp: reverse swell into a sub drop
        t = T(1.1); env = (t / t[-1]) ** 2.2; nz = _lp(rng.standard_normal(len(t)), 200 + 3200 * (t / t[-1]) ** 2) * env
        tone = np.sin(2 * np.pi * np.cumsum(140 + 500 * (t / t[-1]) ** 2) / SR) * env
        return .08 * nz + .04 * tone
    if kind == "swish":     # card glide
        t = T(.3); env = np.sin(np.pi * t / t[-1]) ** 2; return .05 * _lp(rng.standard_normal(len(t)), 900 + 1600 * t / t[-1]) * env
    return np.zeros(1)

SOFT_OFFSET = {"whoosh": -.18, "riser": -.9, "whip": -.1, "zip": -.12}     # sweeps start a little before their moment

def soft_events(sfx):
    """the 'soft' sound set's SFX list after de-duplication: [(start seconds, kind)] ."""
    last = {}; busy = []; out = []
    for t, k in sorted(sfx):
        if t - last.get(k, -9) < (.16 if k in ("pop", "tick", "click", "drop") else .35): continue    # de-duplicate
        if sum(1 for b in busy if t - b < .25) >= 2: continue                         # never more than 2 hits at once
        last[k] = t; busy.append(t); out.append((t + SOFT_OFFSET.get(k, 0), k))
    return out

def voice_duck(V, n):
    """0..1 voice envelope per sample (music and SFX dip a little while someone talks)."""
    hop = 240; m = n // hop; ve = np.sqrt(np.mean(V[:m * hop].reshape(m, hop) ** 2, 1)); ve = np.convolve(ve, np.ones(25) / 25, "same")
    ve = np.clip(ve / (np.percentile(ve[ve > 1e-4], 85) + 1e-9) if (ve > 1e-4).any() else ve, 0, 1); duck = np.repeat(ve, hop); return np.pad(duck, (0, n - len(duck)))

def music_soft(n, end, mood, duck, rng):
    """soft music bed (n samples), already ducked under the voice; zeros for mood 'none'."""
    mus = np.zeros(n)
    if mood != "none":
        bpm = 92 if mood == "bright" else 84; beat = 60 / bpm; mus = np.zeros(n)
        prog = [[261.6, 329.6, 392.0, 493.9], [220.0, 261.6, 329.6, 392.0], [174.6, 220.0, 261.6, 329.6], [196.0, 246.9, 293.7, 349.2]] if mood == "bright" else \
               [[130.8, 155.6, 196.0, 233.1], [103.8, 130.8, 155.6, 196.0], [116.5, 146.8, 174.6, 207.7], [98.0, 116.5, 146.8, 174.6]]
        bar = 4 * beat
        for b in range(int(end / bar) + 1):           # warm pad: detuned sines, slow attack/release per bar
            s = int(b * bar * SR); L = int(bar * SR)
            if s >= n: break
            L = min(L, n - s); t = np.arange(L) / SR; env = np.minimum(1, t / .35) * np.minimum(1, (bar - t) / .4)
            for fq in prog[b % 4]:
                for dt in (-.6, .6): mus[s:s + L] += .010 * np.sin(2 * np.pi * (fq + dt) * t) * env
            bass = prog[b % 4][0] / 2; mus[s:s + L] += .018 * np.sin(2 * np.pi * bass * t) * env
        for b in range(int(end / beat) + 1):          # soft kick on 1 & 3, light shaker on the off-beats
            s = int(b * beat * SR)
            if s >= n: break
            if b % 2 == 0:
                t = np.arange(min(int(.25 * SR), n - s)) / SR; f = 50 + 70 * np.exp(-t * 25); mus[s:s + len(t)] += .05 * np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 12)
            hs = int((b + .5) * beat * SR); hn = min(int(.04 * SR), n - hs)
            if hn > 0: mus[hs:hs + hn] += .006 * rng.standard_normal(hn) * np.exp(-np.arange(hn) / SR * 90)
        mus = _lp(mus, 5200)
        tt = np.arange(n) / SR; mus *= np.clip(tt / 1.0, 0, 1) * np.clip((end - tt) / 1.4, 0, 1) * (1 - .55 * duck)
    return mus

def levels(voice, n_frames, fps):
    hop = SR // fps
    r = np.array([np.sqrt(np.mean(voice[i * hop:(i + 1) * hop] ** 2)) if i * hop < len(voice) else 0 for i in range(n_frames)])
    nz = r[r > 0.01]; g = (np.percentile(nz, 90) if len(nz) else 1) + 1e-6
    # light AGC: quiet passages (soft starts, trailing words) still open the mouth
    from scipy.ndimage import maximum_filter1d
    loc = maximum_filter1d(r, size=max(3, int(fps * 1.2))) * .9 + 1e-6
    return np.clip(r / np.minimum(g, .5 * g + .5 * loc), 0, 1)

def brightness(voice, n_frames, fps):
    """0..1 per frame: high = bright sounds (ee/s/t → wide mouth), low = dark sounds (oo/oh → round mouth). Zero-crossing based."""
    hop = SR // fps; z = np.zeros(n_frames)
    for i in range(n_frames):
        seg = voice[i * hop:(i + 1) * hop]
        if len(seg) > 10: z[i] = np.mean(np.abs(np.diff(np.sign(seg)))) / 2
    nz = z[z > 0]
    if not len(nz): return z
    lo, hi = np.percentile(nz, 20), np.percentile(nz, 85)
    return np.clip((z - lo) / (hi - lo + 1e-9), 0, 1)
