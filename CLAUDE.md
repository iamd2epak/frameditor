# Frameditor engine — instructions for Claude

- This repo is PUBLIC: reusable engine code + docs + the free `starter` theme only. Never add reels, voice files, user
  photos, private theme packs, logos or outputs. `reels/`, `out/`, `themes/<other>`, `models/`, `.cache/` are git-ignored.
- Making a reel or a theme: follow `skill/SKILL.md`. Output = `.frame` only (no MP4 path in the engine).
- Contracts: `docs/FORMAT.md` (.frame, shared with the app: additive changes only, breaking = formatVersion + 1),
  `docs/THEMES.md` (theme packs), `docs/SPEC.md` (core spec).
- Core must stay theme-agnostic: no theme names, colours, fonts or scene types in `core/`.
- Keep it small and clean: no dead code, no per-reel hacks. Commit/push only when the owner asks; push only to `main`.
