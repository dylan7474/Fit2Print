"""Calibrate a printer + filament + profile with ONE printed card. Extracted from Phonosphere's calibrate.py / calibration_card.scad.

    fit2print calibrate card --out DIR        # writes calibration_card.stl and MEASURE.md (print it once per filament and profile, then measure)
    fit2print calibrate record --name "Creality black PLA 0.28" --holes 3.0:2.75,... --outer 20:20.1,... --pin ok --shelf-ok 5 --bridge-ok 10 ...

`record` writes a PROFILE (a copy of the base profile with a [calibration] table) that every check reads (`plate --profile FILE`). What is used where:
  shelf_ok    the longest card shelf that printed clean: a ledge reaching further than this gets painted supports (plate, support.shelves)
  bridge_ok   the longest card bridge that did not sag: the toolpath check's bridge CHECK limit (never above the base profile's)
  flow        the volumetric flow that still gave solid walls: the profile's flow_limit
  hole_comp / outer_comp   what the printer did to holes and outsides; written to printer_offsets.scad for a model to use (hole_d() / outer_d()) with --project
  pin, wall_ok, lean_ok     recorded in the profile and the log, for the designer: no check uses them yet (said plainly, not implied)
Every measurement is sanity-checked first: a number that cannot be a caliper reading (a 3 mm hole 'measuring' 9 mm) is refused, not averaged in."""
import datetime, json, math, os, re, shutil, subprocess
from .settings import ROOT, Settings

CARD = os.path.join(ROOT, "templates", "calibration_card.scad")
HOLES = [2.5, 3.0, 3.3, 4.2, 5.0, 6.0, 9.6]
BRIDGES = [4, 6, 8, 10, 12, 15]
SHELVES = [2, 3.5, 5, 8, 11]
LEANS = [30, 45, 55, 65, 75]
WALLS = [0.8, 1.2, 1.6, 2.0, 2.4]
MAX_ERR = 0.35          # mm: a hole or block that measures more than this from its drawn size is a typing slip or a broken print, not a calibration


MEASURE = """# Measuring the calibration card

Print `calibration_card.stl` once for each filament and each slicer profile (about 35 minutes at 0.28 mm). Measure with calipers after it has cooled.

| Part | What to do | Option |
|---|---|---|
| A: hole ladder (2.5 to 9.6 mm) | Measure what each hole really came out at (inside jaws, or the drill bit that just fits) | `--holes 3.0:2.75,3.3:3.05,...` (drawn:measured) |
| B: two outside blocks (20 and 40 mm) | Measure each | `--outer 20:20.1,40:40.15` |
| C: four pins, 3.0 mm | Push one into the 3.3 mm hole of A: does it fit? | `--pin ok` or `tight` or `loose` |
| D: thin walls (0.8 to 2.4 mm) | The thinnest wall that stood and was solid | `--wall-ok 0.8` |
| E: bridges (4, 6, 8, 10, 12, 15 mm) | The longest span that did not sag (lay a straight edge on it) | `--bridge-ok 10` |
| F: shelves (2, 3.5, 5, 8, 11 mm) | The longest shelf whose underside printed clean | `--shelf-ok 5` |
| G: leaning walls (30 to 75 degrees) | The steepest lean whose underside stayed clean | `--lean-ok 55` |
| flow test (optional) | The highest volumetric flow (mm3/s) that still gave solid walls | `--flow 14` |

Then: `fit2print calibrate record --name "Creality black PLA 0.28" --holes ... --outer ... [--project PROJECT_FOLDER]`.
"""


def card(outdir, command=None, timeout=300):
    """Draw the card with OpenSCAD -> (stl path, measuring sheet path)."""
    os.makedirs(outdir, exist_ok=True)
    stl = os.path.join(outdir, "calibration_card.stl")
    cmd = command or [shutil.which("openscad") or "openscad"]
    try:
        r = subprocess.run(cmd + ["-q", "--backend=manifold", "-o", stl, CARD], capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        raise ValueError("OpenSCAD is not installed on this machine")
    if not os.path.exists(stl) or os.path.getsize(stl) < 200:
        raise ValueError("OpenSCAD drew nothing: " + ((r.stderr.strip().splitlines() or ["no message"])[-1][:160]))
    sheet = os.path.join(outdir, "MEASURE.md")
    with open(sheet, "w") as fh:
        fh.write(MEASURE)
    return stl, sheet


def pairs(text, what):
    """'3.0:2.75,5:4.8' -> [(3.0, 2.75), (5.0, 4.8)]; anything that is not a drawn:measured pair of numbers is refused."""
    out = []
    for p in [x for x in (text or "").split(",") if x.strip()]:
        m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)\s*", p)
        if not m:
            raise ValueError(f"--{what}: '{p.strip()}' is not DRAWN:MEASURED (for example 3.0:2.75)")
        nominal, measured = float(m.group(1)), float(m.group(2))
        if abs(nominal - measured) > MAX_ERR * max(1.0, nominal / 10):
            raise ValueError(f"--{what}: {nominal:g} mm 'measured' {measured:g} mm: that is {abs(nominal - measured):.2f} mm out, more than a printer does. Measure it again (or the print failed there).")
        out.append((nominal, measured))
    return out


def compensation(holes, outer):
    """(hole_comp, outer_comp, notes). Holes of 3 mm and over only: the 2.5 mm hole is dominated by the nozzle path, so it is reported, not averaged."""
    notes = []
    h = [n - m for n, m in holes if n >= 3.0]
    o = [n - m for n, m in outer]
    if not h:
        notes.append("no hole of 3 mm or more was measured: hole_comp is 0 (not measured)")
    if not o:
        notes.append("no outside block was measured: outer_comp is 0 (not measured)")
    snap = lambda v: round(round(v / 0.05) * 0.05, 2) + 0.0
    return (snap(sum(h) / len(h)) if h else 0.0), (snap(sum(o) / len(o)) if o else 0.0), notes


def record(name, base=None, holes="", outer="", pin=None, bridge_ok=None, shelf_ok=None, wall_ok=None, lean_ok=None, flow=None, filament=None, today=None):
    """-> dict(settings values) from the measurements. Raises ValueError for a measurement that cannot be real."""
    if pin not in (None, "ok", "tight", "loose"):
        raise ValueError("--pin must be ok, tight or loose")
    for val, allowed, what in ((bridge_ok, BRIDGES, "bridge-ok"), (shelf_ok, SHELVES, "shelf-ok"), (wall_ok, WALLS, "wall-ok"), (lean_ok, LEANS, "lean-ok")):
        if val is not None and float(val) not in [float(a) for a in allowed]:
            raise ValueError(f"--{what} {val}: the card only has {', '.join(f'{a:g}' for a in allowed)}")
    if flow is not None and not (1.0 <= flow <= 60.0):
        raise ValueError("--flow must be between 1 and 60 mm3/s")
    h, o = pairs(holes, "holes"), pairs(outer, "outer")
    hc, oc, notes = compensation(h, o)
    base_cfg = Settings.load(base)
    rec = dict(name=name, date=(today or datetime.date.today().isoformat()), filament=filament or name, base=base_cfg.name, hole_comp=hc, outer_comp=oc, holes=h, outer=o, pin=pin,
               bridge_ok=bridge_ok, shelf_ok=shelf_ok, wall_ok=wall_ok, lean_ok=lean_ok, flow_limit=flow, notes=notes)
    rec["applied"] = []
    if shelf_ok is not None:
        rec["applied"].append(f"shelf_ok {shelf_ok:g} mm: ledges reaching further get painted supports")
    if bridge_ok is not None:
        new = min(float(bridge_ok), base_cfg.bridge_check)
        rec["bridge_check"] = new
        rec["applied"].append(f"bridge CHECK limit {new:g} mm" + ("" if new == bridge_ok else f" (the card's {bridge_ok:g} mm is above the base profile's, which stays)"))
    if flow is not None:
        rec["applied"].append(f"flow limit {flow:g} mm3/s")
    return rec


def write_profile(rec, path, base=None):
    """Write the calibrated profile (every field the checks read, from the base profile plus this card) to `path`. -> path."""
    cfg = Settings.load(base)
    flow = rec["flow_limit"] if rec.get("flow_limit") is not None else cfg.flow_limit
    bridge_check = rec.get("bridge_check", cfg.bridge_check)
    lines = [f"# Calibrated profile '{rec['name']}' ({rec['date']}): the base profile ({rec['base']}) with the numbers this printer + filament measured on the calibration card.",
             f"name = {json.dumps(rec['name'])}", f"filament_diameter = {cfg.filament_diameter}", f"flow_limit = {flow}", f"flow_share_check = {cfg.flow_share_check}", "",
             "[air]", f"support_distance = {cfg.air_support_distance}", f"check = {cfg.air_check}", f"block = {cfg.air_block}", "",
             "[anchor]", f"resolution = {cfg.resolution}", f"reach = {cfg.reach}", f"look = {cfg.look}", f"cantilever_check = {cfg.cantilever_check}",
             f"cantilever_block = {cfg.cantilever_block}", f"bridge_check = {bridge_check}", f"bridge_block = {cfg.bridge_block}", "",
             "[snap]", f"strain_limit = {cfg.snap_strain_limit}", "", "[calibration]", f"date = {json.dumps(rec['date'])}", f"hole_comp = {rec['hole_comp']}", f"outer_comp = {rec['outer_comp']}"]
    shelf = rec["shelf_ok"] if rec.get("shelf_ok") is not None else cfg.shelf_ok
    lines.append(f"shelf_ok = {float(shelf)}")
    for k in ("bridge_ok", "wall_ok", "lean_ok"):
        if rec.get(k) is not None:
            lines.append(f"{k} = {float(rec[k])}")
    if rec.get("pin"):
        lines.append(f"pin = {json.dumps(rec['pin'])}")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    return path


def write_offsets(rec, folder):
    """printer_offsets.scad in the project: a model includes it and uses hole_d(d) / outer_d(d) for new features. -> path."""
    p = os.path.join(folder, "printer_offsets.scad")
    with open(p, "w") as fh:
        fh.write(f"// written by fit2print calibrate {rec['date']}: {rec['name']}\n"
                 "// hole_comp: add to a hole's drawn diameter; outer_comp: add to an outside dimension. New features use hole_d() / outer_d(); proven values already include their allowance.\n"
                 f"hole_comp = {rec['hole_comp']};\nouter_comp = {rec['outer_comp']};\nfunction hole_d(d) = d + hole_comp;\nfunction outer_d(d) = d + outer_comp;\n")
    return p


def log(rec, folder):
    """Append one line to CALIBRATION.md in the project (a header the first time)."""
    p = os.path.join(folder, "CALIBRATION.md")
    new = not os.path.exists(p)
    with open(p, "a") as fh:
        if new:
            fh.write("# Calibration log (one line per card)\n\n| Date | Name | hole_comp | outer_comp | Pin | Bridge ok | Shelf ok | Wall ok | Lean ok | Flow limit |\n|---|---|---|---|---|---|---|---|---|---|\n")
        g = lambda v: "" if v is None else f"{v:g}"
        fh.write(f"| {rec['date']} | {rec['name']} | {rec['hole_comp']:+g} | {rec['outer_comp']:+g} | {rec['pin'] or ''} | {g(rec['bridge_ok'])} | {g(rec['shelf_ok'])} | {g(rec['wall_ok'])} | {g(rec['lean_ok'])} | {g(rec['flow_limit'])} |\n")
    return p
