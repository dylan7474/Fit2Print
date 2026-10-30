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

if __name__ == "__main__":
    unittest.main()
