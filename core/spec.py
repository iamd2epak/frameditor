"""Reel spec (YAML) loading + validation. Core fields only; each theme documents its own scene fields in its RULES.md
and may declare extra top-level / per-line keys in theme.json ("spec_keys", "line_keys")."""
import os
import yaml
from .character import EXPRESSIONS

TOP = {"title", "theme", "character", "voice", "music", "sound", "lines"}
LINE = {"say", "expr", "emph", "emph_blue", "highlight", "boom", "start", "scene", "sfx"}
VOICE_MODES = ("kokoro", "file")
MUSIC = ("bright", "dark", "none")


class SpecError(SystemExit):
    pass


def load(path):
    if not os.path.isfile(path): raise SpecError(f"spec not found: {path}")
    try: s = yaml.safe_load(open(path, encoding="utf-8"))
    except yaml.YAMLError as e: raise SpecError(f"{path}: invalid YAML: {e}")
    if not isinstance(s, dict): raise SpecError(f"{path}: the spec must be a YAML mapping (title, theme, voice, lines)")
    return s


def validate(s, theme=None, spec_dir="."):
    """(errors, warnings). theme = a loaded core.theme.Theme (adds its keys and character rule)."""
    E, Wn = [], []
    meta = theme.meta if theme else {}
    top = TOP | set(meta.get("spec_keys", [])); line = LINE | set(meta.get("line_keys", []))
    if not s.get("title"): E.append("title: missing")
    if not s.get("theme"): E.append("theme: missing (e.g. theme: depth3d; list installed themes with `python frame.py themes`)")
    for k in s:
        if k not in top: Wn.append(f"unknown top-level key '{k}' (ignored)")
    if theme:
        want = theme.character
        if s.get("character") and want and s["character"] != want:
            E.append(f"character: theme '{theme.id}' always uses {want}. A different character needs its own theme (docs/THEMES.md).")
        if s.get("character") and not want:
            E.append(f"character: theme '{theme.id}' is faceless (no character). Remove `character:` or use a character theme.")
    v = s.get("voice") or {}
    if not isinstance(v, dict): E.append("voice: must be a mapping, e.g. {mode: file, file: voice.mp3}")
    else:
        mode = v.get("mode", "kokoro")
        if mode not in VOICE_MODES: E.append(f"voice.mode must be one of {', '.join(VOICE_MODES)}")
        if mode == "file":
            f = v.get("file")
            if not f: E.append("voice.file: missing (path to the user's audio, relative to the spec)")
            elif not os.path.isfile(f if os.path.isabs(f) else os.path.join(spec_dir, f)): E.append(f"voice.file not found: {f}")
    if s.get("music", "bright") not in MUSIC: E.append(f"music must be one of {', '.join(MUSIC)}")
    L = s.get("lines")
    if not isinstance(L, list) or not L: E.append("lines: missing (a list of {say: ...})"); return E, Wn
    for i, l in enumerate(L):
        at = f"lines[{i}]"
        if not isinstance(l, dict) or not str(l.get("say", "")).strip(): E.append(f"{at}: needs a non-empty `say`"); continue
        for k in l:
            if k not in line: Wn.append(f"{at}: unknown key '{k}' (ignored)")
        if l.get("expr", "neutral") not in EXPRESSIONS: E.append(f"{at}.expr must be one of {', '.join(EXPRESSIONS)}")
        if "scene" in l and not isinstance(l["scene"], dict): E.append(f"{at}.scene must be a mapping")
        for k in ("emph", "emph_blue", "highlight"):
            if k in l and not isinstance(l[k], list): E.append(f"{at}.{k} must be a list of words")
        said = {w.lower().strip(".,!?\"'…:;") for w in str(l["say"]).split()}
        for k in ("emph", "emph_blue", "highlight"):
            for w in l.get(k, []) or []:
                if str(w).lower().strip(".,!?\"'") not in said: Wn.append(f"{at}.{k}: '{w}' is not a word of this line")
    if "scene" not in L[0]: Wn.append("lines[0] has no scene: the first scene falls back to the theme default")
    return E, Wn
