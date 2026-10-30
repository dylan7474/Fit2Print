import unittest
from fit2print import snap
from fit2print.settings import Settings

class Snap(unittest.TestCase):
    def test_known_value(self):          # 1.2 mm thick, 7 mm long, 0.7 mm deflection: 1.5*1.2*0.7/49 = 2.57 %
        self.assertAlmostEqual(snap.strain(1.2, 7, 0.7), 0.0257, places=4)
    def test_stubby_hook_is_flagged(self):   # NEGATIVE CONTROL
        v, e, msg = snap.check(1.2, 7, 0.7)
        self.assertEqual(v, "CHECK", "the checker passed a hook over the strain limit")
    def test_long_hook_passes(self):
        self.assertEqual(snap.check(1.2, 11, 0.7)[0], "PASS")
    def test_very_stubby_hook_blocks(self):
        self.assertEqual(snap.check(1.5, 4, 0.8)[0], "BLOCK")
    def test_min_length_is_consistent(self):
        L = snap.min_length(1.2, 0.7)
        self.assertAlmostEqual(snap.strain(1.2, L, 0.7), Settings().snap_strain_limit, places=6)

if __name__ == "__main__":
    unittest.main()
