"""Keep a project's copy on the server (phobos) and the master copy on the laptop in step, without git and without conflicts.

The laptop copy is the MASTER of everything (model, checks, records). The server copy is a working copy that the phone-facing page writes NEW print-log
entries and photos into. `fit2print sync PROJECT REMOTE` does, in this order:
  1. PULL: entries and photos that exist only on the server are added to the master's print log (an entry is kept once, exact duplicates ignored);
  2. PUSH: the master's state files and photos are copied to the server (never deleting anything there).
Run from the laptop whenever it is on; the page on the server keeps working in between (its state is as of the last sync, its printer panel is live).
REMOTE is a folder, or host:folder reached over ssh."""
import json, os, subprocess, tempfile

def log_path(marker):
    return "PRINT_LOG.jsonl" if marker.get("adapter") == "phonosphere" else os.path.join("records", "prints.jsonl")

def push_files(marker):
    if marker.get("adapter") == "phonosphere":
        return ["fit2print.toml", "parts_register.py", "PLATE_RESULTS.jsonl", "PARTS_AUDIT.json", "PRINT_LOG.jsonl"]
    return ["fit2print.toml", "NEXT.md", "brief.md", os.path.join("records", "plates.jsonl"), os.path.join("records", "prints.jsonl")]

def _run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd[:2])} failed: {r.stderr.strip()[:300]}")
    return r.stdout

def _rsync(src, dst, *opts):
    return _run(["rsync", "-a", *opts, src, dst])

def merge_log(local_log, remote_log):
    """Append to the master log every line of the remote log it does not already have. -> number added."""
    have = set()
    if os.path.exists(local_log):
        with open(local_log) as f:
            have = {l.strip() for l in f if l.strip()}
    added = []
    if os.path.exists(remote_log):
        with open(remote_log) as f:
            for l in f:
                l = l.strip()
                if not l or l in have:
                    continue
                json.loads(l)                                 # refuse a damaged line rather than copy it into the master
                added.append(l); have.add(l)
    if added:
        os.makedirs(os.path.dirname(local_log) or ".", exist_ok=True)
        with open(local_log, "a") as f:
            for l in added:
                f.write(l + "\n")
    return len(added)

def sync(local, remote, marker, dry=False):
    """-> dict(pulled=..., photos_pulled=..., pushed=[...])."""
    local = local.rstrip("/"); remote = remote.rstrip("/")
    lp = log_path(marker)
    out = dict(pulled=0, photos_pulled=0, pushed=[])
    with tempfile.TemporaryDirectory() as tmp:
        try:
            _rsync(f"{remote}/{lp}", os.path.join(tmp, "remote_log"))
        except RuntimeError:
            open(os.path.join(tmp, "remote_log"), "w").close()                 # no log on the server yet
        if not dry:
            out["pulled"] = merge_log(os.path.join(local, lp), os.path.join(tmp, "remote_log"))
        try:
            n = _rsync(f"{remote}/photos/", f"{local}/photos/", "--ignore-existing", "--itemize-changes", *(["--dry-run"] if dry else []))
            out["photos_pulled"] = sum(1 for l in n.splitlines() if l.startswith(">f"))
        except RuntimeError:
            pass
    for rel in push_files(marker):
        if os.path.exists(os.path.join(local, rel)):
            out["pushed"].append(rel)
            if not dry:
                _run(["rsync", "-a", "--mkpath", os.path.join(local, rel), f"{remote}/{rel}"])
    if os.path.isdir(os.path.join(local, "photos")) and not dry:
        _rsync(f"{local}/photos/", f"{remote}/photos/", "--mkpath", "--ignore-existing")
    return out
