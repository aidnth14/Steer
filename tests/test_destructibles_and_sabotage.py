import math
import unittest
import pygame
from tests.helpers import ensure_display
import sim

class TestDestructiblesAndSabotage(unittest.TestCase):
    def setUp(self):
        ensure_display()
        sim.load_assets()
        sim.new_map(42)

    def test_destructibles_assets_loaded(self):
        # 1. Intact surfaces loaded
        for name in ("barrel", "box", "vase"):
            self.assertIn(name, sim.DESTRUCT_RAW, f"{name} should be in DESTRUCT_RAW")
            self.assertIn(name, sim.DESTRUCT_SURF, f"{name} should be in DESTRUCT_SURF")
            self.assertIn(name, sim.DESTRUCT_SHADOW, f"{name} should be in DESTRUCT_SHADOW")
            raw = sim.DESTRUCT_RAW[name]
            surf = sim.DESTRUCT_SURF[name]
            self.assertTrue(raw.get_flags() & pygame.SRCALPHA != 0)
            self.assertTrue(surf.get_flags() & pygame.SRCALPHA != 0)
            # Verify 4-frame shatter animation in FX_FRAMES
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
        car.vy = 200.0  # high speed
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
        car.vy = 20.0  # low speed <= 60

        sim._update_destructibles(0.016, [car])
        self.assertFalse(target["destroyed"], "Destructible should not be destroyed by low speed bump")
        self.assertGreater(target["wobble"], 0.0, "Destructible should wobble when bumped")

    def test_throw_traffic_cone_forward_and_backward(self):
        car = sim.Car(100.0, 100.0, 0.0, (255, 0, 0))
        car.vx = 150.0
        car.vy = 0.0

        # Forward throw
        initial_cones = len(sim.CONES)
        res = sim.throw_traffic_cone(car, forward=True)
        self.assertTrue(res)
        self.assertEqual(len(sim.CONES), initial_cones + 1)
        cone = sim.CONES[-1]
        self.assertTrue(cone["knocked"])
        self.assertGreater(cone["vx"], car.vx + 200.0, "Cone should be launched ahead at high speed")
        self.assertTrue(cone.get("thrown"))
        self.assertEqual(cone.get("owner_uid"), car.uid)

        # Backward drop
        res2 = sim.throw_traffic_cone(car, forward=False)
        self.assertTrue(res2)
        cone2 = sim.CONES[-1]
        self.assertFalse(cone2["knocked"])
        self.assertEqual(cone2["vx"], 0.0)
        self.assertEqual(cone2["vy"], 0.0)

    def test_thrown_cone_smashes_destructible(self):
        target = sim.DESTRUCTIBLES[0]
        target["destroyed"] = False

        # Thrown cone flying toward destructible
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
        self.assertEqual(len(slick), 6)  # [x, y, l, w, angle, max_r]

        # Another car driving over this slick should be affected
        victim = sim.Car(slick[0], slick[1], 45.0, (0, 0, 255))
        victim.vx = 200.0
        victim.stagger = 0.0
        sim._apply_oil(victim)
        self.assertGreater(victim.stagger, 0.0, "Car driving over oil slick should be staggered")

    def test_mystery_box_gives_cone_and_oil(self):
        car = sim.Car(300.0, 300.0, 0.0, (255, 0, 0))
        sim.give_powerup(car, "cone")
        self.assertEqual(car.item, "cone")

        # Using sabotage consumes the held item
        res = car.use_sabotage("cone")
        self.assertTrue(res)
        self.assertIsNone(car.item)

        sim.give_powerup(car, "oil")
        self.assertEqual(car.item, "oil")
        res2 = car.use_sabotage("item")
        self.assertTrue(res2)
        self.assertIsNone(car.item)

if __name__ == "__main__":
    unittest.main()
