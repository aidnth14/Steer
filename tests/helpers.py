"""Shared headless setup for the test suite.

Forces SDL's dummy drivers (no window, no audio) and opens a hidden display once, which
sim.new_map()/load_assets() need to convert() surfaces.
"""
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import sim


def ensure_display():
    # idempotent, and re-inits if a prior test (e.g. the game loop) called pygame.quit()
    if not pygame.display.get_init() or pygame.display.get_surface() is None:
        pygame.init()
        pygame.display.set_mode((sim.W, sim.H))
        sim.load_assets()
