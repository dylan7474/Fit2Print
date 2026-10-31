"""Read a Phonosphere project (its cad/ folder) into Fit2Print's neutral project dict. The records stay where Phonosphere keeps them:
parts_register.py (META and OPEN), PLATE_RESULTS.jsonl (virtual checks), PRINT_LOG.jsonl (real prints), photos/."""
import glob, importlib.util, json, os

def _jsonl(path):
    return [json.loads(l) for l in open(path) if l.strip()] if os.path.exists(path) else []

def load(cad):
    cad = os.path.abspath(cad)
    spec = importlib.util.spec_from_file_location("phonosphere_parts_register", os.path.join(cad, "parts_register.py"))
    reg = importlib.util.module_from_spec(spec); spec.loader.exec_module(reg)
    parts = [dict(name=n, group=m[0], what=m[1], qty=m[2], colour=m[3], fixings=m[4], issues=m[5]) for n, m in reg.META.items()]
    prints = _jsonl(os.path.join(cad, "PRINT_LOG.jsonl"))
    for p in prints:
        if p.get("photo"):
            p["photo"] = os.path.join(cad, p["photo"])
    return dict(parts_label="parts in the radio", name="Phonosphere", subtitle="a cathedral radio, printed on a Bambu A1", parts=parts, groups=["Cabinet", "Face", "Back", "Speaker pod", "Controls", "Electronics", "Trims"],
                runs=_jsonl(os.path.join(cad, "PLATE_RESULTS.jsonl")), prints=prints, open_items=list(reg.OPEN),
                photos=sorted(glob.glob(os.path.join(cad, "photos", "*.jpg")) + glob.glob(os.path.join(cad, "photos", "*.png"))))
