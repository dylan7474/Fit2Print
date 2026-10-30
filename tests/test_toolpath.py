import math, os, unittest
from fit2print import gcode, toolpath
from fit2print.settings import Settings

def loop(z, x0, y0, x1, y1, feat="Outer wall", step=1.0):
    """G-code for one rectangular perimeter at height z, in short extruding moves (a layer needs >= 20 segments to count as a real layer)."""
    out = [f"; FEATURE: {feat}", f"G1 Z{z:.2f} F1200", f"G1 X{x0} Y{y0} F6000"]
    pts = []
    for (ax, ay), (bx, by) in [((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))]:
        n = max(1, int(math.hypot(bx - ax, by - ay) / step))
        pts += [(ax + (bx - ax) * k / n, ay + (by - ay) * k / n) for k in range(1, n + 1)]
    out += [f"G1 X{x:.3f} Y{y:.3f} E0.05 F1800" for x, y in pts]
    return out

def plate(upper_x1):
    """Five layers of a 20 x 20 square, then one layer whose square reaches upper_x1."""
    g = []
    for k in range(5):
        g += loop(0.2 + 0.2 * k, 0, 0, 20, 20)
    g += loop(1.2, 0, 0, upper_x1, 20)
    return g

def run(lines):
    lay, _, _ = gcode.parse(lines)
    return toolpath.analyse(lay), toolpath.verdict(toolpath.analyse(lay))

class Toolpath(unittest.TestCase):
    def test_layer_that_stays_over_its_support_passes(self):
        w, v = run(plate(20.4))
        self.assertEqual(v, "PASS")
    def test_cantilever_is_blocked(self):         # NEGATIVE CONTROL: a layer reaching 8 mm past what is below must be BLOCKed
        w, v = run(plate(28))
        self.assertEqual(v, "BLOCK", "the checker missed an 8 mm cantilever: it is broken")
        self.assertGreater(w["cant"][0], 6.0)
    def test_small_overhang_is_a_check(self):    # 4 mm: between the check (3.5) and block (6.0) limits
        w, v = run(plate(24))
        self.assertEqual(v, "CHECK")
    def test_limits_come_from_the_profile(self):  # a stricter printer profile turns the same 4 mm into a BLOCK
        lay, _, _ = gcode.parse(plate(24))
        strict = Settings(cantilever_check=1.0, cantilever_block=3.0)
        self.assertEqual(toolpath.verdict(toolpath.analyse(lay, strict), strict), "BLOCK")

PH = os.environ.get("PHONOSPHERE_PLATES", os.path.expanduser("~/Downloads/phonosphere_qual/realpod"))
@unittest.skipUnless(os.path.exists(os.path.join(PH, "coupons/lug_coupon_fixed.3mf")), "Phonosphere plate files not on this machine")
class AgainstPhonosphere(unittest.TestCase):
    """The ported check must give the numbers Phonosphere's own anchor_check.py gave (2026-10-30)."""
    def _w(self, rel):
        lay, _, _ = gcode.parse(gcode.read_gcode(os.path.join(PH, rel)))
        return toolpath.analyse(lay)
    def test_lug_coupon_fixed(self):
        w = self._w("coupons/lug_coupon_fixed.3mf")
        self.assertAlmostEqual(w["bridge"][0], 5.8, delta=0.1); self.assertEqual(w["cant"][1], None)
    def test_top_plates(self):
        self.assertAlmostEqual(self._w("pod/top_plates.3mf")["bridge"][0], 6.2, delta=0.1)

if __name__ == "__main__":
    unittest.main()
