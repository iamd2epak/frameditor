# Frameditor engine

Turn a script or voice-over into an animated reel project (`.frame`) that you preview, edit and export as MP4 in the
**Frameditor** app. Claude writes a small YAML spec; this engine times every word to the audio, runs the theme and packs
the result into one portable `.frame` file.

```
spec (YAML) + voice  ->  frame.py  ->  out/<slug>.frame  ->  Frameditor app (preview · edit · MP4)
```

## Quick start
```bash
./setup.sh                                          # once: Python deps + TTS model
python frame.py themes                              # installed theme packs (starter is built in)
python frame.py make themes/starter/examples/starter-example.yaml
```
With Claude: install the `frameditor` skill (`skill/SKILL.md`), then say e.g. *"make a reel about X in depth3d"* and
attach your voice file.

## Themes
The look lives in **theme packs**, not in this repo. A pack is one folder/zip (code, fonts, character, assets, rules).
`python frame.py install <pack.zip | folder | URL>` installs one. `themes/starter` is the free template for building
your own (docs/THEMES.md).

## Layout
| path | what |
|---|---|
| `frame.py` | the command line: themes · install · check · sheet · make · theme-check · theme-pack |
| `core/` | engine: spec checks, voice + word timing, theme loader, `.frame` writer, generic page/caption, logos |
| `themes/starter/` | free minimal theme + template |
| `docs/SPEC.md` | spec fields every theme shares + writing rules |
| `docs/THEMES.md` | theme pack contract: build your own |
| `docs/FORMAT.md` | the `.frame` file format (engine <-> app contract) |
| `skill/SKILL.md` | the Claude skill |

Per-reel files (`reels/`, `out/`), installed packs, models and caches are local and git-ignored.

## License
Engine code: MIT (see `LICENSE`). Fonts in `themes/starter/fonts/`: SIL Open Font License 1.1.
Theme packs are separate works: each pack's `theme.json` (`license`) and its author decide how it may be shared.
