"""The parts register: every part of a project in one table, from the project's own records (PARTS_REGISTER.md). Extracted from Phonosphere's parts_register.py.

A project describes what its parts ARE in parts.toml; everything else is read, never typed:

    title = "Parts register"
    [[part]]
    name = "shell_lower_L"             # the [[export]] name
    section = "Cabinet"                # the table it is listed under (sections appear in the order they are first used)
    what = "left lower cabinet half"
    qty = 1                            # how many go in the finished thing (the totals count it)
    colour = "Charcoal"
    fixings = "M3x16 bolt + nut"       # optional
    issues = "REPRINT NEEDED: ..."     # optional, free text
    [[open]]
    text = "Unproven in print: ..."    # project-wide open items, listed at the end

Read from the project: the exported STLs (and whether each is older than the model), the plate check records (records/plates.jsonl, or PLATE_RESULTS.jsonl for
the radio) and the print log (records/prints.jsonl, or PRINT_LOG.jsonl). Nothing is waived: a part that was never checked says "never checked", and a CHECK is
printed as CHECK. Parts that are exported but not described are listed as UNREGISTERED; parts described but not exported as NOT EXPORTED."""
import datetime, hashlib, json, os, re, tomllib
from . import export as export_mod

REAL = ("ok", "failed", "partial", "pass", "superseded", "printing")


def _jsonl(path):
    out = []
    if os.path.exists(path):
        for l in open(path):
            try:
                out.append(json.loads(l))
            except ValueError:
                continue
    return out


def load_parts(folder):
    p = os.path.join(folder, "parts.toml")
    if not os.path.exists(p):
        raise ValueError("this project has no parts.toml (name, section, what, qty, colour for each part)")
    with open(p, "rb") as fh:
        d = tomllib.load(fh)
    parts = d.get("part") or []
    seen = set()
    for x in parts:
        if not x.get("name") or not x.get("section") or not x.get("what"):
            raise ValueError(f"parts.toml: every [[part]] needs name, section and what: {x}")
        if x["name"] in seen:
            raise ValueError(f"parts.toml: {x['name']} is listed twice")
        seen.add(x["name"])
        if not isinstance(x.get("qty", 1), int) or x.get("qty", 1) < 1:
            raise ValueError(f"parts.toml: {x['name']}: qty must be a whole number, 1 or more")
    return d.get("title", "Parts register"), parts, [o["text"] for o in d.get("open") or [] if o.get("text")]


def _paths(folder, marker):
    radio = marker.get("adapter") == "phonosphere"
    return (os.path.join(folder, "PLATE_RESULTS.jsonl" if radio else os.path.join("records", "plates.jsonl")),
            os.path.join(folder, "PRINT_LOG.jsonl" if radio else os.path.join("records", "prints.jsonl")))


def real_print(part, log):
    """What really happened on the printer, in words: the last two real results, or 'REPRINT NEEDED' when the newest superseded one has no print after it."""
    pat = re.compile(r"(?<![A-Za-z0-9_])" + re.escape(part) + r"(?![A-Za-z0-9_])")
    hits = [e for e in log if pat.search(str(e.get("plate", ""))) and e.get("result") in REAL]
    if not hits:
        return "not printed"
    txt = "; ".join(f"{e.get('date', '?')} {e['result']}" for e in hits[-2:])
    sup = [i for i, e in enumerate(hits) if e["result"] == "superseded"]
    if sup and not any(e["result"] in ("ok", "partial", "printing") for e in hits[sup[-1] + 1:]):
        return f"**REPRINT NEEDED** ({txt})"
    return txt


def build(folder, marker, today=None):
    """-> (markdown text, summary dict)."""
    title, parts, opens = load_parts(folder)
    exports = {p["name"]: p for p in export_mod.pieces(marker)}
    sd = os.path.join(folder, export_mod.stl_dir(marker))
    model = os.path.join(folder, marker["model"]) if isinstance(marker.get("model"), str) else None
    model_t = os.path.getmtime(model) if model and os.path.exists(model) else None
    plates_p, log_p = _paths(folder, marker)
    last = {}
    for r in _jsonl(plates_p):
        last[r.get("part")] = r                                            # later lines win
    log = _jsonl(log_p)
    sections = {}
    for x in parts:
        sections.setdefault(x["section"], []).append(x)
    out = [f"# {title}", "", f"Generated {today or datetime.date.today().isoformat()} by `fit2print register` from parts.toml, the exported STLs, the plate records and the print log. "
           "Edit what a part IS in parts.toml, not here. **CHECK is not a pass.**", ""]
    tot_min = tot_g = 0
    stale_n = unchecked_n = unverifiable = 0
    for sec, xs in sections.items():
        out += [f"## {sec}", "", "| Part | What it is | Qty | Colour | Virtual check | Time / filament | Real print | Fixings | Open issues |", "|---|---|---|---|---|---|---|---|---|"]
        for x in xs:
            n = x["name"]; qty = x.get("qty", 1)
            stl = os.path.join(sd, n + ".stl")
            note = ""
            if n not in exports:
                note = " **NOT EXPORTED** (no [[export]] for it)"
            elif not os.path.exists(stl):
                note = " **NO STL YET** (run fit2print export)"
            elif model_t and os.path.getmtime(stl) < model_t:
                note = " **STL STALE** (older than the model: re-export)"; stale_n += 1
            r = last.get(n)
            if r:
                sha = hashlib.sha256(open(stl, "rb").read()).hexdigest()[:10] if os.path.exists(stl) else None
                mine = bool(r.get("profile"))                                  # only Fit2Print's own records fingerprint the exact STL they were made from
                older = bool(mine and sha and r.get("stl_sha") and "+" not in str(r["stl_sha"]) and r["stl_sha"] != sha)
                unverifiable += not mine
                chk = f"**{r['verdict']}** {r.get('date', '?')}" + (" (plate is from an OLDER STL: re-run)" if older else "")
                tg = f"{r['minutes']} min, {r['grams']} g" if r.get("minutes") else "-"
                if r.get("minutes"):
                    tot_min += r["minutes"] * qty; tot_g += r.get("grams", 0) * qty
            else:
                chk, tg = "never checked", "-"; unchecked_n += 1
            out.append(f"| `{n}` | {x['what']} | {qty} | {x.get('colour', '')} | {chk}{note} | {tg} | {real_print(n, log)} | {x.get('fixings', '')} | {x.get('issues', '')} |")
        out.append("")
    out += [f"Print totals from the latest plate checks (rough, quantities counted): about {tot_min / 60:.0f} h and {tot_g / 1000:.2f} kg.", ""]
    if unverifiable:
        out += [f"Note: {unverifiable} plate record(s) were made by another tool and carry no fingerprint of the STL they came from, so they are NOT compared with today's STL. "
                "Re-run `fit2print plate` on them to get a record that can be checked.", ""]
    described = {x["name"] for x in parts}
    unreg = [n for n in exports if n not in described]
    out += ["## UNREGISTERED (exported, but not described in parts.toml: add them)", ""] + ([f"- `{n}`" for n in unreg] or ["- none"]) + [""]
    out += ["## Open checks (project-wide; keep this list honest)", ""] + ([f"- {t}" for t in opens] or ["- none recorded"]) + [""]
    return "\n".join(out) + "\n", dict(parts=len(parts), unregistered=unreg, stale=stale_n, never_checked=unchecked_n, unverifiable=unverifiable, minutes=tot_min, grams=tot_g,
                                      not_exported=[x["name"] for x in parts if x["name"] not in exports])


def write(folder, marker, out=None):
    text, summary = build(folder, marker)
    path = out or os.path.join(folder, "PARTS_REGISTER.md")
    with open(path, "w") as fh:
        fh.write(text)
    return path, summary
