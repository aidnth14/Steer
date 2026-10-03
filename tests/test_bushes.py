import os
import unittest
import pygame
from tests.helpers import ensure_display
import sim

class TestBushAndTreeDecoration(unittest.TestCase):
    def setUp(self):
        ensure_display()
        sim.load_assets()

    def test_green_bush_asset_loaded(self):
        self.assertIsNotNone(sim.BUSH_RAW, "sim.BUSH_RAW should be loaded from assets")
        self.assertEqual(sim.BUSH_RAW.get_size(), (16, 16))
        self.assertTrue(sim.BUSH_RAW.get_flags() & pygame.SRCALPHA != 0, "Bush should have alpha channel")
        self.assertIsNotNone(sim.BUSH_SURF, "sim.BUSH_SURF should be created")
        self.assertEqual(sim.BUSH_SURF.get_size(), (sim.BUSH_SIZE, sim.BUSH_SIZE), "Bush should be scaled to BUSH_SIZE (24x24)")
        self.assertEqual(sim.BUSH_SIZE, 24)
        self.assertIsNotNone(sim.BUSH_SHADOW, "sim.BUSH_SHADOW should be created")

        # Verify only green bush colors are present
        colors = set()
        for y in range(16):
            for x in range(16):
                c = sim.BUSH_RAW.get_at((x, y))
                if c.a > 0:
                    colors.add((c.r, c.g, c.b))
        
        for r, g, b in colors:
            if (r, g, b) == (0, 0, 0):
                continue
            self.assertGreater(g, r, f"Color ({r}, {g}, {b}) is not green (expected g > r)")

    def test_tree_assets_loaded(self):
        self.assertIsNotNone(sim.TREE_RAW, "sim.TREE_RAW should be loaded from assets/tree.png")
        self.assertEqual(sim.TREE_RAW.get_size(), (48, 64))
        self.assertTrue(sim.TREE_RAW.get_flags() & pygame.SRCALPHA != 0, "Tree 1 should have alpha channel")

        self.assertIsNotNone(sim.TREE2_RAW, "sim.TREE2_RAW should be loaded from assets/tree2.png")
        self.assertEqual(sim.TREE2_RAW.get_size(), (48, 64))
        self.assertTrue(sim.TREE2_RAW.get_flags() & pygame.SRCALPHA != 0, "Tree 2 should have alpha channel")

        self.assertIsNotNone(sim.TREE3_RAW, "sim.TREE3_RAW should be loaded from assets/tree3.png")
        self.assertEqual(sim.TREE3_RAW.get_size(), (48, 64))
        self.assertTrue(sim.TREE3_RAW.get_flags() & pygame.SRCALPHA != 0, "Tree 3 should have alpha channel")

        self.assertIsNotNone(sim.TREE_LOG_RAW, "sim.TREE_LOG_RAW should be loaded from assets/tree_log.png")
        self.assertEqual(sim.TREE_LOG_RAW.get_size(), (16, 16))
        self.assertTrue(sim.TREE_LOG_RAW.get_flags() & pygame.SRCALPHA != 0, "Tree log 1 should have alpha channel")

        self.assertIsNotNone(sim.TREE3_LOG_RAW, "sim.TREE3_LOG_RAW should be loaded from assets/tree3_log.png")
        self.assertEqual(sim.TREE3_LOG_RAW.get_size(), (16, 16))
        self.assertTrue(sim.TREE3_LOG_RAW.get_flags() & pygame.SRCALPHA != 0, "Tree log 3 should have alpha channel")

        self.assertIsNotNone(sim.TREE_SURF, "sim.TREE_SURF should be created with white stroke")
        self.assertEqual(sim.TREE_SURF.get_size(), (50, 66))
        self.assertIsNotNone(sim.TREE2_SURF, "sim.TREE2_SURF should be created with white stroke")
        self.assertEqual(sim.TREE2_SURF.get_size(), (50, 66))
        self.assertIsNotNone(sim.TREE3_SURF, "sim.TREE3_SURF should be created with white stroke")
        self.assertEqual(sim.TREE3_SURF.get_size(), (50, 66))

        self.assertIsNotNone(sim.TREE_SHADOW, "sim.TREE_SHADOW should be created")
        self.assertIsNotNone(sim.TREE2_SHADOW, "sim.TREE2_SHADOW should be created")
        self.assertIsNotNone(sim.TREE3_SHADOW, "sim.TREE3_SHADOW should be created")

        self.assertIsNotNone(sim.CONE_RAW, "sim.CONE_RAW should be loaded from assets/traffic_cone.png")
        self.assertIsNotNone(sim.CONE_SURF, "sim.CONE_SURF should be created")
        self.assertEqual(sim.CONE_SURF.get_size(), (30, 40), "Cone should be 30x40 with white stroke")
        self.assertIsNotNone(sim.CONE_SHADOW, "sim.CONE_SHADOW should be created")
        # Verify white stroke outline
        has_white = any(sim.CONE_SURF.get_at((x, y)) == (255, 255, 255, 255)
                        for y in range(40) for x in range(30))
        self.assertTrue(has_white, "Cone should have white stroke outline")

    def test_decorations_placed_on_map(self):
        sim.new_map(7)
        self.assertGreater(len(sim.BUSHES), 500, "Should generate decorative bushes across the map")
        self.assertGreater(len(sim.TREES), 50, "Should generate decorative trees across the map")
        self.assertGreater(len(sim.TREE_LOGS), 10, "Should generate decorative tree logs across the map")
        self.assertGreater(len(sim.CONES), 0, "Should place traffic cones along the track")
        
        fence_cells = {(f[0], f[1]) for f in sim.FENCES}
        for gx, gy in sim.BUSHES:
            # 1. Never on the dirt road
            self.assertFalse(sim.is_dirt(gx, gy), f"Bush at ({gx}, {gy}) placed on dirt road")
            # 2. Never on a fence cell
            self.assertNotIn((gx, gy), fence_cells, f"Bush at ({gx}, {gy}) placed on fence cell")
            # 3. Not on the inner 1-tile grass verge between road and fence
            idx = (gy % sim.GRID_N) * sim.GRID_N + gx % sim.GRID_N
            self.assertNotEqual(sim.ROAD_NEAR[idx], 1, f"Bush at ({gx}, {gy}) placed on verge")

        for gx, gy in sim.TREES:
            # 1. Never on the dirt road
            self.assertFalse(sim.is_dirt(gx, gy), f"Tree at ({gx}, {gy}) placed on dirt road")
            # 2. Never on a fence cell
            self.assertNotIn((gx, gy), fence_cells, f"Tree at ({gx}, {gy}) placed on fence cell")
            # 3. Placed at ROAD_NEAR >= 3 so canopy never overhangs the road
            idx = (gy % sim.GRID_N) * sim.GRID_N + gx % sim.GRID_N
            self.assertGreaterEqual(sim.ROAD_NEAR[idx], 3, f"Tree at ({gx}, {gy}) too close to road ({sim.ROAD_NEAR[idx]})")
            # 4. Never within fence safety buffer so canopy never comes inside the fence
            for dy in (-3, -2, -1, 0, 1):
                for dx in (-2, -1, 0, 1, 2):
                    self.assertNotIn((gx + dx, gy + dy), fence_cells, f"Tree at ({gx}, {gy}) has canopy overlapping fence at ({gx+dx}, {gy+dy})")

        for gx, gy in sim.TREE_LOGS:
            # 1. Never on the dirt road
            self.assertFalse(sim.is_dirt(gx, gy), f"Log at ({gx}, {gy}) placed on dirt road")
            # 2. Never on a fence cell
            self.assertNotIn((gx, gy), fence_cells, f"Log at ({gx}, {gy}) placed on fence cell")
            # 3. Not on the inner 1-tile grass verge
            idx = (gy % sim.GRID_N) * sim.GRID_N + gx % sim.GRID_N
            self.assertNotEqual(sim.ROAD_NEAR[idx], 1, f"Log at ({gx}, {gy}) placed on verge")

    def test_decorations_deterministic(self):
        sim.new_map(9912)
        bushes_1 = list(sim.BUSHES)
        trees_1 = list(sim.TREES)
        logs_1 = list(sim.TREE_LOGS)
        cones_1 = [(c["x"], c["y"]) for c in sim.CONES]
        sim.new_map(9912)
        bushes_2 = list(sim.BUSHES)
        trees_2 = list(sim.TREES)
        logs_2 = list(sim.TREE_LOGS)
        cones_2 = [(c["x"], c["y"]) for c in sim.CONES]
        self.assertEqual(bushes_1, bushes_2, "Bush placement must be 100% deterministic for a given seed")
        self.assertEqual(trees_1, trees_2, "Tree placement must be 100% deterministic for a given seed")
        self.assertEqual(logs_1, logs_2, "Tree log placement must be 100% deterministic for a given seed")
        self.assertEqual(cones_1, cones_2, "Traffic cone placement must be 100% deterministic for a given seed")

    def test_cone_knock_physics(self):
        sim.new_map(123)
        self.assertGreater(len(sim.CONES), 0)
        cone = sim.CONES[0]
        # Place car right in front of cone moving fast towards it
        car = sim.Car(cone["x"] - 15.0, cone["y"], 0.0, (255, 0, 0))
        car.vx, car.vy = 200.0, 0.0
        orig_car_vx = car.vx
        
        sim._update_cones(1.0 / 60.0, [car])
        self.assertTrue(cone["knocked"], "Cone should be knocked when hit by moving car")
        self.assertGreater(cone["vx"], 50.0, "Cone should gain velocity when knocked")
        # Assert car experienced physical collision response (deflection / pushback)
        self.assertNotEqual(car.vx, orig_car_vx, "Car velocity should be modified by physical collision with cone")
