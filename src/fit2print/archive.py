"""Archiving a project: hide it from Home without deleting anything. An append-only log (records/archive.jsonl, merged between machines like the other logs), so
archive and restore are both remembered and nothing is lost. The newest event decides."""
import datetime, json, os, shutil

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


def why_not_deletable(folder, marker, new_dir):
    """'' if this project may be deleted for good, else the reason it may not. Only an ARCHIVED project made on this machine (inside new_projects_dir) can go;
    the radio and samples never; a symlink or a folder outside new_projects_dir never."""
    if marker.get("adapter") == "phonosphere" or marker.get("kind") == "sample":
        return "this project is kept: it is the radio or a sample"
    if not is_archived(folder):
        return "archive it first: only an archived project can be deleted"
    if not new_dir or os.path.islink(folder):
        return "this project is not one made on this machine"
    if os.path.dirname(os.path.realpath(folder)) != os.path.realpath(new_dir):
        return "this project lives outside the projects folder, so it is not deleted from here"
    return ""

def inventory(folder):
    """(files, bytes) under the folder, for the confirmation page."""
    n = size = 0
    for r, _, fs in os.walk(folder):
        for f in fs:
            n += 1
            try: size += os.path.getsize(os.path.join(r, f))
            except OSError: pass
    return n, size

def delete(folder, marker, new_dir, typed):
    """Delete the project's folder for good. `typed` must be the project's name (or id) exactly. Raises ValueError with the reason when refused."""
    bad = why_not_deletable(folder, marker, new_dir)
    if bad: raise ValueError(bad)
    if typed.strip() not in (marker.get("name", ""), marker.get("id", "")) or not typed.strip():
        raise ValueError("the name you typed does not match: nothing was deleted")
    shutil.rmtree(os.path.realpath(folder))
