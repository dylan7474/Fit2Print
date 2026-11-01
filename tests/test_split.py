import json, os, shutil, subprocess, tempfile, unittest
import numpy as np, trimesh
from fit2print import split

OPENSCAD = shutil.which("openscad")
SLAB = "difference() { cube([520, 300, 40]); translate([200, 100, -1]) cube([120, 100, 42]); translate([40,40,-1]) cylinder(d=6,h=42); }"   # too big for the bed in x and y, with a window and a hole

def make(d, name, scad):
    f = os.path.join(d, name + ".scad"); open(f, "w").write(scad)
    out = os.path.join(d, name + ".stl"); subprocess.run([OPENSCAD, "-q", "--backend=manifold", "-o", out, f], check=True)
    return out

class Pure(unittest.TestCase):
    def test_the_fewest_pieces_that_fit(self):
        self.assertEqual(split.plan_counts([100, 100, 100], (244, 244, 254)), (1, 1, 1))
        self.assertEqual(split.plan_counts([520, 300, 40], (244, 244, 254)), (3, 2, 1))
        n = split.plan_counts([300, 200, 384], (244, 244, 254))
        self.assertEqual(int(np.prod(n)), 4)                      # the radio: 384 tall needs two, 300 wide needs two... a piece may lie down, so fewer cuts are needed
    def test_a_piece_may_lie_down_to_fit(self):
        self.assertIsNone(split.fits([300, 100, 100], (244, 244, 254)))
        self.assertIsNotNone(split.fits([250, 100, 100], (244, 244, 254)))                    # ...but 250 fits standing up (z has 254)
    def test_nothing_fits_a_tiny_bed(self):                                                     # NEGATIVE CONTROL
        self.assertIsNone(split.plan_counts([1000, 1000, 1000], (50, 50, 50), max_pieces=8))

@unittest.skipUnless(OPENSCAD, "OpenSCAD is not installed")
class Split(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = tempfile.mkdtemp(); cls.stl = make(cls.d, "slab", SLAB)
        cls.out = os.path.join(cls.d, "out"); cls.r = split.split(cls.stl, cls.out, base="slab")
    @classmethod
    def tearDownClass(cls): shutil.rmtree(cls.d, ignore_errors=True)
    def test_every_section_fits_the_bed_and_lies_on_the_bed(self):
        self.assertTrue(self.r["ok"], self.r["warnings"]); self.assertEqual(len(self.r["pieces"]), 6)
        for p in self.r["pieces"]:
            m = trimesh.load(p["file"]); lo, hi = m.bounds
            self.assertAlmostEqual(lo[2], 0, places=3)
            self.assertLessEqual(hi[0] - lo[0], 244.01); self.assertLessEqual(hi[1] - lo[1], 244.01); self.assertLessEqual(hi[2] - lo[2], 254.01)
    def test_nothing_is_lost_the_sections_plus_the_pin_holes_are_the_part(self):
        self.assertLess(self.r["volume_mismatch"], 0.002)
        whole = trimesh.load(self.stl).volume
        self.assertAlmostEqual((self.r["volume_pieces"] + self.r["volume_pin_holes"]) / whole, 1.0, places=3)
    def test_every_cut_has_pins_and_the_pins_are_made(self):
        self.assertTrue(all(len(c["pins"]) >= 2 for c in self.r["cuts"]))
        n = sum(len(c["pins"]) for c in self.r["cuts"])
        self.assertEqual(self.r["pins"]["needed"], n); self.assertGreater(self.r["pins"]["count"], n)           # with spares
        self.assertEqual(sum(p["holes"] for p in self.r["pieces"]), 2 * n)                                       # two holes per pin, none lost, none doubled
        self.assertTrue(os.path.exists(self.r["pins"]["file"]))
    def test_the_cuts_keep_clear_of_the_window(self):
        xs = [c["pos"] for c in self.r["cuts"] if c["axis"] == "x"]
        self.assertTrue(all(not (195 < x < 325) for x in xs), xs)                                                 # the window spans x 200-320: planes through it have a longer outline
    def test_pin_holes_stay_clear_of_other_cuts_and_edges(self):
        for c in self.r["cuts"]:
            for a, b in c["pins"]:
                for c2 in self.r["cuts"]:
                    if c2["axis"] != c["axis"]:
                        coord = a if (("xyz".index(c2["axis"]) - "xyz".index(c["axis"])) % 3 == 1) else b
                        self.assertGreater(abs(coord - c2["pos"]), 1.65 + 1.2 - 1e-6)
    def test_a_small_scale_needs_no_cut_at_all(self):
        o = os.path.join(self.d, "small"); r = split.split(self.stl, o, base="slab", scale=0.4)
        self.assertEqual(len(r["pieces"]), 1); self.assertEqual(r["cuts"], []); self.assertIsNone(r["pins"]["file"]); self.assertEqual(r["scale"], 0.4)
        self.assertAlmostEqual(r["pieces"][0]["size"][0], 520 * 0.4, delta=0.2)
    def test_manual_cuts_are_honoured(self):
        o = os.path.join(self.d, "manual"); r = split.split(self.stl, o, base="slab", cuts={"x": [260.0]}, bed=(400, 400, 400))
        self.assertEqual(len(r["pieces"]), 2); self.assertEqual([(c["axis"], c["pos"]) for c in r["cuts"]], [("x", 260.0)])
    def test_no_pins_when_asked(self):
        o = os.path.join(self.d, "nopins"); r = split.split(self.stl, o, base="slab", pins=False)
        self.assertEqual(r["pins"]["count"], 0); self.assertEqual(sum(p["holes"] for p in r["pieces"]), 0); self.assertLess(r["volume_mismatch"], 0.0001)
    def test_the_record_is_written(self):
        j = json.load(open(os.path.join(self.out, "slab_split.json"))); self.assertEqual(j["summary"], self.r["summary"])
    # NEGATIVE CONTROLS: each must say so loudly, never produce quiet nonsense
    def test_a_part_too_big_for_the_piece_limit_is_refused_with_advice(self):
        o = os.path.join(self.d, "toobig"); r = split.split(self.stl, o, base="slab", max_pieces=2)
        self.assertFalse(r["ok"]); self.assertEqual(r["pieces"], []); self.assertIn("smaller scale", r["warnings"][0])
    def test_thin_walls_get_no_pins_and_a_warning(self):
        thin = make(self.d, "thin", "difference() { cube([400, 100, 20]); translate([1.5,1.5,-1]) cube([397, 97, 30]); }")       # a 1.5 mm wall box
        r = split.split(thin, os.path.join(self.d, "thinout"), base="thin")
        self.assertTrue(any("room for only" in w for w in r["warnings"]), r["warnings"]); self.assertEqual(r["pins"]["count"], 0)
        self.assertLess(r["volume_mismatch"], 0.002)
    def test_a_hole_that_breaks_out_of_a_wall_is_caught_by_the_volume_check(self):
        plate = make(self.d, "plate", "cube([400, 100, 12]);")                                                                  # 12 mm thick; a 20 mm pin hole cannot fit
        r = split.split(plate, os.path.join(self.d, "broke"), base="plate", pin_d=20.0, wall=-9.9, bed=(300, 300, 300))
        self.assertFalse(r["ok"]); self.assertTrue(any("off the part's volume" in w for w in r["warnings"]), r["warnings"])
    def test_a_missing_openscad_is_said_plainly(self):
        with self.assertRaises(ValueError): split.split(self.stl, os.path.join(self.d, "noscad"), base="slab", command=["/no/such/openscad"])

if __name__ == "__main__":
    unittest.main()

@unittest.skipUnless(OPENSCAD, "OpenSCAD is not installed")
class Paths(unittest.TestCase):
    def test_a_relative_output_folder_works(self):                # found 2026-11-01: OpenSCAD runs in another folder, so a relative path found no part and every section came out "empty"
        d = tempfile.mkdtemp(); cwd = os.getcwd()
        try:
            stl = make(d, "slab", SLAB); os.chdir(d)
            r = split.split("slab.stl", "rel_out", base="slab")
            self.assertEqual(len(r["pieces"]), 6); self.assertTrue(r["ok"], r["warnings"])
        finally:
            os.chdir(cwd); shutil.rmtree(d, ignore_errors=True)
    def test_a_part_openscad_cannot_read_is_a_failure_not_an_empty_gap(self):       # NEGATIVE CONTROL
        d = tempfile.mkdtemp()
        try:
            stl = make(d, "slab", SLAB); bad = os.path.join(d, "fake_openscad")
            open(bad, "w").write("#!/bin/sh\necho \"WARNING: Can't open import file 'x.stl'\" >&2\nexit 0\n"); os.chmod(bad, 0o755)
            r = split.split(stl, os.path.join(d, "o"), base="slab", command=[bad])
            self.assertFalse(r["ok"]); self.assertTrue(any("could not cut" in w for w in r["warnings"]), r["warnings"])
        finally:
            shutil.rmtree(d, ignore_errors=True)

@unittest.skipUnless(OPENSCAD, "OpenSCAD is not installed")
class Where(unittest.TestCase):
    def test_the_cut_avoids_a_window_even_though_the_window_makes_the_outline_shorter(self):       # found on the arch clock: 'shortest outline' steered the cut INTO the window
        d = tempfile.mkdtemp()
        try:
            stl = make(d, "w", "difference() { cube([300, 300, 20]); translate([100, 130, -1]) cube([100, 40, 22]); }")      # a window 100 x 40 across the middle
            import trimesh as T
            m = T.load(stl)
            self.assertLess(split.outline_length(m, 1, 150), split.outline_length(m, 1, 60))                                  # the premise: through the window is shorter
            p, c, b = split.best_cut(m, 1, 150.0, 30.0, 0, 300)                                                                # nominal 150 is in the window; the window spans y 130-170
            self.assertTrue(p < 130 - 0.5 or p > 170 + 0.5, p)
            m2 = T.load(make(d, "w2", "difference() { cube([300, 300, 20]); translate([100, 130, -1]) cube([100, 40, 22]); }"))
            p2, _, _ = split.best_cut(m2, 0, 150.0, 60.0, 0, 300)                                                              # along x the window spans 100-200: a plane at 150 is inside it
            self.assertTrue(p2 < 100 - 0.5 or p2 > 200 + 0.5, p2)
        finally:
            shutil.rmtree(d, ignore_errors=True)

@unittest.skipUnless(OPENSCAD, "OpenSCAD is not installed")
class Project(unittest.TestCase):
    def setUp(self):
        from fit2print import project
        self.d = tempfile.mkdtemp(); self.f = os.path.join(self.d, "p"); project.init(self.f, "Split Test")
        open(os.path.join(self.f, "model.scad"), "w").write("cube(1);")
        os.makedirs(os.path.join(self.f, "stl")); make(os.path.join(self.f, "stl"), "slab", SLAB)
        open(os.path.join(self.f, "fit2print.toml"), "a").write('\nmodel = "model.scad"\n\n[[split]]\nname = "slab"\npart = "slab"\n')
        t = os.path.getmtime(os.path.join(self.f, "model.scad")) + 5; os.utime(os.path.join(self.f, "stl", "slab.stl"), (t, t))     # the STL is newer than the model: fresh
    def tearDown(self): shutil.rmtree(self.d, ignore_errors=True)
    def run_cli(self, *a):
        from fit2print import cli
        return cli.main(["split", *a])
    def test_a_project_folder_cuts_every_split_table(self):
        self.assertEqual(self.run_cli(self.f), 0)
        self.assertTrue(os.path.exists(os.path.join(self.f, "sections", "slab_s01.stl"))); self.assertTrue(os.path.exists(os.path.join(self.f, "sections", "slab_split.json")))
    def test_a_stale_part_is_never_cut(self):                                                                                       # NEGATIVE CONTROL
        t = os.path.getmtime(os.path.join(self.f, "stl", "slab.stl")) + 100; os.utime(os.path.join(self.f, "model.scad"), (t, t))        # the model is edited after the export
        self.assertEqual(self.run_cli(self.f), 1); self.assertFalse(os.path.exists(os.path.join(self.f, "sections")))
    def test_a_project_with_no_split_table_says_so(self):
        open(os.path.join(self.f, "fit2print.toml"), "w").write('id = "x"\nname = "x"\nkind = "design-and-print"\nadapter = "generic"\nprinter_profile = "bambu_a1_pla"\n')
        self.assertEqual(self.run_cli(self.f), 1)


# ---- plate --split ----------------------------------------------------------
def _fake_split(tmp_path, ok=True):
    import json
    src = tmp_path / "p.stl"; src.write_text("x")
    sec = tmp_path / "p_s01.stl"; sec.write_text("x")
    pins = tmp_path / "p_pins.stl"; pins.write_text("x")
    d = {"ok": ok, "summary": "s", "source": str(src), "pieces": [{"file": str(sec)}], "pins": {"count": 1, "file": str(pins)}}
    j = tmp_path / "p_split.json"; j.write_text(json.dumps(d))
    return j, src, sec, pins


def _args(j, tmp_path):
    import argparse
    return argparse.Namespace(split=str(j), out=str(tmp_path / "o"), filament="pla_black", project=None)


def test_plate_split_refuses_failed_split(tmp_path, capsys):
    from fit2print import cli
    j, *_ = _fake_split(tmp_path, ok=False)
    assert cli._plate_split(_args(j, tmp_path), None) == 1
    assert "REFUSED" in capsys.readouterr().out


def test_plate_split_refuses_missing_section(tmp_path, capsys):
    from fit2print import cli
    j, src, sec, pins = _fake_split(tmp_path)
    sec.unlink()
    assert cli._plate_split(_args(j, tmp_path), None) == 1
    assert "missing" in capsys.readouterr().out


def test_plate_split_refuses_stale_sections(tmp_path, capsys):
    import os
    from fit2print import cli
    j, src, sec, pins = _fake_split(tmp_path)
    os.utime(sec, (1000, 1000)); os.utime(pins, (1000, 1000))
    assert cli._plate_split(_args(j, tmp_path), None) == 1
    assert "newer" in capsys.readouterr().out


def test_plate_split_one_block_fails_the_run(tmp_path, monkeypatch, capsys):
    from fit2print import cli, plate
    j, *_ = _fake_split(tmp_path)
    seen = []
    def fake(f, *a, **k):
        seen.append(f)
        return {"part": "x", "verdict": "BLOCK" if f.endswith("pins.stl") else "PASS", "minutes": 5, "grams": 1, "file": "f", "notes": []}
    monkeypatch.setattr(plate, "make", fake)
    assert cli._plate_split(_args(j, tmp_path), None) == 1
    assert len(seen) == 2
    assert "BLOCKED" in capsys.readouterr().out
