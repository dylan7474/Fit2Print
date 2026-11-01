import os, shutil, sys, tempfile
import pytest
from fit2print import assemblycheck, project
from fit2print.cli import read_marker

pytestmark = pytest.mark.skipif(not shutil.which("openscad"), reason="needs openscad")

MODEL = """part = "assembly";
module plate() difference() { translate([-20,-20,0]) cube([40,40,10]); translate([0,0,-1]) cylinder(d=3.4,h=12,$fn=32); }
module block() translate([-20,-20,-20]) cube([40,40,20]);
if (part == "plate") plate();
if (part == "block") block();
if (part == "lid") translate([-10,-10,10]) cube([20,20,3]);
if (part == "bar") translate([-30,-2,16]) cube([60,4,4]);
if (part == "far") translate([200,200,0]) cube([5,5,5]);
if (part == "farwall") translate([200,200,40]) cube([5,5,5]);
"""

def make(tmp, checks):
    f = os.path.join(tmp, "p"); project.init(f, "Asm Test")
    open(os.path.join(f, "model.scad"), "w").write(MODEL)
    open(os.path.join(f, "fit2print.toml"), "a").write('\nmodel = "model.scad"\n')
    open(os.path.join(f, "checks.toml"), "w").write(checks)
    return f

LID = '[[sweep]]\nname = "lid on"\nmove = ["lid"]\nfixed = ["plate"]\ndirection = [0, 0, -1]\ntravel = 30\nstep = 2\n'
SCREW = '[[screw]]\nname = "plate screw"\nclear = ["plate"]\nthread = ["block"]\ndir = [0, 0, -1]\nclear_len = 10\nthread_len = 4\nat = [[0, 0, 10]]\n'

def run(checks):
    with tempfile.TemporaryDirectory() as t:
        f = make(t, checks)
        lines = []
        r = assemblycheck.run(f, read_marker(f), log=lines.append)
        return r, "\n".join(lines)

def test_a_clean_sweep_and_a_centred_screw_pass_and_both_controls_fire():
    r, out = run(LID + SCREW)
    assert r["ok"], out
    assert "ALL CLEAR" in out and out.count("control:") == 2

def test_a_bar_across_the_path_fails_the_sweep():                          # NEGATIVE CONTROL
    r, out = run(LID.replace('fixed = ["plate"]', 'fixed = ["plate", "bar"]'))
    assert not r["ok"] and "FAIL  lid on" in out and "PROBLEMS FOUND" in out

def test_a_screw_through_solid_fails_the_clearance():                      # NEGATIVE CONTROL
    r, out = run(SCREW.replace("at = [[0, 0, 10]]", "at = [[0, 0, 10], [10, 0, 10]]"))
    assert not r["ok"] and "plate screw 1" in out and "holes not lined up" in out
    assert any(x["name"] == "plate screw 0" and x["ok"] for x in r["results"])

def test_a_screw_that_misses_the_thread_part_fails_the_bite():             # NEGATIVE CONTROL
    r, out = run(SCREW.replace("thread_len = 4", "thread_len = 4").replace('thread = ["block"]', 'thread = ["far"]'))
    assert not r["ok"] and "bites only 0.0 mm" in out

def test_a_check_that_cannot_see_a_collision_is_reported_as_blind():       # NEGATIVE CONTROL: the control must fire
    blind = '[[sweep]]\nname = "nothing near"\nmove = ["far"]\nfixed = ["farwall"]\ndirection = [0, 0, -1]\ntravel = 20\nstep = 10\n'
    r, out = run(blind)
    assert r["parts_ok"] and not r["controls_ok"] and not r["ok"] and "CANNOT SEE" in out

def test_bad_checks_files_are_explained():
    for bad, msg in (('[[sweep]]\nname="x"\n', "needs move"), ('[[screw]]\nname="x"\n', "needs thread"),
                     ('[[sweep]]\nname="x"\nmove=["a"]\nfixed=["b"]\ndirection=[0,0,0]\ntravel=1\n', "not all zero")):
        with tempfile.TemporaryDirectory() as t:
            f = make(t, bad)
            with pytest.raises(ValueError, match=msg):
                assemblycheck.load_cases(f)

def test_a_part_the_model_does_not_draw_is_an_error_not_a_pass():
    with pytest.raises(ValueError, match="draws nothing"):
        run(LID.replace('"lid"', '"ghost"'))

def test_big_steps_are_warned_about_because_they_can_jump_a_thin_rib():
    r, out = run(LID.replace("step = 2", "step = 10").replace('fixed = ["plate"]', 'fixed = ["plate", "bar"]'))
    assert "WARNING: 10 mm steps" in out and r["ok"], "the 4 mm bar is stepped over at 10 mm: that is exactly what the warning is for"


def test_a_part_can_be_defined_by_an_openscad_snippet_and_is_checked_like_any_other():
    snippet = 'prelude = \'part = "none";\'\n[parts]\nlid2 = "translate([-10,-10,10]) cube([20,20,3]);"\nplate2 = "difference() { translate([-20,-20,0]) cube([40,40,10]); translate([0,0,-1]) cylinder(d=3.4,h=12,$fn=32); }"\n'
    checks = snippet + LID.replace('"lid"', '"lid2"').replace('"plate"', '"plate2"')
    r, out = run(checks)
    assert r["ok"] and "ALL CLEAR" in out, out


def test_a_container_closing_round_its_content_is_tested_by_the_content_growing():
    # a hollow box lowered over a block: the box 4 % bigger has a BIGGER cavity (no collision), the block 4 % bigger does collide
    parts = ('prelude = \'part = "none";\'\n[parts]\nbox = "difference() { translate([-30,-30,0]) cube([60,60,40]); translate([-26,-26,-1]) cube([52,52,36]); }"\n'
             'block = "translate([-25.5,-25.5,0]) cube([51,51,30]);"\n')
    sweep = '[[sweep]]\nname = "box over block"\nmove = ["box"]\nfixed = ["block"]\ndirection = [0, 0, -1]\ntravel = 10\nstep = 2\n'
    r, out = run(parts + sweep)
    assert r["ok"], out


# ---- probes, driver runs, rings -----------------------------------------------------------------
DRIVER = '[[driver]]\nname = "plate screw"\nparts = ["plate"]\nradius = 1.5\nlength = 25\ndir = [0, 0, -1]\nat = [[0, 0, 30]]\n'
RING = '[[ring]]\nname = "plate hole"\npart = "plate"\nr_out = 5\nr_in = 1.7\ndepth = 8\ndir = [0, 0, -1]\nat = [[0, 0, 9]]\n'
PROBE_PRELUDE = 'prelude = \'part = "none"; module plate() difference() { translate([-20,-20,0]) cube([40,40,10]); translate([0,0,-1]) cylinder(d=3.4,h=12,$fn=32); } module block() translate([-20,-20,-20]) cube([40,40,20]);\'\n'


def test_a_clear_driver_run_and_a_solid_ring_pass_with_their_controls():
    r, out = run(DRIVER + RING)
    assert r["ok"], out
    assert "driver run clear" in out and "plastic round the hole 100 %" in out or "plastic round the hole 9" in out
    assert out.count("control:") == 2


def test_a_driver_run_into_plastic_fails_and_a_marked_control_case_passes():      # NEGATIVE CONTROL
    r, out = run(DRIVER.replace("at = [[0, 0, 30]]", "at = [[0, 0, 30], [10, 0, 30]]"))
    assert not r["ok"] and "plate screw 2: driver run BLOCKED" in out
    r2, out2 = run(DRIVER.replace("at = [[0, 0, 30]]", "at = [[10, 0, 30]]") + "must_fail = true\n")
    assert r2["ok"] and "expected: this is a control" in out2


def test_a_ring_half_off_the_edge_fails_the_plastic_rule():                       # NEGATIVE CONTROL
    r, out = run(RING.replace("at = [[0, 0, 9]]", "at = [[0, 0, 9], [19, 0, 9]]"))
    assert not r["ok"] and "plate hole 2" in out and "needs 80 %" in out


def test_probes_must_be_empty_and_a_must_overlap_control_must_overlap():
    empty = PROBE_PRELUDE + '[[probe]]\nname = "plate sits on block"\nsnippet = "intersection() { plate(); block(); }"\n'
    r, out = run(empty)
    assert r["ok"], out
    bad = PROBE_PRELUDE + '[[probe]]\nname = "plate and a shifted block"\nsnippet = "intersection() { plate(); translate([0,0,5]) block(); }"\n'
    r2, out2 = run(bad)
    assert not r2["ok"] and "FAIL  plate and a shifted block" in out2
    ctl = PROBE_PRELUDE + '[[probe]]\nname = "block pushed into plate"\nmust_overlap = true\nsnippet = "intersection() { plate(); translate([0,0,5]) block(); }"\n'
    r3, out3 = run(ctl)
    assert r3["ok"], out3
    blind = PROBE_PRELUDE + '[[probe]]\nname = "no overlap anywhere"\nmust_overlap = true\nsnippet = "intersection() { plate(); block(); }"\n'
    r4, out4 = run(blind)
    assert not r4["ok"] and "cannot see a collision" in out4


def test_bad_driver_ring_probe_tables_are_explained():
    for bad, msg in (('[[driver]]\nname="x"\n', "needs parts"), ('[[ring]]\nname="x"\n', "needs part"), ('[[probe]]\nname="x"\n', "snippet or a part"),
                     ('[[ring]]\nname="x"\npart="p"\nr_out=1\nr_in=2\ndepth=1\ndir=[0,0,1]\nat=[[0,0,0]]\n', "r_in < r_out")):
        with tempfile.TemporaryDirectory() as t:
            f = make(t, bad)
            with pytest.raises(ValueError, match=msg):
                assemblycheck.load_cases(f)
