"""A virtual build, before anything is printed: can each part be put on, and do the screws land? Extracted from Phonosphere's check_assembly.py.

The project lists the cases in checks.toml; the parts are drawn from the model in their ASSEMBLED places (not the bed-ready STLs). A part name is either
one of the model's `part` values (when the model draws that part where it goes in the assembly), or defined in checks.toml as an OpenSCAD snippet:

    prelude = 'include <model.scad>  part = "none";'      # put before every snippet (include the model, define helper modules)
    [parts]
    shell = "shell_body();"
    face  = "front_whole(); trims();"

    [[sweep]]                      # slide parts along a straight path and overlap them with what is already fitted
    name  = "the face onto the shell"
    move  = ["face_lower_L", "face_lower_R"]
    fixed = ["shell_lower_L", "shell_lower_R"]
    direction = [0, -1, 0]         # which way the moving part travels to its place; it is tested from `travel` mm away, in `step` mm steps, to the final place
    travel = 40
    step   = 2                     # mm between sampled positions (a rib thinner than the step can be stepped over; the default is 2)
    allow  = 1.0                   # mm3 of overlap accepted anywhere along the way (a touch is nothing)

    [[screw]]                      # a rod stands for each screw
    name   = "face screws"
    clear  = ["shell_lower_L"]     # the rod must pass these without touching them (the holes line up) ...
    thread = ["face_lower_L"]      # ... and bite at least `min_bite` mm of these
    diameter = 3.0
    clear_len = 8.0                # from the head: this much is in the clear parts, then
    thread_len = 4.0               # this much is in the thread parts
    min_bite = 3.5
    at  = [[x, y, z], ...]         # where each screw's head sits
    dir = [0, -1, 0]               # the way the screws go in

    [[probe]]                      # a combination that must be EMPTY (a part against the cabinet, a clearance volume, a hole that must stay open)
    name = "speaker clears the pod"
    snippet = "intersection() { speaker(); pod(); }"     # or: part = "speaker_clash" (a model part value) and define = { chk_i = 3 }
    allow = 1.0                    # mm3 accepted (a touch is nothing); must_overlap = true turns it into a control that MUST find an overlap

    [[driver]]                     # a straight run for a driver: a rod from each point along `dir` must meet no plastic of `parts`
    name = "face screws"
    parts = ["shell"]
    radius = 3.0                   # a 6 mm driver
    length = 300
    dir = [0, 1, 0]
    at = [[x, y, z], ...]
    allow = 1.5                    # mm3: a sliver where the rod starts is not material in the way; must_fail = true marks a case that MUST be blocked

    [[ring]]                       # plastic round a hole: the annulus round each hole must be mostly solid
    name = "pod floor bolts"
    part = "pod_half"
    r_out = 5.0
    r_in = 1.8
    depth = 5.0                    # along dir from `at`
    dir = [1, 0, 0]
    at = [[x, y, z], ...]
    min_fraction = 0.8             # of a full ring; must_fail = true marks a case that MUST fail

Negative controls run on every case and MUST fire, or the checker is blind: a moving part made 4 % too big must collide, and a screw moved 3 mm off its
hole must fail. A case that cannot show its control fails loudly.
"""
import math, os, shutil, subprocess, tempfile, tomllib
import numpy as np
import trimesh

LIMIT = 1.0          # mm3: a touch is nothing
SCALE_CONTROL = 1.04
OFFSET_CONTROL = 3.0


# ---------------------------------------------------------------- reading the cases
def load_cases(folder):
    p = os.path.join(folder, "checks.toml")
    if not os.path.exists(p):
        raise ValueError("this project has no checks.toml (sweep and screw cases for the virtual build)")
    with open(p, "rb") as fh:
        d = tomllib.load(fh)
    sweeps, screws = d.get("sweep") or [], d.get("screw") or []
    defs = dict(prelude=str(d.get("prelude", "")), parts={str(k): str(v) for k, v in (d.get("parts") or {}).items()})
    for s in sweeps:
        for k in ("name", "move", "fixed", "direction", "travel"):
            if k not in s:
                raise ValueError(f"checks.toml: a [[sweep]] needs {k}: {s.get('name', s)}")
        if len(s["direction"]) != 3 or not any(s["direction"]):
            raise ValueError(f"checks.toml: sweep {s['name']}: direction must be three numbers, not all zero")
        if not s["move"] or not s["fixed"]:
            raise ValueError(f"checks.toml: sweep {s['name']}: move and fixed each need at least one part")
    for s in screws:
        for k in ("name", "thread", "at", "dir", "clear_len", "thread_len"):
            if k not in s:
                raise ValueError(f"checks.toml: a [[screw]] needs {k}: {s.get('name', s)}")
        if not s["at"]:
            raise ValueError(f"checks.toml: screw {s['name']} lists no screws")
    probes, drivers, rings = d.get("probe") or [], d.get("driver") or [], d.get("ring") or []
    for pr in probes:
        if not pr.get("name") or not (pr.get("snippet") or pr.get("part")):
            raise ValueError(f"checks.toml: a [[probe]] needs a name and a snippet or a part: {pr}")
    for dr in drivers:
        for k in ("name", "parts", "dir", "at"):
            if k not in dr:
                raise ValueError(f"checks.toml: a [[driver]] needs {k}: {dr.get('name', dr)}")
        if not any(dr["dir"]) or not dr["at"] or not dr["parts"]:
            raise ValueError(f"checks.toml: driver {dr['name']}: dir, at and parts must not be empty")
    for rg in rings:
        for k in ("name", "part", "r_out", "r_in", "depth", "dir", "at"):
            if k not in rg:
                raise ValueError(f"checks.toml: a [[ring]] needs {k}: {rg.get('name', rg)}")
        if not (0 <= float(rg["r_in"]) < float(rg["r_out"])) or not any(rg["dir"]) or not rg["at"]:
            raise ValueError(f"checks.toml: ring {rg['name']}: needs 0 <= r_in < r_out, a dir and at least one point")
    defs.update(probes=probes, drivers=drivers, rings=rings)
    return sweeps, screws, defs


# ---------------------------------------------------------------- drawing and measuring
def draw_parts(folder, marker, names, command=None, timeout=300, defs=None):
    """{part name: STL path} drawn in assembled coordinates with OpenSCAD, cached until the model changes. A name in defs["parts"] is drawn from its snippet."""
    import hashlib
    defs = defs or dict(prelude="", parts={})
    folder = os.path.abspath(folder)
    model = os.path.join(folder, marker["model"])
    cache = os.path.join(folder, ".f2p_cache", "assembled")
    os.makedirs(cache, exist_ok=True)
    from . import render as _render
    _render._hardware_scad(folder, marker)
    cmd = command or [shutil.which("openscad") or "openscad"]
    out = {}
    for n in dict.fromkeys(names):
        snippet = defs["parts"].get(n)
        key = n if snippet is None else f"{n}_{hashlib.sha1((defs['prelude'] + snippet).encode()).hexdigest()[:10]}"
        f = os.path.join(cache, f"{key}.stl")
        if not os.path.exists(f) or os.path.getmtime(f) < os.path.getmtime(model):
            tmp = f + ".tmp.stl"
            if os.path.exists(tmp):
                os.remove(tmp)
            if snippet is None:
                r = subprocess.run(cmd + ["-q", "--backend=manifold", "-D", f'part="{n}"', "-o", tmp, model], capture_output=True, text=True, timeout=timeout, cwd=folder)
            else:
                src = os.path.join(cache, f"{key}.scad")
                open(src, "w").write(defs["prelude"] + "\n" + snippet + "\n")
                env = dict(os.environ, OPENSCADPATH=folder + (os.pathsep + os.environ["OPENSCADPATH"] if os.environ.get("OPENSCADPATH") else ""))      # so `include <model.scad>` is found
                r = subprocess.run(cmd + ["-q", "--backend=manifold", "-o", tmp, src], capture_output=True, text=True, timeout=timeout, cwd=folder, env=env)
            if not os.path.exists(tmp) or os.path.getsize(tmp) < 200:
                raise ValueError(f"the model draws nothing for part \"{n}\": {(r.stderr.strip().splitlines() or ['OpenSCAD made nothing'])[-1][:160]}")
            os.replace(tmp, f)
        out[n] = f
    return out


def _union(files):
    return "union() { " + " ".join(f'import("{f}");' for f in files) + " }"


def _scad(text, command=None, timeout=300):
    """Run OpenSCAD on `text`; -> the mesh, or None when nothing is left (no overlap). A real complaint raises."""
    cmd = command or [shutil.which("openscad") or "openscad"]
    with tempfile.TemporaryDirectory() as d:
        f = os.path.join(d, "c.scad"); out = os.path.join(d, "c.stl")
        open(f, "w").write(text)
        p = subprocess.run(cmd + ["-q", "--backend=manifold", "-o", out, f], capture_output=True, text=True, timeout=timeout)
        if not os.path.exists(out) or os.path.getsize(out) < 200:
            bad = [l for l in (p.stderr or "").splitlines() if any(k in l.lower() for k in ("can't open", "cannot open", "error", "could not"))]
            if bad:
                raise RuntimeError(bad[-1][:200])
            return None
        return trimesh.load(out)


def _vol(m):
    return 0.0 if m is None else abs(float(m.volume))


# ---------------------------------------------------------------- sweeps
def _grown(files, scale, centre):
    c = centre
    u = _union(files)
    if scale == 1.0:
        return u
    return f"translate([{c[0]:.4f},{c[1]:.4f},{c[2]:.4f}]) scale({scale}) translate([{-c[0]:.4f},{-c[1]:.4f},{-c[2]:.4f}]) {u}"


def overlap(move, fixed, vec, scale=1.0, centre=(0, 0, 0), command=None, grow="move"):
    """Volume (mm3) where the moving files, shifted by `vec`, overlap the fixed files. With scale != 1 the `grow` side ("move" or "fixed") is made that
    many times bigger about `centre` first (the control: a part, or what it goes into, 4 % too big must collide)."""
    m = _grown(move, scale if grow == "move" else 1.0, centre)
    f = _grown(fixed, scale if grow == "fixed" else 1.0, centre)
    return _vol(_scad(f"intersection() {{ translate([{vec[0]:.4f},{vec[1]:.4f},{vec[2]:.4f}]) {m} {f} }}", command))


def run_sweep(case, files, command=None, log=print):
    d = np.array(case["direction"], float); d /= np.linalg.norm(d)
    travel, step = float(case["travel"]), float(case.get("step", 2))
    allow = float(case.get("allow", LIMIT))
    mv = [files[n] for n in case["move"]]; fx = [files[n] for n in case["fixed"]]
    offs = [0.0] + [o for o in np.arange(step, travel + 1e-9, step)]
    worst, where = 0.0, 0.0
    for o in offs:                                   # the part starts `o` mm back along its path (against its direction of travel) and comes in
        v = overlap(mv, fx, -d * o, command=command)
        if v > worst:
            worst, where = v, float(o)
    ok = worst <= allow
    res = dict(kind="sweep", name=case["name"], ok=ok, worst=round(worst, 1), at=where, allow=allow)
    res["text"] = f"{case['name']}: worst overlap on the way {worst:.0f} mm3" + (f" at {where:g} mm out (allowed {allow:g})" if worst > LIMIT else "")
    if step > 4:                                      # sampled positions: a rib thinner than the step can be jumped over
        res["text"] += f"  [WARNING: {step:g} mm steps can jump over a rib thinner than that; use step = 2]"
    # the control: the same part 4 % too big has to collide, or this check cannot see a collision
    # (a container moving round something is not hurt by being bigger: its content growing is the test. Either one colliding shows the check can see.)
    cw = 0.0
    for side, files_ in (("move", mv), ("fixed", fx)):
        bb = np.array([trimesh.load(f).bounds for f in files_]); centre = (bb[:, 0].min(0) + bb[:, 1].max(0)) / 2
        cw = max(cw, max(overlap(mv, fx, -d * o, SCALE_CONTROL, centre, command, grow=side) for o in offs))
    res["control"] = round(cw, 1)
    res["control_ok"] = cw > max(allow, worst) and cw > LIMIT
    return res


# ---------------------------------------------------------------- screws
def _rod(at, d, a, b, dia):
    """OpenSCAD for a rod starting at `at`, running along `d` from distance a to b."""
    d = np.array(d, float); d /= np.linalg.norm(d)
    tilt = math.degrees(math.acos(max(-1, min(1, d[2])))); turn = math.degrees(math.atan2(d[1], d[0]))
    return (f"translate([{at[0]:.4f},{at[1]:.4f},{at[2]:.4f}]) rotate([0,{tilt:.5f},{turn:.5f}]) translate([0,0,{a:.4f}]) cylinder(d={dia}, h={b - a:.4f}, $fn=24);")


def _per_screw(mesh, ats, d):
    """Split the rods-in-parts mesh by screw (each face to the nearest rod axis) -> [(volume mm3, extent along the screw mm)]."""
    n = len(ats)
    if mesh is None or len(mesh.faces) == 0:
        return [(0.0, 0.0)] * n
    d = np.array(d, float); d /= np.linalg.norm(d)
    cen = mesh.triangles_center
    dist = []
    for a in ats:
        rel = cen - np.array(a)
        along = rel @ d
        dist.append(np.linalg.norm(rel - np.outer(along, d), axis=1))
    owner = np.argmin(np.array(dist), axis=0)
    tri = mesh.triangles
    signed = np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])) / 6.0
    out = []
    for i, a in enumerate(ats):
        sel = owner == i
        if not sel.any():
            out.append((0.0, 0.0)); continue
        pts = tri[sel].reshape(-1, 3)
        t = (pts - np.array(a)) @ d
        out.append((abs(float(signed[sel].sum())), float(t.max() - t.min())))
    return out


def _measure(case, files, ats, command, shift=None):
    d = case["dir"]; dia = float(case.get("diameter", 3.0))
    ats = [list(map(float, a)) for a in ats]
    if shift is not None:
        ats = [[a[i] + shift[i] for i in range(3)] for a in ats]
    cl, tl = float(case["clear_len"]), float(case["thread_len"])
    clear = [files[n] for n in case.get("clear", [])]; thread = [files[n] for n in case["thread"]]
    c_mesh = None
    if clear:
        c_mesh = _scad(f"intersection() {{ union() {{ " + " ".join(_rod(a, d, 0.01, cl, dia) for a in ats) + f" }} {_union(clear)} }}", command)
    t_mesh = _scad(f"intersection() {{ union() {{ " + " ".join(_rod(a, d, cl, cl + tl, dia) for a in ats) + f" }} {_union(thread)} }}", command)
    return _per_screw(c_mesh, ats, d), _per_screw(t_mesh, ats, d), ats


def run_screws(case, files, command=None):
    """-> list of per-screw results, plus the control result."""
    min_bite = float(case.get("min_bite", 3.5)); tl = float(case["thread_len"])
    cl_res, th_res, ats = _measure(case, files, case["at"], command)
    out = []
    for i, ((cv, _), (_, bite)) in enumerate(zip(cl_res, th_res)):
        problems = []
        if cv > LIMIT:
            problems.append(f"the rod touches the part it should pass through ({cv:.1f} mm3: holes not lined up)")
        if bite < min_bite:
            problems.append(f"bites only {bite:.1f} mm")
        elif bite < tl - 1.0 - 1e-9:
            problems.append(f"plastic runs out after {bite:.1f} mm of the {tl:g} mm the screw goes in: the tip comes out the far side")
        out.append(dict(kind="screw", name=f"{case['name']} {i}", ok=not problems, bite=round(bite, 1), clear_mm3=round(cv, 1),
                        text=f"{case['name']} {i}: bites {bite:.1f} mm" + ("; " + "; ".join(problems) if problems else "")))
    # control: the first screw moved 3 mm sideways must fail
    d = np.array(case["dir"], float); d /= np.linalg.norm(d)
    side = np.cross(d, [0, 0, 1.0] if abs(d[2]) < 0.9 else [1.0, 0, 0]); side /= np.linalg.norm(side)
    sub = dict(case); sub["at"] = [case["at"][0]]
    cv, tv, _ = _measure(sub, files, sub["at"], command, shift=side * OFFSET_CONTROL)
    fired = cv[0][0] > LIMIT or tv[0][1] < min_bite or tv[0][1] < tl - 1.0 - 1e-9
    return out, dict(name=case["name"], control_ok=bool(fired), clear_mm3=round(cv[0][0], 1), bite=round(tv[0][1], 1))


# ---------------------------------------------------------------- probes, driver runs, rings
def _probe_volume(folder, marker, pr, defs, command=None, timeout=300):
    """Volume (mm3) of what a probe draws (0 when it draws nothing)."""
    cmd = command or [shutil.which("openscad") or "openscad"]
    env = dict(os.environ, OPENSCADPATH=folder + (os.pathsep + os.environ["OPENSCADPATH"] if os.environ.get("OPENSCADPATH") else ""))
    with tempfile.TemporaryDirectory() as t:
        out = os.path.join(t, "p.stl")
        if pr.get("snippet"):
            src = os.path.join(t, "p.scad"); open(src, "w").write(defs["prelude"] + "\n" + pr["snippet"] + "\n"); extra = []
        else:
            src = os.path.join(folder, marker["model"])
            extra = ["-D", f'part="{pr["part"]}"'] + [x for k, v in (pr.get("define") or {}).items() for x in ("-D", f'{k}="{v}"' if isinstance(v, str) else f"{k}={v}")]
        r = subprocess.run(cmd + ["-q", "--backend=manifold"] + extra + ["-o", out, src], capture_output=True, text=True, timeout=timeout, cwd=folder, env=env)
        if not os.path.exists(out) or os.path.getsize(out) < 200:
            bad = [l for l in (r.stderr or "").splitlines() if any(k in l.lower() for k in ("can't open", "cannot open", "error", "could not"))]
            if bad:
                raise RuntimeError(f"probe {pr['name']}: {bad[-1][:160]}")
            return 0.0
        return _vol(trimesh.load(out))


def _tube(at, d, depth, r_out, r_in):
    return ("difference() { " + _rod(at, d, 0.0, depth, 2 * r_out) + " " + _rod(at, d, -0.5, depth + 0.5, 2 * r_in) + " }").replace("$fn=24", "$fn=32")


def run_driver(case, files, command=None):
    """Each rod from `at` along `dir` meets at most `allow` mm3 of the listed parts. Control: a rod 15 times fatter must meet plastic."""
    parts = [files[n] for n in case["parts"]]
    r = float(case.get("radius", 3.0)); length = float(case.get("length", 300)); allow = float(case.get("allow", 1.5)); must_fail = bool(case.get("must_fail", False))
    out = []
    for i, a in enumerate(case["at"]):
        v = _vol(_scad(f"intersection() {{ {_rod(a, case['dir'], 0.01, length, 2 * r)} {_union(parts)} }}", command))
        blocked = v > allow
        ok = blocked if must_fail else not blocked
        out.append(dict(kind="driver", name=f"{case['name']} {i + 1}", ok=ok, mm3=round(v, 1),
                        text=f"{case['name']} {i + 1}: driver run " + ("BLOCKED" if blocked else "clear") + (f" ({v:.0f} mm3)" if blocked else "") + (" -- expected: this is a control" if must_fail and ok else "")))
    fat = _vol(_scad(f"intersection() {{ {_rod(case['at'][0], case['dir'], 0.01, length, 2 * r * 15)} {_union(parts)} }}", command))
    return out, dict(name=case["name"], control_ok=fat > allow, mm3=round(fat, 1))


def run_ring(case, files, command=None):
    """The annulus round each hole must be at least `min_fraction` solid. Control: the first ring moved 60 mm away (one of six directions) must find air and fail."""
    part = [files[case["part"]]]
    ro, ri, depth = float(case["r_out"]), float(case["r_in"]), float(case["depth"])
    full = math.pi * (ro ** 2 - ri ** 2) * depth
    need = float(case.get("min_fraction", 0.8)); must_fail = bool(case.get("must_fail", False))
    def frac(a):
        return _vol(_scad(f"intersection() {{ {_tube(a, case['dir'], depth, ro, ri)} {_union(part)} }}", command)) / full
    out = []
    for i, a in enumerate(case["at"]):
        f = frac(a)
        weak = f < need
        ok = weak if must_fail else not weak
        out.append(dict(kind="ring", name=f"{case['name']} {i + 1}", ok=ok, fraction=round(f, 2),
                        text=f"{case['name']} {i + 1}: plastic round the hole {100 * f:.0f} %" + (f" (needs {100 * need:.0f} %)" if weak else "") + (" -- expected: this is a control" if must_fail and ok else "")))
    d = np.array(case["dir"], float); d /= np.linalg.norm(d)
    side = np.cross(d, [0, 0, 1.0] if abs(d[2]) < 0.9 else [1.0, 0, 0]); side /= np.linalg.norm(side)
    # the control: move the first ring 60 mm in each of six directions; at least one must land in air (a long flange can hold the ring wherever it is slid along it)
    up = np.cross(d, side); up /= np.linalg.norm(up)
    lowest = 1.0
    for v in (side, -side, d, -d, up, -up):
        moved = [float(case["at"][0][k]) + 60.0 * v[k] for k in range(3)]
        lowest = min(lowest, frac(moved))
        if lowest < need:
            break
    return out, dict(name=case["name"], control_ok=lowest < need, fraction=round(lowest, 2))


# ---------------------------------------------------------------- the whole thing
def run(folder, marker, only=None, command=None, log=print):
    """Run every case. -> dict(ok, results, controls_ok). Prints one line per case; a control that does not fire is a failure of the CHECKER."""
    sweeps, screws, defs = load_cases(folder)
    probes, drivers, rings = defs["probes"], defs["drivers"], defs["rings"]
    if only:
        sweeps = [s for s in sweeps if only in s["name"]]; screws = [s for s in screws if only in s["name"]]
        probes = [s for s in probes if only in s["name"]]; drivers = [s for s in drivers if only in s["name"]]; rings = [s for s in rings if only in s["name"]]
    names = ([n for s in sweeps for n in s["move"] + s["fixed"]] + [n for s in screws for n in s.get("clear", []) + s["thread"]]
             + [n for s in drivers for n in s["parts"]] + [s["part"] for s in rings])
    files = draw_parts(folder, marker, names, command, defs=defs)
    results, ok, controls_ok = [], True, True
    for s in sweeps:
        r = run_sweep(s, files, command)
        results.append(r); ok &= r["ok"]; controls_ok &= r["control_ok"]
        log(("ok    " if r["ok"] else "FAIL  ") + r["text"])
        log(("ok    " if r["control_ok"] else "FAIL  ") + f"control: {s['name']} with a part 4 % too big collides ({r['control']:.0f} mm3)" + ("" if r["control_ok"] else " -- it did NOT: this check cannot see a collision"))
    for s in screws:
        rs, ctl = run_screws(s, files, command)
        for r in rs:
            results.append(r); ok &= r["ok"]
            log(("ok    " if r["ok"] else "FAIL  ") + r["text"])
        controls_ok &= ctl["control_ok"]
        results.append(dict(kind="control", **ctl))
        log(("ok    " if ctl["control_ok"] else "FAIL  ") + f"control: a {s['name']} screw moved {OFFSET_CONTROL:g} mm off its hole is flagged" + ("" if ctl["control_ok"] else " -- it was NOT: this check cannot see a misaligned hole"))
    for s in drivers:
        rs, ctl = run_driver(s, files, command)
        for r in rs:
            results.append(r); ok &= r["ok"]
            log(("ok    " if r["ok"] else "FAIL  ") + r["text"])
        controls_ok &= ctl["control_ok"]; results.append(dict(kind="control", **ctl))
        log(("ok    " if ctl["control_ok"] else "FAIL  ") + f"control: a rod 15 times fatter on {s['name']} meets plastic ({ctl['mm3']:.0f} mm3)" + ("" if ctl["control_ok"] else " -- it did NOT: this check cannot see plastic in the way"))
    for s in rings:
        rs, ctl = run_ring(s, files, command)
        for r in rs:
            results.append(r); ok &= r["ok"]
            log(("ok    " if r["ok"] else "FAIL  ") + r["text"])
        controls_ok &= ctl["control_ok"]; results.append(dict(kind="control", **ctl))
        log(("ok    " if ctl["control_ok"] else "FAIL  ") + f"control: {s['name']} moved 60 mm away finds air and is flagged ({100 * ctl['fraction']:.0f} %)" + ("" if ctl["control_ok"] else " -- it was NOT: this check cannot see a hole in the air"))
    for pr in probes:
        v = _probe_volume(folder, marker, pr, defs, command)
        allow = float(pr.get("allow", LIMIT)); need_overlap = bool(pr.get("must_overlap", False))
        good = v > allow if need_overlap else v <= allow
        results.append(dict(kind="probe", name=pr["name"], ok=good, mm3=round(v, 1)))
        ok &= good if not need_overlap else True
        controls_ok &= good if need_overlap else True
        if need_overlap:
            log(("ok    " if good else "FAIL  ") + f"control: {pr['name']} ({v:.0f} mm3)" + ("" if good else " -- it found NO overlap: the probes cannot see a collision"))
        else:
            log(("ok    " if good else "FAIL  ") + f"{pr['name']}" + (f": {v:.0f} mm3 overlap (allowed {allow:g})" if v > LIMIT else ""))
    log("\n[assembly] " + ("ALL CLEAR" if ok and controls_ok else "PROBLEMS FOUND" if not ok else "CHECKER CANNOT SEE ITS CONTROLS"))
    return dict(ok=ok and controls_ok, parts_ok=ok, controls_ok=controls_ok, results=results)
