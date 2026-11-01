import base64, io, json, os, re, shutil, subprocess
import pytest, trimesh
from PIL import Image
from fit2print import cli, gcode, plate, report
from fit2print.settings import Settings

SCAD = """difference(){ union(){ cube([40,30,8]); translate([0,0,8]) cube([49,30,6]); }
  translate([12,15,-1]) cylinder(d=6.5,h=7.5,$fn=40); }"""


def _synthetic_layers():
    def loop(z, x0, y0, x1, y1, step=1.0):
        out = ["; FEATURE: Outer wall", f"G1 Z{z:.2f} F1200", f"G1 X{x0} Y{y0} F6000"]
        pts = []
        for (ax, ay), (bx, by) in [((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))]:
            n = max(1, int(((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5 / step))
            pts += [(ax + (bx - ax) * k / n, ay + (by - ay) * k / n) for k in range(1, n + 1)]
        return out + [f"G1 X{x:.3f} Y{y:.3f} E0.05 F1800" for x, y in pts]
    lines = []
    for k in range(6):
        lines += loop(0.2 + 0.2 * k, 0, 0, 20, 20)
    return gcode.parse(lines)[0]


def test_a_spot_picture_is_a_real_png_of_the_requested_size_with_the_ring_drawn():
    layers = _synthetic_layers()
    png = Image.open(io.BytesIO(base64.b64decode(report.spot_png(layers, 1.0, 10, 10, title="x", size=300))))
    assert png.size == (300, 300)
    px = png.convert("RGB").load()
    seen = {px[i, j] for i in range(0, 300, 2) for j in range(0, 300, 2)}
    assert any(c[1] > c[0] + 60 and c[1] > c[2] + 20 for c in seen), "the green ring is missing"      # green ring
    assert any(sum(c) < 120 for c in seen), "the printed lines are missing"                           # black layer


def test_an_empty_first_layer_still_draws_a_picture():
    layers = {1.0: [("Custom", ("G1", 0, 0, 1, 1, 0, 0, 1.0, 0.1, 0), True)]}
    assert base64.b64decode(report.first_layer_png(layers, []))[:4] == b"\x89PNG"


needs = pytest.mark.skipif(not (shutil.which("openscad") and shutil.which("bambu-studio")), reason="needs openscad and bambu-studio")


@pytest.fixture(scope="module")
def plates(tmp_path_factory):
    d = tmp_path_factory.mktemp("rep")
    (d / "sh<elf>.scad").write_text(SCAD)
    subprocess.run(["openscad", "-q", "-o", str(d / "sh<elf>.stl"), str(d / "sh<elf>.scad")], check=True)
    good = plate.make(str(d / "sh<elf>.stl"), str(d / "good"), Settings.load(None))
    prof = d / "prof"; shutil.copytree(plate.PROFILES, prof)
    f = prof / "process_0.28_manual_support.json"
    j = json.load(open(f)); j["support_type"] = "normal(auto)"; json.dump(j, open(f, "w"))
    bad, _ = plate.slice_stl(str(d / "sh<elf>.stl"), str(d / "bad"), "pla_black", str(prof), "bad")
    return dict(stl=str(d / "sh<elf>.stl"), good=good["file"], bad=bad, dir=d)


@needs
def test_a_plugged_pilot_makes_a_BLOCK_report_with_a_picture_of_the_spot(plates):
    doc, overall = report.build(plates["bad"], [plates["stl"]])
    assert overall == "BLOCK" and "Support plastic inside a hole" in doc and "<span class='block'>BLOCK</span>" in doc
    assert len(re.findall(r"data:image/png;base64", doc)) >= 2            # at least the spot and the bed


@needs
def test_the_painted_plate_gives_a_report_that_is_not_a_BLOCK(plates):        # the control's twin
    doc, overall = report.build(plates["good"], [plates["stl"]])
    assert overall != "BLOCK" and "Support plastic inside a hole" not in doc


@needs
def test_file_names_are_escaped_in_the_html(plates):
    doc, _ = report.build(plates["bad"], [plates["stl"]])
    assert "sh<elf>" not in doc and "sh&lt;elf&gt;" in doc


@needs
def test_the_command_writes_the_page_and_its_exit_code_follows_the_verdict(plates, capsys):
    import argparse
    out = str(plates["dir"] / "r.html")
    assert cli.cmd_report(argparse.Namespace(plate=plates["bad"], stl=[plates["stl"]], out=out, profile=None)) == 1
    assert os.path.exists(out) and "Plate report" in open(out).read()
    assert cli.cmd_report(argparse.Namespace(plate=plates["good"], stl=[plates["stl"]], out=out, profile=None)) == 0
    assert cli.cmd_report(argparse.Namespace(plate="/no/such.3mf", stl=[], out=None, profile=None)) == 1


@needs
def test_plate_report_flag_writes_the_page_beside_the_plate_for_single_and_together_modes(plates, tmp_path):
    import argparse
    ns = argparse.Namespace(stl=[plates["stl"]], group=None, split=None, together=False, name=None, out=str(tmp_path / "o"), project=None, profile=None,
                            filament="pla_black", supports="auto", report=True)
    assert cli.cmd_plate(ns) == 0
    assert os.path.exists(tmp_path / "o" / "sh<elf>_report.html")
    c = plates["dir"] / "second.stl"; shutil.copy(plates["stl"], c)
    ns2 = argparse.Namespace(**{**vars(ns), "stl": [plates["stl"], str(c)], "together": True, "name": "duo", "out": str(tmp_path / "o2")})
    assert cli.cmd_plate(ns2) == 0
    assert os.path.exists(tmp_path / "o2" / "duo_report.html")
