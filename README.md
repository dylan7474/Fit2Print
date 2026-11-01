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
* `fit2print split part.stl --out DIR [--scale S] [--bed X Y Z] [--cut x=173.5]` (or `fit2print split PROJECT` for every `[[split]]` table in a project) cuts a part of ANY size into sections that fit the bed: it plans the fewest pieces, moves each cut away from windows and bosses, drills pin holes where the walls are thick enough, lays each section on its largest flat face, and checks that the sections plus the pin holes equal the part. `--scale 0.4` shrinks the whole thing first, for a small test print. See `samples/arch_clock`.
* `fit2print coupon part.stl --out DIR --box NAME X0 X1 Y0 Y1 [--box ...] [--zmax Z]` cuts small test pieces out of a part's real STL (printed coordinates kept, a record of where each came from, refused with a message when the box is empty or beside the part). Several coupons go on one plate to try the doubtful spots of a part before a long print.
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
See [docs/DEPLOY.md](docs/DEPLOY.md): the container on phobos (bound to localhost only), `fit2print sync` to keep it in step with the laptop's master copy, and how to reach it (it is a plain website: put whatever tunnel or login you like in front).

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
    fit2print serve --host 0.0.0.0       # on the network (a phone on your wifi): a plain website, no login; control who can reach it yourself
Home (your projects, with what needs you), a project's dashboard, **Log a print** (a few words, a result, a photo) and **New project**. Standard library only. The **printer panel** shows the printer's live status and camera and links the running job to its project: it reads `~/.config/fit2print/printer.toml` (`[printer]` host, serial, access_code; keep it readable by you only). It is read-only: it listens to the printer's own report and asks it to repeat its status; it never sends a command that moves, heats or stops anything. The assistant panel is not connected yet. See [docs/mockups](docs/mockups/).

- `fit2print plate --split NAME_split.json --out DIR` slices every section and the pin plate from a split, judges each, and fails if any is blocked. It refuses a failed, incomplete or stale split.
- `fit2print split ... --joint auto|pins|keys` (or `joint = ` in a `[[split]]` table): `auto` uses pins and falls back to interlocking 45 degree teeth on seams whose walls are too thin for pins.
- `fit2print plate STL` paints support enforcers under shelves (ledges, rebates) and re-slices, then BLOCKs if any support plastic sits inside a small hole (`--supports none` for the old behaviour). Checked on Phonosphere's hybrid coupon: same shelves painted, same PASS as make_plate.py.
- `fit2print plate` also lays the sliced nozzle path over the model layer by layer (as-built): support plastic inside a hole BLOCKs; a stretch of outer wall not printed, or plastic where the model has none, is a CHECK.
- `fit2print plate A.stl B.stl ... --together --name NAME` puts several parts on one plate; each is painted and compared with its design on its own, matched by file name. `orient = "flip_x"` (or `flip_y`) in an `[[export]]` table writes a piece turned over, for parts that print the other way up.
- `fit2print assembly-check PROJECT` runs checks.toml: [[sweep]] slides parts into place and measures overlap along the way, [[screw]] pushes a rod for each screw (must pass the clear part untouched and bite the thread part). Controls run on every case and must fire, or the checker is reported blind. Result in records/assembly_check.json.

- checks.toml also takes `[[probe]]` (a combination that must be empty, or `must_overlap` as a control), `[[driver]]` (a straight rod for a driver must meet no plastic) and `[[ring]]` (the plastic round a hole must be mostly solid), each with controls that must fire.
- `fit2print selftest PROJECT [--all] [--strict]` runs the checks on plates whose outcome is known (selftest.toml) and fails if they disagree; `assembly-check` and `selftest` append to records/checks.jsonl.
- The project page has a read-only Checks card: the last run of assembly-check and selftest (marked STALE when the model changed since), and each split's summary, joints and warnings.
- `fit2print report PLATE.3mf [STL ...]` (or `plate --report`) writes a one-page plain-English report beside the plate, with a picture of the real layer at every spot the checks flagged. A CHECK is never waived: it is listed with its picture.
