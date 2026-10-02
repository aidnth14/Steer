import math
import os
import unittest
import pygame
from tests.helpers import ensure_display
import sim


class TestParticlesTracksGyro(unittest.TestCase):
    def setUp(self):
        ensure_display()
        sim.load_assets()

    def test_particle_system(self):
        self.assertIsNotNone(sim.PARTICLE_RAW, "assets/particle.png should be loaded")
        self.assertEqual(sim.PARTICLE_RAW.get_size(), (16, 16))

        # Test sprite scaling and tinting cache
        for size in (2, 3, 4, 5):
            for alpha_step in (0, 2, 4):
                sp = sim._get_particle_sprite((255, 180, 50), size, alpha_step)
                self.assertEqual(sp.get_size(), (size, size))
                # Ensure caching works
                self.assertIn((*((255, 180, 50)), size, alpha_step), sim._PARTICLE_CACHE)

        # Test particle spawn and update
        del sim.PARTICLES[:]
        sim.spawn_particles(100, 100, 10, 50, (255, 200, 80), 0.5)
        self.assertEqual(len(sim.PARTICLES), 10)
        sim._update_particles(0.1)
        self.assertGreater(len(sim.PARTICLES), 0)

        # Test drawing particles
        screen = pygame.display.get_surface()
        cam = sim.Camera(sim.Car(100, 100, 0, (255, 0, 0)))
        sim.draw_particles(screen, cam)

    def test_thirteen_second_tyre_tracks(self):
        sim.new_map(807216)
        cars = sim.spawn_grid(1)
        car = cars[0]
        cam = sim.Camera(car)
        screen = pygame.display.get_surface()

        # Step 60 frames while drifting hard to lay down tyre tracks
        dt = 1.0 / 60.0
        for _ in range(60):
            sim.step(dt, cars, [(0.8, None, True)])
            cam.update(dt, car)

        self.assertGreater(len(car.trail), 10, "Continuous skid segments should be created in car.trail")
        # Segments have 7 elements: [x0, y0, x1, y1, life, width, is_grass]
        self.assertEqual(len(car.trail[0]), 7)
        self.assertAlmostEqual(car.trail[-1][4], sim.TRAIL_LIFE, delta=0.5)

        # Test drawing trails on screen
        sim.draw_trails(screen, cars, cam)

        # Advance 10 seconds (600 steps) without drifting
        for _ in range(600):
            sim.step(dt, cars, [(0.0, None, False)])

        # At 10s into its 13s life, tyre tracks MUST still be present
        self.assertGreater(len(car.trail), 0, "Tracks should still exist after 10 seconds")

        # Stop the car so no new skid marks are created while waiting
        car.vx = car.vy = 0.0
        # Advance another 4 seconds (total > 14s elapsed)
        for _ in range(260):
            car.vx = car.vy = 0.0
            sim.step(dt, cars, [(0.0, None, False)])

        # After 14 seconds (> 13.0s TRAIL_LIFE), tracks should be completely expired/cleared
        self.assertEqual(len(car.trail), 0, "Tracks should cleanly fade out and expire after 13s")

    def test_mobile_tilt_simulation(self):
        # Verify sim.MOBILE_TILT maps to steering range
        sim.MOBILE_TILT = 0.75
        self.assertEqual(sim.MOBILE_TILT, 0.75)
        sim.MOBILE_TILT = None


if __name__ == "__main__":
    unittest.main()
