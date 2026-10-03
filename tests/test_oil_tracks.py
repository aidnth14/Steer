import unittest
import math
import pygame
from tests.helpers import ensure_display
import sim

class TestOilTracks(unittest.TestCase):
    def setUp(self):
        ensure_display()
        sim.load_assets()

    def test_oil_asset_and_tiles_loaded(self):
        self.assertIsNotNone(sim.OIL_RAW, "sim.OIL_RAW should be loaded from assets/oil_track.png")
        self.assertEqual(sim.OIL_RAW.get_size(), (48, 48))
        self.assertTrue(sim.OIL_RAW.get_flags() & pygame.SRCALPHA != 0, "Oil raw should have alpha channel")

        # Verify dirt color (184, 111, 80) was chroma-keyed out
        for y in range(48):
            for x in range(48):
                c = sim.OIL_RAW.get_at((x, y))
                if c.a > 0:
                    self.assertNotEqual((c.r, c.g, c.b), (184, 111, 80), "Dirt background should be transparent")

        # Verify 16x16 tile slices
        for key in ("top", "bot", "left", "right", "center"):
            self.assertIn(key, sim.OIL_TILES, f"OIL_TILES should contain '{key}'")
            tile = sim.OIL_TILES[key]
            self.assertEqual(tile.get_size(), (16, 16))
            self.assertTrue(tile.get_flags() & pygame.SRCALPHA != 0)

    def test_various_lengths_and_widths_generated(self):
        test_dimensions = [
            (14, 48), (16, 64), (18, 80), (20, 96),     # Narrow
            (24, 40), (28, 68), (32, 84), (36, 100),    # Medium
            (40, 48), (44, 80), (48, 96), (48, 112)     # Wide
        ]
        for width, length in test_dimensions:
            spr = sim.make_oil_track_sprite(width, length)
            self.assertEqual(spr.get_size(), (width, length), f"Sprite should match ({width}, {length})")
            self.assertTrue(spr.get_flags() & pygame.SRCALPHA != 0)
            
            # Check cached accessor
            cached = sim._get_oil_sprite(width, length)
            self.assertEqual(cached.get_size(), (width, length))

            # Check zoom-scaled accessor
            zw = max(2, round(width * sim.ZOOM))
            zl = max(2, round(length * sim.ZOOM))
            z_spr = sim._get_oil_zoom_sprite(width, length, zw, zl)
            self.assertEqual(z_spr.get_size(), (zw, zl))

    def test_drop_oil_and_map_seeding(self):
        sim.new_map(7)
        self.assertGreater(len(sim.OIL), 0, "new_map should seed initial oil tracks on the road")
        self.assertLessEqual(len(sim.OIL), sim.OIL_MAX)

        for item in sim.OIL:
            x, y, length, width, angle, max_r = item
            self.assertGreaterEqual(width, 14, "Width should be at least 14")
            self.assertLessEqual(width, 88, "Width should be at most 88")
            self.assertGreaterEqual(length, 40, "Length should be at least 40")
            self.assertLessEqual(length, 120, "Length should be at most 120")
            self.assertAlmostEqual(max_r, max(length, width) * 0.5)

        # Test dropping more up to OIL_MAX
        sim.drop_oil(20)
        self.assertEqual(len(sim.OIL), sim.OIL_MAX, "OIL count should not exceed OIL_MAX")

    def test_oil_collision_physics(self):
        sim.new_map(7)
        # Clear and place a single known oil track at (1000, 1000)
        # length 80, width 20, angle 0 (aligned horizontally with +X)
        sim.OIL = [[1000.0, 1000.0, 80.0, 20.0, 0.0, 40.0]]
        
        car = sim.Car(1000.0, 1000.0, 0.0, (255, 0, 0))
        car.stagger = 0.0
        car.omega = 0.0

        # 1. Car right in the center of oil track
        sim._apply_oil(car)
        self.assertGreater(car.stagger, 0.0, "Car on oil center should be staggered")

        # 2. Car along the length (e.g. 30px to the right along X) -> should be inside length 80 (half-length 40)
        car.stagger = 0.0
        car.x, car.y = 1030.0, 1000.0
        sim._apply_oil(car)
        self.assertGreater(car.stagger, 0.0, "Car along oil track length should be staggered")

        # 3. Car far off to the side (e.g. 25px along Y) -> outside width 20 (half-width 10)
        car.stagger = 0.0
        car.x, car.y = 1000.0, 1025.0
        sim._apply_oil(car)
        self.assertEqual(car.stagger, 0.0, "Car outside oil track width should NOT be staggered")

        # 4. Car far away
        car.stagger = 0.0
        car.x, car.y = 1500.0, 1500.0
        sim._apply_oil(car)
        self.assertEqual(car.stagger, 0.0, "Car far from oil track should NOT be staggered")

    def test_draw_oil_renders_without_error(self):
        sim.new_map(7)
        car = sim.Car(sim.OIL[0][0], sim.OIL[0][1], sim.OIL[0][4], (255, 0, 0))
        cam = sim.Camera(car)
        screen = pygame.Surface((sim.W, sim.H))
        sim.draw_ground(screen, cam)
        sim.draw_oil(screen, cam)
        sim.draw_car(screen, car, cam)
