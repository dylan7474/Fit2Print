"""fit2print command line."""
import argparse, sys
from . import __version__, deps, layers, gcode, toolpath
from .settings import Settings

def cmd_doctor(args):
    text, bad = deps.report(deps.probe())
    print(text)
    print("\nRequired tools missing." if bad else "\nAll required tools found. Optional ones that are absent switch their checks off, as listed above.")
    return 1 if bad else 0

def cmd_overhang(args):
    import trimesh
    m = trimesh.load(args.mesh)
    ev = layers.unsupported(m, layer=args.layer, reach=args.reach)
    for e in ev:
        print(f"layer at z {e['z']}: {e['area']} mm2 starts in mid-air near x {e['x']}, y {e['y']}")
    print(f"{len(ev)} layer(s) with unsupported plastic" if ev else "no layer starts in mid-air")
    return 1 if ev else 0

def cmd_toolpath(args):
    cfg = Settings.load(args.profile)
    bad = 0
    for path in args.plate:
        lay, _, _ = gcode.parse(gcode.read_gcode(path), cfg.filament_area)
        v, lines = toolpath.report(lay, cfg)
        print(f"{path.split('/')[-1]:44} {v}")
        for l in lines:
            print("      " + l)
        bad |= v == "BLOCK"
    print(f"profile: {cfg.name}")
    return 1 if bad else 0

def main(argv=None):
    p = argparse.ArgumentParser(prog="fit2print", description=__doc__)
    p.add_argument("--version", action="version", version=__version__)
    s = p.add_subparsers(dest="cmd", required=True)
    s.add_parser("doctor", help="which tools are installed and which checks can run").set_defaults(fn=cmd_doctor)
    o = s.add_parser("overhang", help="find layers whose plastic has nothing under it (the part must sit z-up as printed)")
    o.add_argument("mesh"); o.add_argument("--layer", type=float, default=0.28); o.add_argument("--reach", type=float, default=0.6)
    o.set_defaults(fn=cmd_overhang)
    t = s.add_parser("toolpath", help="on a sliced .3mf/.gcode: is every bit of plastic held up from below, and from how many sides")
    t.add_argument("plate", nargs="+"); t.add_argument("--profile", default=None, help="printer/material profile (default profiles/bambu_a1_pla.toml)")
    t.set_defaults(fn=cmd_toolpath)
    a = p.parse_args(argv)
    return a.fn(a)

if __name__ == "__main__":
    sys.exit(main())
