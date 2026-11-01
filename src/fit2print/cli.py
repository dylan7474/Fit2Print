"""fit2print command line."""
import argparse, os, sys
from . import __version__, deps, layers, gcode, toolpath, dashboard, plate, project, sync, hardware, render as render_mod, export as export_mod, modelview
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
    if args.split:
        return _plate_split(args, cfg)
    if not args.stl and not args.group:
        print("plate needs an STL file, --group NAME, or --split FILE_split.json"); return 1
    if args.group:
        if not args.project:
            print("plate --group needs --project"); return 1
        r = plate.make_group(args.project, marker, args.group, args.out, cfg)
        print(f"{r['part']:24} {r['verdict']:6} {r['minutes']} min {r['grams']} g -> {r['file']}")
        for n, f in r["filaments"].items():
            print(f"      filament {n} {f['colour']}: {', '.join(f['pieces'])}")
        for n in r["notes"]:
            print("      " + n)
        return 1 if r["verdict"] == "BLOCK" else 0
    if args.together:
        r = plate.make_together(args.stl, args.out, cfg, filament=args.filament, name=args.name, source=src, project=args.project, supports=args.supports)
        print(f"{r['part']:24} {r['verdict']:6} {r['minutes']} min {r['grams']} g -> {r['file']}")
        for n, v in r["parts"].items():
            print(f"      {n}: {v['shelves']} shelf region(s), {v['faces_painted']} faces painted")
        for n in r["notes"]:
            print("      " + n)
        return 1 if r["verdict"] == "BLOCK" else 0
    for stl in args.stl:
        r = plate.make(stl, args.out, cfg, filament=args.filament, source=src, project=args.project, supports=args.supports)
        print(f"{r['part']:24} {r['verdict']:6} {r['minutes']} min {r['grams']} g -> {r['file']}")
        for n in r["notes"]:
            print("      " + n)
        bad |= r["verdict"] == "BLOCK"
    return 1 if bad else 0

def _plate_split(args, cfg):
    """plate --split NAME_split.json: slice every section and the pin plate; one verdict per file, worst one decides."""
    import json, os
    try:
        d = json.load(open(args.split))
    except (OSError, ValueError) as e:
        print(f"cannot read {args.split}: {e}"); return 1
    if not d.get("ok"):
        print("REFUSED: that split did not finish OK (" + str(d.get("summary")) + "); fix the split first"); return 1
    src = d.get("source")
    files = [p["file"] for p in d["pieces"]]
    if d.get("pins", {}).get("count"):
        files.append(d["pins"]["file"])
    for f in files + ([src] if src else []):
        if not os.path.isfile(f):
            print(f"REFUSED: {f} is missing (re-run fit2print split)"); return 1
    if src and any(os.path.getmtime(f) < os.path.getmtime(src) for f in files):
        print("REFUSED: the source STL is newer than the sections; re-run fit2print split"); return 1
    bad = 0; total = 0
    for f in files:
        r = plate.make(f, args.out, cfg, filament=args.filament, project=args.project, supports=args.supports)
        total += r["minutes"] or 0
        print(f"{r['part']:24} {r['verdict']:6} {r['minutes']} min {r['grams']} g -> {r['file']}")
        for n in r["notes"]:
            print("      " + n)
        bad |= r["verdict"] == "BLOCK"
    print(f"{len(files)} plates, {total} min in all" + ("  -- AT LEAST ONE BLOCKED" if bad else ""))
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

def cmd_serve(args):
    import os, secrets
    from . import server
    cfg = server.load_config(args.config)
    token = args.token
    if args.token_file:
        with open(os.path.expanduser(args.token_file)) as fh:
            token = fh.read().strip()
    ac_cfg = cfg.get("access", {})
    verifier = None
    if ac_cfg.get("team_domain") and ac_cfg.get("aud"):
        from . import access as access_mod
        verifier = access_mod.Verifier(ac_cfg["team_domain"], ac_cfg["aud"], ac_cfg.get("allowed_emails"))
        print(f"requests through Cloudflare need a valid Access login for {ac_cfg['team_domain']} (no token needed)")
    if args.host not in ("127.0.0.1", "localhost", "::1") and not token and not args.trust_lan and not verifier:
        token = secrets.token_urlsafe(12)
        print(f"no --token given for a network address: made one for this run: {token}")
    from . import printer as printer_mod
    pc = printer_mod.load_printer(args.printer)
    pr = printer_mod.Printer(pc) if pc else None
    if pr:
        pr.start()
        print(f"printer panel on: {pc['host']} (the access code is read from the printer file, never printed)")
    else:
        print("no printer set up (no ~/.config/fit2print/printer.toml): the printer panel is off")
    import shutil
    from . import assistant as assistant_mod
    ac = cfg.get("assistant", {})
    cmd = ac.get("command") or ([shutil.which("claude")] if shutil.which("claude") else None)
    asst = None
    if cmd and ac.get("enabled", True):
        asst = assistant_mod.Assistant(command=cmd, model=ac.get("model", "sonnet"), budget_usd=ac.get("budget_usd", 0.75), f2p=ac.get("fit2print", "fit2print"))
        print(f"assistant on: {' '.join(cmd)} (model {asst.model}, at most ${asst.budget} per message)")
    else:
        print("assistant off (no claude command found or disabled in config)")
    srv = server.make_server(cfg, args.host, args.port, token, pr, asst, cfg.get("render_command"), args.trust_lan, verifier)
    if args.trust_lan:
        print("home-network devices need no token (requests through a proxy still do)")
    q = f"?t={token}" if token else ""
    print(f"Fit2Print is at http://{'localhost' if args.host in ('127.0.0.1', 'localhost') else args.host}:{args.port}/{q}   (Ctrl+C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("stopped")
    return 0

def cmd_sync(args):
    marker = read_marker(args.project)
    r = sync.sync(args.project, args.remote, marker, args.dry_run, args.prefer)
    print(("DRY RUN: " if args.dry_run else "") + f"pulled {r['pulled']} log entr{'y' if r['pulled'] == 1 else 'ies'} and {r['photos_pulled']} photo(s) from the server; "
          f"{'would push' if args.dry_run else 'pushed'} {len(r['pushed'])} file(s) + photos; text: pulled {r['text_pulled'] or 'none'}, pushed {r['text_pushed'] or 'none'}")
    for c in r["conflicts"]:
        print("CONFLICT: " + c)
    return 1 if r["conflicts"] else 0

def cmd_sync_all(args):
    import os
    from . import server
    cfg = server.load_config(args.config)
    root = args.remote.rstrip("/")
    known, bad = set(), 0
    folders = list(cfg["projects"])
    nd = cfg["new_projects_dir"]
    if os.path.isdir(nd):
        folders += [os.path.join(nd, d) for d in sorted(os.listdir(nd))]
    for f in folders:
        m = server.read_marker(f)
        if not m or not m.get("id"):
            continue
        known.add(m["id"])
        try:
            r = sync.sync(f, f"{root}/{m['id']}", m, args.dry_run, args.prefer)
            print(f"{m['id']:24} pulled {r['pulled']} entries, {r['photos_pulled']} photos; text pulled {r['text_pulled'] or '-'}, pushed {r['text_pushed'] or '-'}")
            for c in r["conflicts"]:
                print("  CONFLICT: " + c); bad = 1
        except Exception as e:
            print(f"{m['id']:24} FAILED: {e}"); bad = 1
    if not args.dry_run:
        for pid in sync.pull_new(root, nd, known):
            print(f"{pid:24} started on the server: brought home to {os.path.join(nd, pid)}")
    return bad

def cmd_hardware(args):
    lib = hardware.load_all()
    if args.action == "list":
        for k, e in lib.items():
            n, u = len(e.get("dim", {})), len(hardware.unverified(e))
            print(f"{k:22} {e.get('category', ''):8} {e.get('name', '')}  ({u} fit-critical dimension(s) not yet measured by you)")
        return 0
    if not args.id or args.id not in lib:
        print(f"no such component: {args.id}. Try: fit2print hardware list"); return 1
    e = lib[args.id]
    if args.action == "show":
        print(f"{e.get('name')}  [{e.get('category')}]\n" + "\n".join("  source: " + s for s in e.get("sources", [])))
        for k, d in e["dim"].items():
            tag = f"MEASURED {hardware.value(d)} on {d['measured'].get('on')}" if hardware.is_verified(d) else f"unverified ({d['basis']})"
            print(f"  {'*' if d.get('critical') else ' '} {k:28} {d['value']:>8} {d.get('unit', ''):3} {tag}   <- {d.get('source', '')[:70]}")
        print("  (* = the fit depends on it)")
        return 0
    if args.action == "verify":
        if not (args.dim and args.value):
            print("usage: fit2print hardware verify ID DIMENSION VALUE [--how callipers]"); return 1
        v = hardware.verify(args.id, args.dim, args.value, args.how, library=lib)
        print(f"recorded: {args.id} {args.dim} = {v} (measured, in {hardware.USER_DIR})"); return 0
    if args.action == "openscad":
        print(hardware.openscad(e), end=""); return 0
    return 1

def cmd_render(args):
    marker = read_marker(args.project)
    for r in render_mod.render(args.project, marker):
        print(f"{'ok  ' if r['ok'] else 'FAIL'}  {r['title']} -> renders/{r['name']}.png" + ("" if r["ok"] else f"  ({r['error']})"))
        if r.get("same_as"):
            print(f"WARN  {r['name']} is the SAME picture as {r['same_as']} (same part, same angle): give it a different view = \"front\", \"side\" ... or angle")
    for r in modelview.build(args.project, marker):
        print(f"{'ok  ' if r['ok'] else 'skip'}  3D view: {r['name']}" + ("" if r["ok"] else f"  ({r['error']})"))
    return 0

def cmd_stage(args):
    from . import stage
    read_marker(args.project)
    if args.set:
        stage.set_stage(args.project, args.set, "person")
    cur = stage.current(args.project)
    print(f"{' > '.join(('[' + l + ']') if k == cur else l for k, l in stage.STAGES)}")
    for e in stage.history(args.project)[-5:]:
        print(f"  {e['at']}  {e['from']} -> {e['to']}  ({e['by']})")
    return 0

def cmd_export(args):
    marker = read_marker(args.project)
    bad = 0
    try:
        res = export_mod.export(args.project, marker)
    except ValueError as e:
        print(f"cannot export: {e}"); return 1
    for r in res:
        if r["ok"]:
            print(f"ok    {r['name']}: {os.path.relpath(r['file'], args.project)}  {r['size'][0]} x {r['size'][1]} x {r['size'][2]} mm, {r['volume']} cm3" + ("" if r["watertight"] else "  WARNING: not watertight"))
        else:
            print(f"FAIL  {r['name']}: {r['error']}"); bad = 1
    return bad

def cmd_assembly_check(args):
    from . import assemblycheck
    marker = read_marker(args.project)
    if not marker.get("model"):
        print("the project's marker needs model = \"file.scad\""); return 1
    try:
        r = assemblycheck.run(args.project, marker, only=args.only)
    except (ValueError, RuntimeError, OSError) as e:
        print(f"cannot run the virtual build: {e}"); return 1
    import json
    os.makedirs(os.path.join(args.project, "records"), exist_ok=True)
    with open(os.path.join(args.project, "records", "assembly_check.json"), "w") as fh:
        json.dump(r, fh, indent=1, default=float)
    return 0 if r["ok"] else 1

def cmd_coupon(args):
    from . import coupon as coupon_mod
    try:
        boxes = coupon_mod.boxes_from_args(args.box or [])
        if not boxes:
            print("give at least one --box NAME X0 X1 Y0 Y1 (millimetres, in the STL's own printed coordinates)"); return 1
        res = coupon_mod.cut(args.stl, boxes, args.out, zmax=args.zmax)
    except (ValueError, OSError) as e:
        print(f"cannot cut: {e}"); return 1
    bad = 0
    for r in res:
        if r["ok"]:
            print(f"ok    {r['name']}: {r['file']}  {r['size'][0]} x {r['size'][1]} x {r['size'][2]} mm, {r['volume']} mm3" + ("" if r["watertight"] else "  WARNING: not watertight"))
        else:
            print(f"FAIL  {r['name']}: {r['error']}"); bad = 1
    return bad

def cmd_split(args):
    from . import split as split_mod
    if os.path.isdir(args.stl):                                  # project mode: every [[split]] table in the marker
        marker = read_marker(args.stl)
        tables = marker.get("split") or []
        if not tables:
            print("this project has no [[split]] table: add one (name, part, and optionally scale, max_pieces, bed, margin, pin) to fit2print.toml, or give an STL file"); return 1
        bad = 0
        for tb in tables:
            if not split_mod.NAME.fullmatch(str(tb.get("name", ""))) or not tb.get("part"):
                print(f"a [[split]] needs a name (lower-case letters, digits, - or _) and the part's STL name: {tb}"); bad = 1; continue
            stl = os.path.join(args.stl, export_mod.stl_dir(marker), tb["part"] + ".stl")
            if not os.path.exists(stl):
                print(f"FAIL  {tb['name']}: {stl} is missing: run `fit2print export .` first"); bad = 1; continue
            model = marker.get("model")
            if model and os.path.getmtime(stl) < os.path.getmtime(os.path.join(args.stl, model)):
                print(f"FAIL  {tb['name']}: {os.path.basename(stl)} is older than {model}: run `fit2print export .` again (a stale part is never cut)"); bad = 1; continue
            res = split_mod.split(stl, os.path.join(args.stl, tb.get("out", "sections")), base=tb["name"], bed=tuple(tb.get("bed", split_mod.A1_BED)), margin=float(tb.get("margin", 6.0)),
                                  scale=float(tb.get("scale", 1.0)), max_pieces=int(tb.get("max_pieces", 64)), pin_d=float(tb.get("pin", 3.0)), pins=bool(tb.get("pins", True)), joint=str(tb.get("joint", "auto")))
            print(f"{'ok  ' if res['ok'] else 'FAIL'}  {tb['name']}: {res['summary']}")
            for w in res["warnings"]:
                print("      NOTE  " + w)
            try:
                split_mod.map_picture(stl, res, os.path.join(args.stl, tb.get("out", "sections"), tb["name"] + "_map.png"), scale=float(tb.get("scale", 1.0)))
            except Exception:
                pass
            bad |= not res["ok"]
        return int(bad)
    if not os.path.isdir(args.stl) and not args.out:
        print("give --out FOLDER for where the sections go"); return 1
    cuts = {}
    for item in args.cut or []:
        try:
            ax, pos = item.split("=")
            assert ax in "xyz" and len(ax) == 1
            cuts.setdefault(ax, []).append(float(pos))
        except Exception:
            print(f"cannot read --cut {item!r}: write it like x=173.5 (an axis x, y or z, then a position in mm)"); return 1
    try:
        res = split_mod.split(args.stl, args.out, base=args.base, bed=tuple(args.bed) if args.bed else split_mod.A1_BED, margin=args.margin, scale=args.scale,
                              max_pieces=args.max_pieces, cuts=cuts or None, pin_d=args.pin, pins=not args.no_pins, joint=args.joint)
    except (ValueError, OSError) as e:
        print(f"cannot split: {e}"); return 1
    print(res["summary"])
    for p in res["pieces"]:
        print(("ok    " if p.get("ok") else "FAIL  ") + f"{p['name']}: " + (f"{p['size'][0]} x {p['size'][1]} x {p['size'][2]} mm, on its {p['down']} face, {p['holes']} pin holes" if p.get("ok") else p.get("error", "")))
    if res["pins"]["file"]:
        print("pins  " + res["pins"]["note"])
    for w in res["warnings"]:
        print("NOTE  " + w)
    try:
        pic = split_mod.map_picture(args.stl, res, os.path.join(args.out, (args.base or "cut") + "_map.png"), scale=args.scale)
        print("map   " + pic)
    except Exception as e:
        print(f"(no picture: {type(e).__name__})")
    return 0 if res["ok"] else 1

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
    pl.add_argument("stl", nargs="*"); pl.add_argument("--group", default=None, help="slice the [[export]] pieces of this group as one multi-colour plate (needs --project)"); pl.add_argument("--out", required=True); pl.add_argument("--project", default=None, help="project folder: records the result, and refuses an STL older than its model")
    pl.add_argument("--supports", default="auto", choices=["auto", "none"], help="auto: paint support enforcers under shelves and check no support fills a small hole; none: never paint"); pl.add_argument("--together", action="store_true", help="put all the STLs on ONE plate (each part is painted and checked on its own)"); pl.add_argument("--name", default=None, help="name of the --together plate"); pl.add_argument("--split", default=None, help="slice every section named in a NAME_split.json from `fit2print split`"); pl.add_argument("--filament", default="pla_black"); pl.add_argument("--profile", default=None)
    pl.set_defaults(fn=cmd_plate)
    i = s.add_parser("init", help="start a new project folder from the template (marker, brief, NEXT.md, AI rules)")
    i.add_argument("folder"); i.add_argument("--name", required=True); i.add_argument("--kind", default="design-and-print"); i.add_argument("--printer-profile", default="bambu_a1_pla")
    i.set_defaults(fn=cmd_init)
    sv = s.add_parser("serve", help="the front door: a local web app (Home, project, log a print, new project)")
    sv.add_argument("--config", default=None, help="default ~/.config/fit2print/config.toml"); sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--printer", default=None, help="printer file, default ~/.config/fit2print/printer.toml"); sv.add_argument("--port", type=int, default=8750); sv.add_argument("--token", default=None, help="required for any address except localhost"); sv.add_argument("--trust-lan", action="store_true", help="devices on the home network (private addresses) need no token, unless the request came through a proxy such as a Cloudflare tunnel"); sv.add_argument("--token-file", default=None, help="read the token from this file (keeps it off the command line)")
    sv.set_defaults(fn=cmd_serve)
    sy = s.add_parser("sync", help="keep the server's copy of a project in step with this master copy (pull its new log entries and photos, push the state)")
    sy.add_argument("project"); sy.add_argument("remote", help="folder, or host:folder over ssh"); sy.add_argument("--dry-run", action="store_true"); sy.add_argument("--prefer", choices=["local", "server"], help="settle a both-sides-changed conflict this way")
    sy.set_defaults(fn=cmd_sync)
    sa = s.add_parser("sync-all", help="sync every project in the config with the server, and bring home projects started on the server")
    sa.add_argument("--remote", required=True, help="the server's projects folder, e.g. phobos:f2p_server/projects"); sa.add_argument("--config", default=None)
    sa.add_argument("--dry-run", action="store_true"); sa.add_argument("--prefer", choices=["local", "server"]); sa.set_defaults(fn=cmd_sync_all)
    hw = s.add_parser("hardware", help="the component library: list, show, verify (record YOUR measurement), openscad (parameters for a model)")
    hw.add_argument("action", choices=["list", "show", "verify", "openscad"]); hw.add_argument("id", nargs="?"); hw.add_argument("dim", nargs="?"); hw.add_argument("value", nargs="?")
    hw.add_argument("--how", default="callipers"); hw.set_defaults(fn=cmd_hardware)
    rn = s.add_parser("render", help="draw pictures of what the design should look like (the project's [[render]] views, from its model)")
    rn.add_argument("project"); rn.set_defaults(fn=cmd_render)
    st = s.add_parser("stage", help="show a project's stage (--set STAGE to set it directly, e.g. for an established project)")
    st.add_argument("project"); st.add_argument("--set", choices=[k for k, _ in __import__("fit2print.stage", fromlist=["STAGES"]).STAGES]); st.set_defaults(fn=cmd_stage)
    ac = s.add_parser("assembly-check", help="a virtual build from checks.toml: slide each part into place and push a rod for each screw, with controls that must fire")
    ac.add_argument("project"); ac.add_argument("--only", default=None, help="run only the cases whose name contains this text"); ac.set_defaults(fn=cmd_assembly_check)
    cp = s.add_parser("coupon", help="cut small test pieces (coupons) out of a part's real STL, to try one doubtful spot before a long print")
    cp.add_argument("stl"); cp.add_argument("--out", required=True); cp.add_argument("--zmax", type=float, help="drop everything above this height (mm)")
    cp.add_argument("--box", nargs=5, action="append", metavar=("NAME", "X0", "X1", "Y0", "Y1")); cp.set_defaults(fn=cmd_coupon)
    sp = s.add_parser("split", help="cut a part of any size into sections that fit the bed, with pin joints, each lying on its largest flat cut face")
    sp.add_argument("stl", help="an STL file, or a project folder (then every [[split]] table in its fit2print.toml is cut)"); sp.add_argument("--out"); sp.add_argument("--base"); sp.add_argument("--bed", nargs=3, type=float, metavar=("X", "Y", "Z"), help="the bed in mm (default: Bambu A1 256 x 256 x 256)")
    sp.add_argument("--margin", type=float, default=6.0, help="room kept free round the edge of the bed (default 6 mm)"); sp.add_argument("--scale", type=float, default=1.0, help="shrink or grow the whole part first (a test print at 0.4, say)")
    sp.add_argument("--max-pieces", type=int, default=64); sp.add_argument("--cut", action="append", metavar="AXIS=POS", help="cut exactly here (x=173.5), repeatable, instead of planning")
    sp.add_argument("--pin", type=float, default=3.0, help="pin diameter in mm (default 3.0)"); sp.add_argument("--no-pins", action="store_true"); sp.add_argument("--joint", default="auto", choices=["auto", "pins", "keys"], help="auto: pins, and interlocking teeth where the walls are too thin for pins")  ; sp.set_defaults(fn=cmd_split)
    ex = s.add_parser("export", help="write each [[export]] piece of the model as stl/NAME.stl, flat on the bed, ready for the checks and the slicer")
    ex.add_argument("project"); ex.set_defaults(fn=cmd_export)
    a = p.parse_args(argv)
    return a.fn(a)

if __name__ == "__main__":
    sys.exit(main())
