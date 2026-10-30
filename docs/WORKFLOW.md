# The workflow, and how it is shown to a person

## 1. The process we actually followed (Phonosphere), as a model
Every part moves through the same stages. A stage has inputs, outputs (pictures included), a status, and an owner (person, AI, tool).

| # | Stage | Output | Owner | Gate |
|---|---|---|---|---|
| 1 | **Intent**: what the thing is for, constraints (size, printer, parts in hand) | a short brief | person | none |
| 2 | **Design**: the parametric model and the project file (parts, build order, screws) | model + diff | AI proposes, person approves | person approves the picture |
| 3 | **Virtual checks**: fit, fixings reach, assembly order, overhangs, as-built | findings + pictures | tools | BLOCK stops; CHECK needs a person; nothing is waived silently |
| 4 | **Plate**: slice, paint supports, check the toolpaths | a verified print file | tool | same |
| 5 | **Look**: the person looks at the pictures of the plate | a decision | person | person says print |
| 6 | **Print** (with live status and camera) | photos, time, filament | person + printer | alerts on failure |
| 7 | **Verify**: the photo of the result against what the checks said | a logged outcome | person + AI | outcome recorded |
| 8 | **Fit and assemble**: the real part into the real thing | fit notes | person | notes recorded |
| 9 | **Learn**: a failure becomes a new check with a negative control | a rule + a test | AI drafts, person approves | the control must fail first |

A part's **state** is a line through those stages: *designed, checked, plated, reviewed, printing, printed, verified, installed*. The state
is never typed in: it is derived from an append-only **event log** (what happened, when, what the checks said, which photo). Phonosphere
already keeps this as `PRINT_LOG.jsonl`, `PLATE_RESULTS.jsonl` and the parts register; Fit2Print makes it the source of truth.

## 2. What the person sees (the GUI)
Principles, learned the hard way in this project:
* **One picture at a time.** Never a wall of numbers. A finding is a picture with a sentence under it.
* **Plain words.** "A shelf of plastic starts in mid-air here", not "cantilever depth 4.2 mm".
* **Say what is needed from you.** A permanent "needs you" list: checks to decide, photos to send, prints to start.
* **A BLOCK cannot be waived.** A CHECK is shown and decided by the person, and the decision is logged with the reason.
* **Show what changed.** After any edit: before/after pictures and the checks that moved.

Screens:
1. **Board**: the parts register as a board, columns = stages, a card per part with its status chip and thumbnail. The default view.
2. **Part**: the model in 3D (rotate, section), findings drawn on it, the layer viewer (step through the layers, air in colour), the print history with photos.
3. **Assembly**: the build order as steps you can play and scrub; the swept path of each moved part; the screws and their driver runs.
4. **Printer**: live state (progress, layer, time left, temperatures) and the camera, a button to grab a frame at layer N, and the alerts.
5. **Log**: the timeline: every print with its photo and verdict, every decision, every lesson.
6. **Assistant**: a conversation panel (see section 3) beside whatever is on screen.

## 3. AI in the design process
The AI is a colleague with strict hands:
* **It proposes; it never passes.** It edits the model through a *change*: a diff to the parametric model plus before/after pictures. The person approves the change. Only tools can mark a check as passed.
* **Every change runs the full gate** (all checks, with their negative controls) before the person is even asked.
* **It must say what it checked and what it did not.** The checks produce a "not covered" list (for Phonosphere: the meter, Pi and amp removal, the plinth), shown with the verdict.
* **It reads the project's memory** (the log, the rules, the lessons) at the start of each session, and writes to it at the end.
* **Providers are pluggable.** The assistant speaks to the tools through one interface (an MCP server: run-check, show-layer, propose-change, log-event), so Claude or another model, or a local one, can drive the same workflow. The log records which model proposed what.
* **It drafts new checks from failures** (stage 9): "this failed, here is a check that would have caught it, and a negative control that must fail", for the person to approve.

## 4. Architecture for that
* **Core library** (Python): the checks, the settings, the project/event-log model. No GUI code in it.
* **Local server** (Python, FastAPI): serves the log, runs checks as jobs, streams printer state (Home Assistant or the printer's own protocol), exposes the assistant tools.
* **Browser front end**: three.js for the 3D and the layer viewer, plain components for the board. Runs locally; nothing leaves the machine unless asked.
* **A project is a folder**: `fit2print.toml` (parts, build order, screws, printer profile), the model sources, an `events.jsonl`, and `artefacts/` (pictures, plates, photos).
* **Packaging later** (a desktop shell such as Tauri, or a container with OpenSCAD and the slicer inside) once the browser version is useful.

## 4b. The front door (decided 2026-10-30)
A local web app opened in the browser, working on a phone (photos are uploaded where the printer is). Screens drawn so far are in `docs/mockups/`. Entry is a screen, not a terminal; the assistant is a panel on it. How the page talks to Claude is still open (Claude Code run headlessly in the project folder, or the API with a key): decide once the screens work, and verify the behaviour in a container first.

## 5. Phases
1. **Now**: CLI + reports. Extract the checks; settings in files.
2. **Dashboard**: a static site generated from the event log: the board, parts, print timeline with photos. Useful on its own, no server.
3. **Server + viewer**: live printer tile, layer viewer, assembly player, run checks from the page.
4. **Assistant panel**: the change/diff/approve loop, lessons drafting, pluggable models.
5. **Second project**: prove it is not just for one radio.

## 6. Open questions
* The **project file** format: how much of the model's parts, build order and screws can be *derived* from an OpenSCAD model, and how much must be declared?
* **Other CAD front ends** (Fusion, FreeCAD, Blender): worth supporting, or OpenSCAD/mesh only at first?
* **Privacy**: models and photos stay local by default; which assistant calls send what, and a log of it.
* **Calibration**: a guided calibration (the card print) per printer/material, producing the profile file.
