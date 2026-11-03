# The `.frame` file (format 1)

One reel = one `.frame` file: a ZIP the Frameditor app opens for preview, edits and MP4 export. It is self-contained:
the app needs no theme, no internet and no engine to play it. Written by `core/pack.py`.

```
manifest.json        what this is (small, read first)
timeline.json        everything the app needs to play and edit the reel
poster.jpg           360x640 still for the project list
sprites/<id>.webp    every baked prop image (drawn by the theme)
character/*.png      face rig (only for themes of kind "character")
audio/voice.wav      the voice;  audio/music.wav (optional);  audio/sfx/<kind>.wav one sample per SFX kind
fonts/*.ttf          the fonts named in the theme's style (captions + live text)
```

## manifest.json
| field | meaning |
|---|---|
| `format` | always `"frame"` |
| `formatVersion` | `1`. The app refuses files newer than it knows ("update the app") |
| `slug`, `title` | file name / display title |
| `reelId`, `revision` | stable id per spec + export counter: the app files re-exports as versions v1, v2, ... of one project |
| `theme` | `{id, name, version, kind}` (kind: `character` or `faceless`) |
| `character` | `{name, style: "sprite", version: 1}` or `null` |
| `canvas` | `{width: 1080, height: 1920, fps: 30}` |
| `frames`, `duration`, `poster`, `createdAt`, `generator` | as named |

## timeline.json
| field | meaning |
|---|---|
| `style` | the theme's `style` block (below): how the app draws the page, captions and overlays |
| `camera` | `{focal, cx, cy}`: perspective camera (z = 0 is the page plane; screen = c + (p - c) * focal / (focal + z)) |
| `lines` | `[{say, expr, emph[], emph_blue[], highlight[], boom[], start, end}]` |
| `words` | `[[word, start, end, line]]` (caption timing + lip-sync cues) |
| `levels`, `bright` | per-frame voice loudness / brightness 0..1 (mouth shape) |
| `scenes` | `[{index, start, end, label, lines: [a, b], compose, overlays, anchor_sizes}]` |
| `sprites` | `{id: {file, w, h, ss}}`: logical size in frame px; `ss` = pixels per frame px |
| `tracks` | `[{key, scene, pid, kind, label, shadow, glow, rows, [text], [expr]}]`, one per prop per scene |
| `tracks[].rows` | `[frame, sprite, x, y, z, rx, ry, rz, s, a, blur, mx, my, glint]` (centre in page px, tilt in degrees, scale, alpha, blur px, screen motion for motion blur, glint 0..1 or -1) |
| `anchors` | `{"scene:pid": [[frame, x, y, s, a]]}`: screen centres overlays attach to |
| `shatters` | `[{scene, pid, t}]` |
| `fx` | `{flash: [[f, v]], shake: [[f, x, y]], cracks: [[f, x, y, u]]}` |
| `character` | face rig `{name, size, ink, skin, lw, eyes[], brows[], mouth{}, smile_eyes_max}` or `null` |
| `audio` | `{sample_rate, voice, music, sfx: {gain, samples{kind: file}, events: [[t, kind]]}, master}` |

Track `kind` values the app treats specially: `me` (character tile: the app draws the live face on it),
`pill | sticker | word | heading` (text the user can edit; `text` holds the props), `shard` (shatter pieces).
Every other kind is a plain sprite.

## style (from theme.json, copied into every file)
```json
"background": {"type": "solid", "color": [r,g,b]}
            | {"type": "gradient", "top": [r,g,b], "bottom": [r,g,b]}
            | {"type": "blooms", "color": [r,g,b], "blooms": [[[r,g,b], x, y, radius, speed], ...], "vignette": 0.035},
"caption":  {"type": "kinetic", "y": 1478, "sizes": [68, 62, 56], "row": 84, "max_width": 880,
             "font": "X.ttf", "emph_font": "Y.ttf", "emph_scale": 1.16,
             "colors": {"ink": [..], "emph": [..], "emph_blue": [..], "highlight": [..]}},
"palette":  {"ink", "accent", "blue", "red", "gold", "line", "card"}   (overlays, editable text props),
"text_font": "X.ttf", "label_font": "Y.ttf"                           (editable text props, labels)
```
Captions: words blur + rise in as spoken, pages of max 2 rows (font steps down through `sizes` to fit), `emph` words
in `emph_font` + `emph` colour, `emph_blue` in the blue, `highlight` = band behind the word, `boom` = the word slams in.

## Compatibility rules
- Adding optional fields is not a breaking change; the app ignores fields it does not know.
- Removing/renaming a field or changing a meaning = `formatVersion` + 1 (and a new app release).
