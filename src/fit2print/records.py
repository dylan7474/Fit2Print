"""An append-only record of every check run (records/checks.jsonl): which check, when, the verdict and the counts. The newest line per check is "the last time it was
run"; older lines stay, so a check that stopped being run, or started failing, can be seen. Never rewritten."""
import datetime, json, os


def append(folder, check, ok, **counts):
    os.makedirs(os.path.join(folder, "records"), exist_ok=True)
    line = dict(at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), check=check, ok=bool(ok), **counts)
    with open(os.path.join(folder, "records", "checks.jsonl"), "a") as fh:
        fh.write(json.dumps(line, default=float) + "\n")
    return line


def history(folder, check=None):
    p = os.path.join(folder, "records", "checks.jsonl")
    if not os.path.exists(p):
        return []
    out = []
    for l in open(p):
        try:
            r = json.loads(l)
        except ValueError:
            continue
        if check is None or r.get("check") == check:
            out.append(r)
    return out


def latest(folder):
    """{check: newest line}."""
    out = {}
    for r in history(folder):
        out[r["check"]] = r
    return out
