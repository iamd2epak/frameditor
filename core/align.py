"""Word-level alignment for custom voice files (voice: {mode: file}).

An offline ASR model (NeMo Parakeet TDT via sherpa-onnx, CPU, ~650 MB, downloaded once by
tools/get_asr_model.py) transcribes the audio with per-token timestamps. Script words are then
matched to the recognised words with a fuzzy monotonic alignment (works for Hinglish: English words
and many Hindi words come through, everything in between is interpolated between the anchors and
snapped to the voiced audio). Result: captions, cues and lipsync land on the real word onsets,
including quiet starts that a plain silence detector misses.
"""
import os, re, difflib
import numpy as np
from .util import ROOT, MODELS

SR = 24000
MODEL_DIR = os.path.join(MODELS, "parakeet")


def available():
    return all(os.path.exists(os.path.join(MODEL_DIR, f)) for f in ("encoder.int8.onnx", "decoder.int8.onnx", "joiner.int8.onnx", "tokens.txt"))


def ensure_model():
    if available(): return True
    try:
        import importlib.util
        p = os.path.join(ROOT, "tools", "get_asr_model.py")
        spec = importlib.util.spec_from_file_location("get_asr_model", p); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        m.main()
    except Exception as e:
        print("ASR model download failed, falling back to pause-based timing:", e)
    return available()


# ---------------------------------------------------------------- envelope helpers
def _env(a, hop=0.01):
    n = int(SR * hop); m = len(a) // n
    return np.sqrt(np.mean(a[:m * n].reshape(m, n) ** 2, axis=1)) if m else np.zeros(1)


def _voiced_mask(a):
    e = _env(a); nz = e[e > 1e-4]
    if not len(nz): return e > 0
    th = max(np.percentile(nz, 12) * 1.8, np.percentile(nz, 90) * 0.06)
    return e > th


# ---------------------------------------------------------------- ASR
def _silences(a, min_len=0.12):
    """[(start, end)] runs of silence (10 ms resolution)."""
    v = _voiced_mask(a); out = []; k = 0
    while k < len(v):
        if not v[k]:
            j = k
            while j < len(v) and not v[j]: j += 1
            if out and k / 100 - out[-1][1] < .08: out[-1] = (out[-1][0], j / 100)   # merge pauses split by a tiny blip
            else: out.append((k / 100, j / 100))
            k = j
        else: k += 1
    return [(x, y) for x, y in out if y - x >= min_len]


def _chunks(a, max_len=10.5):
    """Split in the middle of the longest pause inside the last part of each window (chunks <= max_len s)."""
    dur = len(a) / SR; cuts = [0.0]; sil = _silences(a, .1)
    while dur - cuts[-1] > max_len:
        lo, hi = cuts[-1] + max_len * .45, cuts[-1] + max_len
        cand = [(e - s, (s + e) / 2) for s, e in sil if lo <= (s + e) / 2 <= hi]
        cuts.append(max(cand)[1] if cand else hi)
    cuts.append(dur); return list(zip(cuts, cuts[1:]))


def asr_words(a):
    """[(word, start, end)] from the audio (24 kHz mono float)."""
    import sherpa_onnx
    d = MODEL_DIR + "/"
    r = sherpa_onnx.OfflineRecognizer.from_transducer(encoder=d + "encoder.int8.onnx", decoder=d + "decoder.int8.onnx",
                                                      joiner=d + "joiner.int8.onnx", tokens=d + "tokens.txt", model_type="nemo_transducer")
    from scipy.signal import resample_poly
    a16 = resample_poly(a, 2, 3).astype(np.float32)
    toks = []
    for s, e in _chunks(a):
        st = r.create_stream(); st.accept_waveform(16000, a16[int(s * 16000):int(e * 16000)]); r.decode_stream(st)
        for tk, ts in zip(st.result.tokens, st.result.timestamps): toks.append((tk, s + ts))
    words = []
    for tk, ts in toks:
        if tk.startswith(" ") or tk.startswith("▁") or not words: words.append([tk.strip(" ▁"), ts, ts])
        else: words[-1][0] += tk; words[-1][2] = ts
    voiced = _voiced_mask(a); out = []
    for k, (w, s, last) in enumerate(words):
        nxt = words[k + 1][1] if k + 1 < len(words) else len(a) / SR
        e = max(last + .08, s + .12); j = int(e * 100)
        while j < len(voiced) and j < int(nxt * 100) and voiced[j]: j += 1   # extend through voiced audio up to the next word
        out.append((w, s, min(nxt, max(e, j / 100))))
    return [(w, s, e) for w, s, e in out if re.sub(r"[^\w]", "", w)]


# ---------------------------------------------------------------- script <-> ASR alignment
_DV_C = dict(zip(list("कखगघङचछजझञटठडढणतथदधनपफबभमयरलवशषसह") + ["क\u093c", "ख\u093c", "ग\u093c", "ज\u093c", "ड\u093c", "ढ\u093c", "फ\u093c", "ड़", "ढ़", "ज़", "फ़", "क़", "ख़", "ग़"],
                 "k kh g gh n ch chh j jh n t th d dh n t th d dh n p f b bh m y r l v sh sh s h q kh g z r rh f r rh z f q kh g".split()))
_DV_V = dict(zip("अआइईउऊऋएऐओऔऑ", "a a i i u u ri e ai o au o".split()))
_DV_M = dict(zip("ािीुूृेैोौॉ", "a i i u u ri e ai o au o".split()))


def deva2latin(w):
    """rough Devanagari -> Hinglish (for matching Hindi-script captions against the English ASR)"""
    if not re.search(r"[ऀ-ॿ]", w): return w
    out, i = [], 0
    while i < len(w):
        ch = w[i]; nx = w[i + 1] if i + 1 < len(w) else ""
        if nx == "़": ch = ch + nx; nx = w[i + 2] if i + 2 < len(w) else ""; i += 1
        if ch in _DV_C:
            out.append(_DV_C[ch])
            if nx in _DV_M: out.append(_DV_M[nx]); i += 1
            elif nx == "्": i += 1
            elif not nx or not re.match(r"[\u0900-\u097F]", nx): pass   # schwa deletion at word end
            else: out.append("a")
        elif ch in _DV_V: out.append(_DV_V[ch])
        elif ch in "ंँ": out.append("n")
        elif ch.isascii(): out.append(ch)
        i += 1
    return "".join(out)


def _norm(w):
    w = deva2latin(w).lower().replace("ph", "f").replace("w", "v").replace("ee", "i").replace("oo", "u").replace("aa", "a")
    return re.sub(r"[^a-z0-9]", "", w)


# Hindi function words as an English ASR model tends to hear them
EQUIV = {"aur": {"and", "or"}, "ka": {"car", "ca"}, "ki": {"key"}, "se": {"say", "see"}, "to": {"so", "toh"}, "mein": {"me", "main", "men"},
         "hai": {"hi", "high"}, "hain": {"hai", "hen"}, "bhi": {"be", "bee"}, "naam": {"nam", "num"}, "nahi": {"nahin", "nihi", "nahee"}}


def _sim(a, b):
    a0 = a; a, b = _norm(a), _norm(b)
    if not a or not b: return 0.0
    if a == b: return 1.0
    if b in {_norm(x) for x in set(EQUIV.get(a, ())) | EQUIV.get(deva2latin(a0).lower().strip(".,!?।"), set())}: return .9
    r = difflib.SequenceMatcher(None, a, b).ratio()
    if len(a) <= 2 or len(b) <= 2: return r if r >= .99 else r * .6   # short words only on exact matches
    return r


def align(script_words, asr):
    """Monotonic fuzzy alignment. Returns {script_index: (t0, t1)} for confident matches."""
    n, m = len(script_words), len(asr)
    S = np.zeros((n + 1, m + 1)); B = np.zeros((n + 1, m + 1), np.int8)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            wt = .45 + min(len(_norm(script_words[i - 1])), 8) / 8          # long words are more reliable anchors
            s = _sim(script_words[i - 1], asr[j - 1][0]) * wt; best, bb = S[i - 1, j], 1
            if S[i, j - 1] > best: best, bb = S[i, j - 1], 2
            if s >= .62 * wt and S[i - 1, j - 1] + s > best: best, bb = S[i - 1, j - 1] + s, 3
            if j >= 2:                                   # one script word = two recognised words ("get" + "artcraft.com")
                s2 = _sim(script_words[i - 1], asr[j - 2][0] + asr[j - 1][0])
                if s2 >= .7 and S[i - 1, j - 2] + s2 > best: best, bb = S[i - 1, j - 2] + s2, 4
            if i >= 2:                                   # two script words = one recognised word ("kar di" -> "kardi")
                s3 = _sim(script_words[i - 2] + script_words[i - 1], asr[j - 1][0])
                if s3 >= .75 and S[i - 2, j - 1] + s3 > best: best, bb = S[i - 2, j - 1] + s3, 5
            S[i, j], B[i, j] = best, bb
    i, j, M = n, m, {}
    while i > 0 and j > 0:
        b = B[i, j]
        if b == 3: M[i - 1] = (asr[j - 1][1], asr[j - 1][2]); i -= 1; j -= 1
        elif b == 4: M[i - 1] = (asr[j - 2][1], asr[j - 1][2]); i -= 1; j -= 2
        elif b == 5:
            t0, t1 = asr[j - 1][1], asr[j - 1][2]; sp = t0 + (t1 - t0) * len(script_words[i - 2]) / max(1, len(script_words[i - 2]) + len(script_words[i - 1]))
            M[i - 2] = (t0, sp); M[i - 1] = (sp, t1); i -= 2; j -= 1
        elif b == 1: i -= 1
        else: j -= 1
    return M


def word_times(a, lines, asr=None, starts=None):
    """[(word, start, end, line_index)] for the script, timed from the audio.
    starts: {line_index: seconds} hard anchors for lines the ASR can't hear (pure Hindi stretches)."""
    if asr is None: asr = asr_words(a)
    sw = [(w, li) for li, l in enumerate(lines) for w in l.split()]
    M = align([w for w, _ in sw], asr)
    while True:   # drop short-word anchors that would cram the following words into no time (e.g. a repeated "और")
        ks = sorted(M); bad = None
        for x, y in zip(ks, ks[1:]):
            if len(_norm(sw[x][0])) <= 3 and (M[y][0] - M[x][0]) / (y - x) < .09: bad = x; break
        if bad is None: break
        del M[bad]
    for li, st in sorted((starts or {}).items()):   # manual line starts win over ASR anchors that contradict them
        x = next((k for k, (_, l_) in enumerate(sw) if l_ == li), None)
        if x is None: continue
        for k in list(M):
            if (k < x and M[k][1] > st) or (k >= x and M[k][0] < st): del M[k]
        M[x] = (float(st), float(st) + .1 + .075 * len(_norm(sw[x][0])))
    voiced = _voiced_mask(a); dur = len(a) / SR
    first_v = (int(np.argmax(voiced)) / 100) if voiced.any() else 0.0
    last_v = (len(voiced) - int(np.argmax(voiced[::-1]))) / 100 if voiced.any() else dur
    T = [None] * len(sw)
    for i, (s0, s1) in M.items(): T[i] = [s0, s1]
    est = lambda w: .1 + .075 * len(re.sub(r"[^\w]", "", w))                 # rough spoken length of a word
    sil = _silences(a, .15)
    # fill gaps between anchors: spread by text length over the *voiced* time between them
    i = 0
    while i < len(sw):
        if T[i] is not None: i += 1; continue
        k = i
        while k < len(sw) and T[k] is None: k += 1
        if i > 0:     # the previous anchor's end is often stretched over the words ASR missed: cap it
            T[i - 1][1] = min(T[i - 1][1], max(T[i - 1][0] + est(sw[i - 1][0]), T[i - 1][0] + .2))
        t0 = T[i - 1][1] if i > 0 else first_v
        t1 = T[k][0] if k < len(sw) else last_v
        if i > 0 and sw[i - 1][1] != sw[i][1]:          # gap starts a new line: it starts after the pause
            ps = [(e_ - s_, s_, e_) for s_, e_ in sil if T[i - 1][0] + .15 < s_ and e_ < t1 - .1]
            if ps:   # the first real pause after the anchor (not the longest one in a long gap)
                big = [q for q in ps if q[0] >= .25]; _, s_, e_ = min(big, key=lambda q: q[1]) if big else max(ps); T[i - 1][1] = min(T[i - 1][1], s_) if T[i - 1][1] > s_ else T[i - 1][1]; t0 = e_
        if k < len(sw) and sw[k - 1][1] != sw[k][1]:    # gap ends a line: it ends before the pause
            ps = [(e_ - s_, s_, e_) for s_, e_ in sil if t0 + .1 < s_ and e_ <= t1 + .1]
            if ps:   # the last real pause before the next anchor
                big = [q for q in ps if q[0] >= .25]; t1 = (max(big, key=lambda q: q[2]) if big else max(ps))[1]
        if t1 - t0 < .08 * (k - i): t1 = t0 + .18 * (k - i)
        # words of different lines inside this gap: split at the longest pauses (one per line break)
        groups = [[x] for x in range(i, k)]; gl = []
        for x in range(i, k):
            if gl and sw[x][1] == sw[gl[-1][-1]][1]: gl[-1].append(x)
            else: gl.append([x])
        cl = [sum(len(re.sub(r"[^\w]", "", sw[x][0])) + 1.4 for x in grp) for grp in gl]; tot = sum(cl); cands = [(s_, e_) for s_, e_ in sil if t0 + .05 < s_ and e_ < t1 - .05]
        chosen = []; acc = 0
        for g in range(len(gl) - 1):            # each line break -> the long pause nearest its text-length position
            acc += cl[g]; ex = t0 + (t1 - t0) * acc / tot; sg = max(.3, .25 * (t1 - t0))
            pool = [c for c in cands if not chosen or c[0] > chosen[-1][1]]
            if pool: chosen.append(max(pool, key=lambda c: (c[1] - c[0]) * np.exp(-(((c[0] + c[1]) / 2 - ex) / sg) ** 2)))
        bounds = [t0] + [v for s_, e_ in chosen for v in (s_, e_)] + [t1]
        if len(bounds) != 2 * len(gl): bounds = [t0] + [v for q in range(1, len(gl)) for v in (t0 + (t1 - t0) * q / len(gl),) * 2] + [t1]
        for g, grp in enumerate(gl):
            g0, g1 = bounds[2 * g], bounds[2 * g + 1]
            fr = np.arange(int(g0 * 100), max(int(g0 * 100) + 1, int(g1 * 100)))
            vv = fr[voiced[np.clip(fr, 0, len(voiced) - 1)]] if len(fr) else fr
            if len(vv) < 3: vv = fr
            wl = np.array([len(re.sub(r"[^\w]", "", sw[x][0])) + 1.4 for x in grp]); c = np.concatenate([[0], np.cumsum(wl)]) / wl.sum()
            for q, x in enumerate(grp):
                a_ = vv[min(len(vv) - 1, int(c[q] * (len(vv) - 1)))] / 100; b_ = vv[min(len(vv) - 1, int(c[q + 1] * (len(vv) - 1)))] / 100
                T[x] = [a_, max(a_ + .06, b_)]
        i = k
    for x in range(1, len(T)):                     # keep strictly increasing starts
        if T[x][0] < T[x - 1][0] + .03: T[x][0] = T[x - 1][0] + .03; T[x][1] = max(T[x][1], T[x][0] + .06)
    return [(w, float(s), float(e), li) for (w, li), (s, e) in zip(sw, T)], len(M), len(sw)
