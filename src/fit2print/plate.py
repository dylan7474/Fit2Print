"""STL to a sliced, checked print file. Extracted from Phonosphere's make_plate.py (first version: parts that print WITHOUT supports).

  1. refuse a stale STL: if the project names its model source, an STL older than that source is not the current design;
  2. slice with the Bambu Studio command line (A1 profiles in profiles/bambu_a1);
  3. read the sliced toolpaths and judge them (toolpath.report): BLOCK stops the plate, CHECK must be looked at by a person;
  4. note any support the slicer built where none was meant (it would fill holes) and write a record line into the project.
Still in Phonosphere's make_plate.py and to come: painting supports under shelves, the as-built comparison, flipped print orientations.
"""
import datetime, hashlib, json, os, shutil, subprocess, tempfile
from . import gcode, toolpath
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
    """Run Bambu Studio on one STL. -> (path of the sliced 3MF, result dict from the slicer)."""
    name = name or os.path.splitext(os.path.basename(stl))[0]
    os.makedirs(outdir, exist_ok=True)
    with tempfile.TemporaryDirectory() as d:
        cmd = ["bambu-studio", "--load-settings", f"{profiles}/machine.json;{profiles}/process_0.28_manual_support.json",
               "--load-filaments", f"{profiles}/{filament}.json", "--arrange", "1", "--orient", "0", "--slice", "0",
               "--outputdir", d, "--export-3mf", name + ".3mf", os.path.abspath(stl)]
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

def make(stl, outdir, cfg=None, filament="pla_black", source=None, project=None, profiles=PROFILES):
    """-> dict(part, verdict, minutes, grams, notes, file). The verdict is the worst of the checks."""
    cfg = cfg or Settings.load()
    name = os.path.splitext(os.path.basename(stl))[0]
    stale = check_fresh(stl, source)
    if stale:
        raise SystemExit("REFUSED: " + stale)
    dest, plate = slice_stl(stl, outdir, filament, profiles, name)
    layers, _, _ = gcode.parse(gcode.read_gcode(dest), cfg.filament_area)
    supports = sum(1 for segs in layers.values() for f, s, _ in segs if f.startswith("Support"))
    v, lines = toolpath.report(layers, cfg)
    notes = list(lines)
    if supports:
        notes.append(f"{supports} support segments were built where none were painted (they would fill holes): look at the plate")
        v = "CHECK" if v == "PASS" else v
    rec = dict(date=datetime.date.today().isoformat(), part=name, verdict=v, minutes=round(plate["total_predication"] / 60),
               grams=round(sum(f["total_used_g"] for f in plate["filaments"])), notes=notes, file=dest, stl_sha=sha(stl), profile=cfg.name)
    if project:
        os.makedirs(os.path.join(project, "records"), exist_ok=True)
        with open(os.path.join(project, "records", "plates.jsonl"), "a") as f:
            f.write(json.dumps(rec) + "\n")
    return rec
