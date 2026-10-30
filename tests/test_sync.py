import json, os, tempfile, unittest
from fit2print import project, sync

def entry(n): return json.dumps(dict(date="2026-10-30", plate=n, result="ok", what="x"))

class Sync(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory(); self.local = os.path.join(self.d.name, "local"); self.remote = os.path.join(self.d.name, "remote")
        project.init(self.local, "Sync Test"); os.makedirs(self.remote)
        self.marker = dict(adapter="generic")
        self.lp = os.path.join(self.local, "records", "prints.jsonl"); self.rp = os.path.join(self.remote, "records", "prints.jsonl")
    def tearDown(self): self.d.cleanup()
    def write(self, path, lines):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f: f.write("".join(l + "\n" for l in lines))
    def lines(self, path):
        with open(path) as f: return [l.strip() for l in f if l.strip()]
    def test_first_sync_pushes_the_project(self):
        r = sync.sync(self.local, self.remote, self.marker)
        self.assertTrue(os.path.exists(os.path.join(self.remote, "fit2print.toml"))); self.assertIn("NEXT.md", r["pushed"])
    def test_the_model_file_is_pushed_so_the_server_can_draw_it(self):
        open(os.path.join(self.local, "case.scad"), "w").write("cube(1);")
        r = sync.sync(self.local, self.remote, dict(adapter="generic", model="case.scad"))
        self.assertIn("case.scad", r["pushed"]); self.assertTrue(os.path.exists(os.path.join(self.remote, "case.scad")))
    def test_a_model_path_that_escapes_the_project_is_not_pushed(self):    # NEGATIVE CONTROL
        self.assertNotIn("../x.scad", sync.push_files(dict(adapter="generic", model="../x.scad")))
        self.assertNotIn("/etc/passwd", sync.push_files(dict(adapter="generic", model="/etc/passwd")))
    def test_new_entries_on_the_server_come_home_once(self):
        self.write(self.lp, [entry("a")]); self.write(self.rp, [entry("a"), entry("b")])
        self.assertEqual(sync.sync(self.local, self.remote, self.marker)["pulled"], 1)
        self.assertEqual(self.lines(self.lp), [entry("a"), entry("b")])
        self.assertEqual(sync.sync(self.local, self.remote, self.marker)["pulled"], 0)          # a second run adds nothing
        self.assertEqual(self.lines(self.lp), [entry("a"), entry("b")])
    def test_the_masters_entries_are_pushed_without_losing_the_servers(self):
        self.write(self.lp, [entry("a"), entry("c")]); self.write(self.rp, [entry("b")])
        sync.sync(self.local, self.remote, self.marker)
        self.assertEqual(set(self.lines(self.rp)), {entry("a"), entry("b"), entry("c")})        # nothing the server had was lost
    def test_photos_are_copied_both_ways_and_never_overwritten(self):
        os.makedirs(os.path.join(self.local, "photos")); os.makedirs(os.path.join(self.remote, "photos"))
        open(os.path.join(self.remote, "photos", "phone.jpg"), "w").write("from the phone")
        open(os.path.join(self.local, "photos", "bench.jpg"), "w").write("from the laptop")
        open(os.path.join(self.local, "photos", "same.jpg"), "w").write("master"); open(os.path.join(self.remote, "photos", "same.jpg"), "w").write("server")
        sync.sync(self.local, self.remote, self.marker)
        self.assertTrue(os.path.exists(os.path.join(self.local, "photos", "phone.jpg"))); self.assertTrue(os.path.exists(os.path.join(self.remote, "photos", "bench.jpg")))
        self.assertEqual(open(os.path.join(self.local, "photos", "same.jpg")).read(), "master"); self.assertEqual(open(os.path.join(self.remote, "photos", "same.jpg")).read(), "server")
    def test_a_damaged_line_is_refused_not_copied_into_the_master(self):   # NEGATIVE CONTROL
        self.write(self.lp, [entry("a")]); self.write(self.rp, ["{not json"])
        with self.assertRaises(ValueError):
            sync.sync(self.local, self.remote, self.marker)
        self.assertEqual(self.lines(self.lp), [entry("a")])
    def test_dry_run_changes_nothing(self):
        self.write(self.rp, [entry("b")])
        sync.sync(self.local, self.remote, self.marker, dry=True)
        self.assertFalse(os.path.exists(self.lp)); self.assertFalse(os.path.exists(os.path.join(self.remote, "fit2print.toml")))

if __name__ == "__main__":
    unittest.main()
