"""fit2print command line."""
import argparse, sys
from . import __version__, deps, layers, gcode, toolpath, dashboard, plate, project
from .settings import Settings

def cmd_doctor(args):
    text, bad = deps.report(deps.probe())
    print(text)
    print("\nRequired tools missing." if bad else "\nAll required tools found. Optional ones that are absent switch their checks off, as listed above.")
    return 1 if bad else 0

def cmd_overhang(args):
    import trimesh
    m = trimesh.load(args.mesh)
    cfg = Settings.load(args.profile)
    w = layers.analyse(m, layer=args.layer, reach=args.reach)
    for e in w["events"]:
        print(f"z {e['z']:6.2f}: {'bridge, held both ends, span' if e['kind'] == 'bridge' else 'CANTILEVER, depth'} {e['size']} mm near x {e['x']}, y {e['y']}")
    c, b = (w["cant"][0] if w["cant"] else 0), (w["bridge"][0] if w["bridge"] else 0)
    v = "BLOCK" if c > cfg.cantilever_block or b > cfg.bridge_block else "CHECK" if c > cfg.cantilever_check or b > cfg.bridge_check else "PASS"
    print(f"{v}: worst cantilever {c} mm, worst bridge {b} mm (profile: {cfg.name})")
    return 1 if v == "BLOCK" else 0

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

def read_marker(folder):
    """The project marker (fit2print.toml) of a folder, or an explanation of why there is none. Projects are never guessed."""
    import os
    try:
        import tomllib
    except ModuleNotFoundError:
        raise SystemExit("Python 3.11+ is needed")
    p = os.path.join(folder, "fit2print.toml")
    if not os.path.exists(p):
        raise SystemExit(f"{folder}: no fit2print.toml, so this is not a Fit2Print project (refusing to guess which project it is)")
    with open(p, "rb") as f:
        return tomllib.load(f)

def cmd_dashboard(args):
    from .adapters import phonosphere
    marker = read_marker(args.project)
    if marker.get("adapter") != "phonosphere":
        raise SystemExit(f"{args.project} is project '{marker.get('id')}' with adapter '{marker.get('adapter')}': no dashboard adapter for it yet")
    project = phonosphere.load(args.project)
    page = dashboard.render(project)
    open(args.out, "w").write(page)
    print(f"{args.out}: {len(project['parts'])} parts, {len(project['prints'])} real prints, {len(project['runs'])} virtual-check runs, {len(page) // 1024} KB")
    return 0

def cmd_plate(args):
    import os
    cfg = Settings.load(args.profile)
    marker = read_marker(args.project) if args.project else {}
    src = [os.path.join(args.project, s) for s in ([marker["model"]] if isinstance(marker.get("model"), str) else marker.get("model", []))] if args.project else None
    bad = 0
    for stl in args.stl:
        r = plate.make(stl, args.out, cfg, filament=args.filament, source=src, project=args.project)
        print(f"{r['part']:24} {r['verdict']:6} {r['minutes']} min {r['grams']} g -> {r['file']}")
        for n in r["notes"]:
            print("      " + n)
        bad |= r["verdict"] == "BLOCK"
    return 1 if bad else 0

def cmd_init(args):
    pid, folder = project.init(args.folder, args.name, args.kind, args.printer_profile)
    print(f"created project '{pid}' in {folder}")
    print("  fit2print.toml   the marker (every command reads it first)")
    print("  brief.md         stage 0: fill this in with the AI")
    print("  NEXT.md          where the project stands; rewritten at the end of every session")
    print("  CLAUDE.md        the rules the AI reads at the start of every session")
    print("  records/         checks, prints and photos are logged here")
    return 0

def main(argv=None):
    p = argparse.ArgumentParser(prog="fit2print", description=__doc__)
    p.add_argument("--version", action="version", version=__version__)
    s = p.add_subparsers(dest="cmd", required=True)
    s.add_parser("doctor", help="which tools are installed and which checks can run").set_defaults(fn=cmd_doctor)
    o = s.add_parser("overhang", help="find layers whose plastic has nothing under it (the part must sit z-up as printed)")
    o.add_argument("mesh"); o.add_argument("--layer", type=float, default=0.28); o.add_argument("--reach", type=float, default=0.6); o.add_argument("--profile", default=None)
    o.set_defaults(fn=cmd_overhang)
    t = s.add_parser("toolpath", help="on a sliced .3mf/.gcode: is every bit of plastic held up from below, and from how many sides")
    t.add_argument("plate", nargs="+"); t.add_argument("--profile", default=None, help="printer/material profile (default profiles/bambu_a1_pla.toml)")
    t.set_defaults(fn=cmd_toolpath)
    d = s.add_parser("dashboard", help="a one-page board of every part, what needs you, and the print log with photos")
    d.add_argument("project", help="the Phonosphere cad/ folder"); d.add_argument("--out", default="dashboard.html")
    d.set_defaults(fn=cmd_dashboard)
    pl = s.add_parser("plate", help="slice an STL with Bambu Studio and judge the toolpaths (parts that print without supports)")
    pl.add_argument("stl", nargs="+"); pl.add_argument("--out", required=True); pl.add_argument("--project", default=None, help="project folder: records the result, and refuses an STL older than its model")
    pl.add_argument("--filament", default="pla_black"); pl.add_argument("--profile", default=None)
    pl.set_defaults(fn=cmd_plate)
    i = s.add_parser("init", help="start a new project folder from the template (marker, brief, NEXT.md, AI rules)")
    i.add_argument("folder"); i.add_argument("--name", required=True); i.add_argument("--kind", default="design-and-print"); i.add_argument("--printer-profile", default="bambu_a1_pla")
    i.set_defaults(fn=cmd_init)
    a = p.parse_args(argv)
    return a.fn(a)

if __name__ == "__main__":
    sys.exit(main())
