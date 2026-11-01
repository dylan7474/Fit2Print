import json, shutil, subprocess
import pytest, trimesh
from fit2print import asbuilt, gcode, plate
from fit2print.settings import Settings

SCAD = """difference(){ union(){ cube([40,30,8]); translate([0,0,8]) cube([49,30,6]); }
  translate([12,15,-1]) cylinder(d=6.5,h=7.5,$fn=40); }"""
have = shutil.which("openscad") and shutil.which("bambu-studio")
pytestmark = pytest.mark.skipif(not have, reason="needs openscad and bambu-studio")


@pytest.fixture(scope="module")
def made(tmp_path_factory):
    d = tmp_path_factory.mktemp("ab")
    (d / "s.scad").write_text(SCAD)
    subprocess.run(["openscad", "-q", "-o", str(d / "s.stl"), str(d / "s.scad")], check=True)
    cfg = Settings.load(None)
    # the painted plate comes from plate.make (which paints); the plugged one from an auto-support profile
    r = plate.make(str(d / "s.stl"), str(d / "m"), cfg)
    prof = d / "prof"; shutil.copytree(plate.PROFILES, prof)
    f = prof / "process_0.28_manual_support.json"
    j = json.load(open(f)); j["support_type"] = "normal(auto)"; json.dump(j, open(f, "w"))
    auto, _ = plate.slice_stl(str(d / "s.stl"), str(d / "a"), "pla_black", str(prof), "s")
    lay = lambda p: gcode.parse(gcode.read_gcode(p), cfg.filament_area)[0]
    return dict(stl=str(d / "s.stl"), mesh=trimesh.load(str(d / "s.stl")), made=r, painted=lay(r["file"]), auto=lay(auto))


def test_painted_plate_matches_its_design(made):
    v, lines = asbuilt.check(made["painted"], made["mesh"])
    assert v == "PASS", lines


def test_plate_make_includes_the_asbuilt_verdict(made):
    assert made["made"]["verdict"] == "PASS", made["made"]["notes"]


def test_negative_control_auto_supports_plugging_the_pilot_BLOCK(made):
    v, lines = asbuilt.check(made["auto"], made["mesh"])
    assert v == "BLOCK" and any(l.startswith("FILLED") for l in lines), (v, lines)


def test_negative_control_a_plate_of_a_different_design_is_not_a_pass(made):
    other = trimesh.creation.box(extents=[49, 30, 14]); other.apply_translation(-other.bounds[0])     # the same size, but no pilot, no ledge
    v, lines = asbuilt.check(made["painted"], other)
    assert v != "PASS", "a plate that does not match its design must not pass"


def test_summarise_groups_nearby_finds_and_verdict_rules():
    res = {"filled": [(10, 1.0 + 0.3 * i, 20.0, 20.0, 30.0) for i in range(5)], "missing": [(3.0, 5.0, 100.0, 100.0)] * 2, "extra": []}
    feats = asbuilt.summarise(res)
    kinds = {f[0]: f[1] for f in feats}
    assert kinds["filled"] == 5 and kinds["missing"] == 2
    assert asbuilt.verdict(feats) == "BLOCK"
    assert asbuilt.verdict([f for f in feats if f[0] == "missing"]) == "PASS"          # two layers is noise (min 3)
    three = {"filled": [], "missing": [(3.0, 5.0 + i, 1.0, 1.0) for i in range(3)], "extra": []}
    assert asbuilt.verdict(asbuilt.summarise(three)) == "CHECK"
