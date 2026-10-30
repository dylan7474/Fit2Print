import unittest, numpy as np, trimesh
from fit2print import layers

def t_shape(bar_z=(10.0, 12.0)):
    stem = trimesh.creation.box(extents=(4, 4, 10)); stem.apply_translation((0, 0, 5))          # z 0..10
    bar = trimesh.creation.box(extents=(20, 4, bar_z[1] - bar_z[0])); bar.apply_translation((0, 0, sum(bar_z) / 2))
    return trimesh.util.concatenate([stem, bar])

class Layers(unittest.TestCase):
    def test_plain_box_has_no_unsupported_layer(self):
        m = trimesh.creation.box(extents=(10, 10, 10)); m.apply_translation((0, 0, 5))
        self.assertEqual(layers.unsupported(m), [])
    def test_cantilever_is_found(self):          # NEGATIVE CONTROL: a T whose bar hangs 8 mm each side of the stem must be flagged
        ev = layers.unsupported(t_shape())
        self.assertTrue(ev, "the checker missed a flat overhang: it is broken")
        self.assertAlmostEqual(ev[0]["z"], 10.0, delta=0.6)
        self.assertGreater(ev[0]["area"], 40)
    def _frustum(self, grow):                    # a block that gets wider upward: `grow` mm of overhang per mm of height
        h = 10.0; s0 = 10.0; s1 = s0 + 2 * grow * h
        pts = [(sx * s0 / 2, sy * s0 / 2, 0) for sx in (-1, 1) for sy in (-1, 1)] + [(sx * s1 / 2, sy * s1 / 2, h) for sx in (-1, 1) for sy in (-1, 1)]
        return trimesh.convex.convex_hull(np.array(pts, float))
    def test_45_degree_overhang_is_fine(self):  # 1 mm out per mm up = 0.28 mm per layer, inside the 0.6 mm reach
        self.assertEqual(layers.unsupported(self._frustum(1.0)), [])
    def test_shallow_overhang_is_flagged(self): # NEGATIVE CONTROL: 4 mm out per mm up = 1.1 mm per layer, well beyond the reach
        self.assertTrue(layers.unsupported(self._frustum(4.0)))


class Classify(unittest.TestCase):
    def test_bridge_over_a_slot_is_a_bridge(self):      # a block with a 10 mm slot cut across, roofed over: the roof is held both ends
        pillars = [trimesh.creation.box(extents=(10, 20, 6)), trimesh.creation.box(extents=(10, 20, 6))]
        pillars[0].apply_translation((-10, 0, 3)); pillars[1].apply_translation((10, 0, 3))      # a gap of 10 mm between them
        roof = trimesh.creation.box(extents=(30, 20, 2)); roof.apply_translation((0, 0, 7))
        w = layers.analyse(trimesh.util.concatenate(pillars + [roof]))
        self.assertIsNotNone(w["bridge"], "a roof over a slot was not seen as a bridge")
        self.assertIsNone(w["cant"], "a roof held at both ends was called a cantilever")
        self.assertAlmostEqual(w["bridge"][0], 10.0, delta=1.0)
    def test_overhanging_shelf_is_a_cantilever(self):   # NEGATIVE CONTROL: held on one side only
        w = layers.analyse(t_shape())
        self.assertIsNotNone(w["cant"], "an overhanging shelf was not called a cantilever: broken")
        self.assertGreater(w["cant"][0], 6.0)

if __name__ == "__main__":
    unittest.main()
