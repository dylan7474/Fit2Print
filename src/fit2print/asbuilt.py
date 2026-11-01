"""The 'as printed' against the 'as designed'. Extracted from Phonosphere's asbuilt_check.py (built 2026-10-28 after supports plugged blind pilots,
found by eye on the printer instead of by a check).

Replays the sliced G-code into layers and lays each layer over the same layer cut from the 3D model, then reports:
  FILLED   support plastic inside a small hole or pocket of the design (a pilot or counterbore plugged by support, so no screw would go in): BLOCK;
  MISSING  a stretch of the design's outer wall (the 1.2 mm skin of every layer) with no plastic printed on it (a feature the slicer dropped): CHECK;
  EXTRA    part plastic printed where the design has none: CHECK.
The slicer may turn or flip a part on the plate, so best_fit() tries the poses (0/90/180/270, a fitted angle, flipped) and keeps the best match.
"""
import json, math, os, zipfile
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi
from . import gcode as g, layers as layers_mod, support

RES = 0.25
SKIN = 1.2          # mm: the part of the design next to its outline that must be printed
TOL = 0.5           # mm of slack between the design and what the nozzle path draws
MIN_MM2 = 2.0       # smallest region reported
NOT_PART = ("Custom", "Brim", "Skirt", "Prime tower")


class _Grid:
    """The mesh's layer masks on a fixed grid (so each layer is cut once per pose)."""
    def __init__(self, mesh, res):
        self.mesh, self.res = mesh, res
        b = mesh.bounds
        self.x0, self.y0 = b[0][0] - 2, b[0][1] - 2
        self.nx = int((b[1][0] - self.x0 + 2) / res)
        self.ny = int((b[1][1] - self.y0 + 2) / res)

    def mask(self, z):
        return next(layers_mod.masks(self.mesh, [z], res=self.res))[1]

def plate_boxes(path):
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if n.endswith("plate_1.json")]
        if not names:
            return []
        return [(o["name"], o["bbox"]) for o in json.loads(z.read(names[0]))["bbox_objects"]]


def find_box(boxes, stl):
    base = os.path.basename(stl)
    for n, b in boxes:
        if n == base:
            return b
    return None


def draw(segs, origin, shape, want):
    return draw_both(segs, origin, shape, want, lambda f: False)[0]

def draw_both(segs, origin, shape, want_a, want_b):
    """Two masks in one pass over the segments: the lines for which want_a(feature) holds, and those for which want_b does."""
    ims = [Image.new("1", (shape[1], shape[0]), 0) for _ in range(2)]
    ds = [ImageDraw.Draw(i) for i in ims]
    w = max(1, round(0.45 / RES))
    for feat, seg, _ in segs:
        k = 0 if want_a(feat) else (1 if want_b(feat) else None)
        if k is None:
            continue
        p = g.seg_points(seg[:7], RES)[0]
        ds[k].line([((x - origin[0]) / RES, (y - origin[1]) / RES) for x, y in p], fill=1, width=w)
    return [np.array(i, dtype=bool) for i in ims]


def check_part(layers, plate_box, mesh, allow=None, every=1, span=None):
    b = mesh.bounds
    # align: the outer walls of this part (those inside its plate box) against the mesh's own extent
    pad = 3.0
    # (every point along each printed line, not just its start: the slicer prints round parts as long ARCS, so the start points alone missed the true edge
    # by up to 1.4 mm and shifted small round parts against the model: the false MISSING/EXTRA on the knobs and plates, found 2026-10-29)
    wl = [q for segs in layers.values() for f, s, _ in segs if f == "Outer wall"
          and (plate_box is None or (plate_box[0] - pad <= s[1] <= plate_box[2] + pad and plate_box[1] - pad <= s[2] <= plate_box[3] + pad))
          for q in g.seg_points(s[:7], 0.5)[0]]
    walls = np.array(wl)
    if len(walls) == 0:
        return {"error": "no outer walls found for this part"}
    dx, dy = walls[:, 0].min() - b[0][0], walls[:, 1].min() - b[0][1]
    allow = list(allow) if allow is not None else support.shelves(mesh, span=span)      # regions where supports are painted on purpose
    sl = _Grid(mesh, RES)
    shape = (sl.ny, sl.nx)
    origin = (sl.x0 + dx, sl.y0 + dy)               # plate coordinates of the grid's corner
    lo = (b[0][0] + dx - 3, b[0][1] + dy - 3, b[1][0] + dx + 3, b[1][1] + dy + 3)
    inside = lambda s: lo[0] <= s[1] <= lo[2] and lo[1] <= s[2] <= lo[3]
    out = {"missing": [], "extra": [], "filled": [], "dx": dx, "dy": dy}
    zs = g.real_layers(layers)
    H = b[1][2]
    prev_z = 0.0
    enclosed_cache = {}
    for n_, z in enumerate(zs):
        if n_ % every:                      # pose search looks at a sample of the layers; the final check looks at all of them
            continue
        h = max(0.1, z - prev_z); prev_z = z
        if z > H + 0.05:
            break
        segs = [t for t in layers[z] if inside(t[1])]
        if not segs:
            continue
        design = sl.mask(max(0.05, min(H - 0.02, z - 0.14)))
        nparts = sum(1 for f, _, _ in segs if f not in NOT_PART and not f.startswith("Support"))
        part, supp = draw_both(segs, origin, shape, lambda f: f not in NOT_PART and not f.startswith("Support"), lambda f: f.startswith("Support"))
        tol = round(TOL / RES)
        skin = design & ~ndi.binary_erosion(design, iterations=round(SKIN / RES))
        miss = skin & ~ndi.binary_dilation(part, iterations=tol)
        extra = part & ~ndi.binary_dilation(design, iterations=tol + 1)
        for name, mask in (("missing", miss), ("extra", extra)) if nparts >= 20 else ():     # support-only layers (Bambu prints supports on their own z) say nothing about the part
            lab, n = ndi.label(mask)
            for i in range(1, n + 1):
                reg = lab == i
                area = reg.sum() * RES * RES
                if area >= MIN_MM2:
                    ys, xs = np.where(reg)
                    out[name].append((area, z, origin[0] + xs.mean() * RES, origin[1] + ys.mean() * RES))
        if supp.any():
            void = ~design
            lab, n = ndi.label(void)
            border = set(lab[0, :]) | set(lab[-1, :]) | set(lab[:, 0]) | set(lab[:, -1])
            sup_lab = lab[supp & void]
            for i in set(sup_lab.tolist()) - border - {0}:
                area = (lab == i).sum() * RES * RES
                if area < 1200:
                    ys, xs = np.where((lab == i) & supp)
                    mx, my = origin[0] + xs.mean() * RES - dx, origin[1] + ys.mean() * RES - dy
                    if any(x0 - 1 <= mx <= x1 + 1 and y0 - 1 <= my <= y1 + 1 and z <= rz + 0.3 for _, rz, x0, x1, y0, y1, _ in allow):
                        continue
                    out["filled"].append((int(len(xs)), z, origin[0] + xs.mean() * RES, origin[1] + ys.mean() * RES, area))
    return out


def summarise(res):
    """Group per-layer finds that sit in the same place into features: [(kind, layers, x, y, area)]."""
    feats = []
    for kind in ("filled", "missing", "extra"):
        pts = []
        for r in res.get(kind, []):
            pts.append((r[2], r[3], r[1], r[0]))
        used = [False] * len(pts)
        for i, (x, y, z, a) in enumerate(pts):
            if used[i]:
                continue
            grp = [(x, y, z, a)]
            used[i] = True
            for j in range(i + 1, len(pts)):
                if not used[j] and math.hypot(pts[j][0] - x, pts[j][1] - y) < 4.0:
                    grp.append(pts[j]); used[j] = True
            feats.append((kind, len(grp), float(np.mean([q[0] for q in grp])), float(np.mean([q[1] for q in grp])), max(q[3] for q in grp),
                          min(q[2] for q in grp), max(q[2] for q in grp)))
    return feats


def verdict(feats, min_layers=3):
    v = "PASS"
    for kind, n, *_ in feats:
        if n >= min_layers:
            v = "BLOCK" if kind == "filled" else ("CHECK" if v == "PASS" else v)
    return v


def estimate_angles(layers, mesh, flip):
    """The angle (degrees about z) the slicer turned this part by, found by laying the model's outline over the printed outer walls at several heights
    (chamfer distance, coarse 5 degree steps then 0.2 degree refinement). Several heights, because a part whose bottom is a plain disc (a knob) only shows its
    turn higher up. Returns up to two candidate angles; () when it cannot tell."""
    import trimesh
    from scipy.spatial import cKDTree
    try:
        m = mesh.copy()
        if flip:
            m.apply_transform(trimesh.transformations.rotation_matrix(math.pi, [1, 0, 0]))
        zb, ht = m.bounds[0][2], m.bounds[1][2] - m.bounds[0][2]
        zs = sorted(layers)
        pairs = []
        for frac in (0.1, 0.3, 0.5, 0.7, 0.9):
            zk = frac * ht
            zl = min(zs, key=lambda z: abs(z - zk))
            P = np.array([q for f, s, _ in layers[zl] if f == "Outer wall" for q in g.seg_points(s[:7], 0.5)[0]])
            sec = m.section(plane_origin=[0, 0, zb + zk], plane_normal=[0, 0, 1])
            if sec is None or len(P) < 20 or len(sec.vertices) < 20:
                continue
            Q = np.asarray(sec.vertices)[:, :2]
            pairs.append((cKDTree(P), P, Q))
        if not pairs:
            return ()
        def cost(deg):
            c, s_ = math.cos(math.radians(deg)), math.sin(math.radians(deg))
            tot = 0.0
            for tp, P, Q in pairs:
                R = Q @ np.array([[c, s_], [-s_, c]])
                R = R - R.mean(0) + P.mean(0)
                tot += tp.query(R)[0].mean() + cKDTree(R).query(P)[0].mean()
            return tot
        coarse = sorted(((cost(a), a) for a in range(0, 360, 5)))
        out = []
        for _, a in coarse[:2]:
            fine = min(((cost(a + d / 5.0), a + d / 5.0) for d in range(-25, 26)))
            out.append(round(fine[1], 1))
        return tuple(out)
    except Exception:
        return ()


def best_fit(layers, box, mesh, allow=None, every=None, span=None):
    """The slicer may rotate a part on the plate (--arrange): compare the plate box with the mesh footprint and, when turned, try +90 and -90."""
    import trimesh
    b = mesh.bounds
    w, d = b[1][0] - b[0][0], b[1][1] - b[0][1]
    bw, bh = (box[2] - box[0], box[3] - box[1]) if box is not None else (w, d)       # the box includes the brim, so compare which way round fits better
    if box is not None and abs(w - d) > 5 and abs(bw - d) + abs(bh - w) < abs(bw - w) + abs(bh - d):
        best = None
        for ang in (90, -90):
            m2 = mesh.copy()
            m2.apply_transform(trimesh.transformations.rotation_matrix(math.radians(ang), [0, 0, 1]))
            m2.apply_translation([-m2.bounds[0][0], -m2.bounds[0][1], 0])
            r = check_part(layers, box, m2, allow, span=span)
            score = sum(x[0] for x in r.get("missing", [])) + sum(x[0] for x in r.get("extra", []))
            if best is None or score < best[0]:
                best = (score, r)
        return best[1]
    # the slicer may have turned the part on the plate (by ANY angle: --arrange turned a stack of four plates 45 degrees, 2026-10-29, which is why the
    # small parts and the stack always showed MISSING/EXTRA), or printed it flipped over: try the other poses and keep the best fit (a good fit stops the search)
    best = None
    sampled = every is None                                   # first try: score the poses on ~8 layers and check the winner in full
    if sampled:
        every = max(1, len(g.real_layers(layers)) // 8)
    def poses():                                  # lazily: the fitted angle is slow to find, and the common case is a part exactly as modelled
        yield False, 0
        for flip in (False, True):
            for ang in (0, 90, 180, 270):
                if (flip, ang) != (False, 0):
                    yield flip, ang
            for ang in estimate_angles(layers, mesh, flip):
                yield flip, ang
    for flip, ang in poses():
        m2 = mesh.copy()
        if flip:
            m2.apply_transform(trimesh.transformations.rotation_matrix(math.pi, [1, 0, 0]))
        if ang:
            m2.apply_transform(trimesh.transformations.rotation_matrix(math.radians(ang), [0, 0, 1]))
        m2.apply_translation([-m2.bounds[0][0], -m2.bounds[0][1], -m2.bounds[0][2]])
        r = check_part(layers, box, m2, allow, every=every, span=span)
        if "error" in r:
            continue
        score = sum(x[0] for x in r["missing"]) + sum(x[0] for x in r["extra"]) + 50 * len(r["filled"])
        if best is None or score < best[0]:
            best = (score, r, m2)
        if score < 20:                          # a wrong pose scores hundreds of mm2 even on a sample of the layers
            break
    if best is None:
        return check_part(layers, box, mesh, allow, span=span)
    if every == 1:
        return best[1]
    full = check_part(layers, box, best[2], allow, span=span)
    if sum(x[0] for x in full["missing"]) + sum(x[0] for x in full["extra"]) + 50 * len(full["filled"]) < 20 or not sampled:
        return full
    return best_fit(layers, box, mesh, allow, every=1, span=span)       # the sample missed a layer that disagrees: search again with every layer


def check(layers, mesh, plate_box=None, allow=None, span=None):
    """The one call plate.py uses: -> (verdict PASS|CHECK|BLOCK, [human lines]). `allow` = the painted shelf regions (deliberate support)."""
    res = best_fit(layers, plate_box, mesh, allow, span=span)
    if "error" in res:
        return "CHECK", [f"as-built check could not run ({res['error']})"]
    feats = [f for f in summarise(res) if f[1] >= 3]
    lines = [f"{kind.upper()} {n} layers (z {z0:.1f}-{z1:.1f}) at x {x:.0f}, y {y:.0f}" for kind, n, x, y, a, z0, z1 in feats]
    return verdict(feats), lines
