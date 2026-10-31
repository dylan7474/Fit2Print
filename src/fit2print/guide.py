"""The assembly guide: the build order of a project, step by step, with pictures, the parts and fixings each step needs, which hand each part is, and
whether you have actually printed it (and from the CURRENT design).

A project describes its guide in assembly.toml:
    convention = "Left and right are as you look at the FRONT of the radio."
    [[step]]
    title = "..."            text = "..."            tip = "..."
    parts  = ["pod_L", "pod_R"]                     # printed parts (names as in the project)
    bought = ["Visaton FR 10 speaker"]              # things you buy
    fixings = [{what = "M3 x 16 bolt + nut", qty = 4, note = "..."}]
    picture = "pulled-apart"                        # a render view of the project, or an image file inside the project folder
Hand (LEFT/RIGHT) comes from a part name ending _L or _R. A part that is printed but whose design has changed since (the print log recorded the design it was
printed from) is flagged 'printed from an older design'."""
import os, re
from . import dashboard
try:
    import tomllib
except ModuleNotFoundError:
    tomllib = None

HAND = re.compile(r"_(L|R)$")
IMG = re.compile(r"[A-Za-z0-9_.-]{1,80}\.(png|jpg|jpeg)$")

def load(folder):
    p = os.path.join(folder, "assembly.toml")
    if not os.path.exists(p) or tomllib is None:
        return None
    with open(p, "rb") as f:
        d = tomllib.load(f)
    steps = d.get("step", [])
    for i, s in enumerate(steps):
        if not s.get("title"):
            raise ValueError(f"assembly.toml: step {i + 1} needs a title")
    return dict(convention=d.get("convention", "Left and right are as you look at the FRONT of the finished thing."), title=d.get("title", "Assembly guide"),
                note=d.get("note", ""), steps=steps)

def hand(name):
    m = HAND.search(name)
    return {"L": "LEFT", "R": "RIGHT"}.get(m.group(1)) if m else None

def partner(name):
    m = HAND.search(name)
    return name[:m.start()] + ("_R" if m.group(1) == "L" else "_L") if m else None

def picture_url(pid, folder, pic):
    """The URL for a step's picture, or None. A render view name -> its render; a file name inside the project folder -> served by the guide's own image route."""
    if not pic:
        return None
    if re.fullmatch(r"[a-z0-9_-]{1,40}", pic) and os.path.exists(os.path.join(folder, "renders", pic + ".png")):
        return f"/p/{pid}/renders/{pic}.png"
    if IMG.fullmatch(pic) and os.path.isfile(os.path.join(folder, pic)):
        return f"/p/{pid}/guide/img/{pic}"
    return None

def part_status(name, data):
    """('printed' | 'ready' | 'look' | 'onprinter' | 'bad' | 'reprint' | 'none', note) for a printed part, using the project's own records."""
    known = [p for p in data["parts"] if p["name"] == name]
    if not known:
        return "none", "not in this project's parts list"
    st, lp, lr, hist = dashboard.part_state(known[0], data["runs"], data["prints"])
    note = ""
    if st == "printed" and lp and lp.get("design") and lr and lr.get("stl_sha") and lp["design"] != lr["stl_sha"]:
        note = "printed from an older design: the part has changed since"
    return st, note

LABEL = dict(printed="printed", ready="not printed yet", look="not printed yet (a check wants a look)", onprinter="printing now", bad="needs a fix", reprint="printed, but needs a reprint", none="not checked yet")
COLOUR = dict(printed="green", ready="blue", look="amber", onprinter="violet", bad="red", reprint="orange", none="grey")
