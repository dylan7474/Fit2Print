"""Coupons: a small piece cut from the REAL printable STL, to try one doubtful spot before committing a long print.

Lessons from Phonosphere (2026-11-01) this is built on:
  * Test the feature as it really is. A coupon is cut from the part's own STL (same holes, same overhangs, same neighbours), never redrawn by hand,
    so it cannot drift from the design. The cut keeps the part's coordinates (x, y and z as printed), so a coupon can be matched back to its part.
  * Keep the print orientation. The STL is already lying as it will print (z up from the bed); the box is in those coordinates, and `zmax` trims
    away tall features that do not matter to the spot (mouldings above a skin) without touching the underside.
  * Several coupons from several spots go on ONE plate and are checked together (same profile, same supports): the spots of one part that went
    wrong in different ways are tried in one short print.
  * A coupon must contain plastic AND the feature. An empty box, a box beside the part, or a box that is the wrong way round is refused with a message
    (negative controls in tests/test_coupon.py).
Each coupon is written as NAME.stl with NAME.json beside it recording where it came from (source file and its sha, the box), so a coupon made from an
old version of the part can be recognised later.
"""
import hashlib, json, os, re, shutil, subprocess, tempfile
import trimesh

NAME = re.compile(r"[a-z0-9_-]{1,40}")
MIN_VOLUME = 1.0            # mm3: less than this is "nothing in the box"

def boxes_from_args(items):
    """[(name, x0, x1, y0, y1), ...] from the command line's --box NAME X0 X1 Y0 Y1 repeats (strings in, numbers out)."""
    out = []
    for it in items:
        name, *v = it
        if not NAME.fullmatch(str(name)):
            raise ValueError(f"a coupon name needs lower-case letters, digits, - or _ (got {name!r})")
        out.append(dict(name=name, x0=float(v[0]), x1=float(v[1]), y0=float(v[2]), y1=float(v[3])))
    return out

def check_box(b, bounds):
    """None if the box is usable against the part's bounds, else the reason."""
    if not (b["x0"] < b["x1"] and b["y0"] < b["y1"]):
        return "the box is the wrong way round (each start must be smaller than its end)"
    lo, hi = bounds
    if b["x1"] <= lo[0] or b["x0"] >= hi[0] or b["y1"] <= lo[1] or b["y0"] >= hi[1]:
        return f"the box does not touch the part (the part spans x {lo[0]:.1f} to {hi[0]:.1f}, y {lo[1]:.1f} to {hi[1]:.1f})"
    return None

def cut(stl, boxes, outdir, command=None, zmax=None, timeout=300):
    """-> one dict per box: name, ok, error, file, size, volume (mm3), watertight. Written only when the piece is real; nothing is left behind on a failure."""
    stl = os.path.abspath(stl)
    part = trimesh.load(stl)
    names = [b["name"] for b in boxes]
    if len(set(names)) != len(names):
        raise ValueError("two coupons have the same name")
    os.makedirs(outdir, exist_ok=True)
    cmd = command or [shutil.which("openscad") or "openscad"]
    if zmax is not None and float(zmax) <= float(part.bounds[0][2]):
        raise ValueError(f"zmax {zmax} is at or below the part's underside (z {part.bounds[0][2]:.2f}): nothing would be left")
    top = float(zmax) if zmax is not None else float(part.bounds[1][2]) + 1
    src_sha = hashlib.sha256(open(stl, "rb").read()).hexdigest()[:10]
    res = []
    for b in boxes:
        r = dict(name=b["name"], ok=False, error="", file=None)
        why = check_box(b, part.bounds)
        if why:
            r["error"] = why; res.append(r); continue
        with tempfile.TemporaryDirectory() as d:
            scad, tmp = os.path.join(d, "cut.scad"), os.path.join(d, "cut.stl")
            open(scad, "w").write('intersection() { import("%s"); translate([%r, %r, -1]) cube([%r, %r, %r]); }\n'
                                  % (stl.replace("\\", "/"), b["x0"], b["y0"], b["x1"] - b["x0"], b["y1"] - b["y0"], top + 1))
            try:
                p = subprocess.run(cmd + ["-q", "--backend=manifold", "-o", tmp, scad], capture_output=True, text=True, timeout=timeout)
                err = (p.stderr.strip().splitlines() or [""])[-1][:200]
                if not os.path.exists(tmp) or os.path.getsize(tmp) < 200:
                    # OpenSCAD writes nothing (and may exit 1) when the result is empty: that is a box over a gap, not a broken tool
                    r["error"] = "there is no plastic inside that box" if (not err or "empty" in err.lower()) else err
                else:
                    m = trimesh.load(tmp)
                    if abs(m.volume) < MIN_VOLUME:
                        r["error"] = "there is no plastic inside that box"
                    else:
                        out = os.path.join(outdir, b["name"] + ".stl")
                        shutil.copy(tmp, out)
                        json.dump(dict(source=stl, source_sha=src_sha, box={k: b[k] for k in ("x0", "x1", "y0", "y1")}, zmax=top), open(out[:-4] + ".json", "w"), indent=1)
                        lo, hi = m.bounds
                        r.update(ok=True, file=out, size=[round(float(x), 2) for x in (hi - lo)], volume=round(float(abs(m.volume)), 1), watertight=bool(m.is_watertight))
            except FileNotFoundError:
                r["error"] = "OpenSCAD is not installed on this machine"
            except subprocess.TimeoutExpired:
                r["error"] = "cutting took too long"
        res.append(r)
    return res

def is_stale(coupon_stl):
    """None if the coupon was cut from the source file as it is now, else the reason it should be cut again."""
    j = coupon_stl[:-4] + ".json"
    if not os.path.exists(j):
        return "no record of where this coupon came from"
    meta = json.load(open(j))
    src = meta.get("source", "")
    if not os.path.exists(src):
        return f"the part it was cut from ({os.path.basename(src)}) is gone"
    if hashlib.sha256(open(src, "rb").read()).hexdigest()[:10] != meta.get("source_sha"):
        return f"{os.path.basename(src)} has changed since this coupon was cut: cut it again"
    return None
