import os, stat, sys, tempfile, unittest
import numpy as np, trimesh
from fit2print import export, project

FAKE = """#!{py}
import sys
a = sys.argv; out = a[a.index("-o") + 1]; part = [x for x in a if x.startswith("part=")][0]
import trimesh
if "NOTHING" in part: sys.exit(0)
if "BROKEN" in part: sys.exit(2)
m = trimesh.creation.box(extents=(20, 10, 6)); m.apply_translation((50, 70, -3))      # far from the origin and half below the bed, like a model drawn about its centre
m.export(out)
"""

class Export(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory(); self.f = os.path.join(self.d.name, "p"); project.init(self.f, "Export Test")
        open(os.path.join(self.f, "model.scad"), "w").write("cube(1);")
        self.fake = os.path.join(self.d.name, "openscad"); open(self.fake, "w").write(FAKE.format(py=sys.executable)); os.chmod(self.fake, 0o755)
        self.m = dict(model="model.scad", export=[dict(name="body", part="body"), dict(name="lid", part="lid")])
    def tearDown(self): self.d.cleanup()
    def test_each_piece_is_written_flat_on_the_bed_and_centred(self):
        r = export.export(self.f, self.m, [self.fake]); self.assertTrue(all(x["ok"] for x in r))
        m = trimesh.load(os.path.join(self.f, "stl", "body.stl")); lo, hi = m.bounds
        self.assertAlmostEqual(lo[2], 0, places=4); self.assertAlmostEqual((lo[0] + hi[0]) / 2, 0, places=3); self.assertAlmostEqual((lo[1] + hi[1]) / 2, 0, places=3)
        self.assertEqual(r[0]["size"], [20.0, 10.0, 6.0]); self.assertTrue(r[0]["watertight"])
    def test_a_piece_the_model_cannot_draw_is_reported_and_leaves_no_file(self):      # NEGATIVE CONTROLS
        r = export.export(self.f, dict(self.m, export=[dict(name="ghost", part="NOTHING"), dict(name="bad", part="BROKEN")]), [self.fake])
        self.assertFalse(r[0]["ok"]); self.assertFalse(r[1]["ok"]); self.assertEqual(os.listdir(os.path.join(self.f, "stl")), [])
    def test_no_export_tables_is_explained(self):
        with self.assertRaises(ValueError): export.export(self.f, dict(model="model.scad"), [self.fake])
    def test_a_name_with_path_tricks_is_refused(self):
        with self.assertRaises(ValueError): export.pieces(dict(export=[dict(name="../../etc/x")]))
    def test_a_model_outside_the_project_is_refused(self):
        for bad in ("/etc/passwd", "../x.scad", None):
            with self.assertRaises(ValueError): export.export(self.f, dict(model=bad, export=[dict(name="a")]), [self.fake])
    def test_missing_openscad_is_explained(self):
        r = export.export(self.f, self.m, ["/no/such/openscad"]); self.assertIn("not installed", r[0]["error"])

if __name__ == "__main__":
    unittest.main()
