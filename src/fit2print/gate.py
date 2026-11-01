"""One command for "is the whole project fit to print?": `fit2print gate PROJECT`. Extracted from the idea of Phonosphere's gate.py (every part through every check, one verdict).

Steps, in order, each one a command that already exists on its own:
  1. export     draw every [[export]] piece to its STL (--no-export: only check the STLs are there and not older than the model)
  2. plates     slice and judge every piece (or group) with `plate`; a part whose STL has NOT changed since a plate record made by this tool is REUSED, and said so
  3. assembly   `assembly-check` from checks.toml (if the project has one)
  4. selftest   `selftest` from selftest.toml (if the project has one): is the checker still telling the truth?
  5. register   `register` from parts.toml (if the project has one): unregistered, not exported, stale
The verdict is the worst of everything: BLOCK > CHECK > PASS. A CHECK is never turned into a pass: it is listed with its report page and left for a person to decide.
A step that crashes is a BLOCK ("could not run"), never a skip. Results: GATE.md in the project, records/gate.json, a line in records/checks.jsonl."""
import datetime, json, os
from . import assemblycheck, export as export_mod, plate, records, register, report, selftest
from .settings import Settings

ORDER = {"PASS": 0, "CHECK": 1, "BLOCK": 2}


def worst(vs):
    return max(vs, key=lambda v: ORDER[v]) if vs else "PASS"


def _row(step, name, verdict, text, **extra):
    return dict(step=step, name=name, verdict=verdict, text=text, **extra)


def step_export(folder, marker, do_export, only):
    rows = []
    try:
        pieces = [p for p in export_mod.pieces(marker) if not only or p["name"] in only]
    except ValueError as e:
        return [_row("export", "(pieces)", "BLOCK", f"the [[export]] tables are wrong: {e}")]
    if not pieces:
        return [_row("export", "(pieces)", "BLOCK", "nothing to check: no [[export]] piece" + (" matches --parts" if only else ""))]
    sd = os.path.join(folder, export_mod.stl_dir(marker))
    model = os.path.join(folder, marker["model"]) if isinstance(marker.get("model"), str) else None
    if do_export:
        try:
            res = {r["name"]: r for r in export_mod.export(folder, marker)}
        except (ValueError, OSError) as e:
            return [_row("export", "(all)", "BLOCK", f"export failed: {e}")]
        for p in pieces:
            r = res.get(p["name"], dict(ok=False, error="not written"))
            if not r["ok"]:
                rows.append(_row("export", p["name"], "BLOCK", f"not exported: {r['error']}"))
            elif not r.get("watertight", True):
                rows.append(_row("export", p["name"], "CHECK", "exported, but the mesh is not watertight (look at it in the slicer)"))
            else:
                rows.append(_row("export", p["name"], "PASS", f"{r['size'][0]} x {r['size'][1]} x {r['size'][2]} mm"))
        return rows
    for p in pieces:
        f = os.path.join(sd, p["name"] + ".stl")
        if not os.path.exists(f):
            rows.append(_row("export", p["name"], "BLOCK", "no STL (run without --no-export)"))
        elif model and os.path.exists(model) and os.path.getmtime(f) < os.path.getmtime(model):
            rows.append(_row("export", p["name"], "BLOCK", "STL is older than the model: it may not be the current design"))
        else:
            rows.append(_row("export", p["name"], "PASS", "STL present and current"))
    return rows


def _reusable(folder, marker, name, stl, cfg):
    """The newest plate record for `name`, if this tool made it from exactly this STL with this profile and its plate file is still there."""
    p = os.path.join(folder, "records", "plates.jsonl")
    if not os.path.exists(p):
        return None
    last = None
    for l in open(p):
        try:
            r = json.loads(l)
        except ValueError:
            continue
        if r.get("part") == name:
            last = r
    if not last or last.get("profile") != cfg.name or last.get("stl_sha") != plate.sha(stl):
        return None
    f = last.get("file")
    return last if f and os.path.exists(f if os.path.isabs(f) else os.path.join(folder, f)) else None


def step_plates(folder, marker, cfg, only, reuse, outdir, log):
    rows = []
    sd = os.path.join(folder, export_mod.stl_dir(marker))
    pieces = [p for p in export_mod.pieces(marker) if not only or p["name"] in only]
    src = [os.path.join(folder, marker["model"])] if isinstance(marker.get("model"), str) else None
    done_groups = set()
    for p in pieces:
        name, group = p["name"], p.get("group")
        stl = os.path.join(sd, name + ".stl")
        label = f"group {group}" if group else name
        if group in done_groups:
            continue
        try:
            if group:
                done_groups.add(group)
                r = plate.make_group(folder, marker, group, outdir, cfg)
            else:
                if not os.path.exists(stl):
                    rows.append(_row("plate", name, "BLOCK", "no STL to slice")); continue
                old = _reusable(folder, marker, name, stl, cfg) if reuse else None
                if old:
                    rows.append(_row("plate", name, old["verdict"], f"REUSED: the STL has not changed since the {old.get('date', '?')} plate check ({old.get('minutes', '?')} min, {old.get('grams', '?')} g)",
                                     minutes=old.get("minutes"), grams=old.get("grams"), file=old.get("file"), notes=old.get("notes", []), reused=True))
                    continue
                r = plate.make(stl, outdir, cfg, source=src, project=folder)
        except SystemExit as e:
            rows.append(_row("plate", label, "BLOCK", f"refused: {e}")); continue
        except Exception as e:                                           # a crash is a BLOCK, never a skip
            rows.append(_row("plate", label, "BLOCK", f"could not slice or judge it: {type(e).__name__}: {e}")); continue
        pg = None
        if r["verdict"] != "PASS" and r.get("file") and str(r["file"]).endswith(".3mf"):
            try:                                                         # every CHECK and BLOCK gets its picture page
                doc, _ = report.build(r["file"], [stl] if not group else [], cfg)
                pg = os.path.splitext(r["file"])[0] + "_report.html"
                with open(pg, "w") as fh:
                    fh.write(doc)
            except Exception as e:
                log(f"      (report for {label} not made: {type(e).__name__}: {e})")
        rows.append(_row("plate", label, r["verdict"], f"{r['minutes']} min, {r['grams']} g", minutes=r["minutes"], grams=r["grams"], file=r.get("file"), notes=r.get("notes", []), report=pg))
    return rows


def run(folder, marker, parts=None, do_export=True, do_plates=True, reuse=True, selftest_all=False, profile=None, log=print):
    """-> dict(verdict, rows, counts). Writes GATE.md and records/gate.json in the project."""
    folder = os.path.abspath(folder)
    cfg = Settings.load(profile)
    only = set(parts) if parts else None
    rows = []
    def add(rs):
        for r in rs:
            rows.append(r)
            log(f"{r['verdict']:6} {r['step']:9} {r['name']}: {r['text']}")
    log(f"[gate] {marker.get('name', folder)}  (profile: {cfg.name})")
    add(step_export(folder, marker, do_export, only))
    if do_plates and not any(r["verdict"] == "BLOCK" and r["step"] == "export" for r in rows):
        add(step_plates(folder, marker, cfg, only, reuse, os.path.join(folder, "plates"), log))
    elif do_plates:
        add([_row("plate", "(all)", "BLOCK", "not run: an export step is BLOCKED, so there is no current STL to slice")])
    if os.path.exists(os.path.join(folder, "checks.toml")):
        try:
            lines = []
            r = assemblycheck.run(folder, marker, log=lines.append)
            records.append(folder, "assembly-check", r["ok"], cases=len(r["results"]), failed=sum(1 for x in r["results"] if x.get("ok") is False), controls_ok=r["controls_ok"])
            add([_row("assembly", "assembly-check", "PASS" if r["ok"] else "BLOCK",
                      f"{len(r['results'])} cases, ALL CLEAR" if r["ok"] else "; ".join(l.strip() for l in lines if l.startswith("FAIL"))[:600] or "PROBLEMS FOUND")])
        except Exception as e:
            add([_row("assembly", "assembly-check", "BLOCK", f"could not run: {type(e).__name__}: {e}")])
    if os.path.exists(os.path.join(folder, "selftest.toml")):
        try:
            lines = []
            r = selftest.run(os.path.join(folder, "selftest.toml"), include_slow=selftest_all, log=lines.append)
            records.append(folder, "selftest", r["ok"], passed=r["passed"], failed=r["failed"], skipped=r["skipped"])
            add([_row("selftest", "selftest", "PASS" if r["ok"] else "BLOCK",
                      f"{r['passed']} passed, {r['skipped']} skipped" if r["ok"] else f"THE CHECKER IS NOT TRUSTWORTHY: {r['failed']} fixture(s) disagree")])
        except Exception as e:
            add([_row("selftest", "selftest", "BLOCK", f"could not run: {type(e).__name__}: {e}")])
    if os.path.exists(os.path.join(folder, "parts.toml")):
        try:
            path, r = register.write(folder, marker)
            bad = []
            if r["unregistered"]: bad.append("exported but not described: " + ", ".join(r["unregistered"]))
            if r["not_exported"]: bad.append("described but not exported: " + ", ".join(r["not_exported"]))
            if r["stale"]: bad.append(f"{r['stale']} stale STL(s)")
            add([_row("register", "register", "CHECK" if bad else "PASS", "; ".join(bad) if bad else f"{r['parts']} parts described", file=path)])
        except Exception as e:
            add([_row("register", "register", "BLOCK", f"could not run: {type(e).__name__}: {e}")])
    verdict = worst([r["verdict"] for r in rows])
    counts = {v: sum(1 for r in rows if r["verdict"] == v) for v in ORDER}
    result = dict(verdict=verdict, counts=counts, rows=rows, at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), profile=cfg.name)
    _write(folder, marker, result)
    records.append(folder, "gate", verdict != "BLOCK", verdict=verdict, **counts)
    log(f"\n[gate] {verdict}: {counts['PASS']} PASS, {counts['CHECK']} CHECK, {counts['BLOCK']} BLOCK" +
        ("   -- a CHECK is not a pass: look at each one (GATE.md lists them with their report pages)" if counts["CHECK"] else ""))
    return result


def _write(folder, marker, res):
    os.makedirs(os.path.join(folder, "records"), exist_ok=True)
    with open(os.path.join(folder, "records", "gate.json"), "w") as fh:
        json.dump(res, fh, indent=1, default=str)
    md = [f"# Gate: {marker.get('name', os.path.basename(folder))}", "", f"**{res['verdict']}** on {res['at']} (profile: {res['profile']}). {res['counts']['PASS']} PASS, {res['counts']['CHECK']} CHECK, {res['counts']['BLOCK']} BLOCK.",
          "A CHECK is not a pass: each is listed below with its report page, and a person decides.", "", "| Verdict | Step | Item | What |", "|---|---|---|---|"]
    for r in res["rows"]:
        md.append(f"| **{r['verdict']}** | {r['step']} | {r['name']} | {r['text'].replace('|', '/')}" + (f" ([report]({os.path.relpath(r['report'], folder)}))" if r.get("report") else "") + " |")
    flagged = [r for r in res["rows"] if r["verdict"] != "PASS" and r.get("notes")]
    if flagged:
        md += ["", "## What the checks said about the flagged items", ""]
        for r in flagged:
            md += [f"**{r['name']}** ({r['verdict']})"] + [f"- {n}" for n in r["notes"]] + [""]
    with open(os.path.join(folder, "GATE.md"), "w") as fh:
        fh.write("\n".join(md) + "\n")
