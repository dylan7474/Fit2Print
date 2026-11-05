import http.client, io, json, os, tempfile, threading, time, unittest, urllib.parse, zipfile
from fit2print import archive, backup, project, server

def mp(fields, fname, data):
    b = "XBOUNDARYX"; out = b""
    for k, v in fields.items(): out += f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    out += f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="{fname}"\r\nContent-Type: application/zip\r\n\r\n'.encode() + data + f"\r\n--{b}--\r\n".encode()
    return out, f"multipart/form-data; boundary={b}"

class Base(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory(); self.nd = os.path.join(self.d.name, "n"); os.makedirs(self.nd); self.bd = os.path.join(self.d.name, "backups")
        self.f = os.path.join(self.nd, "bk-test"); project.init(self.f, "Bk Test"); open(os.path.join(self.f, "model.scad"), "w").write("cube(10);")
        os.makedirs(os.path.join(self.f, "photos")); open(os.path.join(self.f, "photos", "a.jpg"), "wb").write(b"\xff\xd8jpegdata")
        self.srv = server.make_server(dict(projects=[], new_projects_dir=self.nd, backups_dir=self.bd), "127.0.0.1", 0); self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
    def tearDown(self): self.srv.shutdown(); self.srv.server_close(); self.d.cleanup()
    def call(self, m, p, body=None, ct="application/x-www-form-urlencoded"):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=20)
        c.request(m, p, body=body, headers={"Content-Type": ct} if body else {}); r = c.getresponse(); return r.status, r.read(), r
    def marker(self): return server.read_marker(self.f)

class Make(Base):
    def test_a_backup_holds_every_file_and_says_what_it_is(self):
        z = zipfile.ZipFile(io.BytesIO(backup.make(self.f, self.marker())))
        n = z.namelist(); self.assertIn("project/model.scad", n); self.assertIn("project/photos/a.jpg", n); self.assertIn("project/fit2print.toml", n)
        man = json.loads(z.read("fit2print-backup.json")); self.assertEqual((man["id"], man["kind"], man["version"]), ("bk-test", "project", 1))
    def test_round_trip_restores_the_same_files(self):
        data = backup.make(self.f, self.marker()); before = {r: open(p, "rb").read() for p, r in backup._files(self.f)}
        import shutil; shutil.rmtree(self.f)
        pid, replaced = backup.restore(data, self.nd, {}, self.bd); self.assertEqual((pid, replaced), ("bk-test", False))
        self.assertEqual({r: open(p, "rb").read() for p, r in backup._files(self.f)}, before)
    def test_download_buttons_serve_a_valid_zip(self):
        s, b, r = self.call("GET", "/p/bk-test/backup.zip"); self.assertEqual(s, 200); self.assertIn("attachment", r.getheader("Content-Disposition")); backup.read_manifest(b)
        s, b, _ = self.call("GET", "/backup-all.zip"); self.assertEqual(backup.read_manifest(b)["kind"], "all")
        self.assertIn("Backup", self.call("GET", "/p/bk-test")[1].decode()); self.assertIn("/backups", self.call("GET", "/")[1].decode())

class Hostile(Base):
    def zip(self, entries, man=None):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("fit2print-backup.json", json.dumps(man or dict(format=backup.FORMAT, version=1, kind="project", id="evil")))
            for n, d in entries: z.writestr(n, d)
        return buf.getvalue()
    def test_paths_that_escape_are_refused(self):                          # NEGATIVE CONTROL
        for bad in ("project/../../evil.txt", "/etc/evil", "project/..\\x", "project/a/../../b"):
            with self.assertRaises(ValueError, msg=bad): backup.restore(self.zip([("project/fit2print.toml", 'id = "evil"'), (bad, "x")]), self.nd, {}, self.bd)
        self.assertFalse(os.path.exists(os.path.join(self.d.name, "evil.txt"))); self.assertFalse(os.path.exists(os.path.join(self.nd, "evil")))
    def test_links_in_the_zip_are_refused(self):                           # NEGATIVE CONTROL
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("fit2print-backup.json", json.dumps(dict(format=backup.FORMAT, version=1, kind="project", id="evil")))
            z.writestr("project/fit2print.toml", 'id = "evil"'); zi = zipfile.ZipInfo("project/link"); zi.external_attr = (0o120777 << 16); z.writestr(zi, "/etc/passwd")
        with self.assertRaises(ValueError): backup.restore(buf.getvalue(), self.nd, {}, self.bd)
    def test_junk_and_foreign_zips_are_refused(self):                      # NEGATIVE CONTROL
        for data in (b"not a zip", self.zip([], dict(format="other", version=1, kind="project", id="x")), self.zip([("project/x", "1")]), self.zip([("project/fit2print.toml", "x")], dict(format=backup.FORMAT, version=1, kind="project", id="../x")),
                     self.zip([("project/fit2print.toml", 'id = "evil"'), ("other/file", "1")])):
            with self.assertRaises(ValueError): backup.restore(data, self.nd, {}, self.bd)
        self.assertEqual(sorted(os.listdir(self.nd)), ["bk-test"])
    def test_a_marker_naming_another_project_is_refused_and_leaves_nothing(self):      # NEGATIVE CONTROL
        with self.assertRaises(ValueError): backup.restore(self.zip([("project/fit2print.toml", 'id = "other"')]), self.nd, {}, self.bd)
        self.assertEqual(sorted(os.listdir(self.nd)), ["bk-test"])           # no half-restored folder, no temp folder
    def test_too_many_files_or_bytes_refused(self):                        # NEGATIVE CONTROL
        old = backup.MAX_FILES; backup.MAX_FILES = 2
        try:
            with self.assertRaises(ValueError): backup.read_manifest(self.zip([("project/fit2print.toml", 'id = "evil"'), ("project/a", "1"), ("project/b", "2")]))
        finally: backup.MAX_FILES = old

class Replace(Base):
    def test_an_existing_project_is_not_overwritten_without_the_tick_and_a_copy_is_saved_with_it(self):
        data = backup.make(self.f, self.marker()); open(os.path.join(self.f, "model.scad"), "w").write("changed")
        with self.assertRaises(ValueError): backup.restore(data, self.nd, {"bk-test": self.f}, self.bd)
        self.assertEqual(open(os.path.join(self.f, "model.scad")).read(), "changed")                  # NEGATIVE CONTROL: untouched
        backup.restore(data, self.nd, {"bk-test": self.f}, self.bd, replace=True)
        self.assertEqual(open(os.path.join(self.f, "model.scad")).read(), "cube(10);")
        rep = os.listdir(os.path.join(self.bd, "_replaced")); self.assertEqual(len(rep), 1)             # what was there is kept
        z = zipfile.ZipFile(os.path.join(self.bd, "_replaced", rep[0])); self.assertEqual(z.read("project/model.scad"), b"changed")
        self.assertEqual(sorted(os.listdir(self.nd)), ["bk-test"])
    def test_a_project_outside_the_projects_folder_is_not_replaced(self):          # NEGATIVE CONTROL
        data = backup.make(self.f, self.marker())
        with self.assertRaises(ValueError): backup.restore(data, self.nd, {"bk-test": os.path.join(self.d.name, "elsewhere")}, self.bd, replace=True)
    def test_restore_through_the_page_upload(self):
        data = backup.make(self.f, self.marker()); import shutil; shutil.rmtree(self.f)
        body, ct = mp({}, "x.zip", data); s, _, r = self.call("POST", "/restore", body, ct); self.assertEqual(s, 303); self.assertIn("Restored", urllib.parse.unquote(r.getheader("Location")))
        self.assertTrue(os.path.exists(os.path.join(self.f, "model.scad")))
        body, ct = mp({}, "x.zip", data); s, _, r = self.call("POST", "/restore", body, ct); self.assertIn("err=", r.getheader("Location"))      # exists, no tick
        body, ct = mp({}, "x.zip", b"junk"); s, _, r = self.call("POST", "/restore", body, ct); self.assertIn("err=", r.getheader("Location"))
    def test_restore_everything(self):
        allz = backup.make_all({"bk-test": (self.f, self.marker(), False)}); import shutil; shutil.rmtree(self.f)
        done, skipped = backup.restore_all(allz, self.nd, {}, self.bd); self.assertEqual((done, skipped), (["bk-test"], []))
        done, skipped = backup.restore_all(allz, self.nd, {"bk-test": self.f}, self.bd); self.assertEqual((done, skipped), ([], ["bk-test"]))

class Auto(Base):
    def test_auto_backup_only_when_changed_and_keeps_the_newest_seven(self):
        ps = {"bk-test": (self.f, self.marker(), False)}
        self.assertEqual(backup.auto_backup(ps, self.bd), ["bk-test"]); self.assertEqual(backup.auto_backup(ps, self.bd), [])       # nothing changed: no second copy
        d = os.path.join(self.bd, "bk-test"); self.assertEqual(len(os.listdir(d)), 1)
        for i in range(10):
            open(os.path.join(self.f, "model.scad"), "w").write(f"v{i}"); os.utime(os.path.join(self.f, "model.scad"), (time.time() + 10 * (i + 1),) * 2)
            backup.save(self.f, self.marker(), self.bd); time.sleep(1.1)
        self.assertEqual(len(os.listdir(d)), backup.KEEP_AUTO)
    def test_a_changed_project_is_backed_up_again_after_a_day_not_before(self):
        ps = {"bk-test": (self.f, self.marker(), False)}; backup.auto_backup(ps, self.bd)
        os.utime(os.path.join(self.f, "model.scad"), (time.time() + 5,) * 2); self.assertEqual(backup.auto_backup(ps, self.bd), [])   # changed but under a day: wait
        self.assertEqual(backup.auto_backup(ps, self.bd, every=0), ["bk-test"])
    def test_backups_page_lists_downloads_and_restores_saved_ones(self):
        self.call("POST", "/backups/now"); t = self.call("GET", "/backups")[1].decode(); self.assertIn("bk-test", t)
        rel = backup.listing(self.bd)["auto"]["bk-test"][0]["rel"]
        s, b, _ = self.call("GET", "/backups/file?f=" + urllib.parse.quote(rel)); self.assertEqual(s, 200); backup.read_manifest(b)
        for bad in ("../x.zip", "bk-test/../../etc/passwd", "nope/x.zip", "bk-test/x.txt"): self.assertEqual(self.call("GET", "/backups/file?f=" + urllib.parse.quote(bad))[0], 404, bad)      # NEGATIVE CONTROL
        import shutil; shutil.rmtree(self.f)
        s, _, r = self.call("POST", "/restore-saved", urllib.parse.urlencode(dict(f=rel)).encode()); self.assertIn("Restored", urllib.parse.unquote(r.getheader("Location"))); self.assertTrue(os.path.exists(self.f))

class DeleteSafetyNet(Base):
    def test_deleting_saves_a_copy_that_can_be_restored(self):
        self.call("POST", "/p/bk-test/archive", b"action=archive")
        s, _, _ = self.call("POST", "/p/bk-test/delete", urllib.parse.urlencode(dict(confirm="Bk Test")).encode()); self.assertEqual(s, 303); self.assertFalse(os.path.exists(self.f))
        dl = backup.listing(self.bd)["deleted"]; self.assertEqual(len(dl), 1); self.assertIn("Deleted projects", self.call("GET", "/backups")[1].decode())
        s, _, r = self.call("POST", "/restore-saved", urllib.parse.urlencode(dict(f=dl[0]["rel"])).encode()); self.assertIn("Restored", urllib.parse.unquote(r.getheader("Location")))
        self.assertEqual(open(os.path.join(self.f, "model.scad")).read(), "cube(10);"); self.assertTrue(os.path.exists(os.path.join(self.f, "photos", "a.jpg")))
    def test_if_the_safety_copy_cannot_be_saved_nothing_is_deleted(self):          # NEGATIVE CONTROL
        self.call("POST", "/p/bk-test/archive", b"action=archive"); open(self.bd, "w").write("a file where the backups folder should be")
        s, _, _ = self.call("POST", "/p/bk-test/delete", urllib.parse.urlencode(dict(confirm="Bk Test")).encode()); self.assertEqual(s, 400); self.assertTrue(os.path.exists(self.f))
    def test_a_wrong_name_saves_no_copy(self):                                       # NEGATIVE CONTROL
        self.call("POST", "/p/bk-test/archive", b"action=archive"); self.call("POST", "/p/bk-test/delete", urllib.parse.urlencode(dict(confirm="nope")).encode())
        self.assertEqual(backup.listing(self.bd)["deleted"], []); self.assertTrue(os.path.exists(self.f))

if __name__ == "__main__": unittest.main()
