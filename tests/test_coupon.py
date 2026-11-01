import os, shutil, subprocess, tempfile, unittest
import trimesh
from fit2print import coupon

OPENSCAD = shutil.which("openscad")
PART = """difference() { cube([60, 40, 9]); translate([20, 20, -1]) cylinder(d = 2.5, h = 7.5, $fn = 24); }"""      # a plate 60 x 40 x 9 with a blind 2.5 mm hole open at the bed

@unittest.skipUnless(OPENSCAD, "OpenSCAD is not installed")
class Coupon(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory(); self.out = os.path.join(self.d.name, "c")
        scad = os.path.join(self.d.name, "part.scad"); open(scad, "w").write(PART)
        self.stl = os.path.join(self.d.name, "part.stl")
        subprocess.run([OPENSCAD, "-q", "--backend=manifold", "-o", self.stl, scad], check=True)
    def tearDown(self): self.d.cleanup()
    def box(self, name="c1", x0=10, x1=30, y0=10, y1=30): return dict(name=name, x0=x0, x1=x1, y0=y0, y1=y1)
    def test_a_coupon_is_cut_from_the_real_part_with_its_hole_and_its_coordinates(self):
        r = coupon.cut(self.stl, [self.box()], self.out)[0]
        self.assertTrue(r["ok"], r["error"]); self.assertTrue(r["watertight"])
        m = trimesh.load(r["file"]); lo, hi = m.bounds
        self.assertEqual([round(x, 3) for x in lo[:2]], [10, 10]); self.assertEqual([round(x, 3) for x in hi[:2]], [30, 30])     # still in the part's own coordinates
        whole = 20 * 20 * 9
        self.assertAlmostEqual(r["volume"], whole - 0.5 * 24 * 1.25 ** 2 * 0.258819 * 6.5, delta=0.5)                                        # the blind hole came with it
        self.assertLess(r["volume"], whole)
    def test_zmax_trims_the_top_without_touching_the_underside(self):
        r = coupon.cut(self.stl, [self.box()], self.out, zmax=4)[0]
        self.assertTrue(r["ok"], r["error"]); m = trimesh.load(r["file"])
        self.assertAlmostEqual(m.bounds[0][2], 0, places=3); self.assertAlmostEqual(m.bounds[1][2], 4, places=3)
    def test_several_coupons_one_call(self):
        rs = coupon.cut(self.stl, [self.box("a"), self.box("b", 35, 55, 5, 25)], self.out)
        self.assertTrue(all(r["ok"] for r in rs)); self.assertEqual(sorted(os.listdir(self.out)), ["a.json", "a.stl", "b.json", "b.stl"])
    # NEGATIVE CONTROLS: each must be refused with a message, leaving no file behind
    def test_a_box_beside_the_part_is_refused(self):
        r = coupon.cut(self.stl, [self.box(x0=100, x1=120)], self.out)[0]
        self.assertFalse(r["ok"]); self.assertIn("does not touch", r["error"]); self.assertEqual(os.listdir(self.out), [])
    def test_a_box_the_wrong_way_round_is_refused(self):
        r = coupon.cut(self.stl, [self.box(x0=30, x1=10)], self.out)[0]
        self.assertFalse(r["ok"]); self.assertIn("wrong way round", r["error"])
    def test_a_box_over_a_gap_inside_the_part_bounds_is_refused(self):
        scad = os.path.join(self.d.name, "slot.scad"); open(scad, "w").write("difference() { cube([60, 40, 9]); translate([20, -1, -1]) cube([20, 42, 11]); }")   # a slot right through
        slot = os.path.join(self.d.name, "slot.stl"); subprocess.run([OPENSCAD, "-q", "--backend=manifold", "-o", slot, scad], check=True)
        r = coupon.cut(slot, [self.box(x0=22, x1=38)], self.out)[0]
        self.assertFalse(r["ok"]); self.assertIn("no plastic", r["error"]); self.assertEqual(os.listdir(self.out), [])
    def test_a_zmax_below_the_underside_is_refused(self):
        with self.assertRaises(ValueError): coupon.cut(self.stl, [self.box()], self.out, zmax=-5)
    def test_duplicate_names_are_refused(self):
        with self.assertRaises(ValueError): coupon.cut(self.stl, [self.box("a"), self.box("a")], self.out)
    def test_a_missing_openscad_is_said_plainly(self):
        r = coupon.cut(self.stl, [self.box()], self.out, command=["/no/such/openscad"])[0]
        self.assertFalse(r["ok"]); self.assertIn("not installed", r["error"])
    def test_a_coupon_from_a_changed_part_is_recognised_as_stale(self):
        r = coupon.cut(self.stl, [self.box()], self.out)[0]
        self.assertIsNone(coupon.is_stale(r["file"]))
        open(self.stl, "ab").write(b"\n")                                                                                           # the part changes
        self.assertIn("has changed", coupon.is_stale(r["file"]))
        os.remove(r["file"][:-4] + ".json"); self.assertIn("no record", coupon.is_stale(r["file"]))

class Args(unittest.TestCase):
    def test_box_arguments(self):
        b = coupon.boxes_from_args([["a_1", "1", "2", "3", "4"]]); self.assertEqual(b[0], dict(name="a_1", x0=1.0, x1=2.0, y0=3.0, y1=4.0))
    def test_a_bad_name_is_refused(self):
        with self.assertRaises(ValueError): coupon.boxes_from_args([["Bad Name", "1", "2", "3", "4"]])

if __name__ == "__main__":
    unittest.main()
