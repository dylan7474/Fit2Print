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
        self.assertTrue(os.path.exists(os.path.join(self.remote, "fit2print.toml"))); self.assertIn("NEXT.md", r["text_pushed"])
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

class ThreeWay(unittest.TestCase):
    """brief.md / NEXT.md can be edited on BOTH sides (the assistant on the server, you on the laptop): nothing may be overwritten silently."""
    def setUp(self):
        self.d = tempfile.TemporaryDirectory(); self.local = os.path.join(self.d.name, "local"); self.remote = os.path.join(self.d.name, "remote")
        project.init(self.local, "Three Way"); os.makedirs(self.remote); self.m = dict(adapter="generic")
        sync.sync(self.local, self.remote, self.m)                         # a first sync: both sides now agree
    def tearDown(self): self.d.cleanup()
    def put(self, side, rel, text):
        os.makedirs(os.path.dirname(os.path.join(side, rel)), exist_ok=True)
        with open(os.path.join(side, rel), "w") as f: f.write(text)
    def get(self, side, rel):
        with open(os.path.join(side, rel)) as f: return f.read()
    def test_a_change_on_the_server_comes_home(self):
        self.put(self.remote, "NEXT.md", "the assistant wrote this")
        r = sync.sync(self.local, self.remote, self.m)
        self.assertEqual(self.get(self.local, "NEXT.md"), "the assistant wrote this"); self.assertIn("NEXT.md", r["text_pulled"]); self.assertEqual(r["conflicts"], [])
    def test_a_change_on_the_laptop_goes_out(self):
        self.put(self.local, "brief.md", "I edited this")
        r = sync.sync(self.local, self.remote, self.m)
        self.assertEqual(self.get(self.remote, "brief.md"), "I edited this"); self.assertIn("brief.md", r["text_pushed"])
    def test_a_change_on_both_sides_overwrites_nothing(self):          # NEGATIVE CONTROL: the data-loss case
        self.put(self.local, "NEXT.md", "my version"); self.put(self.remote, "NEXT.md", "the assistant's version")
        r = sync.sync(self.local, self.remote, self.m)
        self.assertEqual(len(r["conflicts"]), 1)
        self.assertEqual(self.get(self.local, "NEXT.md"), "my version"); self.assertEqual(self.get(self.remote, "NEXT.md"), "the assistant's version")
        saved = [f for f in os.listdir(self.local) if f.startswith("NEXT.md.from-server-")]
        self.assertEqual(len(saved), 1); self.assertEqual(self.get(self.local, saved[0]), "the assistant's version")
    def test_a_conflict_can_be_settled_either_way(self):
        self.put(self.local, "NEXT.md", "mine"); self.put(self.remote, "NEXT.md", "theirs")
        sync.sync(self.local, self.remote, self.m, prefer="server"); self.assertEqual(self.get(self.local, "NEXT.md"), "theirs")
        self.put(self.local, "NEXT.md", "mine again"); self.put(self.remote, "NEXT.md", "theirs again")
        sync.sync(self.local, self.remote, self.m, prefer="local"); self.assertEqual(self.get(self.remote, "NEXT.md"), "mine again")
    def test_a_first_sync_with_two_different_files_is_a_conflict_not_an_overwrite(self):
        os.remove(os.path.join(self.local, sync.STATE))
        self.put(self.local, "NEXT.md", "A"); self.put(self.remote, "NEXT.md", "B")
        r = sync.sync(self.local, self.remote, self.m)
        self.assertEqual(len(r["conflicts"]), 1); self.assertEqual(self.get(self.remote, "NEXT.md"), "B")
    def test_the_assistants_history_merges_both_ways(self):
        self.put(self.local, os.path.join("records", "assistant.jsonl"), json.dumps(dict(role="you", text="a")) + "\n")
        self.put(self.remote, os.path.join("records", "assistant.jsonl"), json.dumps(dict(role="assistant", text="b")) + "\n")
        sync.sync(self.local, self.remote, self.m)
        for side in (self.local, self.remote):
            self.assertEqual(len(self.get(side, os.path.join("records", "assistant.jsonl")).splitlines()), 2)

class NewProjects(unittest.TestCase):
    def test_a_project_started_on_the_server_comes_home_once(self):
        with tempfile.TemporaryDirectory() as d:
            remote = os.path.join(d, "server"); local = os.path.join(d, "laptop"); os.makedirs(local)
            project.init(os.path.join(remote, "pico-case"), "Pico Case"); os.makedirs(os.path.join(remote, "stray-folder"))     # one project, one folder with no marker
            self.assertEqual(sync.pull_new(remote, local, known_ids=set()), ["pico-case"])
            self.assertTrue(os.path.exists(os.path.join(local, "pico-case", "fit2print.toml"))); self.assertFalse(os.path.exists(os.path.join(local, "stray-folder")))
            self.assertEqual(sync.pull_new(remote, local, known_ids={"pico-case"}), [])                    # already known: nothing
            self.assertEqual(sync.pull_new(remote, local, known_ids=set()), [])                            # already there: never overwritten

if __name__ == "__main__":
    unittest.main()
