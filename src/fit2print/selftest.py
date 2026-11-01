"""Is the checker still telling the truth? Run it on plates whose outcome is KNOWN and fail if it disagrees. Extracted from Phonosphere's selftest_checks.py.

Run it after ANY change to the checks, the slicer profiles or this tool, and before trusting a green plate. A project lists its fixtures in selftest.toml:

    [[toolpath]]                 # the toolpath check on a sliced plate
    plate  = "a1/known_bad/arch_unsupported_shelf.3mf"    # relative to the manifest; ~ is allowed
    expect = "flag"              # flag: must be CHECK or BLOCK (a known failure) | not_block: must not BLOCK (a print that came out fine)
    why    = "arch lap shelf unsupported (failed print)"

    [[asbuilt]]                  # the design-against-print check
    plate = "a1/known_bad/arch_pilots_filled_with_support.3mf"
    stls  = ["a1/known_bad/arch_pilots_filled_with_support.stl"]
    want  = "BLOCK"             # BLOCK | PASS
    why   = "support plugged 7 blind pilots"

Add `slow = true` to a fixture that takes minutes (a whole-radio plate): it is SKIPPED by default and said so, and runs with --all.
Add every new failure here the day it happens. A fixture whose file is missing is SKIPPED and said so (never counted as a pass); --strict makes a skip a failure.
Synthetic cases (no files) always run: a shelf over a thin stem must BLOCK, and a plain tower must not."""
import os, time, tomllib
import numpy as np
from . import asbuilt, gcode, toolpath
from .settings import Settings


def _path(base, p):
    p = os.path.expanduser(str(p))
    return p if os.path.isabs(p) else os.path.join(base, p)


def load_manifest(path):
    with open(path, "rb") as fh:
        d = tomllib.load(fh)
    tp, ab = d.get("toolpath") or [], d.get("asbuilt") or []
    for t in tp:
        if "plate" not in t or t.get("expect") not in ("flag", "not_block"):
            raise ValueError(f"selftest.toml: a [[toolpath]] needs plate and expect = \"flag\" or \"not_block\": {t}")
    for a in ab:
        if "plate" not in a or not a.get("stls") or a.get("want") not in ("BLOCK", "PASS"):
            raise ValueError(f"selftest.toml: an [[asbuilt]] needs plate, stls and want = \"BLOCK\" or \"PASS\": {a}")
    return tp, ab


def _loop(z, x0, y0, x1, y1, step):
    out = ["; FEATURE: Outer wall", f"G1 Z{z:.2f} F1200", f"G1 X{x0} Y{y0} F6000"]
    pts = []
    for (ax, ay), (bx, by) in [((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))]:
        n = max(1, int(((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5 / step))
        pts += [(ax + (bx - ax) * k / n, ay + (by - ay) * k / n) for k in range(1, n + 1)]
    return out + [f"G1 X{x:.3f} Y{y:.3f} E0.05 F1800" for x, y in pts]


def synthetic(cfg):
    """[(verdict, wanted, why)] from G-code written here, so they need no files."""
    out = []
    lines = []
    for k in range(8):
        lines += _loop(0.2 + 0.2 * k, 0, 0, 10, 10, 5.0)       # a 10 x 10 mm stem whose layers have only 8 long moves
    lines += _loop(1.8, -16, -16, 26, 26, 1.0)                  # a shelf 16 mm out on every side
    layers, _, _ = gcode.parse(lines, cfg.filament_area)
    out.append((toolpath.report(layers, cfg)[0], "BLOCK", "a shelf over a thin stem must BLOCK (a rule that skipped short layers ignored the stem: found 2026-10-30)"))
    lines = []
    for k in range(12):
        lines += _loop(0.2 + 0.2 * k, 0, 0, 20, 20, 1.0)
    layers, _, _ = gcode.parse(lines, cfg.filament_area)
    out.append((toolpath.report(layers, cfg)[0], "PASS", "a plain tower must PASS (a checker that blocks everything proves nothing)"))
    return out


def run(manifest=None, strict=False, log=print, include_slow=False):
    """-> dict(ok, failed, skipped, passed). Prints one line per fixture."""
    cfg = Settings.load(None)
    base = os.path.dirname(os.path.abspath(manifest)) if manifest else os.getcwd()
    tp, ab = load_manifest(manifest) if manifest else ([], [])
    failed = skipped = passed = 0
    for want_v, want, why in [(v, w, y) for v, w, y in synthetic(cfg)]:
        good = (want_v == "BLOCK") if want == "BLOCK" else (want_v == "PASS")
        failed += not good; passed += good
        log(f"{'ok  ' if good else 'FAIL'}  {want_v:5} synthetic, want {want}: {why}")
    for t in tp:
        p = _path(base, t["plate"])
        if t.get("slow") and not include_slow:
            skipped += 1; log(f"SKIP  {t['plate']} (slow: run with --all)"); continue
        if not os.path.exists(p):
            skipped += 1; log(f"SKIP  {t['plate']} (file missing)"); continue
        t0 = time.time()
        layers, _, _ = gcode.parse(gcode.read_gcode(p), cfg.filament_area)
        v = toolpath.report(layers, cfg)[0]
        good = v in ("CHECK", "BLOCK") if t["expect"] == "flag" else v != "BLOCK"
        failed += not good; passed += good
        log(f"{'ok  ' if good else 'FAIL'}  {v:5} {'must be flagged' if t['expect'] == 'flag' else 'must not BLOCK'}: {t.get('why', t['plate'])}  [{time.time() - t0:.0f} s]")
    import trimesh
    for a in ab:
        p = _path(base, a["plate"])
        if a.get("slow") and not include_slow:
            skipped += 1; log(f"SKIP  {a['plate']} (slow: run with --all)"); continue
        stls = [_path(base, s) for s in a["stls"]]
        if not os.path.exists(p) or not all(os.path.exists(s) for s in stls):
            skipped += 1; log(f"SKIP  {a['plate']} (file missing)"); continue
        t0 = time.time()
        layers, _, _ = gcode.parse(gcode.read_gcode(p), cfg.filament_area)
        worst = "PASS"
        for s in stls:
            v = asbuilt.check(layers, trimesh.load(s))[0]
            worst = "BLOCK" if "BLOCK" in (v, worst) else ("CHECK" if "CHECK" in (v, worst) else "PASS")
        good = worst == a["want"]
        failed += not good; passed += good
        log(f"{'ok  ' if good else 'FAIL'}  {worst:5} as-built, want {a['want']}: {a.get('why', a['plate'])}  [{time.time() - t0:.0f} s]")
    ok = failed == 0 and not (strict and skipped)
    log(f"\n[selftest] {passed} passed, {failed} failed, {skipped} skipped" + ("" if ok else "  -- THE CHECKER IS NOT TRUSTWORTHY" if failed else "  -- fixtures missing (strict)"))
    return dict(ok=ok, failed=failed, skipped=skipped, passed=passed)
