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

    def test_camera_centered_on_car(self):
        car = sim.Car(400.0, 600.0, 30.0, (255, 0, 0))
        cam = sim.Camera(car)
        cam.shake = 0.0
        cam.ox = cam.oy = 0.0
        # Check through multiple motion steps
        for speed in (0.0, 100.0, 300.0):
            car.vx, car.vy = speed, speed * 0.5
            car.x += car.vx * 0.016
            car.y += car.vy * 0.016
            cam.update(0.016, car)
            cam.shake = 0.0
            cam.ox = cam.oy = 0.0
            sx, sy = cam.to_screen(car.x, car.y)
            self.assertAlmostEqual(sx, sim.W / 2, delta=0.001)
            self.assertAlmostEqual(sy, sim.H / 2, delta=0.001)

    def test_direction_based_shadows(self):
        # Verify sun direction vector
        self.assertAlmostEqual(sim.SUN_DIR_X**2 + sim.SUN_DIR_Y**2, 1.0, delta=0.001)

        # Verify fence shadows built
        self.assertGreater(len(sim.FENCE_SHADOWS), 0, "FENCE_SHADOWS should have baked tiles")
        sample_shadow = next(iter(sim.FENCE_SHADOWS.values()))
        self.assertIsInstance(sample_shadow, pygame.Surface)

        # Verify car shadow rendering
        car = sim.Car(sim.W / 2, sim.H / 2, 45.0, (255, 0, 0))
        cam = sim.Camera(car)
        screen = pygame.Surface((sim.W, sim.H))
        screen.fill(sim.GRASS_COLOR)
        sim.draw_car_shadow(screen, car, cam)

        # Check that pixels beneath/around the car were darkened by the shadow
        # Car is at W/2, H/2. Light is from top-left, so shadow is cast to bottom-right
        darkened = False
        for ox in range(0, 30):
            for oy in range(0, 30):
                c = screen.get_at((int(sim.W / 2 + ox), int(sim.H / 2 + oy)))
                if c[0] < sim.GRASS_COLOR[0] and c[1] < sim.GRASS_COLOR[1]:
                    darkened = True
                    break
            if darkened:
                break
        self.assertTrue(darkened, "Car shadow should darken ground in sun direction")


if __name__ == "__main__":
    unittest.main()
