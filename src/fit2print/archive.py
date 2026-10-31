"""Archiving a project: hide it from Home without deleting anything. An append-only log (records/archive.jsonl, merged between machines like the other logs), so
archive and restore are both remembered and nothing is lost. The newest event decides."""
import datetime, json, os

def _path(folder):
    return os.path.join(folder, "records", "archive.jsonl")

def events(folder):
    p = _path(folder)
    if not os.path.exists(p):
        return []
    with open(p) as f:
        return [json.loads(l) for l in f if l.strip()]

def is_archived(folder):
    ev = events(folder)
    if not ev:
        return False
    return max(enumerate(ev), key=lambda t: (t[1].get("at", ""), t[0]))[1]["action"] == "archive"

def record(folder, action):
    if action not in ("archive", "restore"):
        raise ValueError("archive or restore")
    os.makedirs(os.path.dirname(_path(folder)), exist_ok=True)
    with open(_path(folder), "a") as f:
        f.write(json.dumps(dict(at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), action=action)) + "\n")
