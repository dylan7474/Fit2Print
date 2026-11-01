import os, shutil, subprocess, json
import pytest, trimesh
from fit2print import gcode, selftest, plate
from fit2print.settings import Settings


def test_the_synthetic_cases_pass_with_no_files():
    r = selftest.run(None, log=lambda *_: None)
    assert r["ok"] and r["passed"] == 2 and r["failed"] == 0


def _manifest(tmp_path, body):
    p = tmp_path / "selftest.toml"; p.write_text(body); return str(p)


def test_a_missing_fixture_is_skipped_and_said_so_and_strict_fails_it(tmp_path):
    m = _manifest(tmp_path, '[[toolpath]]\nplate = "nope.3mf"\nexpect = "flag"\n')
    lines = []
    r = selftest.run(m, log=lines.append)
    assert r["ok"] and r["skipped"] == 1 and any(l.startswith("SKIP") for l in lines)
    assert not selftest.run(m, strict=True, log=lambda *_: None)["ok"]


def test_bad_manifests_are_explained(tmp_path):
    for body, msg in (('[[toolpath]]\nplate = "a"\n', "expect"), ('[[asbuilt]]\nplate = "a"\nwant = "BLOCK"\n', "stls"),
                      ('[[asbuilt]]\nplate = "a"\nstls = ["b"]\nwant = "MAYBE"\n', "want")):
        with pytest.raises(ValueError, match=msg):
            selftest.load_manifest(_manifest(tmp_path, body))


needs = pytest.mark.skipif(not (shutil.which("openscad") and shutil.which("bambu-studio")), reason="needs openscad and bambu-studio")


@needs
def test_a_checker_that_disagrees_is_reported_as_not_trustworthy(tmp_path):
    # a real plate that is fine, declared "must be flagged": the selftest must FAIL, loudly
    (tmp_path / "b.scad").write_text("cube([20,20,8]);")
    subprocess.run(["openscad", "-q", "-o", str(tmp_path / "b.stl"), str(tmp_path / "b.scad")], check=True)
    r = plate.make(str(tmp_path / "b.stl"), str(tmp_path / "o"), Settings.load(None))
    m = _manifest(tmp_path, f'[[toolpath]]\nplate = "{r["file"]}"\nexpect = "flag"\nwhy = "a fine cube wrongly declared a failure"\n'
                            f'[[toolpath]]\nplate = "{r["file"]}"\nexpect = "not_block"\nwhy = "the same cube, declared fine"\n'
                            f'[[asbuilt]]\nplate = "{r["file"]}"\nstls = ["{tmp_path / "b.stl"}"]\nwant = "BLOCK"\nwhy = "a matching plate wrongly declared plugged"\n'
                            f'[[asbuilt]]\nplate = "{r["file"]}"\nstls = ["{tmp_path / "b.stl"}"]\nwant = "PASS"\nwhy = "the same plate, declared matching"\n')
    lines = []
    out = selftest.run(m, log=lines.append)
    assert not out["ok"] and out["failed"] == 2 and out["passed"] == 4          # 2 synthetic + the two honest declarations
    assert sum(l.startswith("FAIL") for l in lines) == 2
    assert any("NOT TRUSTWORTHY" in l for l in lines)


def test_slow_fixtures_are_skipped_by_default_said_so_and_run_with_all(tmp_path):
    m = _manifest(tmp_path, '[[toolpath]]\nplate = "nope.3mf"\nexpect = "flag"\nslow = true\n')
    lines = []
    selftest.run(m, log=lines.append)
    assert any("slow: run with --all" in l for l in lines)
    lines = []
    selftest.run(m, log=lines.append, include_slow=True)
    assert any("file missing" in l for l in lines) and not any("slow" in l for l in lines)       # with --all it really tried to run it
    assert not selftest.run(m, strict=True, log=lambda *_: None)["ok"]                         # strict: a skipped fixture is a failure
