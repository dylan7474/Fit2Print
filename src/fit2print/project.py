"""Starting a project: `fit2print init FOLDER --name "Pi Zero case"` makes the folder, its marker, the brief, NEXT.md and the AI's rules,
from templates/project. Never writes into a folder that already has files in it."""
import os, re, shutil
from .settings import ROOT

def slug(name):
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not s:
        raise SystemExit("the project needs a name with letters or digits in it")
    return s

def init(folder, name, kind="design-and-print", printer_profile="bambu_a1_pla", templates=None):
    folder = os.path.abspath(os.path.expanduser(folder))
    if os.path.exists(folder) and os.listdir(folder):
        raise SystemExit(f"{folder} already has files in it: refusing to write into it (a project is never mixed with other files)")
    tdir = templates or os.path.join(ROOT, "templates", "project")
    if not os.path.isdir(tdir):
        raise SystemExit(f"templates not found at {tdir}")
    pid = slug(name)
    os.makedirs(os.path.join(folder, "records"), exist_ok=True)
    def write(rel, text):
        with open(os.path.join(folder, rel), "w") as fh:
            fh.write(text)
    for f in ("CLAUDE.md", "NEXT.md", "brief.md", "PLAYBOOK.md"):
        with open(os.path.join(tdir, f)) as fh:
            write(f, fh.read().replace("{name}", name).replace("{printer_profile}", printer_profile))
    write("fit2print.toml",
        f'# Project marker (see Fit2Print docs/PROJECTS.md): every Fit2Print command reads this first.\n'
        f'id = "{pid}"\nname = "{name}"\nkind = "{kind}"\nadapter = "generic"\nprinter_profile = "{printer_profile}"\n'
        f'deliverables = "~/Downloads/{pid}"\n# model = "model.scad"     # an STL older than this file is refused as stale\n')
    write(".gitignore", "stl/\n*.3mf\n*.gcode\n__pycache__/\nrenders/\n.fit2print-sync.json\n")
    write(os.path.join("records", ".gitkeep"), "")
    return pid, folder
