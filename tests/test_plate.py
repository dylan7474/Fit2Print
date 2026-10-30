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
            r = plate.make(self._stl(d, trimesh.util.concatenate([stem, bar]), "tee"), d)
            self.assertEqual(r["verdict"], "BLOCK", "an 18 mm shelf in the air was not blocked: the plate check is broken")
    def test_result_is_recorded_in_the_project(self):
        with tempfile.TemporaryDirectory() as d:
            cube = trimesh.creation.box(extents=(15, 15, 6)); cube.apply_translation((0, 0, 3))
            plate.make(self._stl(d, cube, "c"), os.path.join(d, "out"), project=d)
            rec = [json.loads(l) for l in open(os.path.join(d, "records", "plates.jsonl"))]
            self.assertEqual(rec[0]["part"], "c")

if __name__ == "__main__":
    unittest.main()
