import argparse, os, shutil, subprocess
import pytest, trimesh
from fit2print import calibrate, cli, plate, support
from fit2print.settings import Settings

HOLES = "2.5:2.2,3.0:2.75,3.3:3.05,4.2:3.95,5.0:4.75,6.0:5.8,9.6:9.4"
OUTER = "20:20.1,40:40.15"
needs_scad = pytest.mark.skipif(not shutil.which("openscad"), reason="needs openscad")
needs_all = pytest.mark.skipif(not (shutil.which("openscad") and shutil.which("bambu-studio")), reason="needs openscad and bambu-studio")


def test_the_phonosphere_measurements_give_the_numbers_phonosphere_got():
    h, o = calibrate.pairs(HOLES, "holes"), calibrate.pairs(OUTER, "outer")
    hc, oc, notes = calibrate.compensation(h, o)
    assert hc == 0.25 and oc == -0.1 and notes == []          # holes of 3 mm and up average 0.233 -> 0.25; blocks print 0.125 big -> -0.1


def test_the_2_5_mm_hole_is_reported_not_averaged():
    hc, _, _ = calibrate.compensation([(2.5, 2.0), (3.0, 2.9), (4.0, 3.9)], [])
    assert hc == 0.1                                           # the 2.5 mm hole (0.5 out) must not drag it up


def test_nothing_measured_says_so_instead_of_pretending_zero_is_a_measurement():
    hc, oc, notes = calibrate.compensation([], [])
    assert (hc, oc) == (0.0, 0.0) and len(notes) == 2 and all("not measured" in n for n in notes)


def test_impossible_measurements_are_refused():                 # NEGATIVE CONTROLS
    for bad, msg in (("3.0:9.0", "more than a printer does"), ("3.0", "DRAWN:MEASURED"), ("a:b", "DRAWN:MEASURED"), ("3.0:2.75;4:3.9", "DRAWN:MEASURED")):
        with pytest.raises(ValueError, match=msg):
            calibrate.pairs(bad, "holes")
    for kw, msg in ((dict(shelf_ok=4), "card only has"), (dict(bridge_ok=7), "card only has"), (dict(pin="snug"), "ok, tight or loose"), (dict(flow=0.1), "between 1 and 60")):
        with pytest.raises(ValueError, match=msg):
            calibrate.record("x", **kw)


def test_a_bridge_above_the_base_limit_does_not_loosen_it():
    base = Settings.load(None)
    rec = calibrate.record("x", bridge_ok=15)
    assert rec["bridge_check"] == min(15, base.bridge_check)
    assert calibrate.record("y", bridge_ok=6)["bridge_check"] == 6


def test_the_profile_round_trips_and_carries_what_was_measured(tmp_path):
    rec = calibrate.record("Test PLA 0.28", holes=HOLES, outer=OUTER, pin="ok", bridge_ok=10, shelf_ok=8, wall_ok=1.2, lean_ok=55, flow=14, today="2026-11-01")
    path = calibrate.write_profile(rec, str(tmp_path / "sub" / "p.toml"))
    c = Settings.load(path)
    assert c.name == "Test PLA 0.28" and c.flow_limit == 14 and c.bridge_check == 10 and c.shelf_ok == 8
    assert (c.hole_comp, c.outer_comp, c.wall_ok, c.lean_ok, c.pin) == (0.25, -0.1, 1.2, 55, "ok")
    base = Settings.load(None)
    assert c.cantilever_block == base.cantilever_block and c.air_block == base.air_block         # the rest of the base profile is kept


def test_an_uncalibrated_profile_keeps_the_old_defaults():
    c = Settings.load(None)
    assert c.shelf_ok == 5.0 and c.hole_comp == 0.0 and c.pin is None


def test_offsets_and_log_are_written_and_the_log_only_ever_grows(tmp_path):
    rec = calibrate.record("A", holes=HOLES, outer=OUTER, today="2026-11-01")
    p = calibrate.write_offsets(rec, str(tmp_path))
    t = open(p).read()
    assert "hole_comp = 0.25;" in t and "function hole_d(d) = d + hole_comp;" in t
    calibrate.log(rec, str(tmp_path)); calibrate.log(calibrate.record("B", today="2026-11-02"), str(tmp_path))
    rows = [l for l in open(tmp_path / "CALIBRATION.md") if l.startswith("| 2026")]
    assert len(rows) == 2 and "| A |" in rows[0] and "| B |" in rows[1]


@needs_scad
def test_the_card_draws_with_every_part_the_sheet_talks_about(tmp_path):
    stl, sheet = calibrate.card(str(tmp_path))
    m = trimesh.load(stl)
    assert m.is_watertight and 100 < m.extents[0] < 140 and m.extents[2] >= 10
    t = open(sheet).read()
    for opt in ("--holes", "--outer", "--pin", "--wall-ok", "--bridge-ok", "--shelf-ok", "--lean-ok", "--flow"):
        assert opt in t


def test_the_command_writes_a_profile_and_refuses_a_slip(tmp_path, capsys):
    ns = lambda **k: argparse.Namespace(**{**dict(action="record", name="Cmd Test", base=None, profile_out=str(tmp_path / "p.toml"), project=str(tmp_path), holes=HOLES, outer=OUTER,
                                                  pin="ok", bridge_ok=None, shelf_ok=5.0, wall_ok=None, lean_ok=None, flow=None, out="x"), **k})
    assert cli.cmd_calibrate(ns()) == 0 and os.path.exists(tmp_path / "p.toml") and os.path.exists(tmp_path / "printer_offsets.scad")
    assert "hole_comp +0.25" in capsys.readouterr().out
    assert cli.cmd_calibrate(ns(holes="3.0:9.0", profile_out=str(tmp_path / "q.toml"))) == 1 and not os.path.exists(tmp_path / "q.toml")
    assert cli.cmd_calibrate(ns(name=None)) == 1


@needs_all
def test_a_calibrated_shelf_limit_really_changes_what_the_plate_does(tmp_path):
    (tmp_path / "s.scad").write_text("difference(){ union(){ cube([40,30,8]); translate([0,0,8]) cube([49,30,6]); } translate([12,15,-1]) cylinder(d=6.5,h=7.5,$fn=40); }")
    subprocess.run(["openscad", "-q", "-o", str(tmp_path / "s.stl"), str(tmp_path / "s.scad")], check=True)
    default = Settings.load(None)
    assert len(support.shelves(trimesh.load(str(tmp_path / "s.stl")), span=default.shelf_ok)) == 1
    assert plate.make(str(tmp_path / "s.stl"), str(tmp_path / "a"), default)["verdict"] != "BLOCK"           # an 8 mm ledge is painted at the default 5 mm limit
    lax = Settings.load(calibrate.write_profile(calibrate.record("lax", shelf_ok=11), str(tmp_path / "lax.toml")))
    assert support.shelves(trimesh.load(str(tmp_path / "s.stl")), span=lax.shelf_ok) == []                   # a printer that bridges 11 mm shelves clean needs none
    r = plate.make(str(tmp_path / "s.stl"), str(tmp_path / "b"), lax)
    assert not any("painted on" in n for n in r["notes"])
