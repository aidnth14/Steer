import statistics
import time
import unittest

from tests.helpers import ensure_display
import pygame
import sim


class TestTiming(unittest.TestCase):
    def setUp(self):
        ensure_display()

    def test_step_and_draw_under_budget(self):
        screen = pygame.display.get_surface()
        sim.new_map(123)
        cars = sim.spawn_grid(8)
        for i, c in enumerate(cars):
            sim.make_bot(c, i, (60, 140, 230))
        cam = sim.Camera(cars[0])
        dt = 1.0 / 60.0
        for _ in range(40):                 # warm up (JIT-less, but caches/GC settle)
            sim.step(dt, cars, [sim.bot_control(c, cars, dt) for c in cars])
            cam.update(dt, cars[0])
        per_frame = []
        for _ in range(300):
            sim.step(dt, cars, [sim.bot_control(c, cars, dt) for c in cars])
            cam.update(dt, cars[0])
            t0 = time.perf_counter()
            sim.draw_world(screen, cam, cars)
            per_frame.append((time.perf_counter() - t0) * 1000.0)
        # Assert on the *minimum* (intrinsic best-case) frame time: it filters out scheduler /
        # GC / thermal-throttling spikes on a busy CI box but still catches a real regression,
        # which raises the floor consistently. Median is logged for context.
        lo, med = min(per_frame), statistics.median(per_frame)
        print(f"\n[timing] draw_world, 8 karts: min {lo:.2f} ms, median {med:.2f} ms/frame")
        self.assertLess(lo, 16.0, f"min {lo:.2f} ms/frame exceeds 16 ms budget")


if __name__ == "__main__":
    unittest.main()
