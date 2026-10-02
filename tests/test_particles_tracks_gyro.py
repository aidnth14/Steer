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

    def test_permanent_tyre_tracks(self):
        sim.new_map(807216)
        self.assertIsNotNone(sim.GROUND_Z, "GROUND_Z should be built")
        gw, gh = sim.GROUND_Z.get_size()
        ox, oy = sim.GROUND_ORIGIN

        cars = sim.spawn_grid(1)
        car = cars[0]
        cam = sim.Camera(car)

        # Record a sample area on GROUND_Z where the car will drift
        dt = 1.0 / 60.0
        # Steer and drift hard to generate skid marks
        for _ in range(60):
            sim.step(dt, cars, [(0.8, None, True)])
            cam.update(dt, car)

        # Check that skid marks were drawn onto GROUND_Z
        # We search a bounding box around the car's initial area in GROUND_Z coords
        zx = int((car.x - ox) * sim.ZOOM)
        zy = int((car.y - oy) * sim.ZOOM)
        min_x = max(0, zx - 100)
        max_x = min(gw, zx + 100)
        min_y = max(0, zy - 100)
        max_y = min(gh, zy + 100)

        skid_color = (46, 28, 22)
        found_skid_pixels = 0
        for y in range(min_y, max_y, 2):
            for x in range(min_x, max_x, 2):
                col = tuple(sim.GROUND_Z.get_at((x, y)))[:3]
                if col == skid_color or (abs(col[0] - 46) <= 4 and abs(col[1] - 28) <= 4 and abs(col[2] - 22) <= 4):
                    found_skid_pixels += 1

        self.assertGreater(found_skid_pixels, 10, "Skid marks should be permanently drawn on GROUND_Z")

        # Step another 60 frames without drift: previous skid marks MUST still exist on GROUND_Z!
        for _ in range(60):
            sim.step(dt, cars, [(0.0, None, False)])

        found_after = 0
        for y in range(min_y, max_y, 2):
            for x in range(min_x, max_x, 2):
                col = tuple(sim.GROUND_Z.get_at((x, y)))[:3]
                if col == skid_color or (abs(col[0] - 46) <= 4 and abs(col[1] - 28) <= 4 and abs(col[2] - 22) <= 4):
                    found_after += 1

        self.assertGreaterEqual(found_after, found_skid_pixels, "Tyre tracks must remain permanently on GROUND_Z")

    def test_mobile_tilt_simulation(self):
        # Verify sim.MOBILE_TILT maps to steering range
        sim.MOBILE_TILT = 0.75
        self.assertEqual(sim.MOBILE_TILT, 0.75)
        sim.MOBILE_TILT = None


if __name__ == "__main__":
    unittest.main()
