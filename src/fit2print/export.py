"""Make the printable files: each [[export]] table in the project marker names one printable piece of the model, and this writes it as stl/NAME.stl, lying flat
on the bed (lowest point at z = 0, centred on the origin in x and y), ready for the checks and the slicer.

    [[export]]
    name = "body"          # the piece (and the file stl/body.stl): letters, digits, - and _
    part = "body"          # the model's `part` value that draws just that piece
    group = "dice"         # optional: pieces of one group keep their places relative to each other (they print together as ONE plate)
    colour = "#1A1A1A"     # optional: the filament colour of the piece in a group; pieces of different colours print in different filaments
A group is placed as one: the whole group sits flat on the bed and is centred together, so a piece that fills a hole in another still fits it.
Drawn with OpenSCAD like the pictures (same command setting); the model file must be inside the project."""
import os, re, shutil, subprocess
import numpy as np
import trimesh

NAME = re.compile(r"[a-z0-9_-]{1,40}")
COLOUR = re.compile(r"#[0-9a-fA-F]{6}")

def pieces(marker):
    out = []
    for e in marker.get("export") or []:
        if not NAME.fullmatch(str(e.get("name", ""))):
            raise ValueError(f"an [[export]] needs a name of lower-case letters, digits, - or _ (got {e.get('name')!r})")
        g, c = e.get("group"), e.get("colour")
        if g is not None and not NAME.fullmatch(str(g)):
            raise ValueError(f"the group of [[export]] {e['name']} needs lower-case letters, digits, - or _ (got {g!r})")
        if c is not None and not COLOUR.fullmatch(str(c)):
            raise ValueError(f"the colour of [[export]] {e['name']} must look like #1A1A1A (got {c!r})")
        out.append(dict(name=e["name"], part=str(e.get("part", e["name"])), group=g, colour=str(c).upper() if c else None))
    return out

def groups(marker):
    """{group name: [pieces]} for the pieces that share a plate."""
    out = {}
    for p in pieces(marker):
        if p["group"]:
            out.setdefault(p["group"], []).append(p)
    return out

def export(folder, marker, command=None, timeout=300):
    """-> list of dict(name, ok, error, file). Each STL is written to a temporary name first and moved into place only when it is a real mesh."""
    folder = os.path.abspath(folder)
    model = marker.get("model")
    if not model or os.path.isabs(model) or ".." in model.split("/") or not os.path.exists(os.path.join(folder, model)):
        raise ValueError("the project's marker needs model = \"file.scad\" (a file inside the project) to export from")
    ps = pieces(marker)
    if not ps:
        raise ValueError("nothing to export: add an [[export]] table (name, part) to fit2print.toml for each printable piece")
    cmd = command or [shutil.which("openscad") or "openscad"]
    os.makedirs(os.path.join(folder, "stl"), exist_ok=True)
    drawn, res = {}, {}
    for p in ps:
        tmp = os.path.join(folder, "stl", p["name"] + ".part.stl")
        try:
            r = subprocess.run(cmd + ["-q", "--backend=manifold", "-D", f'part="{p["part"]}"', "-o", tmp, os.path.join(folder, model)], capture_output=True, text=True, timeout=timeout, cwd=folder)
            if r.returncode != 0 or not os.path.exists(tmp) or os.path.getsize(tmp) < 200:
                res[p["name"]] = dict(name=p["name"], ok=False, error=(r.stderr.strip().splitlines() or ["OpenSCAD made nothing (does the model draw something for part = \"%s\"?)" % p["part"]])[-1][:200], file=None)
            else:
                drawn[p["name"]] = trimesh.load(tmp)
        except FileNotFoundError:
            res[p["name"]] = dict(name=p["name"], ok=False, error="OpenSCAD is not installed on this machine", file=None)
        except subprocess.TimeoutExpired:
            res[p["name"]] = dict(name=p["name"], ok=False, error="drawing took too long", file=None)
        except Exception as e:
            res[p["name"]] = dict(name=p["name"], ok=False, error=f"could not read what OpenSCAD made ({type(e).__name__})", file=None)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
    lots = {}                                      # what is placed together: a whole group, or a piece alone
    for p in ps:
        lots.setdefault(("g", p["group"]) if p["group"] else ("p", p["name"]), []).append(p["name"])
    for names in lots.values():
        bad = [n for n in names if n not in drawn]
        if bad:
            for n in names:
                if n in drawn:
                    res[n] = dict(name=n, ok=False, error=f"not written: {', '.join(bad)} of the same group could not be drawn, and the group is placed as one", file=None)
            continue
        lo = np.min([drawn[n].bounds[0] for n in names], axis=0); hi = np.max([drawn[n].bounds[1] for n in names], axis=0)
        shift = [-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]]               # flat on the bed, centred (the group as one)
        for n in names:
            m = drawn[n]; m.apply_translation(shift)
            out = os.path.join(folder, "stl", n + ".stl"); m.export(out)
            a, b = m.bounds
            res[n] = dict(name=n, ok=True, error="", file=out, size=[round(float(x), 2) for x in (b - a)], volume=round(float(m.volume) / 1000, 3), watertight=bool(m.is_watertight))
    return [res[p["name"]] for p in ps]
