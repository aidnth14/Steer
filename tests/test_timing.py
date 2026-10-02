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
        frames = 300
        t0 = time.perf_counter()
        for _ in range(frames):
            controls = [sim.bot_control(c, cars, dt) for c in cars]
            sim.step(dt, cars, controls)
            cam.update(dt, cars[0])
            sim.draw_world(screen, cam, cars)
        ms = (time.perf_counter() - t0) / frames * 1000.0
        print(f"\n[timing] step+draw_world, 8 karts: {ms:.2f} ms/frame")
        self.assertLess(ms, 16.0, f"{ms:.2f} ms/frame exceeds 16 ms budget")


if __name__ == "__main__":
    unittest.main()
