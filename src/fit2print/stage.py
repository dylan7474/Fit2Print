"""Where a project is in the workflow, and the gate between stages. Only the PERSON moves a project forward (a button on the page); the assistant is told
which stage it is in and does the work of that stage only. Stage changes are an append-only log (records/stages.jsonl), so the history is never lost.

A project moves to the NEXT stage or back ONE stage; it never skips. A project with no stage log starts in Scope, unless it already has print records (an
established project such as the radio), in which case it starts in Print."""
import datetime, json, os

STAGES = [("scope", "Scope"), ("concept", "Concept"), ("model", "Model"), ("checks", "Checks"), ("plate", "Plate"), ("print", "Print"), ("verify", "Verify"), ("assemble", "Assemble")]
KEYS = [k for k, _ in STAGES]
LABEL = dict(STAGES)

GATE = {   # the button that leaves each stage, and what it means
    "scope": "The brief is complete: start the design",
    "concept": "I like this concept: build the model",
    "model": "The model is right: run the checks",
    "checks": "The checks are clear: prepare the print files",
    "plate": "The plates look right: ready to print",
    "print": "It is printed: check how it came out",
    "verify": "It came out well: on to assembly",
}

WORK = {   # what the assistant does in each stage (given to it as part of its instructions)
    "scope": "SCOPE: only collect information. Ask a little at a time, write brief.md and NEXT.md. Do NOT design or draw anything yet. When you believe the brief is complete, say so plainly and tell the person to press the button 'The brief is complete: start the design'; do not move on by yourself.",
    "concept": "CONCEPT: the brief is approved. Make a first concept: write a simple parametric OpenSCAD model in model.scad (every dimension a named parameter taken from the brief; mark guesses UNVERIFIED). model.scad MUST start with `part = \"assembly\";` and draw everything when part is \"assembly\", draw it pulled apart when part is \"exploded\", and draw each printable piece alone when part is that piece's name. Draw pictures with the render command only, never by hand-writing SVG or image files, add [[render]] views to fit2print.toml (and model = \"model.scad\"); each view has name, title, part and where to look from, either view = \"front\", \"back\", \"left\", \"right\", \"top\", \"bottom\" or \"iso\", or angle = [x, y, z], and no other fields; give every picture a different view; if the render command warns that two pictures are the same, fix that before you describe them, then run exactly `{f2p} render .` (alone, no pipes), look at the picture(s) it makes in renders/, then describe in plain words what they show and ask what to change. One picture at a time. Do not run the checks or slice yet.",
    "model": "MODEL: the concept is approved. Refine model.scad into the real model: real dimensions from the component library, openings, fixings, the parts split into printable pieces. Declare every printable piece as an [[export]] table (name, part) in fit2print.toml, then run exactly `{f2p} export .` (alone): it writes stl/NAME.stl for each piece. Pieces that print TOGETHER in different colours (a body and its inlay) get the same group = \"NAME\" and a colour = \"#RRGGBB\" each; a group is placed as one so the pieces stay in register. List every component from the library that the design uses in fit2print.toml as components = [\"pi-zero-2-w\", ...] (ids from `{f2p} hardware list`; if a part is not in the library, say so and ask the person to measure it: never use numbers from memory). Then `include <hardware.scad>` near the top of model.scad (the render command writes that file from the library and the person's measurements) and draw every library part with its shape module, named after its id with _ for - (for example esp32_devkitc_v4_shape();), moved into place with translate and rotate: never as a plain box with guessed sizes. Build the case round those real shapes, taking clearances, openings and mounts from their sizes. Keep the render views up to date, and declare each piece of the model for the 3D view as a [[model3d]] table in fit2print.toml (name, label in plain words, part = the model's `part` value that draws just that piece IN PLACE as it sits in the finished thing, colour = \"#RRGGBB\"; scene = \"exploded\" for a pulled-apart drawing): `render .` draws these too, and the page then shows the model in 3D that the person can turn and zoom. A piece bigger than the printer bed (the A1 is 256 mm) is NOT shrunk: declare a [[split]] table (name, part = the [[export]] name; optionally scale, max_pieces, joint = \"auto\") in fit2print.toml and run exactly `{f2p} split .` (alone): it cuts the piece into sections that fit, with loose pins (or interlocking teeth where the walls are too thin for pins) and writes sections/NAME_sNN.stl and NAME_split.json. A piece that must print the other way up gets orient = \"flip_x\" or \"flip_y\" in its [[export]]. Describe each part once in parts.toml ([[part]]: name, section, what, qty, colour, fixings) so the register can list it. When parts go together (a face onto a shell, a lid, screws), write checks.toml with [[sweep]] (move, fixed, direction, travel) and [[screw]] (clear, thread, dir, clear_len, thread_len, at) cases; if the model's part values are laid out for printing instead of in place, define the in-place pieces in checks.toml under [parts] as OpenSCAD snippets. Do not run the checks or slice yet.",
    "checks": "CHECKS: run `{f2p} export .` first if the stl/ files are missing or older than model.scad, then run the printability check on each piece, one command each, exactly `{f2p} overhang stl/NAME.stl` (alone, no pipes), show every finding in plain words (an inlay piece of a group can be blocked alone because it floats; say so, do not hide it, and say the group is judged as a whole in the plate stage), fix the model and run them again. Then, if the project has checks.toml, run exactly `{f2p} assembly-check .` (alone): every sweep and screw case must be ok and its controls must fire ('CHECKER CANNOT SEE ITS CONTROLS' is a failure of the check: say so, do not call it a pass). Run exactly `{f2p} selftest .` once per session before trusting a green result (it must say 0 failed), and exactly `{f2p} register .` to list every part and what is stale, unregistered or never checked. Report every line that is not ok. Never say a check passed unless a command in this session said so.",
    "plate": "PLATE: slice each piece that is NOT in a group with exactly `{f2p} plate stl/NAME.stl --project . --out plates` and each group with exactly `{f2p} plate --group NAME --project . --out plates` (one command each, alone; a group prints in several colours as one plate on the A1 with the AMS), report the verdicts, show what a CHECK or BLOCK means, and tell the person the files can be downloaded from the Downloads card on this project's page (each print file as a 3MF, or one zip of them all), then wait for the person to say the plates look right. A split part: run exactly `{f2p} plate --split sections/NAME_split.json --project . --out plates` (every section and the pin plate). Several small parts on one plate: exactly `{f2p} plate stl/A.stl stl/B.stl --together --name NAME --project . --out plates`. Add --report to any plate command to get the one-page report with a picture of every spot the checks flagged, and show the person each CHECK and BLOCK from it. For anything risky and expensive offer a coupon first: exactly `{f2p} coupon stl/NAME.stl --out coupons --box NAME X0 X1 Y0 Y1` (a small piece cut from the real STL). For a new printer or filament offer exactly `{f2p} calibrate card --out calibration` (the person prints and measures it; `{f2p} calibrate record` then writes the profile). When every plate is done run exactly `{f2p} gate .` (alone): it is the ONE verdict for the whole project and a CHECK in it is never a pass.",
    "print": "PRINT: give the person ONE file at a time and say what to look for in the photo. Log each result with them (with the photo), then run exactly `{f2p} register .` so PARTS_REGISTER.md shows what has really been printed.",
    "verify": "VERIFY: compare each photo with what the checks said and record the outcome honestly, then run exactly `{f2p} register .` to refresh the register.",
    "assemble": "ASSEMBLE: write the assembly guide (assembly.toml) with the person: the build order, parts, hands, fixings and a picture for each step.",
}

START = {  # the first message sent to the assistant when a stage begins
    "concept": "The brief is approved. Start the concept stage now: write model.scad and draw the first concept pictures, then tell me what you see and ask what to change.",
    "model": "The concept is approved. Start the model stage now.",
    "checks": "The model is right. Start the checks now.",
    "plate": "The checks are clear. Start preparing the print files now.",
    "print": "The plates look right. Tell me which file to print first.",
    "verify": "It is printed. Let us check how it came out.",
    "assemble": "It came out well. Start the assembly guide with me now.",
}

def _path(folder):
    return os.path.join(folder, "records", "stages.jsonl")

def history(folder):
    p = _path(folder)
    if not os.path.exists(p):
        return []
    with open(p) as f:
        return [json.loads(l) for l in f if l.strip()]

def current(folder):
    h = history(folder)
    if h:
        return max(enumerate(h), key=lambda t: (t[1].get("at", ""), t[0]))[1]["to"]          # the newest by time (logs merged from two machines can interleave)
    for rel in (os.path.join("records", "prints.jsonl"), "PRINT_LOG.jsonl"):       # an established project that predates stages
        q = os.path.join(folder, rel)
        if os.path.exists(q) and os.path.getsize(q) > 0:
            return "print"
    return "scope"

def move(folder, to, by="person"):
    """Move to the next stage or back one. -> the event. Raises ValueError for anything else (no skipping)."""
    cur = current(folder)
    if to not in KEYS:
        raise ValueError(f"no such stage: {to}")
    i, j = KEYS.index(cur), KEYS.index(to)
    if j not in (i + 1, i - 1):
        raise ValueError(f"a project moves to the next stage or back one, not from {LABEL[cur]} to {LABEL[to]}")
    ev = dict(at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), **{"from": cur}, to=to, by=by)
    os.makedirs(os.path.dirname(_path(folder)), exist_ok=True)
    with open(_path(folder), "a") as f:
        f.write(json.dumps(ev) + "\n")
    return ev

def set_stage(folder, to, by="person"):
    """Set any stage directly (for an established project that is already past scope). Logged."""
    if to not in KEYS:
        raise ValueError(f"no such stage: {to}")
    ev = dict(at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), **{"from": current(folder)}, to=to, by=by, note="set directly")
    os.makedirs(os.path.dirname(_path(folder)), exist_ok=True)
    with open(_path(folder), "a") as f:
        f.write(json.dumps(ev) + "\n")
    return ev
