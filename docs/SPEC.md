# Reel spec (core fields, every theme)

A reel is ONE YAML file, `reels/<slug>.yaml`. Scene fields belong to the theme: read `themes/<id>/RULES.md`.

```yaml
title: Three habits of fast learners       # required
theme: depth3d                             # required, an installed theme (python frame.py themes)
voice: {mode: file, file: voice.mp3}       # the user's audio (path next to the spec)  ...or:
# voice: {mode: kokoro, name: am_michael, speed: 1.05, lang: en-us}   # built-in TTS (English)
music: bright                              # bright | dark | none   (default: the theme's)
lines:                                     # required: one entry per spoken sentence/phrase, in order
  - say: "Fast learners all share three habits."    # exactly the spoken words
    expr: happy                            # character face: neutral happy surprised thinking sad angry wink
    emph: [three]                          # 1-2 key words: accent style
    emph_blue: [habits]                    # second accent style
    highlight: [learners]                  # band behind the word
    boom: three                            # the word slams in (+ impact)
    start: 1.2                             # only with voice files the aligner can't hear: hard start (seconds)
    sfx: [{at: three, kind: ding}]         # extra sound (theme decides which kinds exist)
    scene: {...}                           # starts a new scene here (fields: the theme's RULES.md)
```
`character:` is never needed: the theme fixes it. Naming a different one is an error (make a new theme instead).

## Writing rules (every theme)
- `say` matches the audio word for word (repeats included: "ruko ruko"). With a voice file, timing comes from the
  audio itself (word-level ASR, model downloads once); check the printed `word alignment` count.
- Hindi audio: write `say` in Roman Hinglish (English words stay English); on-screen labels in English letters.
- Steps/numbers as digits ("Step 1", "₹500"), never spelled out.
- One idea per scene; a new scene every 1-3 lines (about every 3-6 s); never hold one layout longer than ~8 s.
- Lists of 2-5 items shown one by one: every item gets a `cue` word, so it appears exactly when spoken.
- Cue words should be spoken once in the scene (cues match the first word in the scene that starts with them).
- Only 1-2 `emph` words per line; everything else plain.
- No social handles or IDs on screen.
- Long dead pauses (> 0.8 s) in the user's audio: trim them (ffmpeg) before making the reel.
- Images: only when they clearly help. Prefer files the user sends; a missing image is listed as MISSING IMAGES:
  ask the user for it.
