#!/usr/bin/env python3
"""Run Fit2Print's checks on the sample case (run from anywhere): python3 samples/pizero_case/run_checks.py
Uses: fit2print.layers.analyse (bridge vs cantilever), fit2print.snap (hook strain), and OpenSCAD for fit and the lid's path. Exit 1 on a failure."""
import os, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "src"))
import trimesh
from fit2print import layers, snap
from fit2print.settings import Settings

cfg = Settings.load()
SCAD = os.path.join(HERE, "case.scad")
tmp = tempfile.mkdtemp()
fail = 0

def scad(name, out, **defs):
    cmd = ["openscad", "-q", "--backend=manifold", "-o", out, "-D", f'part="{name}"']
    for k, v in defs.items():
        cmd += ["-D", f"{k}={v}"]
    subprocess.run(cmd + [SCAD], capture_output=True, text=True)

def say(ok, text):
    global fail
    fail |= not ok
    print(("ok    " if ok else "FAIL  ") + text)

def vol(name, **defs):
    out = os.path.join(tmp, name + ".stl")
    if os.path.exists(out): os.remove(out)
    scad(name, out, **defs)
    return abs(trimesh.load(out).volume) if os.path.exists(out) and os.path.getsize(out) > 200 else 0.0

def param(name):
    """Read a numeric parameter from the model (so the check cannot disagree with the model)."""
    import re
    m = re.search(r"\b" + name + r"\s*=\s*([-0-9.]+)\s*[;,]", open(SCAD).read())
    return float(m.group(1))

# 1. printability: each part in its printing orientation
for part in ("base", "lid_print"):
    out = os.path.join(tmp, part + ".stl"); scad(part, out)
    w = layers.analyse(trimesh.load(out))
    c, b = (w["cant"][0] if w["cant"] else 0), (w["bridge"][0] if w["bridge"] else 0)
    ok = c <= cfg.cantilever_check and b <= cfg.bridge_check
    say(ok, f"{part}: worst cantilever {c} mm (limit {cfg.cantilever_check}), worst bridge {b} mm (limit {cfg.bridge_check})")

# 2. the snap hooks: strain
v, e, msg = snap.check(param("hook_t"), param("hook_len"), param("tooth") + 0.1, cfg)
say(v == "PASS", msg + f": {v}" + ("" if v == "PASS" else f"; the shortest hook that passes is {snap.min_length(param('hook_t'), param('tooth') + 0.1, cfg):.1f} mm"))

# 3. fit: the board in the case, with the lid on, must not touch the case anywhere (ports pass through their openings)
for what, p in (("board vs base", "chk_board_base"), ("board vs lid", "chk_board_lid"), ("lid vs base (assembled)", "chk_lid_base")):
    x = vol(p)
    say(x < 1.0, f"{what}: {x:.1f} mm3 overlap")

# 4. putting the lid on: slide it down onto the base in steps; only the hooks' teeth may touch (they flex), nothing else
allowed = 4 * 14.0           # mm3: four teeth, each about 0.5 mm of interference over its height and width
worst = 0.0
for off in (30, 20, 12, 8, 4, 2, 0):
    worst = max(worst, vol("chk_lid_path", chk_off=off))
say(worst <= allowed, f"lid onto the base: worst overlap on the way {worst:.1f} mm3 (the teeth may touch: allowed {allowed:.0f})")

# 5. negative controls: these MUST be flagged
x = vol("chk_board_base_shifted")
say(x > 1.0, f"control: a board shifted 1 mm sideways touches the case ({x:.1f} mm3), must be flagged")
v2 = snap.check(1.2, 4, 0.8, cfg)[0]
say(v2 != "PASS", f"control: a 4 mm hook bent 0.8 mm is flagged ({v2})")

print("\n[sample pizero_case] " + ("ALL CLEAR" if not fail else "PROBLEMS FOUND"))
sys.exit(1 if fail else 0)
