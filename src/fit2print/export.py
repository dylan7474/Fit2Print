"""Make the printable files: each [[export]] table in the project marker names one printable piece of the model, and this writes it as stl/NAME.stl, lying flat
on the bed (lowest point at z = 0, centred on the origin in x and y), ready for the checks and the slicer.

    [[export]]
    name = "body"          # the piece (and the file stl/body.stl): letters, digits, - and _
    part = "body"          # the model's `part` value that draws just that piece
Drawn with OpenSCAD like the pictures (same command setting); the model file must be inside the project."""
import os, re, shutil, subprocess
import trimesh

NAME = re.compile(r"[a-z0-9_-]{1,40}")

def pieces(marker):
    out = []
    for e in marker.get("export") or []:
        if not NAME.fullmatch(str(e.get("name", ""))):
            raise ValueError(f"an [[export]] needs a name of lower-case letters, digits, - or _ (got {e.get('name')!r})")
        out.append(dict(name=e["name"], part=str(e.get("part", e["name"]))))
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
    res = []
    for p in ps:
        out = os.path.join(folder, "stl", p["name"] + ".stl"); tmp = out + ".part.stl"
        try:
            r = subprocess.run(cmd + ["-q", "--backend=manifold", "-D", f'part="{p["part"]}"', "-o", tmp, os.path.join(folder, model)], capture_output=True, text=True, timeout=timeout, cwd=folder)
            if r.returncode != 0 or not os.path.exists(tmp) or os.path.getsize(tmp) < 200:
                res.append(dict(name=p["name"], ok=False, error=(r.stderr.strip().splitlines() or ["OpenSCAD made nothing (does the model draw something for part = \"%s\"?)" % p["part"]])[-1][:200], file=None)); continue
            m = trimesh.load(tmp)
            lo, hi = m.bounds
            m.apply_translation([-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]])       # flat on the bed, centred
            m.export(out)
            res.append(dict(name=p["name"], ok=True, error="", file=out, size=[round(float(x), 2) for x in (hi - lo)], volume=round(float(m.volume) / 1000, 3), watertight=bool(m.is_watertight)))
        except FileNotFoundError:
            res.append(dict(name=p["name"], ok=False, error="OpenSCAD is not installed on this machine", file=None))
        except subprocess.TimeoutExpired:
            res.append(dict(name=p["name"], ok=False, error="drawing took too long", file=None))
        except Exception as e:
            res.append(dict(name=p["name"], ok=False, error=f"could not read what OpenSCAD made ({type(e).__name__})", file=None))
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
    return res
