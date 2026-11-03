---
name: frameditor
description: Make animated faceless reels/shorts as a .frame project for the Frameditor app (preview, edit and MP4 export on the phone), or build a new Frameditor theme pack. Use when the user asks for a reel, short, faceless/explainer video, "/reel", a .frame file, or a new reel theme/style.
---

# Frameditor

The engine is the public repo **github.com/iamd2epak/frameditor**. Looks come from **theme packs** (one zip per theme).
The output is ALWAYS one `.frame` file that the user opens in the Frameditor app.

## Hard rules
1. Deliver `.frame` only. Video, reel and edit requests all end in a `.frame`. The engine never renders MP4: the user
   exports MP4 in the app. If they insist on an MP4 file, say so in one line.
2. Use only installed themes. Never invent one, never imitate a theme you don't have, never edit a pack while making a
   reel. If the theme they want is missing, ask them to attach its pack (`<id>.zip`) or a link. Without a pack, offer
   the free `starter` theme.
3. The character comes with the theme (one fixed character per theme). Asked for another character in the same theme:
   say no in one line and explain that a new theme with that character is needed (offer to build it, §Build a theme).
4. Everything for a reel stays in this sandbox: the spec, the audio, downloaded images or logos. Never commit or push
   anything to any repo.
5. Read only what the task needs: this file, `docs/SPEC.md`, and `themes/<id>/RULES.md` for the chosen theme.
   Don't read other themes, `core/` code or the whole repo.

## Make a reel
1. Setup, once per session:
   `git clone --depth 1 https://github.com/iamd2epak/frameditor && cd frameditor && ./setup.sh`
2. Theme:
   - Run `python frame.py themes`.
   - To install a pack the user sent: `python frame.py install <path-or-url>`. Install errors mean the pack is broken: show the message and stop.
3. Inputs: the theme, the user's voice file (`voice: {mode: file}`, copy it to `reels/`) or a script for the built-in
   English TTS. Missing topic or script? Write a tight script and show it before building. A Hindi voice needs a Roman
   Hinglish `say`.
4. Read `docs/SPEC.md` + `themes/<id>/RULES.md`, then write `reels/<slug>.yaml` (slug: short, kebab-case).
   - Base it on the theme's `examples/*.yaml`.
   - Changing a reel the user already has: edit the SAME slug. The app files it as the next version of that project.
5. `python frame.py check reels/<slug>.yaml` and fix every ERROR. Warnings: fix or consciously accept.
6. `python frame.py sheet reels/<slug>.yaml -n 12`, then LOOK at `out/<slug>_sheet.png`.
   - Fix every LAYOUT WARNING, overlaps, empty frames and text cut at the edges.
   - Repeat until the sheet is clean.
7. `python frame.py make reels/<slug>.yaml` builds `out/<slug>.frame`.
   - Send the file to the user. In claude.ai, copy it to `/mnt/user-data/outputs/`.
   - Reply with 2-3 lines: what's in it, length, and "open it in Frameditor".
8. If the output lists MISSING IMAGES, ask the user for those files, then run `make` again.

## Build a theme (only when the user asks for a new style or character)
1. Read `docs/THEMES.md` first; it defines the contract.
2. Ask what's missing:
   - **Kind:** `character` (one fixed character), `faceless` (voice only, no character), or `face` (their own video, not supported yet: say so).
   - **Look:** colours, fonts, mood.
   - **Character name:** one simple word. If they don't care, pick one and tell them.
3. Copy the starter and edit it: `cp -r themes/starter themes/<id>`. Write theme.json, theme.py, RULES.md and one example.
   - A character needs its PNG plus eye, brow and mouth boxes.
4. Test it:
   - Run `python frame.py theme-check themes/<id>`.
   - Make a sheet from the example and look at it, then run `make`.
   - Iterate until it looks right.
5. Ship it: `python frame.py theme-pack themes/<id>` produces `out/<id>.zip`. Send it.
   - The user installs it with `frame.py install` in later sessions.
   - It never goes into the engine repo.

## Errors
| message | do |
|---|---|
| `theme 'x' is not installed` | ask for the pack zip/link, or offer `starter` |
| `character: theme 'x' always uses Y` | remove `character:` (or build a new theme for the other character) |
| `spec errors` | fix the listed fields (docs/SPEC.md, the theme's RULES.md) |
| `voice.file not found` | the audio must sit next to the spec (path relative to it) |
| `theme pack is not valid` | the pack is broken: tell the user what the message lists |
| setup / download failures | retry once; TTS needs `models/`, timing of voice files downloads an ASR model once (fallback: pause-based timing) |
