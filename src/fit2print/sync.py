"""Keep a project's copy on the server (phobos) and the master copy on the laptop in step, without git, and WITHOUT EVER OVERWRITING WORK.

Both sides can add things: the phone page adds print-log entries and photos, and the assistant on the server edits brief.md and NEXT.md. So files are
treated by kind (`plan(marker)`):
  APPEND  (logs: *.jsonl)       merged both ways: each side gains the lines it lacks (exact duplicates ignored, a damaged line refused);
  TEXT    (brief.md, NEXT.md)   three-way: the hash at the last sync says which side changed. One side changed: it wins. BOTH changed: nothing is
                                overwritten; the server's version is saved beside yours as NAME.from-server-DATE and the conflict is reported;
                                `prefer="local"` or `"server"` settles it;
  PUSH    (model, marker, ...)  the master's own files, copied to the server;
  PHOTOS                        copied both ways, never overwriting.
The laptop copy is the master. New projects started on the phone page are brought home by `pull_new`.
REMOTE is a folder, or host:folder reached over ssh."""
import datetime, hashlib, json, os, shlex, subprocess, tempfile

STATE = ".fit2print-sync.json"

def plan(marker, plates_dir=None, local=None):
    pics = []
    if local and os.path.exists(os.path.join(local, "assembly.toml")):          # the picture files the guide's steps name
        import re
        with open(os.path.join(local, "assembly.toml")) as fh:
            pics = sorted(set(re.findall(r'picture\s*=\s*"([A-Za-z0-9_.-]{1,80}\.(?:png|jpg|jpeg))"', fh.read())))
    if marker.get("adapter") == "phonosphere":
        return dict(append=["PRINT_LOG.jsonl"], text=[], push=pics + ["fit2print.toml", "parts_register.py", "PLATE_RESULTS.jsonl", "PARTS_AUDIT.json", "assembly.toml"])
    push = ["fit2print.toml", "assembly.toml"]
    m = marker.get("model")                                  # the model the pictures are drawn from, so the server can draw them too
    if isinstance(m, str) and not os.path.isabs(m) and ".." not in m.split("/"):
        push.append(m)
    plates = [os.path.join("plates", f) for f in os.listdir(plates_dir) if f.endswith((".3mf", ".gcode"))] if plates_dir and os.path.isdir(plates_dir) else []
    push += pics + plates                                    # the guide's pictures and the sliced plates, so the server's layer preview can show them
    return dict(append=[os.path.join("records", "plates.jsonl"), os.path.join("records", "prints.jsonl"), os.path.join("records", "assistant.jsonl")],
                text=["brief.md", "NEXT.md"], push=push)

def log_path(marker):
    return "PRINT_LOG.jsonl" if marker.get("adapter") == "phonosphere" else os.path.join("records", "prints.jsonl")

def push_files(marker):
    p = plan(marker)
    return p["push"] + p["text"] + p["append"]

def _run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd[:2])} failed: {r.stderr.strip()[:300]}")
    return r.stdout

def _rsync(src, dst, *opts):
    return _run(["rsync", "-a", *opts, src, dst])

def _fetch(remote_file, dest):
    """Copy a remote file here. -> True if it exists."""
    try:
        _rsync(remote_file, dest)
        return True
    except RuntimeError:
        return False

def _hash(path):
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()

def _lines(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [l.strip() for l in f if l.strip()]

def merge_lines(local_log, remote_log):
    """Make local_log hold every line of both files (local order first, then the other side's new lines). -> (lines added to local, lines the other side lacks)."""
    mine, theirs = _lines(local_log), _lines(remote_log)
    have = set(mine); added = []
    for l in theirs:
        json.loads(l)                                         # refuse a damaged line rather than copy it into the master
        if l not in have:
            added.append(l); have.add(l)
    if added:
        os.makedirs(os.path.dirname(local_log) or ".", exist_ok=True)
        with open(local_log, "a") as f:
            for l in added:
                f.write(l + "\n")
    return len(added), len(set(mine + added) - set(theirs))

def merge_log(local_log, remote_log):
    return merge_lines(local_log, remote_log)[0]

def sync(local, remote, marker, dry=False, prefer=None):
    """-> dict(pulled=log lines pulled, photos_pulled, pushed=[...], text_pulled=[...], text_pushed=[...], conflicts=[...])."""
    local = local.rstrip("/"); remote = remote.rstrip("/")
    pl = plan(marker, os.path.join(local, "plates"), local)
    out = dict(pulled=0, photos_pulled=0, pushed=[], text_pulled=[], text_pushed=[], conflicts=[])
    sp = os.path.join(local, STATE)
    state = json.load(open(sp)) if os.path.exists(sp) else {}
    with tempfile.TemporaryDirectory() as tmp:
        # APPEND files: merge both ways
        for rel in pl["append"]:
            rf = os.path.join(tmp, "r_" + rel.replace(os.sep, "_"))
            if not _fetch(f"{remote}/{rel}", rf):
                open(rf, "w").close()
            if dry:
                continue
            added, lacking = merge_lines(os.path.join(local, rel), rf)
            out["pulled"] += added
            if lacking or added or not _lines(rf):
                if os.path.exists(os.path.join(local, rel)):
                    _run(["rsync", "-a", "--mkpath", os.path.join(local, rel), f"{remote}/{rel}"]); out["pushed"].append(rel)
        # TEXT files: three-way
        for rel in pl["text"]:
            lp = os.path.join(local, rel); rf = os.path.join(tmp, "t_" + rel.replace(os.sep, "_"))
            has_remote = _fetch(f"{remote}/{rel}", rf)
            lh, rh, base = _hash(lp), (_hash(rf) if has_remote else None), state.get(rel)
            if lh == rh:
                state[rel] = lh; continue
            if rh is None:                                                   # only here: push
                action = "push"
            elif lh is None:                                                 # only there: pull
                action = "pull"
            elif prefer == "local": action = "push"
            elif prefer == "server": action = "pull"
            elif base is not None and rh == base: action = "push"            # the server did not change it
            elif base is not None and lh == base: action = "pull"            # I did not change it
            else:
                action = "conflict"
            if action == "conflict":
                copy = f"{rel}.from-server-{datetime.datetime.now().strftime('%Y%m%d-%H%M')}"
                if not dry:
                    with open(rf, "rb") as a, open(os.path.join(local, copy), "wb") as b:
                        b.write(a.read())
                out["conflicts"].append(f"{rel}: changed on both sides; the server's version is saved as {copy} and nothing was overwritten")
            elif action == "push":
                if not dry:
                    _run(["rsync", "-a", "--mkpath", lp, f"{remote}/{rel}"]); state[rel] = lh
                out["text_pushed"].append(rel)
            else:
                if not dry:
                    os.makedirs(os.path.dirname(lp) or ".", exist_ok=True)
                    with open(rf, "rb") as a, open(lp, "wb") as b:
                        b.write(a.read())
                    state[rel] = rh
                out["text_pulled"].append(rel)
        try:
            n = _rsync(f"{remote}/photos/", f"{local}/photos/", "--ignore-existing", "--itemize-changes", *(["--dry-run"] if dry else []))
            out["photos_pulled"] = sum(1 for l in n.splitlines() if l.startswith(">f"))
        except RuntimeError:
            pass
    for rel in pl["push"]:
        if os.path.exists(os.path.join(local, rel)):
            out["pushed"].append(rel)
            if not dry:
                _run(["rsync", "-a", "--mkpath", os.path.join(local, rel), f"{remote}/{rel}"])
    if os.path.isdir(os.path.join(local, "photos")) and not dry:
        _rsync(f"{local}/photos/", f"{remote}/photos/", "--mkpath", "--ignore-existing")
    if state and not dry and pl["text"]:
        with open(sp, "w") as f:
            json.dump(state, f)
    return out

def list_remote(remote_root):
    """The folder names inside a remote folder (host:path over ssh, or a local path)."""
    if ":" in remote_root and not remote_root.startswith("/"):
        host, path = remote_root.split(":", 1)
        return sorted(l for l in _run(["ssh", "-o", "BatchMode=yes", host, "ls -1 " + shlex.quote(path)]).splitlines() if l)
    return sorted(os.listdir(remote_root)) if os.path.isdir(remote_root) else []

def pull_new(remote_root, local_root, known_ids):
    """Bring home every project folder on the server (one with a fit2print.toml marker) that the laptop does not know. -> list of ids pulled."""
    pulled = []
    for name in list_remote(remote_root):
        if name in known_ids or name.startswith("."):
            continue
        dest = os.path.join(local_root, name)
        if os.path.exists(dest):
            continue
        with tempfile.TemporaryDirectory() as tmp:
            if not _fetch(f"{remote_root.rstrip('/')}/{name}/fit2print.toml", os.path.join(tmp, "m.toml")):
                continue                                                  # not a project (no marker): leave it alone
        os.makedirs(local_root, exist_ok=True)
        _rsync(f"{remote_root.rstrip('/')}/{name}/", dest + "/", "--mkpath", "--exclude", ".fit2print-sync.json")
        pulled.append(name)
    return pulled
