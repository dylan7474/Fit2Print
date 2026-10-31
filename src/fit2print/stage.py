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
    "concept": "CONCEPT: the brief is approved. Make a first concept: write a simple parametric OpenSCAD model in model.scad (every dimension a named parameter taken from the brief; mark guesses UNVERIFIED), add [[render]] views to fit2print.toml (and model = \"model.scad\"), then run exactly `{f2p} render .` (alone, no pipes), look at the picture(s) it makes in renders/, then describe in plain words what they show and ask what to change. One picture at a time. Do not run the checks or slice yet.",
    "model": "MODEL: the concept is approved. Refine model.scad into the real model: real dimensions from the component library, openings, fixings, the parts split into printable pieces. Keep the render views up to date. Do not slice yet.",
    "checks": "CHECKS: run the virtual checks (fit, printability, assembly) with the Fit2Print commands, show every finding in plain words, fix the model and run them again. Never say a check passed unless a command in this session said so.",
    "plate": "PLATE: slice each part with the Fit2Print plate command, report the verdicts, show what a CHECK or BLOCK means, and wait for the person to say the plates look right.",
    "print": "PRINT: give the person ONE file at a time and say what to look for in the photo. Log each result with them.",
    "verify": "VERIFY: compare each photo with what the checks said and record the outcome honestly.",
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
        return h[-1]["to"]
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
