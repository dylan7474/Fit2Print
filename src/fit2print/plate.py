"""STL to a sliced, checked print file. Extracted from Phonosphere's make_plate.py (first version: parts that print WITHOUT supports).

  1. refuse a stale STL: if the project names its model source, an STL older than that source is not the current design;
  2. slice with the Bambu Studio command line (A1 profiles in profiles/bambu_a1);
  3. read the sliced toolpaths and judge them (toolpath.report): BLOCK stops the plate, CHECK must be looked at by a person;
  4. note any support the slicer built where none was meant (it would fill holes) and write a record line into the project.
  5. supports=auto: shelves get painted support enforcers (support.py), the plate is re-sliced, and support inside a small hole BLOCKs.
  6. the as-built comparison (asbuilt.py): the nozzle path laid over the model, layer by layer. FILLED (support in a hole) BLOCKs; MISSING/EXTRA are CHECKs.
  7. make_together(): several STLs on one plate, painted and compared per part (matched by file name). Flipped parts: `orient` in [[export]].
"""
import datetime, hashlib, json, os, shutil, subprocess, tempfile
from . import asbuilt, export as export_mod, gcode, multicolour, support, toolpath
from .settings import ROOT, Settings

PROFILES = os.path.join(ROOT, "profiles", "bambu_a1")

def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()[:10]

def check_fresh(stl, source):
    """None if the STL is at least as new as `source` (a file, or a list of files), else the reason it is refused."""
    srcs = [source] if isinstance(source, str) else list(source or [])
    for s in srcs:
        if os.path.exists(s) and os.path.getmtime(stl) < os.path.getmtime(s):
            return f"{os.path.basename(stl)} is older than {os.path.basename(s)}: it may not be the current design (rebuild it)"
    return None

def slice_stl(stl, outdir, filament="pla_black", profiles=PROFILES, name=None):
    """Run Bambu Studio on one STL (or on a ready-made project .3mf, whose own filaments are kept). -> (path of the sliced 3MF, result dict from the slicer)."""
    stls = [stl] if isinstance(stl, str) else list(stl)         # several STLs go on one plate together
    name = name or os.path.splitext(os.path.basename(stls[0]))[0]
    stl = stls[0]
    os.makedirs(outdir, exist_ok=True)
    with tempfile.TemporaryDirectory() as d:
        if stl.endswith(".3mf"):
            cmd = ["bambu-studio", "--load-settings", f"{profiles}/machine.json;{profiles}/process_0.28_manual_support.json", "--slice", "0",
                   "--outputdir", d, "--export-3mf", name + ".3mf", os.path.abspath(stl)]
        else:
            cmd = ["bambu-studio", "--load-settings", f"{profiles}/machine.json;{profiles}/process_0.28_manual_support.json",
                   "--load-filaments", f"{profiles}/{filament}.json", "--arrange", "1", "--orient", "0", "--slice", "0",
                   "--outputdir", d, "--export-3mf", name + ".3mf"] + [os.path.abspath(f) for f in stls]
        subprocess.run(cmd, capture_output=True, timeout=1800)
        rj = os.path.join(d, "result.json")
        if not os.path.exists(rj):
            raise RuntimeError("Bambu Studio produced no result.json: the slice failed (is the STL valid and does it fit the plate?)")
        res = json.load(open(rj))
        if not res.get("sliced_plates"):
            raise RuntimeError(f"Bambu Studio could not slice {stl}: {res.get('error_string') or res}")
        dest = os.path.join(outdir, name + ".3mf")
        shutil.copy(os.path.join(d, name + ".3mf"), dest)
    return dest, res["sliced_plates"][0]

def make(stl, outdir, cfg=None, filament="pla_black", source=None, project=None, profiles=PROFILES, supports="auto"):
    """-> dict(part, verdict, minutes, grams, notes, file). The verdict is the worst of the checks.
    supports="auto": shelves (ledges, rebates) found in the model get painted support enforcers and the plate is re-sliced; nothing else is supported.
    supports="none": never paint (the old behaviour; any support the slicer builds is reported)."""
    cfg = cfg or Settings.load()
    name = os.path.splitext(os.path.basename(stl))[0]
    stale = check_fresh(stl, source)
    if stale:
        raise SystemExit("REFUSED: " + stale)
    dest, plate = slice_stl(stl, outdir, filament, profiles, name)
    regions, painted = [], 0
    if supports == "auto" and stl.endswith((".stl", ".STL")):
        import trimesh
        mesh = trimesh.load(stl)
        regions = support.shelves(mesh, span=cfg.shelf_ok)
        if regions:
            tmp = os.path.join(tempfile.mkdtemp(), "painted.3mf")
            painted = support.paint(dest, mesh, regions, tmp)
            if painted:
                dest, plate = slice_stl(tmp, outdir, filament, profiles, name)
            os.unlink(tmp)
    return _judge(dest, plate, name, cfg, stl, project, regions=regions, painted=painted)

def make_together(stls, outdir, cfg=None, filament="pla_black", name=None, source=None, project=None, profiles=PROFILES, supports="auto"):
    """Several STLs on ONE plate (e.g. the mirror pair, or four small parts for one overnight print). Each part gets its own shelf painting and its own
    as-built check, matched to the plate by file name. -> the same dict as make()."""
    cfg = cfg or Settings.load()
    stls = [os.path.abspath(f) for f in stls]
    if len(stls) < 2:
        raise SystemExit("REFUSED: --together needs two or more STLs")
    if len({os.path.basename(f) for f in stls}) != len(stls):
        raise SystemExit("REFUSED: two of the STLs have the same file name; the plate matches parts by name")
    for f in stls:
        stale = check_fresh(f, source)
        if stale:
            raise SystemExit("REFUSED: " + stale)
    name = name or "+".join(os.path.splitext(os.path.basename(f))[0] for f in stls)[:60]
    dest, plate = slice_stl(stls, outdir, filament, profiles, name)
    import trimesh
    meshes = {os.path.basename(f): trimesh.load(f) for f in stls}
    regions = {n: (support.shelves(m, span=cfg.shelf_ok) if supports == "auto" else []) for n, m in meshes.items()}
    painted = {}
    if any(regions.values()):
        tmp = os.path.join(tempfile.mkdtemp(), "painted.3mf")
        painted = support.paint_plate(dest, {n: (meshes[n], regions[n]) for n in meshes}, tmp)
        if sum(painted.values()):
            dest, plate = slice_stl(tmp, outdir, filament, profiles, name)
        os.unlink(tmp)
    rec = _judge(dest, plate, name, cfg, stls, project, regions=[r for v in regions.values() for r in v], painted=sum(painted.values()))
    rec["parts"] = {n: dict(shelves=len(regions[n]), faces_painted=painted.get(n, 0)) for n in meshes}
    return rec

def make_group(folder, marker, group, outdir, cfg=None, profiles=PROFILES):
    """Slice the pieces of one [[export]] group as ONE multi-colour plate (each piece in its own filament). -> the same dict as make()."""
    cfg = cfg or Settings.load()
    ps = export_mod.groups(marker).get(group)
    if not ps:
        raise SystemExit(f"REFUSED: the project has no [[export]] group called {group!r}")
    src = [os.path.join(folder, marker["model"])] if isinstance(marker.get("model"), str) else None
    stls = []
    for p in ps:
        f = os.path.join(folder, export_mod.stl_dir(marker), p["name"] + ".stl")
        if not os.path.exists(f):
            raise SystemExit(f"REFUSED: {os.path.relpath(f, folder)} is missing (run the export first)")
        stale = check_fresh(f, src)
        if stale:
            raise SystemExit("REFUSED: " + stale)
        stls.append(f)
    nums, colours = multicolour.slots(ps)
    with tempfile.TemporaryDirectory() as d:
        proj = os.path.join(d, group + ".3mf")
        multicolour.write_3mf(proj, group, [(p["name"], multicolour.load_mesh(f), n) for p, f, n in zip(ps, stls, nums)], colours)
        dest, plate = slice_stl(proj, outdir, profiles=profiles, name=group)
    rec = _judge(dest, plate, group, cfg, stls, folder)
    rec["filaments"] = {str(n): dict(colour=colours[n], pieces=[p["name"] for p, k in zip(ps, nums) if k == n]) for n in colours}
    return rec

def _judge(dest, plate, name, cfg, stl, project, regions=(), painted=0, asbuilt_check=True):
    layers, _, _ = gcode.parse(gcode.read_gcode(dest), cfg.filament_area)
    supports = sum(1 for segs in layers.values() for f, s, _ in segs if f.startswith("Support"))
    v, lines = toolpath.report(layers, cfg)
    notes = list(lines)
    if regions:
        notes.append(f"{len(regions)} shelf region(s): support enforcers painted on {painted} faces")
        if not painted:
            notes.append("BLOCK: a shelf needs support but no faces could be painted"); v = "BLOCK"
        elif not supports:
            notes.append("BLOCK: supports were painted but none were built"); v = "BLOCK"
        if isinstance(stl, str) and stl.endswith((".stl", ".STL")):
            import trimesh
            holes = support.holes_with_support(trimesh.load(stl), layers, allow=regions)
            if holes:
                notes.append(f"BLOCK: support inside {len(holes)} small hole(s), e.g. at x {holes[0][1]:.0f}, y {holes[0][2]:.0f}"); v = "BLOCK"
    elif supports:
        notes.append(f"{supports} support segments were built where none were painted (they would fill holes): look at the plate")
        v = "CHECK" if v == "PASS" else v
    if asbuilt_check and isinstance(stl, str) and stl.endswith((".stl", ".STL")):
        import trimesh
        av, alines = asbuilt.check(layers, trimesh.load(stl), span=cfg.shelf_ok)
        for t in alines:
            notes.append(("BLOCK: " if av == "BLOCK" else "CHECK: ") + t)
        v = "BLOCK" if av == "BLOCK" or v == "BLOCK" else ("CHECK" if av == "CHECK" and v == "PASS" else v)
    elif asbuilt_check and isinstance(stl, list) and stl and all(f.endswith((".stl", ".STL")) for f in stl) and dest.endswith(".3mf"):
        import trimesh
        boxes = asbuilt.plate_boxes(dest)                       # where the slicer put each part, by file name
        for f in stl:
            box = asbuilt.find_box(boxes, f)
            if box is None:
                notes.append(f"CHECK: {os.path.basename(f)} was not found on the plate, so it was not compared with its design"); v = "CHECK" if v == "PASS" else v
                continue
            av, alines = asbuilt.check(layers, trimesh.load(f), box, span=cfg.shelf_ok)
            for t in alines:
                notes.append(("BLOCK: " if av == "BLOCK" else "CHECK: ") + os.path.basename(f) + ": " + t)
            v = "BLOCK" if av == "BLOCK" or v == "BLOCK" else ("CHECK" if av == "CHECK" and v == "PASS" else v)
    rec = dict(date=datetime.date.today().isoformat(), part=name, verdict=v, minutes=round(plate["total_predication"] / 60),
               grams=round(sum(f["total_used_g"] for f in plate["filaments"])), notes=notes, file=dest, stl_sha=sha(stl) if isinstance(stl, str) else "+".join(sha(x) for x in stl), profile=cfg.name)
    if project:
        os.makedirs(os.path.join(project, "records"), exist_ok=True)
        with open(os.path.join(project, "records", "plates.jsonl"), "a") as f:
            f.write(json.dumps(rec) + "\n")
    return rec
