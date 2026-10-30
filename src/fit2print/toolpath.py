"""Is every bit of plastic held up from below, and from how many sides? On the real toolpaths. Ported from Phonosphere's anchor_check.py.

A line-length test cannot tell a good 9 mm bridge (a zigzag across a groove, held on both long sides) from a corner that starts in the
air (held on one side or none). This can: every layer is drawn as the footprint of its extrusions; 'air' is part material with no material
(supports included) within `reach` of it in the layer below; from each air pixel it looks in 8 directions for the nearest material below:
two opposite directions both finding material = a BRIDGE (its span is the shortest such pair); otherwise a CANTILEVER (the distance to the
nearest material below).
"""
import math
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi
from . import gcode as g
from .settings import Settings

DIRS = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]

def footprint(segs, origin, shape, res, support_only=False):
    im = Image.new("1", (shape[1], shape[0]), 0)
    d = ImageDraw.Draw(im)
    for feat, seg, _ in segs:
        if feat == "Custom" or feat.startswith("Support") != support_only:
            continue
        p = g.seg_points(seg, res)[0]
        d.line([((x - origin[0]) / res, (y - origin[1]) / res) for x, y in p], fill=1, width=max(1, round(0.45 / res)))
    return np.array(im, dtype=bool)

def dilate(a, n):
    return ndi.binary_dilation(a, structure=np.ones((3, 3), bool), iterations=n) if n > 0 else a.copy()

def shift(a, dx, dy):
    """a shifted so out[y, x] = a[y + dy, x + dx] (False outside)."""
    out = np.zeros_like(a)
    h, w = a.shape
    ys, ye = max(0, -dy), min(h, h - dy)
    xs, xe = max(0, -dx), min(w, w - dx)
    out[ys:ye, xs:xe] = a[ys + dy:ye + dy, xs + dx:xe + dx]
    return out

def analyse(layers, cfg=None, collect=None):
    """The worst cantilever and bridge: {'cant': (mm, (z, x, y) | None), 'bridge': (...)}. With collect={} also stores, per layer z,
    the air cells {'cant': [...], 'bridge': [...]} for a viewer."""
    cfg = cfg or Settings()
    RES = cfg.resolution
    allp = [g.seg_points(s, 1.0)[0] for z in layers for f, s, _ in layers[z] if f != "Custom"]
    worst = {"cant": (0.0, None), "bridge": (0.0, None)}
    if not allp:
        return worst
    pts = np.vstack(allp)
    origin = (pts[:, 0].min() - 2, pts[:, 1].min() - 2)
    shape = (int((pts[:, 1].max() - origin[1] + 2) / RES) + 1, int((pts[:, 0].max() - origin[0] + 2) / RES) + 1)
    n = int(cfg.look / RES)
    recent = []                                  # (z, footprint incl. supports) of the layers printed in the last 0.55 mm
    for z in g.real_layers(layers):
        segs = layers[z]
        part = footprint(segs, origin, shape, RES)
        everything = part | footprint(segs, origin, shape, RES, support_only=True)
        recent = [(zz, f) for zz, f in recent if z - zz <= 0.55 and zz < z]
        prev = np.logical_or.reduce([f for _, f in recent]) if recent else None
        if prev is not None:
            air = part & ~dilate(prev, round(cfg.reach / RES))
            if air.sum() * RES * RES > 3.0:
                ys, xs = np.where(air)
                y0, y1 = max(0, ys.min() - n - 2), min(shape[0], ys.max() + n + 3)
                x0, x1 = max(0, xs.min() - n - 2), min(shape[1], xs.max() + n + 3)
                S, A = prev[y0:y1, x0:x1], air[y0:y1, x0:x1]
                dist = []
                for dx, dy in DIRS:
                    step = RES * math.hypot(dx, dy)
                    dd = np.full(S.shape, np.inf)
                    for k in range(1, n + 1):
                        hit = shift(S, dx * k, dy * k) & np.isinf(dd)
                        dd[hit] = k * step
                    dist.append(dd)
                span = np.min(np.stack([dist[i] + dist[i + 4] for i in range(4)]), axis=0)
                depth = np.min(np.stack(dist), axis=0)
                bridge = A & np.isfinite(span)
                cant = A & ~np.isfinite(span)
                if collect is not None:
                    sub = lambda M: [(round(origin[0] + (xx + x0) * RES, 1), round(origin[1] + (yy + y0) * RES, 1)) for yy, xx in zip(*np.where(M))][::4]
                    collect[z] = {"cant": sub(cant & (depth > 1.0)), "bridge": sub(bridge)}
                if bridge.any():
                    v = float(span[bridge].max()); i = np.unravel_index(np.argmax(np.where(bridge, span, -1)), S.shape)
                    if v > worst["bridge"][0]:
                        worst["bridge"] = (v, (z, origin[0] + (i[1] + x0) * RES, origin[1] + (i[0] + y0) * RES))
                if cant.any():
                    dv = np.where(np.isinf(np.where(cant, depth, 0)), cfg.look, np.where(cant, depth, 0))
                    v = float(dv.max()); i = np.unravel_index(np.argmax(dv), S.shape)
                    if v > worst["cant"][0]:
                        worst["cant"] = (v, (z, origin[0] + (i[1] + x0) * RES, origin[1] + (i[0] + y0) * RES))
        recent.append((z, everything))
    return worst

def verdict(w, cfg=None):
    cfg = cfg or Settings()
    c, b = w["cant"][0], w["bridge"][0]
    if c > cfg.cantilever_block or b > cfg.bridge_block:
        return "BLOCK"
    if c > cfg.cantilever_check or b > cfg.bridge_check:
        return "CHECK"
    return "PASS"

def report(layers, cfg=None):
    """(verdict, [lines]): BLOCK stops the plate; CHECK must be shown to the person and decided by them."""
    cfg = cfg or Settings()
    w = analyse(layers, cfg)
    fmt = lambda t: f"{t[0]:.1f} mm at z {t[1][0]:.2f}, x {t[1][1]:.0f}, y {t[1][2]:.0f}"
    lines = []
    if w["cant"][1]:
        lines.append(f"unsupported cantilever {fmt(w['cant'])}: material starts in the air with support on one side only")
    if w["bridge"][1]:
        lines.append(f"longest bridge {fmt(w['bridge'])} (held on opposite sides)")
    return verdict(w, cfg), lines
