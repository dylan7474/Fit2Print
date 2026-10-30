"""The dependency picklist (deps.toml): probe this machine and say which checks can run."""
import importlib.util, os, shutil, sys
try:
    import tomllib
except ModuleNotFoundError:           # Python 3.10
    tomllib = None

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def load(path=None):
    path = path or os.path.join(ROOT, "deps.toml")
    if tomllib is None:
        raise RuntimeError("Python 3.11+ is needed to read deps.toml")
    with open(path, "rb") as f:
        return tomllib.load(f)

def probe(spec=None):
    """-> list of dicts: kind, name, found, required, why, checks"""
    spec = spec or load()
    rows = []
    for m in spec.get("module", []):
        rows.append(dict(kind="module", name=m["name"], found=importlib.util.find_spec(m["name"]) is not None,
                         required=m.get("required", False), why=m.get("why", ""), checks=m.get("checks", []), pip=m.get("pip", m["name"])))
    for p in spec.get("program", []):
        rows.append(dict(kind="program", name=p["name"], found=shutil.which(p["name"]) is not None,
                         required=p.get("required", False), why=p.get("why", ""), checks=p.get("checks", []), pip=None))
    return rows

def report(rows):
    lines, bad = [], False
    for r in rows:
        mark = "ok   " if r["found"] else ("MISSING" if r["required"] else "absent ")
        bad |= (not r["found"]) and r["required"]
        lines.append(f"{mark:8}{r['kind']:8}{r['name']:14}{r['why']}")
        if not r["found"] and r["pip"]:
            lines.append(f"{'':16}-> pip install {r['pip']}")
        if not r["found"] and r["checks"]:
            lines.append(f"{'':16}-> without it these checks are off: {', '.join(r['checks'])}")
    return "\n".join(lines), bad
