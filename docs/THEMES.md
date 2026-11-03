# Theme packs: use one, or build your own

A **theme pack** is one folder that holds everything a look needs. The engine core never contains a theme; packs are
installed locally (`python frame.py install <pack.zip | folder | URL>`) and stay out of this repo (except the free
`starter`). Anyone can build a pack; any valid pack produces `.frame` files the Frameditor app opens.

## 1. Folder layout
```
<id>/                     folder name = theme id (lowercase, a-z 0-9 _)
  theme.json              metadata + style (required)
  theme.py                the code (required, contract below)
  RULES.md                how to write a reel in this theme (required; Claude reads ONLY this file for the theme)
  fonts/                  every font the theme uses (required; licences allowed for redistribution)
  examples/*.yaml         at least one complete example spec (required)
  character/              the character PNG (kind "character" only)
  logos/ stickers/ ...    any other assets (optional; brand logos not in logos/ auto-download per session)
  *.py                    any helper modules (import them relatively: `from . import stage`)
```
Validate: `python frame.py theme-check themes/<id>`. Ship: `python frame.py theme-pack themes/<id>` -> `out/<id>.zip`.

## 2. theme.json
| field | rule |
|---|---|
| `id` | = folder name |
| `name`, `description`, `author` | display text |
| `version` | integer, +1 on every visual change |
| `format` | `1` (the .frame format this pack targets) |
| `kind` | `character` (one fixed character) · `faceless` (no character, voice only) · `face` (the user's own video: planned, not in format 1) |
| `license` | `free` · `paid` · `private` (information for people; the owner decides who gets the pack) |
| `character` | kind `character`: `{name, style: "sprite", image, skin, ink, eyes, brows, mouth}`; otherwise `null` |
| `music`, `sound` | music bed `bright` · `dark` · `none`; sound set `soft` |
| `fonts` | font files from `fonts/` that go into every .frame |
| `style` | what the app draws itself: background, caption, palette, text_font (docs/FORMAT.md) |
| `spec_keys`, `line_keys` | extra top-level / per-line spec keys the theme reads (others print a warning) |

## 3. One theme = one character (hard rule)
- A character theme has exactly ONE character, fixed. Specs never choose it. A request for a different character in the
  same style = a NEW theme (copy the pack, swap `character/` + the `character` block, new id + name).
- Re-using an existing character in a new theme: copy its `character/` folder + `character` block from the pack you own.
- Character names: one simple, easy word that matches the character (Max, Riya, Kabir). Ask the user for the name; if
  they don't care, pick one and say it.
- Sprite character (format 1): ONE transparent PNG of a head/bust, ~1000-1300 px, front-facing, eyes open, mouth
  closed, clean dark outlines. Give pixel boxes for both `eyes`, both `brows` (optional) and the `mouth` (around the
  drawn closed mouth). The engine erases those areas to `skin` and redraws blinking, talking and brow moves in the `ink`
  colour; the app animates the same rig live. Check the boxes on a sheet (`frame.py sheet`) before shipping.

## 4. theme.py contract
```python
DEFAULT_SCENE = {...}            # scene used when line 0 has no `scene:` (optional)
def setup(R): ...                # once, after timing: build scenes, add SFX events to R.sfx (optional)
def frame(R, t, i) -> Image      # RGBA 1080x1920 frame at t seconds (frame i): previews + poster
def record(R, rec): ...          # fill the recorder for the .frame (below)
def check(spec) -> [str]         # static warnings for `frame.py check` (optional)
```
`R` (core/reel.py): `spec, dir, lines, SS, SE, words, END, N, lvl, bri, main, mainb, sfx, char, line_at(t), scene_index(t)`;
`R.mainb[k] = (start, end, scene, ctx)`, `ctx.cue("word" | seconds)` -> the time the word is spoken in that scene.

Recorder (core/pack.py), for every frame `i` set `rec.frame = i`, then per visible prop:
```python
tr = rec.track(f"{scene}:{pid}", scene, pid, kind, label="card: Plan")      # one track per prop per scene
rec.row(tr, rec.sid(sprite_image, ss), x, y, z=0, rx=0, ry=0, rz=0, s=1, a=1, blur=0)
```
Also: `rec.scenes.append({index, start, end, label, lines: [a, b], compose, overlays: {}, anchor_sizes: {}})` per scene,
`rec.add_flash(v)`, `rec.add_shake(x, y)`, `rec.anchor(key, x, y, s, a)`, `rec.camera = {focal, cx, cy}`.
A character theme draws the character tile as `kind: "me"` (the app paints the live face into it).

Rules: the same sprite image object = the same sprite id (bake once, reuse; cache by content). Props that change every
frame (live charts) cost size: keep them few. `frame()` and `record()` must show the same thing; draw the background
and caption with `core/look.py` from `style` so the previews match the app.

## 5. RULES.md (what Claude reads)
Short and exact: the look, every scene type + field with one YAML example each, layout limits (safe margins: 90 px
sides, captions own y > 1380), what to avoid, and the workflow (check -> sheet -> make). No engine internals.

## 6. Build a theme in 6 steps
1. `cp -r themes/starter themes/<id>`; set `id`, `name`, `kind`, `license`, `version: 1` in theme.json.
2. Change `style` (page + caption colours, fonts in `fonts/`) and the sprite drawing in theme.py.
3. Character theme: add `character/<name>.png` + the `character` block (section 3); draw a `kind: "me"` tile.
4. Write RULES.md + one `examples/<id>-example.yaml`.
5. `python frame.py theme-check themes/<id>` -> `python frame.py sheet themes/<id>/examples/<id>-example.yaml` -> `make`
   -> open the .frame in the app.
6. `python frame.py theme-pack themes/<id>` -> `out/<id>.zip`. Share it with whoever should have it (it never goes into
   the engine repo).
