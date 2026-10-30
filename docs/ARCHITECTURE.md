# Architecture and extraction plan

## Shape
* **Python core** (numpy, scipy, trimesh), one module per check, each returning plain data (lists of findings) so any front end can use it.
* **CLI first** (`fit2print ...`), exit code 1 when a check fails, so it can gate a build.
* **Reports are static HTML + PNG**, as in Phonosphere. A web viewer comes later (see "Front end").
* **External tools through their command lines only** (OpenSCAD, Bambu Studio, PrusaSlicer): no bundling, which keeps GPL/AGPL out of this code.
* **Settings in files**, not code: printer, material, layer height, limits (the numbers in Phonosphere's `DESIGN_RULES.md` came from our own calibration card and must be per-printer).
* **A project describes itself** in a small file (parts, the build order, the screws): that is what the assembly and fixings checks read.

## What exists in Phonosphere (`cad/`) and where it goes

| Phonosphere tool | What it does | Fit2Print module | Work needed |
|---|---|---|---|
| (new today) layer slicer | slice a mesh, find plastic with nothing under it | `layers.py` | **done** |
| `anchor_check.py` | on real toolpaths: bridge span, cantilever depth, held on how many sides | `toolpath.py` | **done** (limits from `profiles/`; same numbers as the original on real plates) |
| `gcode_check.py` | read G-code into line segments; the air-line and flow checks | `gcode.py` (reader **done**), `air.py` (air line + flow: next) | port the air-line and flow checks |
| `asbuilt_check.py` | compare what the slicer will print with the design (missing/extra, any turn angle) | `asbuilt.py` | generic; needs the mesh and G-code only |
| `gate.py`, `selftest_checks.py` | the gate and the known-bad cases that must stay blocked | `gate.py`, `tests/` | split constants from logic |
| `make_plate.py` | STL to a verified print file (slicer CLI, painted supports, stale-file guard) | `plate.py` | slicer profiles into settings; refuse stale input |
| `plate_report.py`, `layer_viewer.py` | pictures of the layers | `report.py` | generic |
| `check_fixings.py` + `fixings_check.scad` | every bolt hole passes through plastic; a straight run for a driver | `fixings.py` | the cases come from the project file, not hard-coded |
| `check_assembly.py` + `assembly_check.scad` | the virtual build: sweeps in the real order, screw holes line up, thread bite | `assembly.py` | build order and screws from the project file |
| `check_fit.py` | every bought part against the cabinet; overlaps | `fit.py` | generic given a list of parts |
| `print_log.py`, `parts_register.py` | the print log (with photos) and the register of every part | `log.py`, `register.py` | file formats into the project file |
| `drop_to_bed.py` | put a part flat on the bed (had a float32 bug on big meshes) | `orient.py` | fix the rounding first |

## Gaps found by the Pi Zero sample (2026-10-30)
See `samples/pizero_case/FINDINGS.md`: the checks must read a project file (parts, build order, screws) instead of being hard-wired; `plate.py` is needed for any project; the dashboard needs a generic record format; model parameters should be exported, not scraped.

## Order of extraction
1. `layers.py` (done), then `gcode.py` + `toolpath.py` (the unsupported-plastic checks on real G-code).
2. `settings` (printer/material/limits in a file) so nothing is hard-coded.
3. `asbuilt.py`, `plate.py`.
4. The project file format, then `fixings.py` and `assembly.py` reading it.
5. `log.py` / `register.py`.
Each step ends with tests, including the negative controls, and a run against Phonosphere as the first customer.

## Front end (decide later)
* Today's useful front end is the report: static HTML plus PNG layer pictures.
* Next: a local web app (a small Python server and a three.js viewer) to rotate the model, step the assembly and click a finding.
* A desktop toolkit (Qt) is not worth it: harder to share, no advantage over the browser.
* An **assistant interface** (an MCP server exposing "run this check", "show me the layer") fits the original workflow: the AI drives the checks, the person looks at the pictures.

## Outside pieces we might replace later (only if they hurt)
| Piece | Used for | Verdict |
|---|---|---|
| OpenSCAD | geometry booleans, assembly sweeps | keep; or `manifold3d` in Python once it is installable everywhere |
| trimesh | meshes | keep |
| shapely/networkx/rtree | exact 2D shapes, graph code, ray casts | optional; `layers.py` already avoids them |
| Bambu Studio / PrusaSlicer | real toolpaths | keep; command line only |
| our own: layer slicer, overhang, screw-bite | small and ours | keep |
