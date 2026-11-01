import json, os, shutil, subprocess
import numpy as np, pytest, trimesh
from fit2print import gcode, plate, support
from fit2print.settings import Settings, ROOT

SCAD = """difference(){ union(){ cube([40,30,8]); translate([0,0,8]) cube([49,30,6]); }
  translate([12,15,-1]) cylinder(d=6.5,h=7.5,$fn=40); }"""
have_openscad = shutil.which("openscad") is not None
have_bambu = shutil.which("bambu-studio") is not None


def scad_mesh(tmp_path, name, text):
    if not have_openscad:
        pytest.skip("no openscad")
    (tmp_path / (name + ".scad")).write_text(text)
    subprocess.run(["openscad", "-q", "-o", str(tmp_path / (name + ".stl")), str(tmp_path / (name + ".scad"))], check=True)
    return trimesh.load(str(tmp_path / (name + ".stl")))


@pytest.fixture(scope="module")
def shelf(tmp_path_factory):
    if not have_openscad:
        pytest.skip("no openscad")
    d = tmp_path_factory.mktemp("shelf")
    (d / "shelf.scad").write_text(SCAD)
    subprocess.run(["openscad", "-q", "-o", str(d / "shelf.stl"), str(d / "shelf.scad")], check=True)
    return str(d / "shelf.stl")


def test_ledge_is_a_shelf_and_the_small_pilot_roof_is_not(shelf):
    m = trimesh.load(shelf)
    regs = support.shelves(m)
    assert len(regs) == 1 and abs(regs[0][1] - 8.0) < 0.5 and regs[0][6] > support.PAINT_SPAN
    small = [r for r in support.overhangs(m) if r[6] <= support.PAINT_SPAN]
    assert small, "the pilot's roof is an overhang the detector sees but must not paint"


def test_the_apex_of_a_bore_is_a_bridge_not_a_shelf(tmp_path):
    # a 134 mm tube bored along x: the bore closes at its apex in a long thin sliver. Measured along itself it is 60+ mm; it is nowhere far from the wall.
    m = scad_mesh(tmp_path, "tube", "difference(){translate([-67,-9,0])cube([134,18,14.5]);translate([-70,0,4.5])rotate([0,90,0])cylinder(d=9.6,h=140,$fn=64);}")
    spans = [r[6] for r in support.overhangs(m)]
    assert spans and max(spans) < support.PAINT_SPAN, spans
    assert support.shelves(m) == []


def test_a_plain_block_has_no_shelf(tmp_path):
    m = trimesh.creation.box(extents=[30, 30, 20]); m.apply_translation(-m.bounds[0])
    assert support.shelves(m) == []


def test_shallow_channel_bridge_is_not_supported(tmp_path):
    # a slot roof 1.2 mm above the bed is bridged, not supported (MIN_VOID)
    m = scad_mesh(tmp_path, "slot", "difference(){cube([40,30,10]);translate([-1,9,-1])cube([42,12,2.2]);}")
    assert support.shelves(m) == []


def _layers(support_xy, wall_box=(0.0, 0.0, 40.0, 30.0)):
    x0, y0, x1, y1 = wall_box
    seg = lambda a, b, c, d: ("G1", a, b, c, d, 0, 0, 1.0, 0.1, 0)
    layers = {1.0: [("Outer wall", seg(x0, y0, x1, y0), True), ("Outer wall", seg(x1, y1, x0, y1), True)]}
    layers[2.0] = [("Support", seg(x, y, x + 0.2, y), True) for x, y in support_xy for _ in range(2)]
    return layers


def test_support_in_a_closed_hole_is_reported_and_outside_is_not(tmp_path):
    m = scad_mesh(tmp_path, "holed", "difference(){cube([40,30,6]);translate([12,15,-1])cylinder(d=6.5,h=3,$fn=40);translate([12,15,2])cylinder(d=6.5,h=1,$fn=40);translate([12,15,-1])cylinder(d=6.5,h=1,$fn=40);}")
    inside = [(12 + 0.2 * i, 15) for i in range(-6, 7)]
    assert support.holes_with_support(m, _layers(inside)), "support plugging a pilot must be reported"
    assert support.holes_with_support(m, _layers([(30, 5)])) == []
    # deliberate (painted) support is allowed where a region says so
    assert support.holes_with_support(m, _layers(inside), allow=[(100, 2.0, 5, 20, 8, 22, 8)]) == []


def fake_plate(path, names):
    import zipfile
    model = "<resources>" + "".join(f'<object id="{2 * i + 2}" type="model"><components><component p:path="/3D/Objects/object_{i + 1}.model" objectid="{2 * i + 1}"/></components></object>' for i in range(len(names))) + "</resources>"
    cfg = "".join(f'<object id="{2 * i + 2}"><metadata key="name" value="{n}"/></object>' for i, n in enumerate(names))
    with zipfile.ZipFile(path, "w") as f:
        f.writestr("3D/3dmodel.model", model); f.writestr("Metadata/model_settings.config", cfg)
        for i in range(len(names)):
            f.writestr(f"3D/Objects/object_{i + 1}.model", "")


def test_single_object_paint_refuses_a_plate_with_two(tmp_path):
    fake_plate(tmp_path / "x.3mf", ["a.stl", "b.stl"])
    with pytest.raises(ValueError, match="one object only"):
        support.paint(str(tmp_path / "x.3mf"), trimesh.creation.box(), [], str(tmp_path / "o.3mf"))


def test_objects_are_found_by_name_and_a_missing_name_is_an_error(tmp_path):
    import zipfile
    fake_plate(tmp_path / "x.3mf", ["a.stl", "b.stl"])
    d = tmp_path / "u"; zipfile.ZipFile(tmp_path / "x.3mf").extractall(d)
    objs = support.plate_objects(str(d))
    assert set(objs) == {"a.stl", "b.stl"} and objs["b.stl"].endswith("object_2.model")
    with pytest.raises(ValueError, match="not on the plate: c.stl"):
        support.paint_plate(str(tmp_path / "x.3mf"), {"c.stl": (trimesh.creation.box(), [])}, str(tmp_path / "o.3mf"))


@pytest.mark.skipif(not (have_openscad and have_bambu), reason="needs openscad and bambu-studio")
def test_plate_paints_the_shelf_keeps_the_pilot_clear_and_passes(shelf, tmp_path):
    r = plate.make(shelf, str(tmp_path), Settings.load(None))
    assert r["verdict"] != "BLOCK", r["notes"]
    assert any("painted on" in n for n in r["notes"])


@pytest.mark.skipif(not (have_openscad and have_bambu), reason="needs openscad and bambu-studio")
def test_negative_control_auto_supports_fill_the_pilot(shelf, tmp_path):
    prof = tmp_path / "prof"; shutil.copytree(plate.PROFILES, prof)
    f = prof / "process_0.28_manual_support.json"
    d = json.load(open(f)); d["support_type"] = "normal(auto)"; json.dump(d, open(f, "w"))
    dest, _ = plate.slice_stl(shelf, str(tmp_path / "o"), "pla_black", str(prof), "auto")
    layers, _, _ = gcode.parse(gcode.read_gcode(dest), Settings.load(None).filament_area)
    assert support.holes_with_support(trimesh.load(shelf), layers), "the old failure must be caught"


def test_names_with_xml_special_characters_are_matched(tmp_path):
    import zipfile
    fake_plate(tmp_path / "x.3mf", ["a&amp;b.stl", "c&lt;d&gt;.stl"])
    d = tmp_path / "u"; zipfile.ZipFile(tmp_path / "x.3mf").extractall(d)
    assert set(support.plate_objects(str(d))) == {"a&b.stl", "c<d>.stl"}
