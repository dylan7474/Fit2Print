import json, os, shutil, subprocess
import pytest, trimesh
from fit2print import plate
from fit2print.settings import Settings

SHELF = """difference(){ union(){ cube([40,30,8]); translate([0,0,8]) cube([49,30,6]); }
  translate([12,15,-1]) cylinder(d=6.5,h=7.5,$fn=40); }"""
have = shutil.which("openscad") and shutil.which("bambu-studio")
pytestmark = pytest.mark.skipif(not have, reason="needs openscad and bambu-studio")


@pytest.fixture(scope="module")
def parts(tmp_path_factory):
    d = tmp_path_factory.mktemp("tog")
    (d / "shelf.scad").write_text(SHELF)
    subprocess.run(["openscad", "-q", "-o", str(d / "shelf.stl"), str(d / "shelf.scad")], check=True)
    b = trimesh.creation.box(extents=[30, 20, 12]); b.apply_translation(-b.bounds[0]); b.export(str(d / "block.stl"))
    return dict(dir=d, shelf=str(d / "shelf.stl"), block=str(d / "block.stl"))


def test_two_parts_on_one_plate_each_painted_and_checked_on_its_own(parts, tmp_path):
    r = plate.make_together([parts["shelf"], parts["block"]], str(tmp_path), Settings.load(None), name="duo")
    assert r["verdict"] != "BLOCK", r["notes"]
    assert r["parts"]["shelf.stl"]["shelves"] == 1 and r["parts"]["shelf.stl"]["faces_painted"] > 0
    assert r["parts"]["block.stl"]["faces_painted"] == 0
    assert os.path.exists(r["file"])


def test_a_single_stl_or_two_with_the_same_name_is_refused(parts, tmp_path):
    with pytest.raises(SystemExit, match="two or more"):
        plate.make_together([parts["shelf"]], str(tmp_path))
    other = tmp_path / "x"; other.mkdir(); shutil.copy(parts["shelf"], other / "shelf.stl")
    with pytest.raises(SystemExit, match="same file name"):
        plate.make_together([parts["shelf"], str(other / "shelf.stl")], str(tmp_path))


def test_negative_control_auto_supports_on_a_shared_plate_BLOCK_and_name_the_part(parts, tmp_path):
    prof = tmp_path / "prof"; shutil.copytree(plate.PROFILES, prof)
    f = prof / "process_0.28_manual_support.json"
    j = json.load(open(f)); j["support_type"] = "normal(auto)"; json.dump(j, open(f, "w"))
    stls = [parts["shelf"], parts["block"]]
    dest, pl = plate.slice_stl(stls, str(tmp_path / "o"), "pla_black", str(prof), "duo")
    r = plate._judge(dest, pl, "duo", Settings.load(None), stls, None)
    assert r["verdict"] == "BLOCK" and any("shelf.stl: FILLED" in n for n in r["notes"]), r["notes"]


def test_mirror_twins_of_identical_size_are_both_painted(parts, tmp_path):
    m = trimesh.load(parts["shelf"])
    m.apply_transform(trimesh.transformations.reflection_matrix([0, 0, 0], [1, 0, 0])); m.invert()      # mirrored in x, faces turned back outward
    m.apply_translation(-m.bounds[0]); twin = str(tmp_path / "shelf_R.stl"); m.export(twin)
    r = plate.make_together([parts["shelf"], twin], str(tmp_path / "o"), Settings.load(None), name="twins")
    a, b = r["parts"]["shelf.stl"], r["parts"]["shelf_R.stl"]
    assert a["shelves"] == b["shelves"] == 1 and a["faces_painted"] > 0 and b["faces_painted"] > 0, r["parts"]
    assert r["verdict"] != "BLOCK", r["notes"]
