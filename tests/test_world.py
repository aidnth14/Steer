import math
import unittest

from tests.helpers import ensure_display
import sim


def fence_loops(cells):
    seen, comps = set(), 0
    for c in cells:
        if c in seen:
            continue
        comps += 1
        stack = [c]
        seen.add(c)
        while stack:
            x, y = stack.pop()
            for nb in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if nb in cells and nb not in seen:
                    seen.add(nb)
                    stack.append(nb)
    return comps


class TestWorld(unittest.TestCase):
    def setUp(self):
        ensure_display()

    def test_seeds(self):
        for seed in range(25):
            with self.subTest(seed=seed):
                sim.new_map(seed)
                cells = {(gx, gy) for gx, gy, _ in sim.FENCES}
                self.assertTrue(sim.FENCES, "no fences generated")

                # exactly two separate fence loops
                self.assertEqual(fence_loops(cells), 2, "expected 2 fence loops")

                # every post links to exactly two neighbours
                for gx, gy, links in sim.FENCES:
                    self.assertEqual(sum(links), 2,
                                     f"post {(gx, gy)} links {links} != 2 neighbours")

                # no fence cell is on the road
                for gx, gy, _ in sim.FENCES:
                    self.assertFalse(sim.is_dirt(gx, gy),
                                     f"fence cell {(gx, gy)} is on the road")

                # every start-grid kart is on the road
                for c in sim.spawn_grid(8):
                    self.assertEqual(sim.dist_to_dirt(c.x, c.y, 60.0), 0.0,
                                     "grid kart off the road")

                # every mystery box is on the road
                for b in sim.BOXES:
                    self.assertEqual(sim.dist_to_dirt(b["x"], b["y"], 60.0), 0.0,
                                     "mystery box off the road")


if __name__ == "__main__":
    unittest.main()
