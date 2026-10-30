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
