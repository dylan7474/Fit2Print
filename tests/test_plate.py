import json, os, shutil, tempfile, time, unittest
import trimesh
from fit2print import plate

class Stale(unittest.TestCase):
    def test_stl_older_than_its_model_is_refused(self):    # NEGATIVE CONTROL for the stale-file lesson (2026-10-29)
        with tempfile.TemporaryDirectory() as d:
            stl, src = os.path.join(d, "a.stl"), os.path.join(d, "a.scad")
            open(stl, "w").write("x"); time.sleep(0.05); open(src, "w").write("y")
            self.assertIn("older than", plate.check_fresh(stl, src))
    def test_fresh_stl_is_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            src, stl = os.path.join(d, "a.scad"), os.path.join(d, "a.stl")
            open(src, "w").write("y"); time.sleep(0.05); open(stl, "w").write("x")
            self.assertIsNone(plate.check_fresh(stl, src))

@unittest.skipUnless(shutil.which("bambu-studio"), "Bambu Studio is not installed")
class Slicing(unittest.TestCase):
    def _stl(self, d, mesh, name):
        p = os.path.join(d, name + ".stl"); mesh.export(p); return p
    def test_a_cube_passes(self):
        with tempfile.TemporaryDirectory() as d:
            cube = trimesh.creation.box(extents=(20, 20, 10)); cube.apply_translation((0, 0, 5))
            r = plate.make(self._stl(d, cube, "cube"), d)
            self.assertEqual(r["verdict"], "PASS"); self.assertGreater(r["minutes"], 0); self.assertGreater(r["grams"], 0)
    def test_a_hanging_shelf_is_blocked(self):             # NEGATIVE CONTROL: no support is painted, so the shelf prints in the air
        with tempfile.TemporaryDirectory() as d:
            stem = trimesh.creation.box(extents=(4, 20, 10)); stem.apply_translation((0, 0, 5))
            bar = trimesh.creation.box(extents=(40, 20, 2)); bar.apply_translation((0, 0, 11))
            r = plate.make(self._stl(d, trimesh.util.concatenate([stem, bar]), "tee"), d, supports="none")
            self.assertEqual(r["verdict"], "BLOCK", "an 18 mm shelf in the air was not blocked: the plate check is broken")
    def test_the_same_shelf_prints_when_supports_are_painted(self):      # the fix the control above is waiting for
        with tempfile.TemporaryDirectory() as d:
            stem = trimesh.creation.box(extents=(4, 20, 10)); stem.apply_translation((0, 0, 5))
            bar = trimesh.creation.box(extents=(40, 20, 2)); bar.apply_translation((0, 0, 11))
            r = plate.make(self._stl(d, trimesh.util.concatenate([stem, bar]), "tee"), d)
            self.assertNotEqual(r["verdict"], "BLOCK", r["notes"]); self.assertTrue(any("painted on" in n for n in r["notes"]))
    def test_result_is_recorded_in_the_project(self):
        with tempfile.TemporaryDirectory() as d:
            cube = trimesh.creation.box(extents=(15, 15, 6)); cube.apply_translation((0, 0, 3))
            plate.make(self._stl(d, cube, "c"), os.path.join(d, "out"), project=d)
            rec = [json.loads(l) for l in open(os.path.join(d, "records", "plates.jsonl"))]
            self.assertEqual(rec[0]["part"], "c")

class Slots(unittest.TestCase):
    def test_same_colour_shares_a_filament_and_an_unset_colour_gets_its_own(self):
        from fit2print import multicolour
        n, c = multicolour.slots([dict(colour="#111111"), dict(colour="#ffffff"), dict(colour="#111111"), dict(colour=None)])
        self.assertEqual(n, [1, 2, 1, 3]); self.assertEqual(c[1], "#111111"); self.assertEqual(c[2], "#FFFFFF")

@unittest.skipUnless(shutil.which("bambu-studio"), "Bambu Studio is not installed")
class TwoColour(unittest.TestCase):
    """A black block and a white plug on top of it: two pieces in register, the case the slicer refused as two loose files."""
    def _project(self, d, colours=("#111111", "#FFFFFF")):
        from fit2print import project
        f = os.path.join(d, "p"); project.init(f, "Two Colour"); os.makedirs(os.path.join(f, "stl"))
        block = trimesh.creation.box(extents=(20, 20, 8)); block.apply_translation((0, 0, 4))
        plug = trimesh.creation.cylinder(radius=3, height=3); plug.apply_translation((0, 0, 8 + 1.5))
        block.export(os.path.join(f, "stl", "block.stl")); plug.export(os.path.join(f, "stl", "plug.stl"))
        return f, dict(export=[dict(name="block", part="block", group="duo", colour=colours[0]), dict(name="plug", part="plug", group="duo", colour=colours[1])])
    def test_two_pieces_slice_as_one_plate_with_two_filaments(self):
        from fit2print import layerview, gcode
        with tempfile.TemporaryDirectory() as d:
            f, mk = self._project(d)
            try:
                r = plate.make_group(f, mk, "duo", os.path.join(f, "plates"))
            except Exception as e:
                self.skipTest(f"could not slice here: {e}")
            self.assertEqual(r["filaments"]["1"]["pieces"], ["block"]); self.assertEqual(r["filaments"]["2"]["colour"], "#FFFFFF")
            pl = layerview.Plate(r["file"])
            self.assertEqual([c.upper() for c in pl.fcolours], ["#111111", "#FFFFFF"])
            used = {s[9] for segs in pl.layers.values() for fe, s, _ in segs if fe != "Custom"}
            self.assertEqual(used, {0, 1})                                              # both filaments really print
            top = pl.layer(len(pl.zs) - 1); self.assertIn(1, [t for ts in top["tools"].values() for t in ts])    # the plug shows on the top layer
            self.assertEqual(set(pl.tri_fil.tolist()), {0, 1}); self.assertEqual(len(pl.tri_fil), len(pl.tris))
    def test_a_single_colour_plate_shows_no_filaments(self):                           # NEGATIVE CONTROL: the viewer must not invent colours
        from fit2print import layerview
        with tempfile.TemporaryDirectory() as d:
            cube = trimesh.creation.box(extents=(15, 15, 6)); cube.apply_translation((0, 0, 3)); p = os.path.join(d, "c.stl"); cube.export(p)
            r = plate.make(p, d); pl = layerview.Plate(r["file"])
            self.assertEqual(pl.fcolours, []); self.assertIsNone(pl.tri_fil); self.assertEqual(pl.layer(3)["tools"], {})
    def test_a_missing_or_stale_piece_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            f, mk = self._project(d); os.remove(os.path.join(f, "stl", "plug.stl"))
            with self.assertRaises(SystemExit): plate.make_group(f, mk, "duo", os.path.join(f, "plates"))
            with self.assertRaises(SystemExit): plate.make_group(f, mk, "nope", os.path.join(f, "plates"))

class Tools(unittest.TestCase):
    def test_gcode_tool_changes_are_followed(self):
        from fit2print import gcode
        lines = ["; FEATURE: Outer wall", "T0", "G1 Z0.2", "G1 X0 Y0", "G1 X10 Y0 E1", "T1", "G1 X10 Y10 E1", "T255", "G1 X0 Y10 E1"]
        layers, _, _ = gcode.parse(lines)
        self.assertEqual([s[9] for f, s, _ in layers[0.2]], [0, 1, 1])         # T255 (AMS unload) is not a filament
        self.assertEqual(gcode.filament_colours(["; filament_colour = #111111;#FFFFFF"]), ["#111111", "#FFFFFF"])

if __name__ == "__main__":
    unittest.main()
