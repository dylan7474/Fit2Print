"""Supports only where a shelf needs them, and a check that none ended up inside a small hole. Extracted from Phonosphere's make_plate.py / gate.py.

The slicer profile has supports ON in *manual* mode: it builds support only where a face is painted. So:
  1. shelves(mesh): every overhang region reaching further than PAINT_SPAN inside its layer (a ledge's seat, a rebate) and starting higher than
     MIN_VOID above the bed (a shallow channel is bridged, not supported);
  2. paint(...): mark exactly the downward faces of those regions as support enforcers in the 3MF, so counterbores, pockets and pilots are never filled;
  3. holes_with_support(...): after slicing, any support plastic lying inside a small closed void of the part (a screw pilot filled with support
     is the failure that cost a print on 2026-10-27) is reported. Auto supports always fail this; painted ones must pass.
"""
import json, os, re, tempfile, zipfile
import numpy as np
from scipy import ndimage as ndi
from . import layers as layers_mod

MIN_REGION = 8.0         # mm2: smaller patches are corner rounding
MIN_VOID = 2.5           # mm: a region starting lower than this above the bed is bridged, not supported
PAINT_SPAN = 5.0         # mm: a region reaching further than this inside its layer gets enforcers
LAYER = 0.28


def geodesic_span(region, seeds, res):
    """Largest distance inside `region` from `seeds`; inf if part of the region never reaches a seed. Two grid metrics averaged (within ~6 %)."""
    covered0 = seeds & region
    if not covered0.any():
        return float("inf")
    out = []
    for conn in (1, 2):
        cross = ndi.generate_binary_structure(2, conn)
        covered, steps = covered0.copy(), 1
        while True:
            nxt = ndi.binary_dilation(covered, cross) & region & ~covered
            if not nxt.any():
                break
            covered |= nxt
            steps += 1
        if (region & ~covered).any():
            return float("inf")
        out.append(steps * res)
    return sum(out) / 2


def overhangs(mesh, res=0.8):
    """Every overhang region of every layer: (area mm2, z, x0, x1, y0, y1, span mm)."""
    H = mesh.bounds[1][2]
    zs = [0.1] + [0.2 + LAYER * i for i in range(0, int(H / LAYER) + 1)]
    zs = [z for z in zs if z < H - 0.05]
    found, prev = [], None
    cross = ndi.generate_binary_structure(2, 1)
    for z, cur, (x0, y0) in layers_mod.masks(mesh, zs, res):
        if prev is not None:
            supported = ndi.binary_dilation(prev, iterations=1)
            lab, n = ndi.label(cur & ~supported)
            for i in range(1, n + 1):
                reg = lab == i
                ys, xs = np.where(reg)
                area = len(xs) * res * res
                if area < MIN_REGION:
                    continue
                seeds = ndi.binary_dilation(supported, cross) & reg
                found.append((area, z, x0 + xs.min() * res, x0 + xs.max() * res, y0 + ys.min() * res, y0 + ys.max() * res, geodesic_span(reg, seeds, res)))
        prev = cur
    return found


def shelves(mesh, res=0.8):
    """The overhang regions that get supports."""
    return [f for f in overhangs(mesh, res) if f[6] > PAINT_SPAN and f[1] >= MIN_VOID]


def plate_objects(root):
    """{file name given to the slicer (e.g. 'a.stl'): path of that object's mesh file} for an unpacked 3MF."""
    model = open(f"{root}/3D/3dmodel.model").read()
    ids = {}
    for oid, body in re.findall(r'<object id="(\d+)"[^>]*>(.*?)</object>', model, re.S):
        m = re.search(r'p:path="([^"]+)"', body)
        if m:
            ids[oid] = root + m.group(1)
    names = {}
    cfg = open(f"{root}/Metadata/model_settings.config").read()
    for oid, body in re.findall(r'<object id="(\d+)">(.*?)</object>', cfg, re.S):
        m = re.search(r'<metadata key="name" value="([^"]*)"', body)
        if m and oid in ids:
            names[m.group(1)] = ids[oid]
    return names


def _paint_text(text, mesh, regions):
    """-> (new mesh-file text, faces painted): enforcers on the downward faces of the shelf regions."""
    vs = np.array(re.findall(r'<vertex x="([-\d.e]+)" y="([-\d.e]+)" z="([-\d.e]+)"', text), float)
    T = np.array(re.findall(r'<triangle v1="(\d+)" v2="(\d+)" v3="(\d+)"/>', text), int)
    if len(vs) == 0 or len(T) == 0:
        raise ValueError("could not read the mesh inside the 3MF")
    P = vs[T] + (mesh.bounds[0] - vs.min(0))                 # back to the mesh's own coordinates
    nrm = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])
    ln = np.linalg.norm(nrm, axis=1)
    nrm = nrm / np.where(ln == 0, 1, ln)[:, None]
    c = P.mean(axis=1)
    sel = np.zeros(len(T), bool)
    for area, z, x0, x1, y0, y1, span in regions:
        sel |= (nrm[:, 2] < -0.9) & (c[:, 2] > z - 0.32) & (c[:, 2] < z + 0.05) \
               & (c[:, 0] > x0 - 0.6) & (c[:, 0] < x1 + 0.6) & (c[:, 1] > y0 - 0.6) & (c[:, 1] < y1 + 0.6)
    parts = text.split("<triangle ")
    out = [parts[0]] + [seg.replace("/>", ' paint_supports="4"/>', 1) if sel[k] else seg for k, seg in enumerate(parts[1:])]
    return "<triangle ".join(out), int(sel.sum())


def _repack(root, dest):
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for r, _, files in os.walk(root):
            for f in files:
                full = os.path.join(r, f)
                z.write(full, os.path.relpath(full, root))


def paint_plate(base3mf, items, dest):
    """Write `dest`: `base3mf` with support enforcers painted on every listed object and manual supports forced on.
    items = {file name as given to the slicer: (mesh, regions)}. Objects are matched by NAME (not by size, so mirror twins are safe).
    -> {name: faces painted}. An item whose name is not in the plate is an error, never a silent skip."""
    with tempfile.TemporaryDirectory() as d:
        zipfile.ZipFile(base3mf).extractall(d)
        objs = plate_objects(d)
        missing = [n for n in items if n not in objs]
        if missing:
            raise ValueError(f"not on the plate: {', '.join(missing)} (the plate holds {', '.join(sorted(objs))})")
        done = {}
        for name, (mesh, regions) in items.items():
            text = open(objs[name]).read()
            if regions:
                text, n = _paint_text(text, mesh, regions)
                open(objs[name], "w").write(text)
            else:
                n = 0
            done[name] = n
        cfgp = f"{d}/Metadata/project_settings.config"
        cfg = json.load(open(cfgp))
        cfg.update({"enable_support": "1", "support_type": "normal(manual)", "support_on_build_plate_only": "1"})
        json.dump(cfg, open(cfgp, "w"), indent=1)
        _repack(d, dest)
    return done


def paint(base3mf, mesh, regions, dest):
    """Single-object plate: paint `regions` on its one object. -> faces painted."""
    with tempfile.TemporaryDirectory() as d:
        zipfile.ZipFile(base3mf).extractall(d)
        names = list(plate_objects(d))
    if len(names) != 1:
        raise ValueError("support painting handles a plate with one object only (use paint_plate for several)")
    return paint_plate(base3mf, {names[0]: (mesh, regions)}, dest)[names[0]]


def holes_with_support(mesh, layers, res=0.4, allow=(), max_area=1200.0):
    """Support plastic lying inside a small closed void of the part (a pilot filled with support): [(moves, x, y)] per hole.
    Aligns the G-code to the mesh through the outer walls' extent (single-part plates). `allow` = painted regions, where support is deliberate."""
    walls = np.array([(s[1], s[2]) for segs in layers.values() for f, s, _ in segs if f == "Outer wall"])
    if len(walls) == 0:
        return []
    b = mesh.bounds
    dx, dy = walls[:, 0].min() - b[0][0], walls[:, 1].min() - b[0][1]
    found = {}
    sup_z = {z: [((s[1] + s[3]) / 2 - dx, (s[2] + s[4]) / 2 - dy) for f, s, _ in segs if f.startswith("Support")] for z, segs in layers.items()}
    zs = sorted(z for z, v in sup_z.items() if v and z <= b[1][2])
    if not zs:
        return []
    for z, mask, (x0, y0) in layers_mod.masks(mesh, [max(0.05, z - 0.12) for z in zs], res):
        zz = zs[0]; zs = zs[1:]
        lab, n = ndi.label(~mask)
        border = set(lab[0, :]) | set(lab[-1, :]) | set(lab[:, 0]) | set(lab[:, -1])
        for x, y in sup_z[zz]:
            if any(rx0 - 1 <= x <= rx1 + 1 and ry0 - 1 <= y <= ry1 + 1 and zz <= rz + 0.3 for _, rz, rx0, rx1, ry0, ry1, _ in allow):
                continue
            i, j = int((y - y0) / res), int((x - x0) / res)
            if 0 <= i < mask.shape[0] and 0 <= j < mask.shape[1] and lab[i, j] and lab[i, j] not in border:
                if (lab == lab[i, j]).sum() * res * res < max_area:
                    k = (round(x / 3), round(y / 3))
                    c = found.setdefault(k, [0, x, y])
                    c[0] += 1
    return [tuple(v) for v in found.values() if v[0] >= 8]
