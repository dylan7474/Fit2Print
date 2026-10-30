"""The component library: the real dimensions of the parts a design has to hold, each with WHERE IT CAME FROM and whether YOU have measured it.

A number in a design must come from here, never from memory. Every dimension has:
  value      the published or estimated figure
  basis      official (the maker's own drawing/datasheet) | derived (worked out from official numbers) | third-party (a shop or database)
             | estimate (no published source: measure it) | notes (an earlier project's notes)
  source     where it came from (a URL or a plain description)
  critical   does the fit depend on it (the page asks for these first)
  measured   what the person measured, with the date and how; once set, THIS is the value models use
Entries are TOML files. The shipped library is hardware/ in the Fit2Print repo; the person's own measurements live in a user folder that overrides it,
and a project may carry a hardware/ folder of its own (the assistant proposes new parts there; the person promotes them)."""
import datetime, os, re
from .settings import ROOT

try:
    import tomllib
except ModuleNotFoundError:
    tomllib = None

BASES = ("official", "derived", "third-party", "estimate", "notes")
USER_DIR = os.path.expanduser("~/.config/fit2print/hardware")

def shipped_dir():
    return os.path.join(ROOT, "hardware")

def _read(path):
    if tomllib is None:
        raise RuntimeError("Python 3.11+ is needed to read hardware files")
    with open(path, "rb") as f:
        d = tomllib.load(f)
    if not re.fullmatch(r"[a-z0-9-]+", d.get("id", "")):
        raise ValueError(f"{path}: needs an id of lower-case letters, digits and hyphens")
    for k, dim in d.get("dim", {}).items():
        if "value" not in dim or dim.get("basis") not in BASES:
            raise ValueError(f"{path}: dimension '{k}' needs a value and a basis (one of {', '.join(BASES)})")
        if dim["basis"] != "derived" and not dim.get("source"):
            raise ValueError(f"{path}: dimension '{k}' has no source: say where it came from, or mark it basis = \"estimate\" with a note")
    return d

def load_all(dirs=None):
    """{id: entry}. Later folders override earlier ones (shipped, then user, then project), per dimension: a measurement beats a published figure."""
    out = {}
    for d in dirs or [shipped_dir(), USER_DIR]:
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if fn.endswith(".toml"):
                e = _read(os.path.join(d, fn))
                if e["id"] in out:
                    out[e["id"]]["dim"].update(e.get("dim", {}))
                    for k in ("name", "category", "sources", "retrieved", "note"):
                        if k in e: out[e["id"]][k] = e[k]
                else:
                    out[e["id"]] = e
    return out

def value(dim):
    """The number a model should use: what the person measured, else the published/estimated figure."""
    m = dim.get("measured")
    return m["value"] if isinstance(m, dict) and "value" in m else dim["value"]

def is_verified(dim):
    return isinstance(dim.get("measured"), dict) and "value" in dim["measured"]

def to_toml(e):
    def q(s): return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'
    out = [f"id = {q(e['id'])}", f"name = {q(e.get('name', e['id']))}", f"category = {q(e.get('category', ''))}"]
    if e.get("sources"): out.append("sources = [" + ", ".join(q(s) for s in e["sources"]) + "]")
    if e.get("retrieved"): out.append(f"retrieved = {q(e['retrieved'])}")
    if e.get("note"): out.append(f"note = {q(e['note'])}")
    for k, d in e.get("dim", {}).items():
        out += ["", f"[dim.{k}]", f"value = {d['value']}", f"unit = {q(d.get('unit', 'mm'))}", f"basis = {q(d['basis'])}", f"source = {q(d.get('source', ''))}",
                f"critical = {'true' if d.get('critical') else 'false'}"]
        if d.get("note"): out.append(f"note = {q(d['note'])}")
        m = d.get("measured")
        if isinstance(m, dict) and "value" in m:
            out += [f"[dim.{k}.measured]", f"value = {m['value']}", f"on = {q(m.get('on', ''))}", f"how = {q(m.get('how', ''))}"]
    return "\n".join(out) + "\n"

def verify(entry_id, dim, measured, how="callipers", user_dir=None, library=None):
    """Record the PERSON's measurement in their own folder (never in the shipped library). -> the new value."""
    lib = library or load_all()
    if entry_id not in lib:
        raise KeyError(f"no component '{entry_id}'")
    if dim not in lib[entry_id].get("dim", {}):
        raise KeyError(f"'{entry_id}' has no dimension '{dim}'")
    measured = float(measured)
    if not (0 < measured < 1000):
        raise ValueError("a measurement in mm between 0 and 1000, please")
    user_dir = user_dir or USER_DIR
    os.makedirs(user_dir, exist_ok=True)
    path = os.path.join(user_dir, entry_id + ".toml")
    own = _read(path) if os.path.exists(path) else dict(id=entry_id, name=lib[entry_id].get("name", entry_id), category=lib[entry_id].get("category", ""), dim={})
    base = dict(lib[entry_id]["dim"][dim])
    base.pop("measured", None)
    own["dim"][dim] = dict(base, measured=dict(value=measured, on=datetime.date.today().isoformat(), how=how))
    with open(path, "w") as f:
        f.write(to_toml(own))
    return measured

def unverified(entry, only_critical=True):
    return [k for k, d in entry.get("dim", {}).items() if (d.get("critical") or not only_critical) and not is_verified(d)]

def openscad(entry):
    """OpenSCAD parameter lines for a model to include: the measured value where there is one, and a comment saying what each number rests on."""
    pre = entry["id"].replace("-", "_")
    lines = [f"// {entry.get('name', entry['id'])}: from the Fit2Print component library. A model must use these, not numbers from memory."]
    for k, d in entry.get("dim", {}).items():
        tag = "MEASURED by you" if is_verified(d) else f"UNVERIFIED ({d['basis']})"
        lines.append(f"{pre}_{k} = {value(d)};   // {d.get('unit', 'mm')}, {tag}")
    return "\n".join(lines) + "\n"
