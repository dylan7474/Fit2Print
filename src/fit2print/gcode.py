"""Read sliced G-code (a Bambu .3mf or a plain .gcode) into per-layer extrusion segments. Ported from Phonosphere's gcode_check.py."""
import math, re, zipfile
from collections import defaultdict
import numpy as np

NUM = re.compile(r"([XYZEFIJ])(-?\d*\.?\d+)")

def read_gcode(path):
    if path.endswith(".gcode"):
        with open(path) as f:
            return f.read().splitlines()
    z = zipfile.ZipFile(path)
    name = next((n for n in z.namelist() if n.startswith("Metadata/plate_") and n.endswith(".gcode")), None)
    if name is None:
        raise ValueError(f"{path}: no sliced G-code inside (open it in the slicer and slice it first)")
    return z.read(name).decode().splitlines()

def seg_points(s, step):
    """Points along a segment (line or arc) every `step` mm: (points Nx2, length)."""
    kind, x0, y0, x1, y1, i, j = s[:7]
    if kind == "G1":
        L = math.hypot(x1 - x0, y1 - y0)
        n = max(1, int(L / step))
        t = (np.arange(n + 1) / n)[:, None]
        return np.array([x0, y0]) * (1 - t) + np.array([x1, y1]) * t, L
    cx, cy = x0 + i, y0 + j
    r = math.hypot(i, j)
    a0 = math.atan2(y0 - cy, x0 - cx)
    a1 = math.atan2(y1 - cy, x1 - cx)
    ang = (a0 - a1) % (2 * math.pi) if kind == "G2" else (a1 - a0) % (2 * math.pi)
    if ang == 0 and (x0, y0) == (x1, y1):
        ang = 2 * math.pi
    L = r * ang
    n = max(1, int(L / step))
    th = a0 + (np.arange(n + 1) / n) * ang * (-1 if kind == "G2" else 1)
    return np.c_[cx + r * np.cos(th), cy + r * np.sin(th)], L

def parse(lines, filament_area=math.pi * 0.875 ** 2):
    """-> (layers, flow_time, max_flow). layers[z] = [(feature, segment, contiguous_with_previous)]; a segment is
    (cmd, x0, y0, x1, y1, I, J, flow mm3/s, seconds, filament): the filament is the slicer's tool number (T0, T1 ...) counted from 0."""
    x = y = z = 0.0
    feed, feat, tool = 1800.0, None, 0
    layers = defaultdict(list)
    flow_time, max_flow = defaultdict(float), defaultdict(float)
    last_end = None
    for l in lines:
        if l.startswith("; FEATURE:"):
            feat = l[10:].strip()
            continue
        if len(l) > 1 and l[0] == "T" and l[1:].split(None, 1)[0].isdigit():       # a filament change (T255 is the AMS unload at the end, not a filament)
            if int(l[1:].split(None, 1)[0]) < 32:
                tool = int(l[1:].split(None, 1)[0])
            continue
        if not l or l[0] not in "GM":
            continue
        cmd = l.split(None, 1)[0]
        if cmd not in ("G0", "G1", "G2", "G3"):
            continue
        v = {k: float(n) for k, n in NUM.findall(l.split(";")[0])}
        if "F" in v:
            feed = v["F"]
        nx, ny = v.get("X", x), v.get("Y", y)
        if "Z" in v:
            z = v["Z"]
        if cmd != "G0" and v.get("E", 0) > 0 and ("X" in v or "Y" in v) and feat:
            seg = (cmd, x, y, nx, ny, v.get("I", 0.0), v.get("J", 0.0))
            _, length = seg_points(seg, 1e9)
            if length > 0:
                secs = length / (feed / 60.0) if feed else 0
                if secs:
                    q = v["E"] * filament_area / secs
                    flow_time[feat] += secs
                    max_flow[feat] = max(max_flow[feat], q)
                    seg = seg + (q, secs, tool)
                else:
                    seg = seg + (0.0, 0.0, tool)
                contiguous = last_end is not None and math.hypot(last_end[0] - x, last_end[1] - y) < 0.05
                layers[round(z, 3)].append((feat, seg, contiguous))
                last_end = (nx, ny)
        else:
            last_end = None if (cmd == "G0" or "E" not in v) else last_end
        x, y = nx, ny
    return layers, flow_time, max_flow

def real_layers(layers, min_segments=20, min_length=30.0):
    """z values of real layers: a z with only a handful of short moves is a purge line or a wipe at a z-hop. A layer is real if it has
    min_segments part moves OR min_length mm of them. (Segment count alone is not enough: a thin pin has few long-ish moves per layer, and
    when it was skipped the layers above it had nothing to be compared with: 2026-10-30, found by the plate negative control.)"""
    out = []
    for z in sorted(layers):
        part = [s for f, s, _ in layers[z] if f != "Custom"]
        if len(part) >= min_segments or sum(seg_points(s, 1e9)[1] for s in part) >= min_length:
            out.append(z)
    return out

def filament_colours(lines):
    """['#RRGGBB', ...] from the sliced file's own header (one per filament), or []."""
    for l in lines[:20000]:
        if l.startswith("; filament_colour ="):
            return [c.strip() for c in l.split("=", 1)[1].split(";") if c.strip()]
    return []
