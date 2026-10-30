"""Read a generic Fit2Print project (made by `fit2print init`) into the neutral project dict the dashboard draws.
Records: records/plates.jsonl (virtual checks), records/prints.jsonl (real prints), photos/ ; NEXT.md's 'Needs the person' list."""
import glob, json, os, re

def _jsonl(path):
    return [json.loads(l) for l in open(path) if l.strip()] if os.path.exists(path) else []

def needs(folder):
    p = os.path.join(folder, "NEXT.md")
    if not os.path.exists(p):
        return []
    t = open(p).read()
    m = re.search(r"## Needs the person\s*(.*?)(?:\n## |\Z)", t, re.S)
    items = [re.sub(r"^\*\s*", "", l).strip() for l in (m.group(1).splitlines() if m else []) if l.strip().startswith("*")]
    return [i for i in items if i and not i.startswith("(")]

def load(folder, marker=None):
    folder = os.path.abspath(folder)
    runs = _jsonl(os.path.join(folder, "records", "plates.jsonl"))
    prints = _jsonl(os.path.join(folder, "records", "prints.jsonl"))
    for p in prints:
        if p.get("photo") and not os.path.isabs(p["photo"]):
            p["photo"] = os.path.join(folder, p["photo"])
    names = []
    for r in runs:
        if r["part"] not in names:
            names.append(r["part"])
    for p in prints:                                   # a part printed that was never checked here still shows up
        n = p["plate"].split(" (")[0].split(" ")[0]
        if n not in names and n not in ("",):
            names.append(n)
    parts = [dict(name=n, group="Parts", what="", qty=1, colour="", fixings="", issues="") for n in names]
    m = marker or {}
    return dict(name=m.get("name", os.path.basename(folder)), subtitle=m.get("kind", ""), parts=parts, groups=["Parts"], runs=runs, prints=prints,
                open_items=needs(folder), photos=sorted(glob.glob(os.path.join(folder, "photos", "*.jpg")) + glob.glob(os.path.join(folder, "photos", "*.png"))))
