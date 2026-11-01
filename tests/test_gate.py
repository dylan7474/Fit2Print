import argparse, json, os, shutil, tempfile, unittest
import numpy as np
from fit2print import cli, export as export_mod, gate, plate, project, records
from fit2print.settings import Settings

MODEL = 'part = "none";\nif (part == "a") cube([20, 20, 10]);\nif (part == "b") translate([30, 0, 0]) cube([15, 15, 8]);\n'


def fake_make(verdicts, calls):
    def make(stl, outdir, cfg=None, filament="pla_black", source=None, project=None, profiles=None, supports="auto"):
        name = os.path.splitext(os.path.basename(stl))[0]
        calls.append(name)
        v = verdicts.get(name, "PASS")
        if isinstance(v, Exception):
            raise v
        rec = dict(date="2026-11-02", part=name, verdict=v, minutes=5, grams=3, notes=[f"note for {name}"], file=os.path.join(outdir, name + ".3mf"), stl_sha=plate.sha(stl), profile=cfg.name)
        if project:
            os.makedirs(os.path.join(project, "records"), exist_ok=True)
            open(os.path.join(project, "records", "plates.jsonl"), "a").write(json.dumps(rec) + "\n")
        os.makedirs(outdir, exist_ok=True); open(rec["file"], "w").write("x")
        return rec
    return make


@unittest.skipUnless(shutil.which("openscad"), "needs openscad")
class Gate(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory(); self.f = os.path.join(self.d.name, "p"); project.init(self.f, "Gate Test")
        open(os.path.join(self.f, "model.scad"), "w").write(MODEL)
        open(os.path.join(self.f, "fit2print.toml"), "a").write('\nmodel = "model.scad"\n[[export]]\nname = "a"\npart = "a"\n[[export]]\nname = "b"\npart = "b"\n')
        self.m = cli.read_marker(self.f)
        self.calls = []
        self.orig = (plate.make, gate.report.build)
        gate.report.build = lambda *a, **k: ("<html></html>", "CHECK")
    def tearDown(self):
        plate.make, gate.report.build = self.orig
        self.d.cleanup()
    def go(self, verdicts=None, **kw):
        plate.make = fake_make(verdicts or {}, self.calls)
        return gate.run(self.f, self.m, log=lambda *_: None, **kw)
    def test_everything_clear_is_a_pass_and_writes_the_gate_page_and_a_record(self):
        r = self.go()
        self.assertEqual(r["verdict"], "PASS"); self.assertEqual(sorted(self.calls), ["a", "b"])
        self.assertIn("**PASS**", open(os.path.join(self.f, "GATE.md")).read())
        self.assertTrue(records.latest(self.f)["gate"]["ok"])
    def test_a_check_stays_a_check_with_its_report_page_and_never_becomes_a_pass(self):     # NEGATIVE CONTROL
        r = self.go({"b": "CHECK"})
        self.assertEqual(r["verdict"], "CHECK"); self.assertEqual(r["counts"]["CHECK"], 1)
        row = [x for x in r["rows"] if x["step"] == "plate" and x["name"] == "b"][0]
        self.assertTrue(row["report"].endswith("b_report.html") and os.path.exists(row["report"]))
        md = open(os.path.join(self.f, "GATE.md")).read()
        self.assertIn("not a pass", md); self.assertIn("note for b", md)
    def test_one_block_makes_the_whole_gate_a_block(self):                                  # NEGATIVE CONTROL
        r = self.go({"a": "BLOCK", "b": "CHECK"})
        self.assertEqual(r["verdict"], "BLOCK")
        ns = argparse.Namespace(project=self.f, parts=None, no_export=True, no_plates=True, fresh=False, all_selftest=False, profile=None, strict=False)
        plate.make = fake_make({"a": "BLOCK"}, self.calls)
        self.assertEqual(cli.cmd_gate(argparse.Namespace(**{**vars(ns), "no_plates": False})), 1)
    def test_a_crashing_step_is_a_block_never_a_skip(self):                                  # NEGATIVE CONTROL
        r = self.go({"a": RuntimeError("bambu studio exploded")})
        row = [x for x in r["rows"] if x["name"] == "a" and x["step"] == "plate"][0]
        self.assertEqual(row["verdict"], "BLOCK"); self.assertIn("bambu studio exploded", row["text"]); self.assertEqual(r["verdict"], "BLOCK")
    def test_a_piece_whose_stl_has_not_changed_is_reused_and_a_changed_one_is_re_sliced(self):
        self.go(); self.calls.clear()
        r = self.go(do_export=False)
        self.assertEqual(self.calls, [])                                                       # nothing re-sliced
        self.assertTrue(all(x.get("reused") for x in r["rows"] if x["step"] == "plate"))
        self.assertTrue(any("REUSED" in x["text"] for x in r["rows"]))
        open(os.path.join(self.f, "model.scad"), "w").write(MODEL.replace("[20, 20, 10]", "[20, 20, 12]"))
        self.calls.clear(); self.go()
        self.assertEqual(self.calls, ["a"])                                                    # only the changed part
    def test_fresh_re_slices_everything(self):
        self.go(); self.calls.clear(); self.go(reuse=False, do_export=False)
        self.assertEqual(sorted(self.calls), ["a", "b"])
    def test_a_stale_stl_blocks_when_not_re_exported(self):                                  # NEGATIVE CONTROL
        self.go()
        later = os.path.getmtime(os.path.join(self.f, "stl", "a.stl")) + 100
        os.utime(os.path.join(self.f, "model.scad"), (later, later))
        r = self.go(do_export=False)
        self.assertEqual(r["verdict"], "BLOCK"); self.assertTrue(any("older than the model" in x["text"] for x in r["rows"]))
        self.assertTrue(any("not run" in x["text"] for x in r["rows"] if x["step"] == "plate"))       # no slicing on a stale design
    def test_parts_filters_and_an_unknown_part_is_an_error_not_a_pass(self):
        r = self.go(parts=["b"])
        self.assertEqual(self.calls, ["b"])
        self.calls.clear(); r = self.go(parts=["nope"])
        self.assertEqual(r["verdict"], "BLOCK"); self.assertIn("no [[export]] piece matches", r["rows"][0]["text"])
    def test_a_registry_with_unregistered_parts_is_a_check(self):
        open(os.path.join(self.f, "parts.toml"), "w").write('[[part]]\nname = "a"\nsection = "S"\nwhat = "part a"\n')
        r = self.go()
        row = [x for x in r["rows"] if x["step"] == "register"][0]
        self.assertEqual(row["verdict"], "CHECK"); self.assertIn("b", row["text"])
    def test_the_assembly_check_and_selftest_join_the_verdict(self):
        open(os.path.join(self.f, "selftest.toml"), "w").write('[[toolpath]]\nplate = "nope.3mf"\nexpect = "flag"\n')
        r = self.go()
        row = [x for x in r["rows"] if x["step"] == "selftest"][0]
        self.assertEqual(row["verdict"], "PASS"); self.assertIn("1 skipped", row["text"])
        open(os.path.join(self.f, "checks.toml"), "w").write('[[sweep]]\nname = "x"\nmove = ["ghost"]\nfixed = ["a"]\ndirection = [0, 0, -1]\ntravel = 5\n')
        r = self.go()
        row = [x for x in r["rows"] if x["step"] == "assembly"][0]
        self.assertEqual(row["verdict"], "BLOCK"); self.assertIn("could not run", row["text"])      # a part the model does not draw cannot be checked: not a pass
    def test_the_command_needs_a_model_and_exports(self):
        g = tempfile.mkdtemp(); project.init(os.path.join(g, "q"), "Empty Gate")
        ns = argparse.Namespace(project=os.path.join(g, "q"), parts=None, no_export=False, no_plates=False, fresh=False, all_selftest=False, profile=None, strict=False)
        self.assertEqual(cli.cmd_gate(ns), 1)
