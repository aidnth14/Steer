"""Steer test suite.
Consolidated test suite covering physics, game loop, world generation,
bushes/trees/props, oil tracks, destructibles, timing, particles/tracks/gyro,
button manager, network relay, and Redis scaling.
"""

import asyncio
import json
import math
import os
import shutil
import socket
import statistics
import subprocess
import sys
import tempfile
import time
import types
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import websockets

import sim
import net
import main
import buttonmanager

ROOT = os.path.dirname(os.path.abspath(__file__))

# Headless setup helper
def ensure_display():
    if not pygame.display.get_init() or pygame.display.get_surface() is None:
        pygame.init()
        pygame.display.set_mode((sim.W, sim.H))
        sim._FONT_CACHE.clear()
        sim.load_assets()

# Backward compatibility alias
_th = types.ModuleType("tests.helpers")
_th.ensure_display = ensure_display
sys.modules["tests.helpers"] = _th


# ============================================================================
# 1. Physics Tests
# ============================================================================
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


# ============================================================================
# 2. Timing Tests
# ============================================================================
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
        lo, med = min(per_frame), statistics.median(per_frame)
        print(f"\n[timing] draw_world, 8 karts: min {lo:.2f} ms, median {med:.2f} ms/frame")
        self.assertLess(lo, 16.0, f"min {lo:.2f} ms/frame exceeds 16 ms budget")


# ============================================================================
# 3. World Generation & Track Tests
# ============================================================================
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

    def test_ground_opacity(self):
        sim.new_map(733141)
        ox, oy = sim.GROUND_ORIGIN
        for gx, gy, _ in sim.FENCES[:30]:
            px, py = gx * sim.TILE - ox, gy * sim.TILE - oy
            for dy in range(sim.TILE):
                for dx in range(sim.TILE):
                    self.assertEqual(sim.GROUND_SURF.get_at((px + dx, py + dy))[3], 255,
                                     "fence pixel on GROUND_SURF has non-opaque alpha")


# ============================================================================
# 4. Game Loop Simulation Tests
# ============================================================================
W2 = sim.W // 2

class KeyState:
    def __init__(self, held):
        self.held = held

    def __getitem__(self, k):
        return 1 if k in self.held else 0


class Script:
    def __init__(self):
        self.frame = -1
        self.events = {}
        self.mouse = {}
        self.keys = {}
        self.cur_mouse = (0, 0)
        self.cur_keys = set()
        self.END = 460

    def click(self, frame, pos):
        self.mouse[frame] = pos
        self.events.setdefault(frame, []).append(
            pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos))

    def key(self, frame, k):
        self.events.setdefault(frame, []).append(
            pygame.event.Event(pygame.KEYDOWN, key=k, unicode="", mod=0))

    def hold(self, f0, f1, keycodes):
        for f in range(f0, f1):
            self.keys.setdefault(f, set()).update(keycodes)

    def get_pos(self):
        self.frame += 1
        f = self.frame
        if f in self.mouse:
            self.cur_mouse = self.mouse[f]
        self.cur_keys = self.keys.get(f, set())
        return self.cur_mouse

    def event_get(self):
        f = self.frame
        if f >= self.END:
            return [pygame.event.Event(pygame.QUIT)]
        return self.events.get(f, [])

    def get_pressed(self):
        return KeyState(self.cur_keys)


class TestGameLoop(unittest.TestCase):
    def setUp(self):
        ensure_display()

    def test_play_a_race(self):
        script = Script()
        script.click(5, (136, 281))
        script.click(12, (146, 281))
        script.click(19, (W2, 108))
        script.click(26, (W2, 277))
        script.hold(30, 400, {pygame.K_a})
        for f in (230, 250, 270):
            script.key(f, pygame.K_q)
            script.key(f + 5, pygame.K_e)
            script.key(f + 10, pygame.K_SPACE)
        script.key(330, pygame.K_ESCAPE)
        script.click(345, (136, 239))

        calls = {"n": 0}
        real_step = sim.step

        def counting_step(*a, **k):
            calls["n"] += 1
            return real_step(*a, **k)

        tmp = tempfile.mkdtemp()
        orig_profile = main.PROFILE_PATH
        orig_get, orig_pos, orig_keys, orig_step = (
            pygame.event.get, pygame.mouse.get_pos, pygame.key.get_pressed, sim.step)
        main.PROFILE_PATH = os.path.join(tmp, "profile.json")
        pygame.event.get = script.event_get
        pygame.mouse.get_pos = script.get_pos
        pygame.key.get_pressed = script.get_pressed
        sim.step = counting_step
        try:
            with self.assertRaises(SystemExit):
                main.main()
        finally:
            pygame.event.get, pygame.mouse.get_pos = orig_get, orig_pos
            pygame.key.get_pressed, sim.step = orig_keys, orig_step
            main.PROFILE_PATH = orig_profile

        self.assertGreater(calls["n"], 50, "race never ran (sim.step called too few times)")


# ============================================================================
# 5. Bushes, Trees & Decorations Tests
# ============================================================================
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
        self.assertIsNotNone(sim.TREE_RAW, "sim.TREE_RAW should be loaded from assets/decor/tree.png")
        self.assertEqual(sim.TREE_RAW.get_size(), (48, 64))
        self.assertTrue(sim.TREE_RAW.get_flags() & pygame.SRCALPHA != 0, "Tree 1 should have alpha channel")

        self.assertIsNotNone(sim.TREE2_RAW, "sim.TREE2_RAW should be loaded from assets/decor/tree2.png")
        self.assertEqual(sim.TREE2_RAW.get_size(), (48, 64))
        self.assertTrue(sim.TREE2_RAW.get_flags() & pygame.SRCALPHA != 0, "Tree 2 should have alpha channel")

        self.assertIsNotNone(sim.TREE3_RAW, "sim.TREE3_RAW should be loaded from assets/decor/tree3.png")
        self.assertEqual(sim.TREE3_RAW.get_size(), (48, 64))
        self.assertTrue(sim.TREE3_RAW.get_flags() & pygame.SRCALPHA != 0, "Tree 3 should have alpha channel")

        self.assertIsNotNone(sim.TREE_LOG_RAW, "sim.TREE_LOG_RAW should be loaded from assets/decor/tree_log.png")
        self.assertEqual(sim.TREE_LOG_RAW.get_size(), (16, 16))
        self.assertTrue(sim.TREE_LOG_RAW.get_flags() & pygame.SRCALPHA != 0, "Tree log 1 should have alpha channel")

        self.assertIsNotNone(sim.TREE3_LOG_RAW, "sim.TREE3_LOG_RAW should be loaded from assets/decor/tree3_log.png")
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

        self.assertIsNotNone(sim.CONE_RAW, "sim.CONE_RAW should be loaded from assets/props/traffic_cone.png")
        self.assertIsNotNone(sim.CONE_SURF, "sim.CONE_SURF should be created")
        self.assertEqual(sim.CONE_SURF.get_size(), (26, 35), "Cone should be 26x35 with white stroke")
        self.assertIsNotNone(sim.CONE_SHADOW, "sim.CONE_SHADOW should be created")
        cw, ch = sim.CONE_SURF.get_size()
        has_white = any(sim.CONE_SURF.get_at((x, y)) == (255, 255, 255, 255)
                        for y in range(ch) for x in range(cw))
        self.assertTrue(has_white, "Cone should have white stroke outline")

    def test_decorations_placed_on_map(self):
        sim.new_map(7)
        self.assertGreater(len(sim.BUSHES), 500, "Should generate decorative bushes across the map")
        self.assertGreater(len(sim.TREES), 50, "Should generate decorative trees across the map")
        self.assertGreater(len(sim.TREE_LOGS), 10, "Should generate decorative tree logs across the map")
        self.assertGreater(len(sim.CONES), 0, "Should place traffic cones along the track")
        
        fence_cells = {(f[0], f[1]) for f in sim.FENCES}
        for gx, gy in sim.BUSHES:
            self.assertFalse(sim.is_dirt(gx, gy), f"Bush at ({gx}, {gy}) placed on dirt road")
            self.assertNotIn((gx, gy), fence_cells, f"Bush at ({gx}, {gy}) placed on fence cell")
            idx = (gy % sim.GRID_N) * sim.GRID_N + gx % sim.GRID_N
            self.assertNotEqual(sim.ROAD_NEAR[idx], 1, f"Bush at ({gx}, {gy}) placed on verge")

        for gx, gy in sim.TREES:
            self.assertFalse(sim.is_dirt(gx, gy), f"Tree at ({gx}, {gy}) placed on dirt road")
            self.assertNotIn((gx, gy), fence_cells, f"Tree at ({gx}, {gy}) placed on fence cell")
            idx = (gy % sim.GRID_N) * sim.GRID_N + gx % sim.GRID_N
            self.assertGreaterEqual(sim.ROAD_NEAR[idx], 3, f"Tree at ({gx}, {gy}) too close to road ({sim.ROAD_NEAR[idx]})")
            for dy in (-3, -2, -1, 0, 1):
                for dx in (-2, -1, 0, 1, 2):
                    self.assertNotIn((gx + dx, gy + dy), fence_cells, f"Tree at ({gx}, {gy}) has canopy overlapping fence at ({gx+dx}, {gy+dy})")

        for gx, gy in sim.TREE_LOGS:
            self.assertFalse(sim.is_dirt(gx, gy), f"Log at ({gx}, {gy}) placed on dirt road")
            self.assertNotIn((gx, gy), fence_cells, f"Log at ({gx}, {gy}) placed on fence cell")
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
        car = sim.Car(cone["x"] - 15.0, cone["y"], 0.0, (255, 0, 0))
        car.vx, car.vy = 200.0, 0.0
        orig_car_vx = car.vx
        
        sim._update_cones(1.0 / 60.0, [car])
        self.assertTrue(cone["knocked"], "Cone should be knocked when hit by moving car")
        self.assertGreater(cone["vx"], 50.0, "Cone should gain velocity when knocked")
        self.assertNotEqual(car.vx, orig_car_vx, "Car velocity should be modified by physical collision with cone")


# ============================================================================
# 6. Oil Tracks Tests
# ============================================================================
class TestOilTracks(unittest.TestCase):
    def setUp(self):
        ensure_display()
        sim.load_assets()

    def test_oil_asset_and_tiles_loaded(self):
        self.assertIsNotNone(sim.OIL_RAW, "sim.OIL_RAW should be loaded from assets/track_tiles/oil_track.png")
        self.assertEqual(sim.OIL_RAW.get_size(), (48, 48))
        self.assertTrue(sim.OIL_RAW.get_flags() & pygame.SRCALPHA != 0, "Oil raw should have alpha channel")

        for y in range(48):
            for x in range(48):
                c = sim.OIL_RAW.get_at((x, y))
                if c.a > 0:
                    self.assertNotEqual((c.r, c.g, c.b), (184, 111, 80), "Dirt background should be transparent")

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
            
            cached = sim._get_oil_sprite(width, length)
            self.assertEqual(cached.get_size(), (width, length))

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

        sim.drop_oil(20)
        self.assertEqual(len(sim.OIL), sim.OIL_MAX, "OIL count should not exceed OIL_MAX")

    def test_oil_collision_physics(self):
        sim.new_map(7)
        sim.OIL = [[1000.0, 1000.0, 80.0, 20.0, 0.0, 40.0]]
        
        car = sim.Car(1000.0, 1000.0, 0.0, (255, 0, 0))
        car.stagger = 0.0
        car.omega = 0.0

        sim._apply_oil(car)
        self.assertGreater(car.stagger, 0.0, "Car on oil center should be staggered")

        car.stagger = 0.0
        car.x, car.y = 1030.0, 1000.0
        sim._apply_oil(car)
        self.assertGreater(car.stagger, 0.0, "Car along oil track length should be staggered")

        car.stagger = 0.0
        car.x, car.y = 1000.0, 1025.0
        sim._apply_oil(car)
        self.assertEqual(car.stagger, 0.0, "Car outside oil track width should NOT be staggered")

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


# ============================================================================
# 7. Particles, Tracks & Gyro Tests
# ============================================================================
class TestParticlesTracksGyro(unittest.TestCase):
    def setUp(self):
        ensure_display()
        sim.load_assets()

    def test_particle_system(self):
        self.assertIsNotNone(sim.PARTICLE_RAW, "assets/fx/particle.png should be loaded")
        self.assertEqual(sim.PARTICLE_RAW.get_size(), (16, 16))

        for size in (2, 3, 4, 5):
            for alpha_step in (0, 2, 4):
                sp = sim._get_particle_sprite((255, 180, 50), size, alpha_step)
                self.assertEqual(sp.get_size(), (size, size))
                self.assertIn((*((255, 180, 50)), size, alpha_step), sim._PARTICLE_CACHE)

        del sim.PARTICLES[:]
        sim.spawn_particles(100, 100, 10, 50, (255, 200, 80), 0.5)
        self.assertEqual(len(sim.PARTICLES), 10)
        sim._update_particles(0.1)
        self.assertGreater(len(sim.PARTICLES), 0)

        screen = pygame.display.get_surface()
        cam = sim.Camera(sim.Car(100, 100, 0, (255, 0, 0)))
        sim.draw_particles(screen, cam)

    def test_thirteen_second_tyre_tracks(self):
        sim.new_map(807216)
        cars = sim.spawn_grid(1)
        car = cars[0]
        cam = sim.Camera(car)
        screen = pygame.display.get_surface()

        dt = 1.0 / 60.0
        for _ in range(60):
            sim.step(dt, cars, [(0.8, None, True)])
            cam.update(dt, car)

        self.assertGreater(len(car.trail), 10, "Continuous skid segments should be created in car.trail")
        self.assertEqual(len(car.trail[0]), 7)
        self.assertAlmostEqual(car.trail[-1][4], sim.TRAIL_LIFE, delta=0.5)

        sim.draw_trails(screen, cars, cam)

        car.vx = car.vy = 0.0
        car.dead = True

        for _ in range(600):
            sim.step(dt, cars, [(0.0, None, False)])

        self.assertGreater(len(car.trail), 0, "Tracks should still exist after 10 seconds")

        for _ in range(300):
            sim.step(dt, cars, [(0.0, None, False)])

        self.assertEqual(len(car.trail), 0, "Tracks should cleanly fade out and expire after 13s")

    def test_mobile_tilt_simulation(self):
        sim.MOBILE_TILT = 0.75
        self.assertEqual(sim.MOBILE_TILT, 0.75)
        sim.MOBILE_TILT = None

    def test_camera_centered_on_car(self):
        car = sim.Car(400.0, 600.0, 30.0, (255, 0, 0))
        cam = sim.Camera(car)
        cam.shake = 0.0
        cam.ox = cam.oy = 0.0
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
        self.assertAlmostEqual(sim.SUN_DIR_X**2 + sim.SUN_DIR_Y**2, 1.0, delta=0.001)
        self.assertGreater(len(sim.FENCE_SHADOWS), 0, "FENCE_SHADOWS should have baked tiles")
        sample_shadow = next(iter(sim.FENCE_SHADOWS.values()))
        self.assertIsInstance(sample_shadow, pygame.Surface)

        car = sim.Car(sim.W / 2, sim.H / 2, 45.0, (255, 0, 0))
        cam = sim.Camera(car)
        screen = pygame.Surface((sim.W, sim.H))
        screen.fill(sim.GRASS_COLOR)
        sim.draw_car_shadow(screen, car, cam)

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

    def test_blue_mystery_boxes_and_random_powerups(self):
        self.assertGreaterEqual(sim.BOX_SIZE, 28)
        self.assertEqual(sim.BOX_TYPES, ["mystery"])
        self.assertEqual(sim.BOX_COLORS["mystery"], (45, 145, 255))
        self.assertEqual(sim.BOX_LETTER["mystery"], "?")

        sim.new_map(25524)
        for b in sim.BOXES:
            self.assertEqual(b["kind"], "mystery")

        self.assertIn("boost", sim.POWERUP_KINDS)
        self.assertIn("heart", sim.POWERUP_KINDS)
        self.assertIn("bash", sim.POWERUP_KINDS)


# ============================================================================
# 8. Destructibles and Sabotage Tests
# ============================================================================
class TestDestructiblesAndSabotage(unittest.TestCase):
    def setUp(self):
        ensure_display()
        sim.load_assets()
        sim.new_map(42)

    def test_destructibles_assets_loaded(self):
        for name in ("barrel", "box", "vase"):
            self.assertIn(name, sim.DESTRUCT_RAW, f"{name} should be in DESTRUCT_RAW")
            self.assertIn(name, sim.DESTRUCT_SURF, f"{name} should be in DESTRUCT_SURF")
            self.assertIn(name, sim.DESTRUCT_SHADOW, f"{name} should be in DESTRUCT_SHADOW")
            raw = sim.DESTRUCT_RAW[name]
            surf = sim.DESTRUCT_SURF[name]
            self.assertTrue(raw.get_flags() & pygame.SRCALPHA != 0)
            self.assertTrue(surf.get_flags() & pygame.SRCALPHA != 0)
            break_key = f"{name}_break"
            self.assertIn(break_key, sim.FX_FRAMES, f"{break_key} should be registered in FX_FRAMES")
            self.assertEqual(len(sim.FX_FRAMES[break_key]), 4, f"{break_key} should have 4 animation frames")

    def test_destructibles_spawning(self):
        self.assertGreater(len(sim.DESTRUCTIBLES), 0, "DESTRUCTIBLES should be populated on map spawn")
        for d in sim.DESTRUCTIBLES:
            self.assertIn(d["type"], ("barrel", "box", "vase"))
            self.assertFalse(d["destroyed"])
            self.assertIn("x", d)
            self.assertIn("y", d)
            self.assertIn("wobble", d)
            self.assertIn("respawn_timer", d)

    def test_high_speed_car_smashes_destructible(self):
        self.assertTrue(len(sim.DESTRUCTIBLES) > 0)
        target = sim.DESTRUCTIBLES[0]
        target["destroyed"] = False

        car = sim.Car(target["x"], target["y"] - 10, 90, (255, 0, 0))
        car.vx = 0.0
        car.vy = 200.0
        initial_fx_count = len(sim.FX)

        sim._update_destructibles(0.016, [car])
        self.assertTrue(target["destroyed"], "Destructible should be destroyed upon high speed impact")
        self.assertGreater(target["respawn_timer"], 0.0)
        self.assertGreater(len(sim.FX), initial_fx_count, "Break FX animation should be spawned")

    def test_low_speed_car_wobbles_and_pushes(self):
        target = sim.DESTRUCTIBLES[0]
        target["destroyed"] = False
        target["wobble"] = 0.0

        car = sim.Car(target["x"], target["y"] - 12, 90, (255, 0, 0))
        car.vx = 0.0
        car.vy = 20.0

        sim._update_destructibles(0.016, [car])
        self.assertFalse(target["destroyed"], "Destructible should not be destroyed by low speed bump")
        self.assertGreater(target["wobble"], 0.0, "Destructible should wobble when bumped")

    def test_throw_traffic_cone_forward_and_backward(self):
        car = sim.Car(100.0, 100.0, 0.0, (255, 0, 0))
        car.vx = 150.0
        car.vy = 0.0

        initial_cones = len(sim.CONES)
        res = sim.throw_traffic_cone(car, forward=True)
        self.assertTrue(res)
        self.assertEqual(len(sim.CONES), initial_cones + 1)
        cone = sim.CONES[-1]
        self.assertTrue(cone["knocked"])
        self.assertGreater(cone["vx"], car.vx + 200.0, "Cone should be launched ahead at high speed")
        self.assertTrue(cone.get("thrown"))
        self.assertEqual(cone.get("owner_uid"), car.uid)

        res2 = sim.throw_traffic_cone(car, forward=False)
        self.assertTrue(res2)
        cone2 = sim.CONES[-1]
        self.assertFalse(cone2["knocked"])
        self.assertEqual(cone2["vx"], 0.0)
        self.assertEqual(cone2["vy"], 0.0)

    def test_thrown_cone_smashes_destructible(self):
        target = sim.DESTRUCTIBLES[0]
        target["destroyed"] = False

        sim.CONES.append({
            "x": target["x"],
            "y": target["y"] - 5,
            "base_x": target["x"],
            "base_y": target["y"],
            "vx": 0.0,
            "vy": 300.0,
            "angle": 0.0,
            "vrot": 200.0,
            "knocked": True,
            "timer": 5.0,
            "thrown": True,
            "owner_uid": 999,
        })
        sim._update_destructibles(0.016, [])
        self.assertTrue(target["destroyed"], "Destructible should be destroyed when struck by a flying cone")

    def test_spill_oil(self):
        car = sim.Car(200.0, 200.0, 45.0, (255, 0, 0))
        car.vx = 100.0
        car.vy = 100.0
        initial_oil_count = len(sim.OIL)

        res = sim.spill_oil(car)
        self.assertTrue(res)
        self.assertGreater(len(sim.OIL), initial_oil_count)
        slick = sim.OIL[-1]
        self.assertEqual(len(slick), 6)

        victim = sim.Car(slick[0], slick[1], 45.0, (0, 0, 255))
        victim.vx = 200.0
        victim.stagger = 0.0
        sim._apply_oil(victim)
        self.assertGreater(victim.stagger, 0.0, "Car driving over oil slick should be staggered")

    def test_mystery_box_gives_cone_and_oil(self):
        car = sim.Car(300.0, 300.0, 0.0, (255, 0, 0))
        sim.give_powerup(car, "cone")
        self.assertEqual(car.item, "cone")

        res = car.use_sabotage("cone")
        self.assertTrue(res)
        self.assertIsNone(car.item)

        sim.give_powerup(car, "oil")
        self.assertEqual(car.item, "oil")
        res2 = car.use_sabotage("item")
        self.assertTrue(res2)
        self.assertIsNone(car.item)


# ============================================================================
# 9. Button Manager Tests
# ============================================================================
class TestButtonManager(unittest.TestCase):
    def setUp(self):
        ensure_display()

    def test_key_icon_default_size(self):
        icon = buttonmanager.get_key_icon("a")
        self.assertIsNotNone(icon)
        self.assertEqual(icon.get_size(), (21, 21), "Key icon default should be scaled to 21x21")

    def test_controller_icon_default_size(self):
        icon = buttonmanager.get_controller_icon("xbox", "a")
        self.assertIsNotNone(icon)
        self.assertEqual(icon.get_size(), (21, 21), "Controller icon default should be scaled to 21x21")

    def test_custom_sizes(self):
        icon16 = buttonmanager.get_key_icon("space", size=16)
        self.assertEqual(icon16.get_size(), (16, 16))
        icon24 = buttonmanager.get_controller_icon("ps", "cross", size=24)
        self.assertEqual(icon24.get_size(), (24, 24))


# ============================================================================
# 10. Network Client and Relay Server Tests
# ============================================================================
class TestNetClient(unittest.TestCase):
    def test_close_before_connect_is_safe(self):
        n = net.Net("ws://127.0.0.1:1")
        n.close()
        self.assertEqual(n.poll(), [])


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


async def recv_until(ws, kind, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        raw = await asyncio.wait_for(ws.recv(), timeout=end - time.time())
        msg = json.loads(raw)
        if msg.get("t") == kind:
            return msg
    raise AssertionError(f"timed out waiting for {kind!r}")


async def drain(ws, seconds=0.8):
    out = []
    end = time.time() + seconds
    while time.time() < end:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=end - time.time())
            out.append(json.loads(raw))
        except (asyncio.TimeoutError, websockets.ConnectionClosed):
            break
    return out


class TestNet(unittest.TestCase):
    def setUp(self):
        self.port = free_port()
        env = dict(os.environ, PORT=str(self.port))
        self.proc = subprocess.Popen([sys.executable, "server.py"], cwd=ROOT, env=env,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(50):
            try:
                socket.create_connection(("127.0.0.1", self.port), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.1)

    def tearDown(self):
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()

    def url(self):
        return f"ws://127.0.0.1:{self.port}"

    def run_async(self, coro):
        return asyncio.run(asyncio.wait_for(coro, timeout=15))

    def test_host_join_ready_start(self):
        async def scenario():
            async with websockets.connect(self.url()) as host, \
                    websockets.connect(self.url()) as joiner:
                await host.send(json.dumps({"t": "host", "name": "H", "flag": "bd", "max": 4}))
                room = await recv_until(host, "room")
                code = room["code"]
                await joiner.send(json.dumps({"t": "join", "code": code, "name": "J", "flag": "us"}))
                await recv_until(joiner, "room")
                await host.send(json.dumps({"t": "ready", "v": True}))
                await joiner.send(json.dumps({"t": "ready", "v": True}))
                hstart = await recv_until(host, "start")
                jstart = await recv_until(joiner, "start")
                self.assertEqual(hstart["seed"], jstart["seed"])
        self.run_async(scenario())

    def test_kick(self):
        async def scenario():
            async with websockets.connect(self.url()) as host, \
                    websockets.connect(self.url()) as joiner:
                await host.send(json.dumps({"t": "host", "name": "H", "flag": "bd", "max": 4}))
                hroom = await recv_until(host, "room")
                await joiner.send(json.dumps({"t": "join", "code": hroom["code"], "name": "J"}))
                jroom = await recv_until(joiner, "room")
                jid = jroom["self"]
                await host.send(json.dumps({"t": "kick", "id": jid}))
                kicked = await recv_until(joiner, "kicked")
                self.assertEqual(kicked["t"], "kicked")
        self.run_async(scenario())

    def test_host_migration(self):
        async def scenario():
            host = await websockets.connect(self.url())
            joiner = await websockets.connect(self.url())
            try:
                await host.send(json.dumps({"t": "host", "name": "H"}))
                hroom = await recv_until(host, "room")
                await joiner.send(json.dumps({"t": "join", "code": hroom["code"], "name": "J"}))
                jroom = await recv_until(joiner, "room")
                jid = jroom["self"]
                await host.close()
                promoted = None
                for _ in range(10):
                    m = await recv_until(joiner, "room", timeout=5)
                    if m.get("host") == jid:
                        promoted = m
                        break
                self.assertIsNotNone(promoted, "joiner was not promoted to host")
            finally:
                await joiner.close()
        self.run_async(scenario())

    def test_nonhost_cannot_send_authoritative(self):
        async def scenario():
            async with websockets.connect(self.url()) as host, \
                    websockets.connect(self.url()) as joiner:
                await host.send(json.dumps({"t": "host", "name": "H", "max": 4}))
                hroom = await recv_until(host, "room")
                await joiner.send(json.dumps({"t": "join", "code": hroom["code"], "name": "J"}))
                await recv_until(joiner, "room")
                await recv_until(host, "room")
                await joiner.send(json.dumps({"t": "finished", "order": [0, 1]}))
                msgs = await drain(host, 1.0)
                self.assertFalse(any(m.get("t") == "finished" for m in msgs),
                                 "server relayed a non-host authoritative message")
        self.run_async(scenario())

    def test_host_settings_sync(self):
        async def scenario():
            async with websockets.connect(self.url()) as host, \
                    websockets.connect(self.url()) as joiner:
                await host.send(json.dumps({
                    "t": "host", "name": "H", "max": 4,
                    "settings": {"bot_aggression": "Brutal", "laps": 5, "bot_count": "none"}
                }))
                hroom = await recv_until(host, "room")
                self.assertEqual(hroom["settings"]["bot_aggression"], "Brutal")
                self.assertEqual(hroom["settings"]["laps"], 5)
                self.assertEqual(hroom["settings"]["bot_count"], "none")

                await joiner.send(json.dumps({"t": "join", "code": hroom["code"], "name": "J"}))
                jroom = await recv_until(joiner, "room")
                self.assertEqual(jroom["settings"]["bot_aggression"], "Brutal")
                await recv_until(host, "room")

                await host.send(json.dumps({
                    "t": "settings",
                    "settings": {"bot_aggression": "Chill", "laps": 7}
                }))
                async def wait_aggr(ws, expected):
                    end = time.time() + 5.0
                    while time.time() < end:
                        m = await recv_until(ws, "room", timeout=end - time.time())
                        if m.get("settings", {}).get("bot_aggression") == expected:
                            return m
                    raise AssertionError(f"timed out waiting for bot_aggression={expected}")

                updated_h = await wait_aggr(host, "Chill")
                self.assertEqual(updated_h["settings"]["bot_aggression"], "Chill")
                self.assertEqual(updated_h["settings"]["laps"], 7)
                updated_j = await wait_aggr(joiner, "Chill")
                self.assertEqual(updated_j["settings"]["bot_aggression"], "Chill")
                self.assertEqual(updated_j["settings"]["laps"], 7)

                await host.send(json.dumps({"t": "ready", "v": True}))
                await joiner.send(json.dumps({"t": "ready", "v": True}))
                hstart = await recv_until(host, "start")
                jstart = await recv_until(joiner, "start")
                self.assertEqual(hstart["settings"]["bot_aggression"], "Chill")
                self.assertEqual(jstart["settings"]["bot_aggression"], "Chill")
        self.run_async(scenario())


# ============================================================================
# 11. Redis Multi-Instance Cluster Tests
# ============================================================================
try:
    import redis  # noqa: F401
    HAVE_REDIS = True
except ImportError:
    HAVE_REDIS = False

REDIS_BIN = shutil.which("redis-server")


def wait_port(port, timeout=6):
    end = time.time() + timeout
    while time.time() < end:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            return True
        except OSError:
            time.sleep(0.1)
    return False


@unittest.skipUnless(HAVE_REDIS and REDIS_BIN, "redis-server / redis not available")
class TestRedisCluster(unittest.TestCase):
    def setUp(self):
        self.rport = free_port()
        self.redis = subprocess.Popen(
            [REDIS_BIN, "--port", str(self.rport), "--save", "", "--appendonly", "no"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.assertTrue(wait_port(self.rport), "redis did not start")
        url = f"redis://127.0.0.1:{self.rport}"
        self.pa, self.pb = free_port(), free_port()
        env = dict(os.environ, REDIS_URL=url)
        self.sa = subprocess.Popen([sys.executable, "server.py"], cwd=ROOT,
                                   env=dict(env, PORT=str(self.pa)),
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.sb = subprocess.Popen([sys.executable, "server.py"], cwd=ROOT,
                                   env=dict(env, PORT=str(self.pb)),
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.assertTrue(wait_port(self.pa) and wait_port(self.pb), "servers did not start")
        time.sleep(0.8)

    def tearDown(self):
        for p in (self.sa, self.sb, self.redis):
            p.terminate()
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()

    def test_cross_instance_lobby(self):
        async def scenario():
            host = await websockets.connect(f"ws://127.0.0.1:{self.pa}")
            joiner = await websockets.connect(f"ws://127.0.0.1:{self.pb}")
            try:
                await host.send(json.dumps({"t": "host", "name": "A", "flag": "bd", "max": 4}))
                room = await recv_until(host, "room")
                code = room["code"]
                await joiner.send(json.dumps({"t": "join", "code": code, "name": "B"}))
                jroom = await recv_until(joiner, "room")
                self.assertIn("self", jroom)
                self.assertEqual(len(jroom["players"]), 2)
                await host.send(json.dumps({"t": "ready", "v": True}))
                await joiner.send(json.dumps({"t": "ready", "v": True}))
                hs = await recv_until(host, "start")
                js = await recv_until(joiner, "start")
                self.assertEqual(hs["seed"], js["seed"])
                await host.send(json.dumps({"t": "state", "slot": 0, "car": {"x": 1.0}}))
                st = await recv_until(joiner, "state")
                self.assertEqual(st["car"]["x"], 1.0)
            finally:
                await host.close()
                await joiner.close()
        asyncio.run(asyncio.wait_for(scenario(), timeout=15))


class TestTilesets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((sim.W, sim.H), pygame.NOFRAME)
        sim.load_assets()

    def test_all_tilesets_load_and_generate(self):
        for ts in ["meadow_dirt", "asphalt_circuit", "frost_pass"]:
            sim.set_tileset(ts)
            self.assertEqual(sim.CURRENT_TILESET, ts)
            self.assertIsNotNone(sim.TILES)
            self.assertEqual(len(sim.TILES), 3)
            self.assertEqual(len(sim.TILES[0]), 3)
            self.assertTrue(all(sim.CHECK_TILES.get(k) is not None for k in ("center", "left", "right", "top", "bottom")))
            sim.new_map(100, tileset=ts)
            self.assertGreater(sim.ROAD_LEN, 1000)
            self.assertIsNotNone(sim.GROUND_SURF)

    def test_frost_pass_palette(self):
        sim.set_tileset("frost_pass")
        # Grass (deep snow) is high-key snow #f0f8ff (240, 248, 255)
        self.assertGreater(sim.GRASS_COLOR[0], 230)
        self.assertGreater(sim.GRASS_COLOR[1], 230)
        self.assertGreater(sim.GRASS_COLOR[2], 230)
        # Skid marks are grey / slate
        self.assertEqual(sim.SKID_ROAD_COLOR, (70, 74, 85))
        self.assertEqual(sim.SKID_GRASS_COLOR, (165, 190, 206))


if __name__ == "__main__":
    unittest.main()
