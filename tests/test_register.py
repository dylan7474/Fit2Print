import argparse, hashlib, json, os, tempfile, time, unittest
import trimesh
from fit2print import cli, project, register

PARTS = """title = "Test register"
[[part]]
name = "body"
section = "Main"
what = "the body"
qty = 2
colour = "black"
fixings = "4 screws"
issues = "none"
[[part]]
name = "lid"
section = "Main"
what = "the lid"
[[part]]
name = "ghost"
section = "Extras"
what = "described but never exported"
[[open]]
text = "Unproven in print: the lid snap."
"""


class Reg(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory(); self.f = os.path.join(self.d.name, "p"); project.init(self.f, "Reg Test")
        open(os.path.join(self.f, "model.scad"), "w").write("cube(1);")
        open(os.path.join(self.f, "fit2print.toml"), "a").write('\nmodel = "model.scad"\n[[export]]\nname = "body"\npart = "body"\n[[export]]\nname = "lid"\npart = "lid"\n[[export]]\nname = "extra"\npart = "extra"\n')
        open(os.path.join(self.f, "parts.toml"), "w").write(PARTS)
        os.makedirs(os.path.join(self.f, "stl")); os.makedirs(os.path.join(self.f, "records"), exist_ok=True)
        for n in ("body", "lid"):
            trimesh.creation.box(extents=[10, 10, 5]).export(os.path.join(self.f, "stl", n + ".stl"))
        later = time.time() + 5
        for n in ("body", "lid"):
            os.utime(os.path.join(self.f, "stl", n + ".stl"), (later, later))                  # the STLs are newer than the model: fresh
        self.m = cli.read_marker(self.f)
    def tearDown(self): self.d.cleanup()
    def sha(self, n): return hashlib.sha256(open(os.path.join(self.f, "stl", n + ".stl"), "rb").read()).hexdigest()[:10]
    def jl(self, name, rows):
        with open(os.path.join(self.f, "records", name), "w") as fh:
            for r in rows: fh.write(json.dumps(r) + "\n")
    def build(self): return register.build(self.f, self.m, today="2026-11-01")
    def test_it_lists_parts_by_section_with_totals_and_open_items(self):
        self.jl("plates.jsonl", [dict(date="2026-11-01", part="body", verdict="PASS", minutes=60, grams=40, stl_sha=self.sha("body"))])
        t, s = self.build()
        self.assertIn("## Main", t); self.assertIn("## Extras", t); self.assertIn("| `body` | the body | 2 | black |", t)
        self.assertIn("**PASS** 2026-11-01", t); self.assertIn("about 2 h and 0.08 kg", t)          # 60 min x 2 = 120 min; 40 g x 2 = 80 g
        self.assertIn("Unproven in print: the lid snap.", t)
    def test_unregistered_and_not_exported_parts_are_named_never_dropped(self):        # NEGATIVE CONTROLS
        t, s = self.build()
        self.assertEqual(s["unregistered"], ["extra"]); self.assertEqual(s["not_exported"], ["ghost"])
        self.assertIn("- `extra`", t); self.assertIn("**NOT EXPORTED**", t)
    def test_a_part_with_no_check_says_never_checked_and_a_check_is_never_called_a_pass(self):
        self.jl("plates.jsonl", [dict(date="2026-11-01", part="lid", verdict="CHECK", minutes=10, grams=5, stl_sha=self.sha("lid"))])
        t, s = self.build()
        self.assertIn("never checked", t); self.assertIn("**CHECK** 2026-11-01", t); self.assertNotIn("**PASS**", t); self.assertEqual(s["never_checked"], 2)             # body and the never-exported ghost
    def test_a_plate_made_from_an_older_stl_is_flagged(self):
        self.jl("plates.jsonl", [dict(date="2026-11-01", part="body", verdict="PASS", minutes=1, grams=1, stl_sha="0123456789", profile="Bambu A1")])
        self.assertIn("plate is from an OLDER STL", self.build()[0])
    def test_a_record_from_another_tool_is_not_compared_but_the_register_says_so(self):
        self.jl("plates.jsonl", [dict(date="2026-10-31", part="body", verdict="PASS", minutes=1, grams=1, stl_sha="0123456789"), dict(date="2026-10-31", part="lid", verdict="PASS", minutes=1, grams=1, stl_sha="abcdef0123")])
        t, s = self.build()
        self.assertNotIn("OLDER STL", t); self.assertEqual(s["unverifiable"], 2); self.assertIn("2 plate record(s) were made by another tool", t)
    def test_a_stl_older_than_the_model_is_stale(self):
        old = time.time() - 3600
        os.utime(os.path.join(self.f, "stl", "lid.stl"), (old, old))
        t, s = self.build()
        self.assertIn("**STL STALE**", t); self.assertEqual(s["stale"], 1)
    def test_a_missing_stl_is_said_not_hidden(self):
        os.remove(os.path.join(self.f, "stl", "lid.stl"))
        self.assertIn("**NO STL YET**", self.build()[0])
    def test_real_prints_say_what_happened_and_a_superseded_print_needs_a_reprint(self):
        self.jl("prints.jsonl", [dict(date="2026-10-25", plate="lid", result="ok"), dict(date="2026-10-31", plate="lid (the 25 Oct print)", result="superseded"),
                                 dict(date="2026-11-01", plate="body plate", result="pending"), dict(date="2026-11-01", plate="bodyguard", result="ok")])
        t, s = self.build()
        self.assertIn("**REPRINT NEEDED**", t)
        body = [l for l in t.splitlines() if l.startswith("| `body`")][0]
        self.assertIn("not printed", body)                  # 'pending' is a prepared plate, not a print; 'bodyguard' is another part
        self.jl("prints.jsonl", [dict(date="2026-10-31", plate="lid", result="superseded"), dict(date="2026-11-02", plate="lid reprint", result="ok")])
        self.assertNotIn("REPRINT NEEDED", self.build()[0])
    def test_bad_parts_files_are_explained(self):
        for body, msg in (('[[part]]\nname="a"\n', "needs name, section and what"), ('[[part]]\nname="a"\nsection="s"\nwhat="w"\n[[part]]\nname="a"\nsection="s"\nwhat="w"\n', "twice"),
                          ('[[part]]\nname="a"\nsection="s"\nwhat="w"\nqty=0\n', "qty")):
            open(os.path.join(self.f, "parts.toml"), "w").write(body)
            with self.assertRaisesRegex(ValueError, msg): register.load_parts(self.f)
        os.remove(os.path.join(self.f, "parts.toml"))
        with self.assertRaisesRegex(ValueError, "no parts.toml"): register.load_parts(self.f)
    def test_the_command_writes_the_file_and_strict_fails_on_problems(self):
        ns = lambda **k: argparse.Namespace(**{**dict(project=self.f, out=None, strict=False), **k})
        self.assertEqual(cli.cmd_register(ns()), 0); self.assertTrue(os.path.exists(os.path.join(self.f, "PARTS_REGISTER.md")))
        self.assertEqual(cli.cmd_register(ns(strict=True)), 1)                                   # extra is unregistered, ghost not exported, parts never checked
