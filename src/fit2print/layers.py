"""A small layer slicer with no heavy dependencies: slice a mesh into 2D masks on a grid and find plastic that starts in mid-air.

Why it exists: trimesh's own section/polygon code needs networkx and shapely, which are not always installed, and a check that is silently
switched off is worse than none. This rasterises each layer with an even-odd scanline fill, so it needs only numpy, scipy and trimesh's
plane intersection. Printed in layers, a 'new' region in layer n that has no material within `reach` mm in layer n-1 has nothing to sit on.
"""
import numpy as np
import trimesh
from scipy import ndimage as ndi

def masks(mesh, zs, res=0.25):
    """Yield (z, mask, (x0, y0)): mask[j, i] is True where the mesh is solid at height z, on a grid of `res` mm."""
    x0, y0 = mesh.bounds[0][:2] - 2
    w = int((mesh.bounds[1][0] - x0 + 2) / res)
    h = int((mesh.bounds[1][1] - y0 + 2) / res)
    ys = (np.arange(h) + 0.5) * res + y0
    for z in zs:
        seg = trimesh.intersections.mesh_plane(mesh, [0, 0, 1], [0, 0, z])
        out = np.zeros((h, w), bool)
        if len(seg):
            a, b = seg[:, 0, :2], seg[:, 1, :2]
            lo = np.minimum(a[:, 1], b[:, 1]); hi = np.maximum(a[:, 1], b[:, 1])
            for j, y in enumerate(ys):
                k = (lo <= y) & (y < hi)
                if not k.any():
                    continue
                t = (y - a[k, 1]) / (b[k, 1] - a[k, 1])
                xs = np.sort(a[k, 0] + t * (b[k, 0] - a[k, 0]))
                for p in range(0, len(xs) - 1, 2):
                    i0 = int(np.ceil((xs[p] - x0) / res - 0.5)); i1 = int(np.floor((xs[p + 1] - x0) / res - 0.5))
                    out[j, max(i0, 0):i1 + 1] = True
        yield z, out, (x0, y0)

def unsupported(mesh, layer=0.28, reach=0.6, min_area=0.5, res=0.25):
    """Find layers where plastic starts with nothing under it. -> list of dicts: z, area (mm2), x, y (centre of the unsupported region)."""
    zs = np.arange(layer / 2, mesh.bounds[1][2], layer)
    events, prev = [], None
    for z, cur, (x0, y0) in masks(mesh, zs, res):
        if prev is not None:
            # + half a pixel: rasterising two layers can add that much
            air = cur & ~ndi.binary_dilation(prev, iterations=max(1, int(np.ceil((reach + 0.5 * res) / res))))
            area = air.sum() * res * res
            if area > min_area:
                yy, xx = np.nonzero(air)
                events.append(dict(z=round(float(z), 2), area=round(float(area), 1),
                                   x=round(float(xx.mean() * res + x0), 1), y=round(float(yy.mean() * res + y0), 1)))
        prev = cur
    return events
