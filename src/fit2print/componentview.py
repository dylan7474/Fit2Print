"""The 3D view of a library component: its [[shape.part]] tables (see hardware.py) drawn with OpenSCAD, kept in a cache folder, shown with the same WebGL
viewer as a project's model. A piece is flagged unverified when a size it rests on has not been measured by the person; measuring a size changes the
shape (and the cache key), so the view always follows the numbers."""
import hashlib, json, os, shutil, subprocess, time
import numpy as np
import trimesh
from . import hardware, modelview

CACHE = os.path.expanduser("~/.cache/fit2print/hardware3d")

def key(entry):
    parts = hardware.shape_parts(entry)
    return hashlib.sha1(json.dumps(parts, sort_keys=True).encode()).hexdigest()[:10]

def has_shape(entry):
    return bool((entry.get("shape") or {}).get("part"))

def ensure(entry, command=None, cache=None, timeout=120):
    """-> the folder holding meta.json and the piece .bin files for this component's current numbers (drawn once, then reused)."""
    cache = cache or CACHE
    parts = hardware.shape_parts(entry)
    if not parts:
        raise ValueError("this component has no 3D shape yet")
    out = os.path.join(cache, f"{entry['id']}-{key(entry)}")
    if os.path.exists(os.path.join(out, "meta.json")):
        return out
    cmd = command or [shutil.which("openscad") or "openscad"]
    tmpd = out + ".tmp"; shutil.rmtree(tmpd, ignore_errors=True); os.makedirs(tmpd)
    kept = []
    try:
        for p in parts:
            scad = os.path.join(tmpd, p["name"] + ".scad"); stl = os.path.join(tmpd, p["name"] + ".stl")
            with open(scad, "w") as fh: fh.write(hardware.shape_scad(p) + "\n")
            r = subprocess.run(cmd + ["-q", "--backend=manifold", "-o", stl, scad], capture_output=True, text=True, timeout=timeout, cwd=tmpd)
            if r.returncode != 0 or not os.path.exists(stl) or os.path.getsize(stl) < 200:
                raise RuntimeError(f"OpenSCAD could not draw '{p['name']}': " + (r.stderr.strip().splitlines() or ["nothing drawn"])[-1][:160])
            tri = modelview.triangles(trimesh.load(stl, force="mesh"))
            tri.tofile(os.path.join(tmpd, p["name"] + ".bin"))
            kept.append(dict(name=p["name"], label=p["label"], colour=p["colour"], scene="assembled", status=p["status"], uses=p["uses"], tris=len(tri) // 3,
                             lo=[round(float(x), 2) for x in tri.min(0)], hi=[round(float(x), 2) for x in tri.max(0)]))
        meta = dict(stamp=key(entry), note=(entry.get("shape") or {}).get("note", ""), scenes=[dict(name="assembled", label="Shape", pieces=kept)])
        with open(os.path.join(tmpd, "meta.json"), "w") as fh: json.dump(meta, fh)
        shutil.rmtree(out, ignore_errors=True); os.replace(tmpd, out)
    finally:
        shutil.rmtree(tmpd, ignore_errors=True)
    return out

def card(hid, entry):
    """'' for a component with no shape yet."""
    if not has_shape(entry):
        return ""
    return modelview.viewer_card(f"/hardware/{hid}/3d", key(entry), "3D shape")
