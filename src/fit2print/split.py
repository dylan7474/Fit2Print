"""Split a part of ANY size into printable sections, with joints, so a thing bigger than the bed (or a big thing you first want to try small) can be printed.

Lessons from Phonosphere this is built on (a 300 x 200 x 384 mm radio cut by hand into shell, back, face and plinth pieces, each in a few parts):
  * Cut where the part is plain. A plane through a window, a boss or a grille is a bad cut; the splitter tries planes around each nominal position
    and takes the one farthest from a feature edge (where the outline length jumps because a window, boss or groove starts or stops).
  * Every cut gets a joint. Loose printed pins in blind holes (3.0 mm pin, 3.3 mm hole, 8 mm deep each side, proven on Phonosphere's back seams): nothing
    stands proud, and the pieces cannot slide or turn. Pins go only where the plastic is thick enough all the way down the hole; a cut with no room is
    reported, never silently left without a joint.
  * Each section lies on its largest flat cut face. That face is flat by construction, so a section needs no support under it, and it is the best
    surface to stick to the bed. A section that does not fit the bed in any such orientation is reported as a failure, with the advice to cut more.
  * Check that nothing was lost. The volume of the sections plus the volume of the pin holes must equal the volume of the part (a hole that broke out of a
    wall, or a cut that dropped a sliver, shows up as a mismatch).
  * Scale is a parameter. `scale` shrinks the whole part first, so a large, complicated design can be test-printed small (in one or a few sections) before
    the full-size cut.

Needs only numpy, scipy, trimesh and OpenSCAD (the same engine the rest of Fit2Print uses). Coordinates: the STL as given (it is already lying as it will print).
"""
import itertools, json, math, os, re, shutil, subprocess, tempfile
import numpy as np
import trimesh
from scipy import ndimage as ndi
from . import layers

AXES = "xyz"
A1_BED = (256.0, 256.0, 256.0)
WINDOW_FRAC = 0.5                   # how far from an even split a cut may move to dodge a feature (a fraction of a piece), while every piece still fits
NAME = re.compile(r"[a-z0-9_-]{1,40}")

def usable(bed, margin):
    """The room a piece may take: a margin each side in x and y (skirt, purge line, nozzle wipe) and 2 mm of headroom in z."""
    return (bed[0] - 2 * margin, bed[1] - 2 * margin, bed[2] - 2.0)

def fits(dims, room):
    """True if a box of these dimensions fits the room in ANY right-angle turn. Returns the turn (a permutation of axes) or None."""
    for perm in itertools.permutations(range(3)):
        if all(dims[perm[i]] <= room[i] + 1e-6 for i in range(3)):
            return perm
    return None

def plan_counts(extents, room, max_pieces=64, max_per_axis=8):
    """How many pieces along x, y, z: the fewest pieces that all fit; among equals, the least cut area. -> (nx, ny, nz) or None."""
    best = None
    for n in itertools.product(range(1, max_per_axis + 1), repeat=3):
        total = n[0] * n[1] * n[2]
        if total > max_pieces:
            continue
        dims = [extents[i] / n[i] for i in range(3)]
        if fits(dims, room) is None:
            continue
        area = sum((n[i] - 1) * extents[(i + 1) % 3] * extents[(i + 2) % 3] for i in range(3))
        key = (total, area)
        if best is None or key < best[0]:
            best = (key, n)
    return None if best is None else best[1]

def outline_length(mesh, axis, pos):
    """Length of the outline where the plane axis=pos cuts the part: long where the cut crosses many features. inf when the plane misses the part."""
    n = np.zeros(3); n[axis] = 1; o = np.zeros(3); o[axis] = pos
    seg = trimesh.intersections.mesh_plane(mesh, n, o)
    seg = np.asarray(seg)
    if seg.size == 0:
        return math.inf
    return float(np.linalg.norm(seg[:, 1] - seg[:, 0], axis=1).sum())

def section_pieces(mesh, axis, pos, res=1.0):
    """How many separate solid pieces plus how many holes the cut section has: 1 for a plain section, more where the plane passes through a window, a slot or a gap
    (a window through the whole thickness splits a plate's section in two). inf when the plane misses the part."""
    m, _ = _permuted(mesh, axis)
    z = float(np.clip(pos, m.bounds[0][2] + 0.02, m.bounds[1][2] - 0.02))
    got = next(layers.masks(m, [z], res=res), None)
    if got is None or not got[1].any():
        return math.inf
    mask = got[1]
    _, solid = ndi.label(mask)
    _, voids = ndi.label(~np.pad(mask, 1), structure=None)
    return float(solid + max(voids - 1, 0))

def section_change(mesh, axis, pos, d=3.0, res=1.0):
    """How much the section changes within `d` mm either side of the plane, as a fraction of its area: near 0 on a plain stretch, large where a post, window
    or boss starts or stops within reach (a cut grazing a boss 0.25 mm from its edge would leave a hair-thin wall beside the pin holes)."""
    m, _ = _permuted(mesh, axis)
    lo_z, hi_z = float(m.bounds[0][2]) + 0.02, float(m.bounds[1][2]) - 0.02
    za, zb, zc = (float(np.clip(pos + k, lo_z, hi_z)) for k in (-d, 0.0, d))
    got = [next(layers.masks(m, [z], res=res), None) for z in (za, zb, zc)]
    if any(g is None for g in got):
        return 1.0
    # the grids start from each slice's own bounds: they are the same part, so equal except where the section grew or shrank; compare on the common grid size
    A, B = got[0][1], got[2][1]
    h, w = min(A.shape[0], B.shape[0]), min(A.shape[1], B.shape[1])
    area = max(float(got[1][1].sum()), 1.0)
    return float(np.logical_xor(A[:h, :w], B[:h, :w]).sum()) / area

def best_cut(mesh, axis, nominal, window, lo_limit, hi_limit, steps=41, bucket=0.003):
    """The plane near `nominal` (within +-window, between the limits) that is plainest. -> (position, outline length, nominal's length).
    Judged in this order (a tuple, so a lower rule always beats a higher one):
      1. how many separate pieces and holes the section has (a plane through a window that goes right through the thickness splits the section in two);
      2. how much the section changes within 3 mm either side (a boss, post or groove close to the plane is a thin wall beside the pin holes);
      3. nearness to the even split (so the sections stay about the same size).
    Why not 'the shortest outline' (found on the arch clock, 2026-11-01): a plane through a big window has a SHORTER outline, so it steered the cut INTO the window."""
    cands = np.linspace(max(nominal - window, lo_limit), min(nominal + window, hi_limit), steps)
    base = outline_length(mesh, axis, nominal)
    rows = []
    for p in cands:
        p = float(p)
        c = outline_length(mesh, axis, p)
        if not np.isfinite(c):
            continue
        rows.append((section_pieces(mesh, axis, p), p, c))
    if not rows:
        return float(nominal), math.inf, base
    topo_min = min(r[0] for r in rows)
    best = None
    for tp, p, c in rows:
        ch = section_change(mesh, axis, p) if tp == topo_min else math.inf       # only the plainest topology is worth the extra slices
        key = (tp - topo_min, int(ch / bucket) if np.isfinite(ch) else 10 ** 6, abs(p - nominal))
        if best is None or key < best[0]:
            best = (key, p, c)
    return best[1], best[2], base

def _permuted(mesh, axis):
    """A copy of the mesh with `axis` turned into z (a cyclic turn, so faces keep their outside), for slicing along that axis with the layer slicer."""
    perm = [(axis + 1) % 3, (axis + 2) % 3, axis]
    m = mesh.copy(); m.vertices = m.vertices[:, perm]
    return m, perm

def pin_sites(mesh, axis, pos, hole_d, depth, wall=1.2, spacing=45.0, max_pins=10, res=0.5, avoid=()):
    """Where pins can go on the cut plane: points whose whole hole (hole_d wide, `depth` deep each side) has at least `wall` mm of plastic round it.
    -> list of (a, b) in the plane's own two axes (axis+1, axis+2), plus the usable area in mm2 and the section's solid area."""
    m, _ = _permuted(mesh, axis)
    zs = [pos - depth + 0.3, pos - 0.2, pos + 0.2, pos + depth - 0.3]
    need = hole_d / 2 + wall
    cand = None; area = 0.0; origin = None
    for n_, z in enumerate(zs):
        z = float(np.clip(z, m.bounds[0][2] + 0.05, m.bounds[1][2] - 0.05))
        got = next(layers.masks(m, [z], res=res), None)
        if got is None:
            return [], 0.0, 0.0
        _, mask, (x0, y0) = got
        origin = (x0, y0)
        edt = ndi.distance_transform_edt(np.pad(mask, 1))[1:-1, 1:-1] * res
        ok = edt >= need
        cand = ok if cand is None else (cand & ok)
        if n_ == 2:                                      # the layer just above the plane is the section the pieces meet on
            area = float(mask.sum()) * res * res
    if cand is None or not cand.any():
        return [], 0.0, area
    jj, ii = np.nonzero(cand)
    pts = np.stack([(ii + 0.5) * res + origin[0], (jj + 0.5) * res + origin[1]], axis=1)
    for ci, v in avoid:                                  # a hole must not straddle another cut plane: it would be cut in two
        pts = pts[np.abs(pts[:, ci] - v) >= need]
    if len(pts) == 0:
        return [], 0.0, area
    if len(pts) > 6000:
        pts = pts[:: len(pts) // 6000 + 1]
    # the plane's solid area decides how many pins; at least two (one pin lets the pieces turn)
    span = float(max(np.ptp(pts[:, 0]), np.ptp(pts[:, 1])))          # a pin every `spacing` mm along the seam (Phonosphere: 7 on a 360 mm seam), at least two
    k = int(np.clip(math.ceil(span / spacing) + 1, 2, max_pins))
    c = pts.mean(axis=0)
    first = pts[np.argmax(np.linalg.norm(pts - c, axis=1))]
    chosen = [first]
    while len(chosen) < k:
        d = np.min([np.linalg.norm(pts - q, axis=1) for q in chosen], axis=0)
        if d.max() < hole_d * 3:                      # nothing left that is not on top of another pin
            break
        chosen.append(pts[np.argmax(d)])
    return [tuple(map(float, q)) for q in chosen], float(cand.sum()) * res * res, area

def section_area(mesh, axis, pos, res=0.5):
    """Solid area (mm2) of the part where the plane axis=pos cuts it."""
    m, _ = _permuted(mesh, axis)
    got = next(layers.masks(m, [float(np.clip(pos + 0.2, m.bounds[0][2] + 0.05, m.bounds[1][2] - 0.05))], res=res), None)
    return 0.0 if got is None else float(got[1].sum()) * res * res

def key_gap_bound(area, clearance):
    """The most plastic the teeth's clearance can take out of a seam of solid area `area` (measured: about 0.6 x clearance per mm2 on thin
    walls, where the sloped sides cut across the wall; 4 x clearance is a safe upper limit)."""
    return area * clearance * 4

def _hole_scad(axis, side, pos, ab, hole_d, depth):
    """OpenSCAD for one blind hole starting on the plane and going into the piece on `side` (+1 above the plane, -1 below)."""
    p = [0.0, 0.0, 0.0]
    p[axis] = pos; p[(axis + 1) % 3] = ab[0]; p[(axis + 2) % 3] = ab[1]
    rot = {(0, 1): "[0,90,0]", (0, -1): "[0,-90,0]", (1, 1): "[-90,0,0]", (1, -1): "[90,0,0]", (2, 1): "[0,0,0]", (2, -1): "[180,0,0]"}[(axis, side)]
    # start 0.01 before the plane so no film is left over the hole's mouth
    return f"translate([{p[0]:.4f},{p[1]:.4f},{p[2]:.4f}]) rotate({rot}) translate([0,0,-0.01]) cylinder(d={hole_d}, h={depth + 0.01}, $fn=32);"

def _key_blocks(axis, pos, lo_c, hi_c, period, height, grow=0.0, below=0.0):
    """OpenSCAD for the 'keys' joint on one cut plane: a chessboard of square teeth `period` mm wide, `height` mm tall, with 45 degree sides so
    they print without supports whichever way the seam faces. Clipped to the piece's own footprint lo_c..hi_c. The chessboard is laid on absolute
    coordinates, so both pieces agree where the teeth are. grow = clearance: the receiving piece's pocket is wider all round by `grow` and taller by `grow`."""
    o1, o2 = (axis + 1) % 3, (axis + 2) % 3
    top_half = period / 2 - height                      # half-width of a tooth's flat top (45 degrees: it shrinks as fast as it rises)
    if top_half < 0.4:
        raise ValueError("key_height too large for key_period: the teeth would have no flat top")
    def box(z0, z1, half, ca, cb):
        o = [0.0] * 3; d = [0.0] * 3
        o[axis] = z0; d[axis] = z1 - z0
        o[o1] = ca - half; d[o1] = 2 * half; o[o2] = cb - half; d[o2] = 2 * half
        return "translate([%.4f,%.4f,%.4f]) cube([%.4f,%.4f,%.4f]);" % (o[0], o[1], o[2], d[0], d[1], d[2])
    teeth = []
    for ia in range(int(math.floor(lo_c[o1] / period)) - 1, int(math.ceil(hi_c[o1] / period)) + 1):
        for ib in range(int(math.floor(lo_c[o2] / period)) - 1, int(math.ceil(hi_c[o2] / period)) + 1):
            if (ia + ib) % 2:
                continue
            ca = (ia + 0.5) * period; cb = (ib + 0.5) * period
            if ca + period / 2 + grow < lo_c[o1] or ca - period / 2 - grow > hi_c[o1] or cb + period / 2 + grow < lo_c[o2] or cb - period / 2 - grow > hi_c[o2]:
                continue
            base = box(pos - below, pos, period / 2 + grow, ca, cb)
            top = box(pos + height + grow - 0.001, pos + height + grow, top_half, ca, cb)
            teeth.append("hull() { %s %s }" % (base, top))
    if not teeth:
        return []
    clip = [0.0] * 3; size = [0.0] * 3
    clip[axis] = pos - 1000; size[axis] = 2000
    clip[o1] = lo_c[o1]; size[o1] = hi_c[o1] - lo_c[o1]; clip[o2] = lo_c[o2]; size[o2] = hi_c[o2] - lo_c[o2]
    return ["intersection() { union() { %s } translate([%.4f,%.4f,%.4f]) cube([%.4f,%.4f,%.4f]); }" % (" ".join(teeth), *clip, *size)]

def _run_scad(scad_text, out, command=None, timeout=900):
    cmd = command or [shutil.which("openscad") or "openscad"]
    with tempfile.TemporaryDirectory() as d:
        f = os.path.join(d, "s.scad"); open(f, "w").write(scad_text)
        p = subprocess.run(cmd + ["-q", "--backend=manifold", "-o", out, f], capture_output=True, text=True, timeout=timeout)
    if not os.path.exists(out) or os.path.getsize(out) < 200:
        err = (p.stderr or "")
        bad = [l for l in err.splitlines() if any(k in l.lower() for k in ("can't open", "cannot open", "error", "could not"))]
        return bad[-1][:200] if bad else False                      # a real complaint is a failure; a plain "empty" is just a cell the part does not reach
    return True

def _flat_area(mesh, axis, sign):
    """Area of the flat faces at the extreme end of the piece facing -sign along `axis` (what would lie on the bed if that end went down)."""
    tri = mesh.triangles; nrm = mesh.face_normals; ar = mesh.area_faces
    if sign < 0:                                            # the low end faces -axis
        ext = mesh.bounds[0][axis]; want = -1
    else:
        ext = mesh.bounds[1][axis]; want = 1
    sel = (nrm[:, axis] * want > 0.999) & (np.abs(tri[:, :, axis].mean(axis=1) - ext) < 0.06)
    return float(ar[sel].sum())

def _down_matrix(axis, sign):
    """A turn that brings the end `sign` of `axis` to the bottom (-z)."""
    v = np.zeros(3); v[axis] = float(sign)
    if axis == 2 and sign < 0:
        return np.eye(4)                                    # already on the bed
    if axis == 2:
        return trimesh.transformations.rotation_matrix(math.pi, [1, 0, 0])
    return trimesh.geometry.align_vectors(v, [0, 0, -1])

def orient(mesh, room):
    """Lay the piece on its largest flat end that lets it fit the room. -> (mesh turned and centred on the bed, description) or (None, reason)."""
    options = []
    for axis in range(3):
        for sign in (-1, 1):
            options.append((_flat_area(mesh, axis, sign), axis, sign))
    options.sort(reverse=True)
    best = options[0][0]
    for k, (area, axis, sign) in enumerate(options):             # the file is already lying as it was meant to print: keep that end down unless another is clearly bigger
        if (axis, sign) == (2, -1) and area >= 0.98 * best:
            options.insert(0, options.pop(k)); break
    for area, axis, sign in options:
        if area <= 1.0:
            continue
        m = mesh.copy(); m.apply_transform(_down_matrix(axis, sign))
        lo, hi = m.bounds; d = hi - lo
        for turn in (0, 1):                                  # the bed is square-ish but not always: try the piece turned a quarter about z too
            dx, dy = (d[0], d[1]) if turn == 0 else (d[1], d[0])
            if dx <= room[0] + 1e-6 and dy <= room[1] + 1e-6 and d[2] <= room[2] + 1e-6:
                if turn:
                    m.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [0, 0, 1]))
                lo, hi = m.bounds
                m.apply_translation([-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]])
                return m, dict(down=("-" if sign < 0 else "+") + AXES[axis], flat_mm2=round(area, 1), turned=bool(turn))
    return None, "no flat end lets it fit the bed in any turn"

def split(stl, outdir, base=None, bed=A1_BED, margin=6.0, scale=1.0, max_pieces=64, cuts=None, pin_d=3.0, clearance=0.3, depth=8.0,
          wall=1.2, pins=True, joint="auto", key_period=8.0, key_height=2.5, key_clearance=0.15, command=None, timeout=900):
    """Cut the part at `stl` into sections that fit the bed and write them to `outdir`.
    cuts: optional {"x": [pos...], "y": [...], "z": [...]} to cut exactly there instead of planning. -> a result dict (also written as split.json)."""
    stl = os.path.abspath(stl); outdir = os.path.abspath(outdir); os.makedirs(outdir, exist_ok=True)       # OpenSCAD runs elsewhere: every path must be absolute
    base = base or re.sub(r"[^a-z0-9_-]+", "_", os.path.splitext(os.path.basename(stl))[0].lower())[:28]
    if not NAME.fullmatch(base):
        raise ValueError(f"the base name {base!r} needs lower-case letters, digits, - or _")
    mesh = trimesh.load(stl)
    if scale != 1.0:
        mesh.apply_scale(scale)
    work = os.path.join(outdir, ".work"); os.makedirs(work, exist_ok=True)
    src = os.path.join(work, "part.stl"); mesh.export(src)         # the scaled part, the one OpenSCAD cuts
    room = usable(bed, margin)
    lo, hi = mesh.bounds; ext = hi - lo
    res = dict(source=stl, base=base, scale=scale, bed=list(bed), room=[round(x, 1) for x in room], extents=[round(float(x), 2) for x in ext],
               cuts=[], pieces=[], pins=dict(count=0, file=None), warnings=[], ok=True, volume=round(float(abs(mesh.volume)), 1))
    hole_d = pin_d + clearance
    # 1. where to cut
    if cuts:
        planes = {a: sorted(float(v) for v in cuts.get(a, [])) for a in AXES}
    else:
        n = plan_counts(ext, room, max_pieces=max_pieces)
        if n is None:
            res["ok"] = False
            res["warnings"].append(f"no way to cut it into {max_pieces} or fewer pieces that fit the bed (the part is {ext[0]:.0f} x {ext[1]:.0f} x {ext[2]:.0f} mm, the room {room[0]:.0f} x {room[1]:.0f} x {room[2]:.0f}): use a smaller scale or raise max_pieces")
            return _finish(res, outdir)
        planes = {}
        for ax in range(3):
            pos = []
            piece = ext[ax] / n[ax]
            cap = room[ax] if ax == 2 else min(room[0], room[1])     # the longest a piece may be along this axis and still lie flat
            minp = 0.2 * piece
            prev = lo[ax]
            for k in range(1, n[ax]):
                nominal = lo[ax] + k * piece
                left = n[ax] - k                                    # pieces still to come to the right of this plane, counting the one just right of it
                lower = max(prev + minp, hi[ax] - left * cap)       # the pieces on either side must still fit
                upper = min(prev + cap, hi[ax] - (left - 1) * minp)
                p, c, base_len = best_cut(mesh, ax, nominal, WINDOW_FRAC * piece, lower, upper)
                pos.append(p); prev = p
            planes[AXES[ax]] = pos
    planes = {a: [round(float(p), 2) for p in v] for a, v in planes.items()}
    edges = [[lo[i] - 1.0] + planes[AXES[i]] + [hi[i] + 1.0] for i in range(3)]
    for i, a in enumerate(AXES):
        for p in planes[a]:
            res["cuts"].append(dict(axis=a, pos=round(p, 2), outline_mm=round(outline_length(mesh, i, p), 1), pins=[]))
    # 2. the pins on every cut plane
    sites = {}
    keyed = set()                                        # seams joined by interlocking teeth instead of pins
    if joint not in ("auto", "pins", "keys"):
        raise ValueError("joint must be auto, pins or keys")
    if joint == "keys":
        for c in res["cuts"]:
            keyed.add((AXES.index(c["axis"]), c["pos"])); c["joint"] = "keys"
    elif pins:
        for c in res["cuts"]:
            ax = AXES.index(c["axis"])
            avoid = []                                       # the other cut planes, as (which of the plane's two coordinates, position)
            for c2 in res["cuts"]:
                a2 = AXES.index(c2["axis"])
                if a2 != ax:
                    avoid.append((0 if a2 == (ax + 1) % 3 else 1, c2["pos"]))
            pts, usable_area, area = pin_sites(mesh, ax, c["pos"], hole_d, depth, wall=wall, avoid=avoid)
            sites[(ax, c["pos"])] = pts
            c["pins"] = [[round(a, 2), round(b, 2)] for a, b in pts]; c["solid_mm2"] = round(area, 1)
            c["joint"] = "pins"
            if len(pts) < 2:
                if joint == "auto":                      # walls too thin for two pins: interlocking teeth work in any wall
                    sites[(ax, c["pos"])] = []; c["pins"] = []; c["joint"] = "keys"
                    keyed.add((ax, c["pos"]))
                    res["warnings"].append(f"cut {c['axis']} = {c['pos']:.1f}: the walls here are thinner than {2 * (hole_d / 2 + wall):.1f} mm, so this seam is joined with interlocking teeth ({key_period:g} mm squares, {key_height:g} mm tall) instead of pins; glue them")
                else:
                    res["warnings"].append(f"cut {c['axis']} = {c['pos']:.1f}: room for only {len(pts)} pin(s) (the walls here are thinner than {2 * (hole_d / 2 + wall):.1f} mm): use joint=auto for interlocking teeth, or glue / screws")
    # 3. build every piece with OpenSCAD: the cell of the grid, minus the pin holes on its cut faces
    npieces = 0
    pins_total = 0
    hole_volume = 0.0
    cells = list(itertools.product(*[range(len(e) - 1) for e in edges]))
    cells.sort(key=lambda c: (c[2], c[1], c[0]))
    for cell in cells:
        lo_c = [edges[i][cell[i]] for i in range(3)]; hi_c = [edges[i][cell[i] + 1] for i in range(3)]
        holes = []
        adds = []
        nholes = 0
        for i in range(3):
            o1, o2 = (i + 1) % 3, (i + 2) % 3
            def mine(ab):                                            # a pin belongs to the piece whose footprint it stands in
                return lo_c[o1] <= ab[0] <= hi_c[o1] and lo_c[o2] <= ab[1] <= hi_c[o2]
            if cell[i] > 0:                                          # a cut plane on this piece's low side: its hole goes up into the piece
                pos = edges[i][cell[i]]
                if (i, pos) in keyed:                                # the teeth of the piece below stand in here: leave room for them
                    holes += _key_blocks(i, pos, lo_c, hi_c, key_period, key_height, grow=key_clearance, below=0.05)
                for ab in sites.get((i, pos), []):
                    if mine(ab):
                        holes.append(_hole_scad(i, +1, pos, ab, hole_d, depth)); nholes += 1
            if cell[i] < len(edges[i]) - 2:                          # a cut plane on the high side: the hole goes down into the piece
                pos = edges[i][cell[i] + 1]
                if (i, pos) in keyed:                                # this piece's teeth stand up past the plane
                    adds += _key_blocks(i, pos, lo_c, hi_c, key_period, key_height, below=0.5)
                for ab in sites.get((i, pos), []):
                    if mine(ab):
                        holes.append(_hole_scad(i, -1, pos, ab, hole_d, depth)); nholes += 1
        size = [hi_c[i] - lo_c[i] for i in range(3)]
        scad = ('difference() {\n  intersection() { import("%s"); union() { translate([%.4f,%.4f,%.4f]) cube([%.4f,%.4f,%.4f]);\n    %s\n  } }\n  union() {\n    %s\n    cube(0.0001);\n  }\n}\n'
                % (src.replace("\\", "/"), lo_c[0], lo_c[1], lo_c[2], size[0], size[1], size[2], "\n    ".join(adds), "\n    ".join(holes)))
        tmp = os.path.join(work, f"cell_{cell[0]}{cell[1]}{cell[2]}.stl")
        if os.path.exists(tmp):
            os.remove(tmp)
        try:
            made = _run_scad(scad, tmp, command=command, timeout=timeout)
        except FileNotFoundError:
            raise ValueError("OpenSCAD is not installed on this machine")
        except subprocess.TimeoutExpired:
            made = False
        if isinstance(made, str):                                    # OpenSCAD said something other than "empty": that is a failure, not a gap
            res["ok"] = False
            res["warnings"].append(f"cell {cell}: OpenSCAD could not cut it ({made})")
            continue
        if not made:
            continue                                                 # an empty cell (the part does not reach it)
        m = trimesh.load(tmp)
        if abs(m.volume) < 1.0:
            continue
        npieces += 1
        name = f"{base}_s{npieces:02d}"
        hole_volume += nholes * math.pi * (hole_d / 2) ** 2 * depth
        pins_total += nholes
        turned, info = orient(m, room)
        entry = dict(name=name, cell=list(cell), volume=round(float(abs(m.volume)), 1), holes=nholes, watertight=bool(m.is_watertight))
        if turned is None:
            res["ok"] = False
            entry.update(ok=False, error=info, size=[round(float(x), 1) for x in (m.bounds[1] - m.bounds[0])])
            res["warnings"].append(f"{name} does not fit the bed ({entry['size'][0]} x {entry['size'][1]} x {entry['size'][2]} mm): cut it further")
        else:
            out = os.path.join(outdir, name + ".stl"); turned.export(out)
            lo2, hi2 = turned.bounds
            entry.update(ok=True, file=out, size=[round(float(x), 1) for x in (hi2 - lo2)], **info)
        res["pieces"].append(entry)
    # 4. nothing lost: the pieces plus the pin holes make the part
    total = sum(p["volume"] for p in res["pieces"])
    res["volume_pieces"] = round(total, 1); res["volume_pin_holes"] = round(hole_volume, 1)
    key_bound = sum(key_gap_bound(section_area(mesh, a, p), key_clearance) for a, p in keyed)
    lost = res["volume"] - total - hole_volume                      # what the clearance of the teeth takes: never negative, never over the bound
    res["volume_key_gap"] = round(lost, 1) if keyed else 0.0; res["volume_key_gap_bound"] = round(key_bound, 1)
    mismatch = max(0.0, lost - key_bound, -lost) / max(res["volume"], 1.0)
    res["volume_mismatch"] = round(mismatch, 5)
    if mismatch > 0.01:
        res["ok"] = False
        res["warnings"].append(f"the sections plus the pin holes are {100 * mismatch:.1f}% off the part's volume: material was lost or doubled (a hole may have broken out of a wall)")
    if any(not p["watertight"] for p in res["pieces"]):
        res["warnings"].append("a section is not watertight: check it in the slicer before printing")
    # 5. the pins to print: one per pair of holes, with spares
    pairs = sum(len(v) for v in sites.values())
    if pairs:
        n = pairs + max(2, int(math.ceil(pairs * 0.25)))
        L = 2 * depth - 1.0
        cols = int(math.ceil(math.sqrt(n)))
        parts = []
        for k in range(n):
            c = trimesh.creation.cylinder(radius=pin_d / 2, height=L, sections=24)
            c.apply_translation([(k % cols) * (pin_d + 5), (k // cols) * (pin_d + 5), L / 2]); parts.append(c)
        pm = trimesh.util.concatenate(parts)
        pf = os.path.join(outdir, f"{base}_pins.stl"); pm.export(pf)
        res["pins"] = dict(count=n, needed=pairs, diameter=pin_d, length=L, file=pf, note=f"{n} loose pins {pin_d} x {L:g} mm (standing up on the bed): {pairs} needed, {n - pairs} spare; hole {hole_d} mm, {depth:g} mm deep each side")
    shutil.rmtree(work, ignore_errors=True)
    return _finish(res, outdir)

def _finish(res, outdir):
    res["summary"] = summary(res)
    with open(os.path.join(outdir, (res.get("base") or "split") + "_split.json"), "w") as f:
        json.dump(res, f, indent=1)
    return res

def summary(res):
    if not res["pieces"]:
        return "; ".join(res["warnings"]) or "nothing was cut"
    ok = sum(1 for p in res["pieces"] if p.get("ok"))
    return f"{len(res['pieces'])} sections ({ok} fit the bed), {len(res['cuts'])} cut plane(s), {res['pins']['count']} pins; scale {res['scale']:g}; " + ("OK" if res["ok"] else "NOT OK")

def map_picture(stl, result, out_png, scale=1.0, max_faces=60000):
    """One picture of how the part was cut: front, top and side views with the cut planes (red) and each section's name. Drawn from the real mesh."""
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection
    mesh = trimesh.load(stl)
    if scale != 1.0:
        mesh.apply_scale(scale)
    tri = mesh.triangles
    if len(tri) > max_faces:
        tri = tri[:: len(tri) // max_faces + 1]
    views = [("Front (x across, z up)", 0, 2, 1), ("Top (x across, y up)", 0, 1, 2), ("Side (y across, z up)", 1, 2, 0)]
    fig, axs = plt.subplots(1, 3, figsize=(18, 7), facecolor="#fffff0")
    for ax, (title, a, b, depth) in zip(axs, views):
        order = np.argsort(tri[:, :, depth].mean(axis=1))
        polys = tri[order][:, :, [a, b]]
        ax.add_collection(PolyCollection(polys, facecolors="#d9d9d0", edgecolors="#b5b5aa", linewidths=0.15))
        for c in result["cuts"]:
            i = AXES.index(c["axis"])
            if i == a:
                ax.axvline(c["pos"], color="#e00000", lw=2)
            elif i == b:
                ax.axhline(c["pos"], color="#e00000", lw=2)
        lo, hi = mesh.bounds
        ax.set_xlim(lo[a] - 10, hi[a] + 10); ax.set_ylim(lo[b] - 10, hi[b] + 10); ax.set_aspect("equal"); ax.set_title(title, fontsize=14, weight="bold")
        ax.set_xlabel(AXES[a] + " (mm)"); ax.set_ylabel(AXES[b] + " (mm)")
    fig.suptitle(f"How it was cut: {result['summary']}", fontsize=15, weight="bold")
    fig.savefig(out_png, dpi=70, facecolor="#fffff0"); plt.close(fig)
    return out_png
