"""Classify plastic that has nothing directly under it as a BRIDGE or a CANTILEVER. Shared by the toolpath check (real G-code footprints) and
the geometric check (layers.analyse on a mesh), so both judge the same way.

From each unsupported pixel, look in 8 directions for the nearest material below it. If two OPPOSITE directions both find material it is held
at both ends: a bridge, whose span is the shortest such pair's total length. Otherwise it is a cantilever, and its depth is the distance to
the nearest material below."""
import math
import numpy as np

DIRS = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]

def shift(a, dx, dy):
    """a shifted so out[y, x] = a[y + dy, x + dx] (False outside)."""
    out = np.zeros_like(a)
    h, w = a.shape
    if abs(dx) >= w or abs(dy) >= h:      # shifted wholly off the picture (a small crop)
        return out
    ys, ye = max(0, -dy), min(h, h - dy)
    xs, xe = max(0, -dx), min(w, w - dx)
    out[ys:ye, xs:xe] = a[ys + dy:ye + dy, xs + dx:xe + dx]
    return out

def classify(S, A, res, look):
    """S: material in the layer below (bool), A: the unsupported pixels (bool), same shape. -> (span, depth, bridge, cant) arrays."""
    n = int(look / res)
    dist = []
    for dx, dy in DIRS:
        step = res * math.hypot(dx, dy)
        dd = np.full(S.shape, np.inf)
        for k in range(1, n + 1):
            hit = shift(S, dx * k, dy * k) & np.isinf(dd)
            dd[hit] = k * step
        dist.append(dd)
    span = np.min(np.stack([dist[i] + dist[i + 4] for i in range(4)]), axis=0)
    depth = np.min(np.stack(dist), axis=0)
    bridge = A & np.isfinite(span)
    cant = A & ~np.isfinite(span)
    return span, depth, bridge, cant
