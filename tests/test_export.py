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

class Groups(Export):
    def setUp(self):
        super().setUp()
        self.fake2 = os.path.join(self.d.name, "openscad2")
        open(self.fake2, "w").write(FAKE.replace("trimesh.creation.box(extents=(20, 10, 6)); m.apply_translation((50, 70, -3))",
            "trimesh.creation.box(extents=((20, 6, 6) if 'body' in part else (4, 4, 2))); m.apply_translation((50, 70, -3) if 'body' in part else (53, 70, 2))").format(py=sys.executable))
        os.chmod(self.fake2, 0o755)
        self.g = dict(model="model.scad", export=[dict(name="body", part="body", group="duo", colour="#111111"), dict(name="dot", part="dot", group="duo", colour="#ffffff")])
    def test_a_group_is_placed_as_one_so_a_piece_keeps_its_place_in_the_other(self):
        r = export.export(self.f, self.g, [self.fake2]); self.assertTrue(all(x["ok"] for x in r))
        body = trimesh.load(os.path.join(self.f, "stl", "body.stl")); dot = trimesh.load(os.path.join(self.f, "stl", "dot.stl"))
        lo = min(body.bounds[0][2], dot.bounds[0][2]); self.assertAlmostEqual(lo, 0, places=4)           # the group sits on the bed
        self.assertAlmostEqual(dot.bounds[0][2] - body.bounds[0][2], 7.0, places=3)                       # 7 mm above the body's foot, as drawn (1 - -6)
        self.assertAlmostEqual(dot.centroid[0] - body.centroid[0], 3.0, places=3)                          # 3 mm to the side, as drawn
    def test_a_piece_alone_is_still_centred_on_its_own(self):                                              # the old behaviour, unchanged
        r = export.export(self.f, dict(self.g, export=[dict(name="body", part="body"), dict(name="dot", part="dot")]), [self.fake2])
        dot = trimesh.load(os.path.join(self.f, "stl", "dot.stl")); self.assertAlmostEqual(dot.bounds[0][2], 0, places=4); self.assertAlmostEqual(float(dot.centroid[0]), 0, places=3)
    def test_one_bad_member_fails_the_whole_group_and_writes_nothing(self):                               # NEGATIVE CONTROL
        r = export.export(self.f, dict(self.g, export=[dict(name="body", part="body", group="duo"), dict(name="dot", part="NOTHING", group="duo")]), [self.fake2])
        self.assertFalse(r[0]["ok"]); self.assertFalse(r[1]["ok"]); self.assertIn("same group", r[0]["error"]); self.assertEqual(os.listdir(os.path.join(self.f, "stl")), [])
    def test_bad_colours_and_group_names_are_refused(self):
        for bad in (dict(colour="red"), dict(colour="#12345"), dict(group="../x")):
            with self.assertRaises(ValueError): export.pieces(dict(export=[dict(name="a", **bad)]))
    def test_groups_lists_the_pieces(self):
        self.assertEqual([p["name"] for p in export.groups(self.g)["duo"]], ["body", "dot"])


class ExportOrient(unittest.TestCase):
    """A piece printed the other way up than it is drawn."""
    FAKE = """#!{py}
import sys, trimesh
a = sys.argv; out = a[a.index("-o") + 1]
base = trimesh.creation.box(extents=(20, 10, 4)); base.apply_translation((0, 0, 2))
nub = trimesh.creation.box(extents=(4, 4, 6)); nub.apply_translation((0, 0, 7))          # a nub standing on top: 10 mm tall in all
trimesh.util.concatenate([base, nub]).export(out)
"""
    def setUp(self):
        self.d = tempfile.TemporaryDirectory(); self.f = os.path.join(self.d.name, "p"); project.init(self.f, "Orient Test")
        open(os.path.join(self.f, "model.scad"), "w").write("cube(1);")
        self.fake = os.path.join(self.d.name, "openscad"); open(self.fake, "w").write(self.FAKE.format(py=sys.executable)); os.chmod(self.fake, 0o755)
    def tearDown(self): self.d.cleanup()
    def _z_centroid(self, orient):
        m = dict(model="model.scad", export=[dict(name="p", part="p", **({"orient": orient} if orient else {}))])
        r = export.export(self.f, m, [self.fake]); self.assertTrue(r[0]["ok"], r)
        mesh = trimesh.load(os.path.join(self.f, "stl", "p.stl")); self.assertAlmostEqual(mesh.bounds[0][2], 0, places=3)
        return mesh.bounds[1][2], mesh.centroid[2]
    def test_flip_puts_the_heavy_slab_on_the_bed_nub_up_becomes_nub_down(self):
        h0, c0 = self._z_centroid(None); h1, c1 = self._z_centroid("flip_x"); h2, c2 = self._z_centroid("flip_y")
        self.assertAlmostEqual(h0, 10, places=2); self.assertAlmostEqual(h1, 10, places=2)
        self.assertLess(c0, 5); self.assertGreater(c1, c0 + 1)             # flipped: the slab is now on top of the nub, so the mass moves up
        self.assertAlmostEqual(c1, c2, places=2)
    def test_a_flipped_piece_is_still_a_valid_solid(self):
        m = dict(model="model.scad", export=[dict(name="p", part="p", orient="flip_x")])
        r = export.export(self.f, m, [self.fake]); self.assertTrue(r[0]["watertight"]); self.assertGreater(r[0]["volume"], 0)
    def test_an_unknown_orient_is_refused(self):                          # NEGATIVE CONTROL
        with self.assertRaises(ValueError):
            export.export(self.f, dict(model="model.scad", export=[dict(name="p", part="p", orient="upside_down")]), [self.fake])

if __name__ == "__main__":
    unittest.main()
