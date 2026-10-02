import math
import unittest

from tests.helpers import ensure_display
import sim


class TestPhysics(unittest.TestCase):
    def setUp(self):
        ensure_display()

    def test_sixty_seconds(self):
        dt = 1.0 / 60.0
        fence_limit = sim.FENCE_OFFSET * sim.TILE
        for seed in (1, 42, 777):
            with self.subTest(seed=seed):
                sim.new_map(seed)
                cars = sim.spawn_grid(7)
                for i, c in enumerate(cars):
                    sim.make_bot(c, i, (60, 140, 230))
                for _ in range(60 * 60):            # 60 s
                    controls = [sim.bot_control(c, cars, dt) for c in cars]
                    sim.step(dt, cars, controls)
                    for c in cars:
                        self.assertTrue(math.isfinite(c.x) and math.isfinite(c.y),
                                        "position went non-finite")
                        self.assertTrue(math.isfinite(c.vx) and math.isfinite(c.vy),
                                        "velocity went non-finite")
                        self.assertTrue(math.isfinite(c.omega), "spin went non-finite")
                        self.assertLessEqual(sim.dist_to_dirt(c.x, c.y, 400.0), fence_limit,
                                             "kart got past the fence")
                for c in cars:
                    self.assertLessEqual(c.rescues, 3, "kart rescued too many times")
                    if not c.dead:
                        laps = c.progress / sim.ROAD_LEN
                        self.assertGreaterEqual(laps, 1.5, f"only {laps:.2f} laps in 60 s")


if __name__ == "__main__":
    unittest.main()
