"""Pictures of what the design should look like: each view in the project's marker ([[render]] tables) is drawn with OpenSCAD from the project's model
and saved in the project's renders/ folder. A view names the model's `part`, a camera `angle` [x, y, z rotation] and a title; the framing is automatic.

    [[render]]
    name = "pulled-apart"      # file name (letters, digits, - and _)
    title = "Pulled apart"
    part = "exploded"          # the model's `part` variable
    angle = [64, 0, 32]
Without any [[render]] tables the project gets one view: part = "assembly"."""
import os, re, shutil, subprocess

DEFAULT = [dict(name="assembled", title="Assembled", part="assembly", angle=[64, 0, 32])]
NAME = re.compile(r"[a-z0-9_-]{1,40}")

def views(marker):
    out = []
    for v in marker.get("render") or DEFAULT:
        if not NAME.fullmatch(str(v.get("name", ""))):
            raise ValueError(f"a render view needs a name of lower-case letters, digits, - or _ (got {v.get('name')!r})")
        a = v.get("angle", [64, 0, 32])
        if len(a) != 3 or not all(isinstance(x, (int, float)) for x in a):
            raise ValueError(f"view '{v['name']}': angle must be three numbers")
        out.append(dict(name=v["name"], title=v.get("title", v["name"]), part=str(v.get("part", "assembly")), angle=[float(x) for x in a]))
    return out

def renders_dir(folder):
    return os.path.join(folder, "renders")

def list_renders(folder, marker):
    """The pictures that exist: [(title, file name)] in the marker's order."""
    out = []
    try:
        vs = views(marker)
    except ValueError:
        return out
    for v in vs:
        if os.path.exists(os.path.join(renders_dir(folder), v["name"] + ".png")):
            out.append((v["title"], v["name"] + ".png"))
    return out

def render(folder, marker, command=None, size=(1100, 720), timeout=300):
    """Draw every view. -> list of dict(name, title, ok, error). Needs the marker's `model` (an OpenSCAD file inside the project)."""
    folder = os.path.abspath(folder)         # the drawing runs with the project as its working folder, so paths must not be relative
    model = marker.get("model")
    if not model or os.path.isabs(model) or ".." in model.split("/"):
        raise ValueError("the project's marker needs model = \"file.scad\" (a file inside the project) to be drawn")
    mp = os.path.join(folder, model)
    if not os.path.exists(mp):
        raise ValueError(f"model file not found: {model}")
    cmd = command or [shutil.which("openscad") or "openscad"]
    os.makedirs(renders_dir(folder), exist_ok=True)
    res = []
    for v in views(marker):
        out = os.path.join(renders_dir(folder), v["name"] + ".png")
        c = cmd + ["-q", "--backend=manifold", "-D", f'part="{v["part"]}"', "--autocenter", "--viewall", "--projection", "p",
                   "--camera=0,0,0," + ",".join(str(x) for x in v["angle"]) + ",100", f"--imgsize={size[0]},{size[1]}", "-o", out + ".part.png", mp]
        try:
            r = subprocess.run(c, capture_output=True, text=True, timeout=timeout, cwd=folder)
            ok = r.returncode == 0 and os.path.exists(out + ".part.png") and os.path.getsize(out + ".part.png") > 500
            if ok:
                os.replace(out + ".part.png", out)                       # only a finished picture replaces the old one
            res.append(dict(name=v["name"], title=v["title"], ok=ok, error="" if ok else (r.stderr.strip().splitlines() or ["OpenSCAD drew nothing"])[-1][:200]))
        except FileNotFoundError:
            res.append(dict(name=v["name"], title=v["title"], ok=False, error="OpenSCAD is not installed on this machine"))
        except subprocess.TimeoutExpired:
            res.append(dict(name=v["name"], title=v["title"], ok=False, error="drawing took too long"))
        finally:
            if os.path.exists(out + ".part.png"):
                os.remove(out + ".part.png")
    return res
