"""Backup and restore of projects. A backup is ONE zip: fit2print-backup.json (what it is) + project/<every file>. Backups are written automatically (daily, when a project has
changed), on demand (the Download button) and just before a project is deleted for good. Restoring never trusts the zip: every path is checked, nothing is a link, sizes are capped,
and the project is unpacked next to its final place and swapped in, so a bad zip never leaves a half-restored project. Replacing an existing project saves a copy of it first."""
import datetime, io, json, os, re, shutil, stat, sys, threading, time, zipfile

FORMAT = "fit2print-backup"
MAX_FILES = 20000
MAX_BYTES = 1 << 30                  # 1 GiB unpacked
KEEP_AUTO = 7                        # newest automatic backups kept per project
KEEP_DELETED = 30                    # newest copies of deleted projects kept
KEEP_REPLACED = 10
MIN_FREE = 1 << 30                   # skip an automatic backup if the disk has less than 1 GiB free
ID_RE = re.compile(r"[a-z0-9][a-z0-9-]*")
SKIP_DIRS = {"__pycache__", ".git"}

def _now():
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")

def _files(folder):
    for r, ds, fs in os.walk(folder):
        ds[:] = [d for d in ds if d not in SKIP_DIRS and not os.path.islink(os.path.join(r, d))]
        for f in fs:
            p = os.path.join(r, f)
            if not os.path.islink(p) and os.path.isfile(p):
                yield p, os.path.relpath(p, folder).replace(os.sep, "/")

def newest_mtime(folder):
    t = 0
    for p, _ in _files(folder):
        try: t = max(t, os.path.getmtime(p))
        except OSError: pass
    return t

def make(folder, marker, archived=False):
    """The backup of one project as zip bytes."""
    items = list(_files(folder))
    man = dict(format=FORMAT, version=1, kind="project", id=marker.get("id"), name=marker.get("name", marker.get("id")), archived=bool(archived),
               created=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), files=len(items), bytes=sum(os.path.getsize(p) for p, _ in items))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("fit2print-backup.json", json.dumps(man, indent=1))
        for p, rel in items:
            z.write(p, "project/" + rel)
    return buf.getvalue()

def make_all(projects):
    """projects = {id: (folder, marker, archived)} -> one zip holding each project's own backup."""
    buf = io.BytesIO(); ids = []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        for pid, (folder, mk, arch) in sorted(projects.items()):
            z.writestr(f"projects/{pid}.zip", make(folder, mk, arch)); ids.append(pid)
        z.writestr("fit2print-backup.json", json.dumps(dict(format=FORMAT, version=1, kind="all", projects=ids, created=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")), indent=1))
    return buf.getvalue()

def _safe_name(n):
    if not n or n.startswith("/") or "\\" in n or "\0" in n or re.match(r"^[A-Za-z]:", n): return False
    return ".." not in n.split("/")

def read_manifest(data):
    """Check a zip is one of ours and safe to unpack. Returns its manifest, or raises ValueError saying what is wrong."""
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise ValueError("that is not a zip file")
    with z:
        names = z.namelist()
        if "fit2print-backup.json" not in names: raise ValueError("that zip is not a Fit2Print backup")
        try: man = json.loads(z.read("fit2print-backup.json"))
        except Exception: raise ValueError("the backup's description is unreadable")
        if man.get("format") != FORMAT or man.get("version") != 1: raise ValueError("that is not a Fit2Print backup this version understands")
        infos = z.infolist()
        if len(infos) > MAX_FILES or sum(i.file_size for i in infos) > MAX_BYTES: raise ValueError("the backup is too large to restore from here")
        for i in infos:
            if not _safe_name(i.filename): raise ValueError(f"unsafe path in the zip: {i.filename!r}")
            if stat.S_ISLNK(i.external_attr >> 16): raise ValueError(f"the zip contains a link ({i.filename}); refused")
            if i.filename != "fit2print-backup.json" and not (i.filename.startswith("project/") or i.filename.startswith("projects/")): raise ValueError(f"unexpected file in the backup: {i.filename}")
        if man.get("kind") == "project":
            if not ID_RE.fullmatch(str(man.get("id", ""))): raise ValueError("the backup has no valid project id")
            if "project/fit2print.toml" not in names: raise ValueError("the backup has no project marker (fit2print.toml)")
        elif man.get("kind") != "all":
            raise ValueError("unknown kind of backup")
    return man

def _tomllib():
    try:
        import tomllib; return tomllib
    except ImportError:
        return None

def _unpack(data, dest):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        root = os.path.realpath(dest)
        for i in z.infolist():
            if not i.filename.startswith("project/") or i.filename.endswith("/"): continue
            out = os.path.realpath(os.path.join(dest, i.filename[len("project/"):]))
            if not out.startswith(root + os.sep): raise ValueError(f"unsafe path in the zip: {i.filename!r}")
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with z.open(i) as src, open(out, "wb") as dst: shutil.copyfileobj(src, dst)

def restore(data, new_dir, existing, backups_dir, replace=False):
    """Restore a one-project backup into new_dir/<id>. `existing` = {id: folder} of the projects the app knows. Returns (id, replaced?)."""
    man = read_manifest(data)
    if man["kind"] != "project": raise ValueError("that is a whole-server backup: use 'restore everything'")
    pid = man["id"]; target = os.path.join(new_dir, pid)
    if pid in existing and os.path.realpath(existing[pid]) != os.path.realpath(target):
        raise ValueError(f"a project with the id '{pid}' exists outside the projects folder, so it is not replaced from here")
    exists = os.path.isdir(target)
    if exists and not replace:
        raise ValueError(f"'{pid}' already exists. Tick 'replace it' to overwrite it (a copy of the current one is saved first).")
    os.makedirs(new_dir, exist_ok=True)
    tmp = os.path.join(new_dir, f".restore-{pid}-{os.getpid()}-{int(time.time())}")
    old = target + f".old-{int(time.time())}"
    try:
        _unpack(data, tmp)
        tl = _tomllib(); mp = os.path.join(tmp, "fit2print.toml")
        if tl is None or not os.path.exists(mp): raise ValueError("the backup has no project marker (fit2print.toml)")
        with open(mp, "rb") as f: mid = tl.load(f).get("id")
        if mid != pid: raise ValueError("the backup is inconsistent (its marker names another project)")
        if exists:
            save(target, {"id": pid, "name": pid}, backups_dir, "_replaced", KEEP_REPLACED)
            os.rename(target, old)
        os.rename(tmp, target)
        if exists: shutil.rmtree(old, ignore_errors=True)
    finally:
        if os.path.isdir(tmp): shutil.rmtree(tmp, ignore_errors=True)
    return pid, exists

def restore_all(data, new_dir, existing, backups_dir, replace=False):
    """Restore a whole-server backup. Projects that already exist are left alone unless replace. Returns (restored ids, skipped ids)."""
    man = read_manifest(data)
    if man["kind"] != "all": return [restore(data, new_dir, existing, backups_dir, replace)[0]], []
    done, skipped = [], []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for pid in man.get("projects", []):
            inner = z.read(f"projects/{pid}.zip")
            try:
                done.append(restore(inner, new_dir, existing, backups_dir, replace)[0])
            except ValueError as e:
                if "already exists" in str(e): skipped.append(pid)
                else: raise
    return done, skipped

# ---- the backups folder: backups/<id>/<id>-<stamp>.zip, backups/_deleted/..., backups/_replaced/...
def _prune(d, keep):
    zs = sorted((f for f in os.listdir(d) if f.endswith(".zip")), reverse=True)
    for f in zs[keep:]:
        try: os.remove(os.path.join(d, f))
        except OSError: pass

def save(folder, marker, backups_dir, sub=None, keep=KEEP_AUTO, archived=False):
    """Write a backup of the project into the backups folder. Returns the file path."""
    pid = marker.get("id") or os.path.basename(folder)
    d = os.path.join(backups_dir, sub or pid); os.makedirs(d, exist_ok=True)
    marker = dict(marker); marker.setdefault("id", pid)
    data = make(folder, marker, archived)
    p = os.path.join(d, f"{pid}-{_now()}.zip"); tmp = p + ".part"
    with open(tmp, "wb") as f: f.write(data)
    os.rename(tmp, p); _prune(d, keep)
    return p

def listing(backups_dir):
    """{'auto': [(id, [entries])], 'deleted': [entries], 'replaced': [entries]}; entry = dict(rel, name, size, mtime), newest first."""
    out = dict(auto={}, deleted=[], replaced=[])
    if not os.path.isdir(backups_dir): return out
    for sub in sorted(os.listdir(backups_dir)):
        d = os.path.join(backups_dir, sub)
        if not os.path.isdir(d): continue
        es = []
        for f in sorted(os.listdir(d), reverse=True):
            if f.endswith(".zip"):
                st = os.stat(os.path.join(d, f)); es.append(dict(rel=f"{sub}/{f}", name=f, size=st.st_size, mtime=st.st_mtime))
        if sub == "_deleted": out["deleted"] = es
        elif sub == "_replaced": out["replaced"] = es
        elif es: out["auto"][sub] = es
    return out

def path_of(backups_dir, rel):
    """The real path of a listed backup, or None (only names in the listing are ever served)."""
    if not re.fullmatch(r"[a-z0-9_-]+/[A-Za-z0-9._-]+\.zip", rel or ""): return None
    p = os.path.join(backups_dir, rel)
    return p if os.path.isfile(p) and not os.path.islink(p) else None

def auto_backup(projects, backups_dir, force=False, every=20 * 3600):
    """Back up every project that changed since its last backup (at most about once a day unless force). projects = {id: (folder, marker, archived)}. Returns the ids backed up."""
    done = []
    os.makedirs(backups_dir, exist_ok=True)
    if shutil.disk_usage(backups_dir).free < MIN_FREE and not force: return done
    for pid, (folder, mk, arch) in projects.items():
        d = os.path.join(backups_dir, pid)
        last = max((os.path.getmtime(os.path.join(d, f)) for f in os.listdir(d) if f.endswith(".zip")), default=0) if os.path.isdir(d) else 0
        changed = newest_mtime(folder) > last
        if force and not changed and last: continue                     # nothing new since the last one: not worth a copy
        if not force and (not changed or time.time() - last < every): continue
        save(folder, dict(mk, id=pid), backups_dir, None, KEEP_AUTO, arch); done.append(pid)
    return done

def start_auto(get_projects, backups_dir, interval=3600, first_delay=60):
    """A daemon thread: first run a minute after start, then hourly. get_projects() -> {id: (folder, marker, archived)}."""
    def loop():
        time.sleep(first_delay)
        while True:
            try:
                for pid in auto_backup(get_projects(), backups_dir): print(f"backup: {pid}", flush=True)
            except Exception as e:
                print(f"backup failed: {e}", file=sys.stderr, flush=True)
            time.sleep(interval)
    t = threading.Thread(target=loop, daemon=True); t.start(); return t
