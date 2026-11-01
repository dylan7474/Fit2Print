"""The files a project makes, in one place to download: print files (3MF), models (STL), coupons, split sections, reports. The page lists them and serves them.

Safety, because this serves files from the machine: the LIST is the whitelist. A file is served only if collect() lists it, and collect() looks only inside a few
named folders of THIS project (plates, coupons, sections, calibration, and the project's stl folder) plus a few named report files at the top. Nothing is
matched by a pattern in the URL, a file whose real path leaves the project (a symlink) is never listed, and every file is sent as an attachment (an html
report may also be VIEWED, but only under a locked-down content policy)."""
import io, json, os, re, zipfile
from . import export as export_mod

NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+() -]{0,119}")
MAX_ZIP = 400 * 1024 * 1024
TOP_FILES = ("GATE.md", "PARTS_REGISTER.md", "CALIBRATION.md")
# (folder, extensions listed there, the group they belong to)
SOURCES = [("plates", (".3mf",), "print"), ("plates", (".html",), "reports"), ("coupons", (".3mf",), "print"), ("coupons", (".stl",), "models"),
           ("sections", (".stl",), "models"), ("calibration", (".stl", ".md"), "models"), ("renders", (), "none")]
GROUPS = [("print", "Print files (3MF: open in Bambu Studio)"), ("models", "Models (STL)"), ("reports", "Reports and records")]
CTYPES = {".3mf": "application/vnd.ms-package.3dmanufacturing-3dmodel+xml", ".stl": "model/stl", ".html": "text/html; charset=utf-8", ".md": "text/markdown; charset=utf-8", ".json": "application/json"}


def _inside(folder, path):
    root = os.path.realpath(folder) + os.sep
    return os.path.realpath(path).startswith(root) and os.path.isfile(path)


def _verdicts(folder, marker):
    """{file name: (verdict, minutes, grams)} from the plate records, for the label beside each print file."""
    p = os.path.join(folder, "PLATE_RESULTS.jsonl" if marker.get("adapter") == "phonosphere" else os.path.join("records", "plates.jsonl"))
    out = {}
    if os.path.exists(p):
        for l in open(p):
            try:
                r = json.loads(l)
            except ValueError:
                continue
            if r.get("file"):
                out[os.path.basename(str(r["file"]))] = (r.get("verdict", ""), r.get("minutes"), r.get("grams"))
    return out


def collect(folder, marker):
    """-> list of dict(rel, name, group, size, label), newest first within a group. Only files inside the project, only in the named folders."""
    folder = os.path.abspath(folder)
    try:
        stl_dir = export_mod.stl_dir(marker)
    except ValueError:
        stl_dir = "stl"
    sources = list(SOURCES) + [(stl_dir, (".stl",), "models")]
    seen, out = set(), []
    vd = _verdicts(folder, marker)
    for sub, exts, group in sources:
        d = os.path.join(folder, sub)
        if not exts or not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            full = os.path.join(d, fn)
            rel = f"{sub}/{fn}"
            if rel in seen or not NAME.fullmatch(fn) or not fn.lower().endswith(exts) or fn.endswith(".part.stl") or not _inside(folder, full):
                continue
            seen.add(rel)
            label = ""
            if fn.endswith(".3mf") and fn in vd:
                v, m, g = vd[fn]
                label = " ".join(x for x in (v, f"{m} min" if m else "", f"{g} g" if g else "") if x)
            out.append(dict(rel=rel, name=fn, group=group, size=os.path.getsize(full), mtime=os.path.getmtime(full), label=label))
    for fn in TOP_FILES:
        full = os.path.join(folder, fn)
        if os.path.isfile(full) and _inside(folder, full):
            out.append(dict(rel=fn, name=fn, group="reports", size=os.path.getsize(full), mtime=os.path.getmtime(full), label=""))
    return out


def lookup(folder, marker, rel):
    """The listed entry for `rel`, or None. This IS the whitelist: nothing that is not listed can be fetched, whatever the URL says."""
    return next((e for e in collect(folder, marker) if e["rel"] == rel), None)


def content_type(name):
    return CTYPES.get(os.path.splitext(name)[1].lower(), "application/octet-stream")


def zip_bytes(folder, entries):
    """-> (bytes, None) or (None, reason). 3MF files are already compressed, so they are stored."""
    total = sum(e["size"] for e in entries)
    if total > MAX_ZIP:
        return None, f"these files are {total // (1024 * 1024)} MB: too big for one zip (the limit is {MAX_ZIP // (1024 * 1024)} MB); download them one at a time"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for e in entries:
            z.write(os.path.join(folder, e["rel"]), e["rel"], compress_type=zipfile.ZIP_STORED if e["name"].endswith(".3mf") else zipfile.ZIP_DEFLATED)
    return buf.getvalue(), None


def human(n):
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024 or u == "GB":
            return f"{n:.0f} {u}" if u == "B" else f"{n:.1f} {u}"
        n /= 1024
