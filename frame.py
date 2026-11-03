#!/usr/bin/env python3
"""Frameditor engine: turn a reel spec (YAML) + an installed theme pack into ONE .frame project for the Frameditor app.

  python frame.py themes                          # installed theme packs
  python frame.py install depth3d.zip [--force]   # install a theme pack (.zip, folder or https URL)
  python frame.py check reels/x.yaml              # validate the spec (no rendering)
  python frame.py sheet reels/x.yaml [-n 8]       # contact-sheet preview PNG -> out/x_sheet.png
  python frame.py make  reels/x.yaml              # -> out/x.frame   (open it in the Frameditor app)
  python frame.py theme-check themes/<id>         # validate a theme pack you are building
  python frame.py theme-pack  themes/<id>         # validate + zip it -> out/<id>.zip

The app does preview, edits and the MP4 export. The engine writes .frame files only.
"""
import argparse, math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import theme as themes
from core.util import ROOT, FPS

OUT = os.path.join(ROOT, "out")
IDS = os.path.join(ROOT, "reels", ".frame-ids.json")


def _missing():
    from core.media import MISSING
    if MISSING: print("MISSING IMAGES (download blocked or bad path) - ask the user to send these:", *sorted(set(MISSING)), sep="\n  ")


def cmd_themes(a):
    found = themes.installed()
    if not found: print("no themes installed. Install a pack: python frame.py install <pack.zip | folder | URL>"); return
    for tid, p in found.items():
        m = themes.read_json(p); c = (m.get("character") or {}).get("name")
        print(f"{tid:16s} v{m.get('version')}  {m.get('kind'):9s} {m.get('license'):7s} {('character: ' + c) if c else 'no character'}  - {m.get('name')}")


def cmd_install(a):
    tid, m = themes.install(a.src, force=a.force)
    print(f"installed theme '{tid}' v{m['version']} -> themes/{tid}/  (rules: themes/{tid}/RULES.md)")


def cmd_check(a):
    from core import spec as S
    s = S.load(a.spec); E, Wn = S.validate(s)
    if not E:
        th = themes.Theme(s["theme"]); E, Wn = S.validate(s, th, os.path.dirname(os.path.abspath(a.spec)))
        if hasattr(th.mod, "check") and not E:
            Wn += th.mod.check(s) or []
    for w in Wn: print("warning:", w)
    if E: print("ERRORS:", *E, sep="\n  "); sys.exit(1)
    print(f"spec ok ({len(s['lines'])} lines, theme {s['theme']})")


def cmd_sheet(a):
    from core.reel import open_reel
    from PIL import Image, ImageDraw
    R = open_reel(a.spec); base = os.path.splitext(os.path.basename(a.spec))[0]
    times = [float(x) for x in a.at.split(",")] if a.at else [R.SS[k] + (R.SE[k] - R.SS[k]) * .7 for k in sorted({round(i * (len(R.SS) - 1) / max(1, a.n - 1)) for i in range(a.n)})]
    tw, th = 360, 640; ims = [R.frame(int(t * FPS)).resize((tw, th)) for t in times]; cols = min(4, len(ims)); rows = math.ceil(len(ims) / cols)
    c = Image.new("RGB", (cols * tw, rows * (th + 30)), (255, 255, 255)); d = ImageDraw.Draw(c)
    for k, (t, im) in enumerate(zip(times, ims)):
        c.paste(im, ((k % cols) * tw, (k // cols) * (th + 30))); d.text(((k % cols) * tw + 8, (k // cols) * (th + 30) + th + 6), f"{t:.1f}s", fill=(0, 0, 0))
    os.makedirs(OUT, exist_ok=True); out = os.path.join(OUT, base + "_sheet.png"); c.save(out); print("sheet:", out); _missing()


def cmd_make(a):
    from core.reel import open_reel
    from core import pack
    R = open_reel(a.spec); base = os.path.splitext(os.path.basename(a.spec))[0]
    pack.export(R, a.out or os.path.join(OUT, base + pack.EXT), IDS); _missing()


def cmd_theme_check(a):
    errs = themes.validate(a.path)
    if errs: print("theme pack problems:", *errs, sep="\n  "); sys.exit(1)
    print("theme pack ok:", themes.read_json(a.path)["id"])


def cmd_theme_pack(a):
    print("theme pack:", themes.pack(a.path, a.out or OUT))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter); sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("themes").set_defaults(fn=cmd_themes)
    p = sp.add_parser("install"); p.add_argument("src"); p.add_argument("--force", action="store_true"); p.set_defaults(fn=cmd_install)
    p = sp.add_parser("check"); p.add_argument("spec"); p.set_defaults(fn=cmd_check)
    p = sp.add_parser("sheet"); p.add_argument("spec"); p.add_argument("-n", type=int, default=8); p.add_argument("--at", default="", help="seconds, e.g. 1.5,6,12"); p.set_defaults(fn=cmd_sheet)
    p = sp.add_parser("make"); p.add_argument("spec"); p.add_argument("-o", "--out"); p.set_defaults(fn=cmd_make)
    p = sp.add_parser("theme-check"); p.add_argument("path"); p.set_defaults(fn=cmd_theme_check)
    p = sp.add_parser("theme-pack"); p.add_argument("path"); p.add_argument("-o", "--out"); p.set_defaults(fn=cmd_theme_pack)
    a = ap.parse_args(); a.fn(a)


if __name__ == "__main__": main()
