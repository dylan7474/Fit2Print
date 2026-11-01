"""One page, plain English, with a picture of every spot the checks flagged. Extracted from Phonosphere's plate_report.py (and drawn with pillow, so no matplotlib).

Runs the toolpath check (is every bit of plastic held up?) and, when the part STLs are given, the as-built check (does the print match the design?), then draws
the REAL printed layer at each flagged spot: black = this layer, grey = the layer below, blue = support, green ring = the spot. Nothing is waived here: every
CHECK and BLOCK is listed with its picture, and the decision is the person's. Self-contained HTML (pictures embedded)."""
import base64, html, io, os
import numpy as np
import trimesh
from PIL import Image, ImageDraw, ImageFont
from . import asbuilt, gcode as g, toolpath
from .settings import Settings

PLAIN = {
    "cant": ("Plastic with nothing under it on one side",
             "Part of a layer hangs out with support on one side only, like a shelf or a corner starting in mid-air. Printers sag or fail here. "
             "A tiny one at the top of a small round hole is usually harmless; a corner or edge is not."),
    "bridge": ("A bridge (held on two opposite sides)",
               "The printer stretches plastic across a gap. Short bridges (under about 15 mm) normally print fine; this one is the longest on the plate."),
    "filled": ("Support plastic inside a hole",
               "Support has been built inside a small hole or pocket, so a screw or bolt would not go in. Unless that support is there on purpose, the hole is plugged."),
    "missing": ("Design wall with no plastic printed on it",
                "The model has an outer wall here but the print path puts no plastic on it, so the feature may be missing or have a gap."),
    "extra": ("Plastic printed where the design has none",
              "Part plastic appears outside the model's outline. Often it is another part sharing the plate that was not given to the check."),
}
BLACK, GREY, BLUE, GREEN, RED = (17, 17, 17), (181, 181, 181), (74, 144, 226), (26, 152, 80), (192, 57, 43)
SS = 2                                            # draw at twice the size and shrink: smooth lines without a drawing library


def _font(size):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _real(layers):
    return sorted(q for q in layers if sum(1 for f, _, _ in layers[q] if f != "Custom") >= 20)


def _png(im):
    b = io.BytesIO(); im.save(b, format="PNG", optimize=True)
    return base64.b64encode(b.getvalue()).decode()


def _lines(draw, segs, to_px, colour_of, width, step):
    for f, s, _ in segs:
        if f == "Custom":
            continue
        col = colour_of(f)
        if col is None:
            continue
        p = g.seg_points(s[:7], step)[0]
        draw.line([to_px(x, y) for x, y in p], fill=col, width=width)


def spot_png(layers, z, x, y, half=22.0, title="", size=480):
    """The real layer nearest `z`, `half` mm each side of (x, y): this layer black, the layers just under it grey, support blue, the spot ringed green."""
    zs = _real(layers) or sorted(layers)
    cur = min(zs, key=lambda q: abs(q - z))
    S = size * SS
    to_px = lambda a, b: ((a - (x - half)) / (2 * half) * S, S - (b - (y - half)) / (2 * half) * S)
    im = Image.new("RGB", (S, S), "white"); d = ImageDraw.Draw(im)
    for q in zs:
        if 0 < cur - q <= 0.55:
            _lines(d, layers[q], to_px, lambda f: BLUE if f.startswith("Support") else GREY, SS, 0.4)
    _lines(d, layers[cur], to_px, lambda f: BLUE if f.startswith("Support") else BLACK, SS + 1, 0.4)
    cx, cy = to_px(x, y); r = 3.0 / (2 * half) * S
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=GREEN, width=3 * SS)
    im = im.resize((size, size), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, size - 1, size - 1], outline=(200, 200, 200))
    d.text((8, 6), f"{title}  (layer z = {cur:.2f} mm)", fill=(40, 40, 40), font=_font(13))
    d.text((8, size - 20), f"{2 * half:.0f} mm across", fill=(120, 120, 120), font=_font(11))
    return _png(im)


def first_layer_png(layers, boxes, size=640):
    """The whole bed's first layer (black = part, blue = support) with each part's name where the plate puts it."""
    zs = _real(layers) or sorted(layers)
    segs = [s for f, s, _ in layers[zs[0]] if f != "Custom"]
    pts = np.vstack([g.seg_points(s[:7], 2.0)[0] for s in segs]) if segs else np.array([[0.0, 0.0], [1.0, 1.0]])
    lo, hi = pts.min(0) - 6, pts.max(0) + 6
    span = float((hi - lo).max())
    S = size * SS
    to_px = lambda a, b: ((a - lo[0]) / span * S, S - (b - lo[1]) / span * S)
    im = Image.new("RGB", (S, S), "white"); d = ImageDraw.Draw(im)
    _lines(d, layers[zs[0]], to_px, lambda f: BLUE if f.startswith("Support") else BLACK, SS, 0.6)
    im = im.resize((size, size), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    f = _font(12)
    for n, b in boxes:
        cx, cy = to_px((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
        d.text((cx / SS, cy / SS), n.replace(".stl", ""), fill=RED, font=f, anchor="mm")
    d.text((8, 6), "First layer on the bed (black = part, blue = support)", fill=(40, 40, 40), font=_font(13))
    return _png(im)


def findings_for(layers, plate, stls, cfg):
    """-> (findings [(kind, severity, caption, png)], as-built rows [(part, verdict)]). Severity is BLOCK / CHECK / OK."""
    boxes = asbuilt.plate_boxes(plate) if plate.endswith(".3mf") else []
    out, rows = [], []
    w = toolpath.analyse(layers, cfg)
    for key, block, check in (("cant", cfg.cantilever_block, cfg.cantilever_check), ("bridge", cfg.bridge_block, cfg.bridge_check)):
        v, pos = w[key]
        if pos is None:
            continue
        sev = "BLOCK" if v > block else "CHECK" if v > check else "OK"
        out.append((key, sev, f"{v:.1f} mm, at x {pos[1]:.0f}, y {pos[2]:.0f}, layer {pos[0]:.2f} mm up", spot_png(layers, pos[0], pos[1], pos[2], title=PLAIN[key][0])))
    for s in stls:
        name = os.path.splitext(os.path.basename(s))[0]
        res = asbuilt.best_fit(layers, asbuilt.find_box(boxes, s) if len(stls) > 1 else None, trimesh.load(s))
        if "error" in res:
            rows.append((name, "could not run: " + res["error"])); continue
        feats = [f for f in asbuilt.summarise(res) if f[1] >= 3]
        rows.append((name, asbuilt.verdict(feats)))
        for kind, n, x, y, area, z0, z1 in feats:
            out.append((kind, "BLOCK" if kind == "filled" else "CHECK", f"{name}: {n} layers (z {z0:.1f} to {z1:.1f} mm) at x {x:.0f}, y {y:.0f}",
                        spot_png(layers, (z0 + z1) / 2, x, y, title=PLAIN[kind][0])))
    return out, rows, boxes


def build(plate, stls=(), cfg=None):
    """-> (html text, overall verdict). `plate` is a sliced .3mf (or .gcode); `stls` the design files of its parts."""
    cfg = cfg or Settings.load(None)
    layers, _, _ = g.parse(g.read_gcode(plate), cfg.filament_area)
    findings, rows, boxes = findings_for(layers, plate, list(stls), cfg)
    sevs = [f[1] for f in findings] + [v for _, v in rows if v in ("BLOCK", "CHECK")]
    overall = "BLOCK" if "BLOCK" in sevs else "CHECK" if "CHECK" in sevs else "PASS"
    rowhtml = "".join(f"<tr><td>{html.escape(n)}</td><td class='{v.lower().split()[0]}'>{html.escape(v)}</td></tr>" for n, v in rows)
    cards = ""
    for kind, sev, cap, png in findings:
        t, expl = PLAIN[kind]
        cards += (f"<div class='card'><h3><span class='{sev.lower()}'>{sev}</span> {html.escape(t)}</h3><p><b>{html.escape(cap)}</b></p>"
                  f"<p>{html.escape(expl)}</p><img alt='the layer at this spot' src='data:image/png;base64,{png}'></div>")
    doc = f"""<!doctype html><meta charset=utf-8><title>Plate report {html.escape(os.path.basename(plate))}</title>
<style>body{{font:15px/1.5 system-ui,sans-serif;max-width:900px;margin:24px auto;padding:0 16px;color:#222}}
.card{{border:1px solid #ccc;border-radius:8px;padding:8px 16px;margin:16px 0}}img{{max-width:100%}}
.block{{background:#c0392b;color:#fff;padding:1px 8px;border-radius:4px}}.check{{background:#e6a817;padding:1px 8px;border-radius:4px}}
.pass,.ok{{background:#2e8b57;color:#fff;padding:1px 8px;border-radius:4px}}td{{padding:2px 12px}}</style>
<h1>Plate report: {html.escape(os.path.basename(plate))}</h1>
<p>Overall: <span class='{overall.lower()}'>{overall}</span>. A CHECK is not a pass: it is a spot you should look at and decide on. Nothing here has been waived.</p>
<h2>Parts compared with their design</h2><table>{rowhtml or "<tr><td>no part files given</td></tr>"}</table>
<h2>Spots to look at ({len(findings)})</h2>{cards or "<p>No spots flagged.</p>"}
<h2>The bed</h2><img alt='first layer' src='data:image/png;base64,{first_layer_png(layers, boxes)}'>
<h2>What this report cannot tell you</h2><p>It checks that every bit of plastic has something under it and that the print matches the model. It cannot see a dirty bed, damp filament,
a plate that does not stick, stringing, or how a surface will look. Watch the first layers go down.</p>"""
    return doc, overall
