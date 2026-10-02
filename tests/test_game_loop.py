import os
import tempfile
import unittest

from tests.helpers import ensure_display
import pygame
import sim
import main

W2 = sim.W // 2


class KeyState:
    """Stand-in for pygame.key.get_pressed(): truthy only for held keycodes."""
    def __init__(self, held):
        self.held = held

    def __getitem__(self, k):
        return 1 if k in self.held else 0


class Script:
    """Feeds scripted events / mouse / keys per frame to a headless main()."""
    def __init__(self):
        self.frame = -1
        self.events = {}        # frame -> [pygame.event.Event]
        self.mouse = {}         # frame -> (x, y)
        self.keys = {}          # frame -> set(keycodes)
        self.cur_mouse = (0, 0)
        self.cur_keys = set()
        self.END = 460          # after this, force QUIT every frame

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
        # main calls get_pos() first each frame, so advance the frame counter here
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
        # menu: Play (first menu button, y=100 h=46)
        script.click(5, (W2, 123))
        # mode: Singleplayer (sp_btn at y=120 h=48)
        script.click(12, (W2, 144))
        # gamemode: Race (first mode button at y=90 h=36)
        script.click(19, (W2, 108))
        # name_entry: Start Race (start_btn at y=256 h=42)
        script.click(26, (W2, 277))
        # countdown is 3 s (~180 frames); hold steer through the race
        script.hold(30, 400, {pygame.K_a})
        # bashes + ram once racing
        for f in (230, 250, 270):
            script.key(f, pygame.K_q)
            script.key(f + 5, pygame.K_e)
            script.key(f + 10, pygame.K_SPACE)
        # Esc -> pause menu, then Resume (first menu button), then let END post QUIT
        script.key(330, pygame.K_ESCAPE)
        script.click(345, (W2, 123))

        # count sim.step calls to prove we reached the race
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


if __name__ == "__main__":
    unittest.main()
