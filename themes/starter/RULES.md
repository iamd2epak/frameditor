# starter — rules for writing a reel

`theme: starter` (free, faceless: no character, never set `character:`).

## Look
- Soft gradient page, kinetic caption at the bottom (words blur in as they are spoken).
- Top area (y 300-1300): one optional `title` + up to 4 items: white text cards or images. Items pop in on their `cue`
  word and fade out when the scene ends.

## Scene
```yaml
scene:
  type: cards
  title: "3 habits"            # optional, short (1-3 words), accent colour
  layout: column               # column (default) | row | grid (2x2)
  items:                       # max 4
    - {text: "Teach it", cue: teach}        # text card (max ~6 words)
    - {image: photo.jpg, cue: photo}        # image: path next to the spec, or https URL
```
`cue` = a word of the scene's lines (the item appears when it is spoken) or seconds from the scene start (`0.2`).

## Captions
Per line: `emph: [word]` (accent colour), `emph_blue: [word]`, `highlight: [word]`, `boom: word` (slams in big).
Only 1-2 key words per line.

## Workflow
`python frame.py check reels/x.yaml` -> `python frame.py sheet reels/x.yaml -n 8` (look at it) -> `python frame.py make reels/x.yaml`.
