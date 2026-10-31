# Fit2Print

Virtual checks that catch 3D-printing and assembly problems **before anything is printed**.

Born from the Phonosphere cathedral radio (a large multi-part 3D-printed cabinet): most of the expensive failures there were not print
failures, they were design failures found only after hours of printing: a screw nobody could reach, a part that could not be put in
in the order it had to go, a flat shelf hanging in mid-air, a stale file printed by mistake. Every one became a permanent check.

## Status: 0.1.0, extraction in progress
Working now:
* `fit2print doctor` reads the dependency picklist (`deps.toml`) and says which checks can run on this machine.
* `fit2print toolpath plate.3mf` judges a sliced file on the real toolpaths (bridge span, cantilever, how each is held), with limits read from a printer profile (`profiles/`). It reproduces Phonosphere's `anchor_check.py` exactly on real plates.
* `fit2print plate part.stl --out DIR [--project DIR]` slices an STL with Bambu Studio (profiles in `profiles/bambu_a1/`), judges the real toolpaths, refuses a stale STL and records the result (parts that print without supports).
* `fit2print overhang part.stl` finds layers where plastic starts with nothing under it (a small self-contained layer slicer,
  `layers.py`; it needs only numpy, scipy and trimesh). On the Phonosphere lug coupon it flags the two layers that printed ragged and
  none on the fixed version.

The plan for how the whole workflow (and an AI design assistant) is shown to a person is in [docs/WORKFLOW.md](docs/WORKFLOW.md).

Everything else is still in the Phonosphere repo (`cad/`) and is listed, with its plan, in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Principles
1. **Every check has a negative control**: a known-bad case it must flag, or the checker reports itself broken (`tests/`).
2. **A missing tool switches a check off loudly**, never silently (`doctor`).
3. **Every real failure becomes a check** ([docs/LESSONS.md](docs/LESSONS.md)).
4. **Look at it as well as measuring it**: checks produce pictures, not only numbers.
5. Never waive a failed check; show it.

## Start a project, and the playbook
`fit2print init FOLDER --name "My thing"` makes a project from the template: marker, brief, `NEXT.md` (where it stands) and the AI's rules. [docs/PLAYBOOK.md](docs/PLAYBOOK.md) is the repeatable model: how a session starts and ends, the nine stages and who does what, the standing rules, what the AI may and may not do, and how Claude is wired in (with the concerns and what is done about each).

## Components and renders
* **Component library** (`hardware/`, `fit2print hardware list|show|verify|openscad`, and the Components page): real dimensions with where each came from (official drawing, derived, third-party, estimate, notes) and whether *you* have measured them. Your measurements live in `~/.config/fit2print/hardware/` and override the published figures; a project lists the components it holds (`hardware = [...]` in its marker) and "what I need from you" asks you to measure the fit-critical ones. A number with no source is refused.
* **Layer preview** (a plate's link on the project page): step or play through a sliced plate layer by layer, exactly as the printer will lay it down, coloured by what each line is (outer wall, infill, bridge, supports...). Plastic with little or nothing under it is marked on the layer where it starts (orange = a bridge held at both ends, red = hanging), from the same check that gives the verdict. Under it, **the part in 3D** (a small WebGL viewer with no outside library): drag to turn, scroll or pinch to zoom, and it is cut at the layer you are looking at so you can watch the print build up, with the hanging-plastic spots shown as dots. Open at a layer with `?l=44`; arrow keys step.
* **Assembly guide** (`assembly.toml` in a project; the page's "Open the guide"): the build order step by step with a picture, the parts and fixings each step needs, **which hand each part is** (LEFT/RIGHT, with its other half named), whether you have printed it, and a warning if the print came from an older design than the part's current one. Fixings are added up across the steps.
* **Stages and the gate** (the strip at the top of a project page): Scope, Concept, Model, Checks, Plate, Print, Verify, Assemble. A project sits in a stage until the PERSON presses the button that leaves it (for example "The brief is complete: start the design"); it only moves to the next stage or back one, never skips, and every move is logged. The assistant is told which stage it is in and does only that stage's work: in Scope it only asks questions and writes the brief; after the gate it writes a first model and draws the first pictures.
* **Export** (`fit2print export PROJECT`): each `[[export]]` table in the marker (name, part) is written as `stl/NAME.stl`, flat on the bed and centred, from the project's model; the checks and the slicer start from these.
* **Archive** (the "Housekeeping" box at the bottom of a project page; "Restore" on Home): hides a project from Home without deleting anything. It is an append-only log that syncs between machines. There is deliberately no delete yet.
* **Renders** (`fit2print render PROJECT`, and "What it should look like" on the project page): pictures of each part as it will sit on the bed, assembled and pulled apart, drawn from the project's own model. The views are the marker's `[[render]]` tables.

## On a server, and from a phone
See [docs/DEPLOY.md](docs/DEPLOY.md): the container on phobos (bound to localhost only), `fit2print sync` to keep it in step with the laptop's master copy, and the steps for a Cloudflare Zero Trust tunnel + Access policy.

## Run it in a container
See [docs/DOCKER.md](docs/DOCKER.md): a 2.6 GB image with pinned OpenSCAD and Bambu Studio; tested on a home server with identical results to the laptop.

## Try it
    pip install -e .          # numpy, scipy, trimesh, pillow
    fit2print doctor
    fit2print overhang some_part.stl        # the part standing as it will print, z up
    python -m unittest discover -s tests

Private for now. Licence to be chosen before anything is shared.

## The dashboard
    fit2print dashboard ~/src/dylan7474/Phonosphere/cad --out dashboard.html
One self-contained page: what needs you, a board of every part by state (not checked / ready / look first / on the printer / printed / failed), and the real print log with your photos. States are worked out from the records, never typed in.

## The front door
    fit2print serve                      # http://localhost:8750 , the projects listed in ~/.config/fit2print/config.toml
    fit2print serve --host 0.0.0.0       # on the network (a phone on your wifi): needs a token, made for you if you give none
Home (your projects, with what needs you), a project's dashboard, **Log a print** (a few words, a result, a photo) and **New project**. Standard library only. The **printer panel** shows the printer's live status and camera and links the running job to its project: it reads `~/.config/fit2print/printer.toml` (`[printer]` host, serial, access_code; keep it readable by you only). It is read-only: it listens to the printer's own report and asks it to repeat its status; it never sends a command that moves, heats or stops anything. The assistant panel is not connected yet. See [docs/mockups](docs/mockups/).
