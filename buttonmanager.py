"""Button Manager for Steer.
Manages and renders pixel-art keyboard and controller button prompt sprites
from assets/UI/keyboardbtn/ and assets/UI/controller/.
"""

import os
import sys
import pygame

# Resolve base directories
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KEYBOARD_DIR = os.path.join(_BASE_DIR, "assets", "UI", "keyboardbtn")
CONTROLLER_DIR = os.path.join(_BASE_DIR, "assets", "UI", "controller")

# Key code and name mapping to filename stems
KEY_MAPPINGS = {
    # Letters
    pygame.K_a: "a", pygame.K_b: "b", pygame.K_c: "c", pygame.K_d: "d",
    pygame.K_e: "e", pygame.K_f: "f", pygame.K_g: "g", pygame.K_h: "h",
    pygame.K_i: "i", pygame.K_j: "j", pygame.K_k: "k", pygame.K_l: "l",
    pygame.K_m: "m", pygame.K_n: "n", pygame.K_o: "o", pygame.K_p: "p",
    pygame.K_q: "q", pygame.K_r: "r", pygame.K_s: "s", pygame.K_t: "t",
    pygame.K_u: "u", pygame.K_v: "v", pygame.K_w: "w", pygame.K_x: "x",
    pygame.K_y: "y", pygame.K_z: "z",
    # Numbers
    pygame.K_0: "0", pygame.K_1: "1", pygame.K_2: "2", pygame.K_3: "3",
    pygame.K_4: "4", pygame.K_5: "5", pygame.K_6: "6", pygame.K_7: "7",
    pygame.K_8: "8", pygame.K_9: "9",
    # Navigation / Specials
    pygame.K_SPACE: "space",
    pygame.K_RETURN: "enter",
    pygame.K_KP_ENTER: "enter",
    pygame.K_ESCAPE: "esc",
    pygame.K_TAB: "tab",
    pygame.K_BACKSPACE: "backspace",
    pygame.K_LSHIFT: "shift",
    pygame.K_RSHIFT: "shift",
    pygame.K_LCTRL: "ctrl",
    pygame.K_RCTRL: "ctrl",
    pygame.K_LALT: "alt",
    pygame.K_RALT: "alt",
    pygame.K_UP: "up",
    pygame.K_DOWN: "down",
    pygame.K_LEFT: "left",
    pygame.K_RIGHT: "right",
    pygame.K_DELETE: "delete",
    pygame.K_HOME: "home",
    pygame.K_END: "end",
    pygame.K_PAGEUP: "pageup",
    pygame.K_PAGEDOWN: "pagedown",
    pygame.K_MINUS: "minus",
    pygame.K_KP_MINUS: "minus",
    pygame.K_EQUALS: "equal",
    pygame.K_PLUS: "plus",
    pygame.K_KP_PLUS: "plus",
    pygame.K_SLASH: "slash",
    pygame.K_KP_DIVIDE: "slash",
    # Function keys
    pygame.K_F1: "f1", pygame.K_F2: "f2", pygame.K_F3: "f3", pygame.K_F4: "f4",
    pygame.K_F5: "f5", pygame.K_F6: "f6", pygame.K_F7: "f7", pygame.K_F8: "f8",
    pygame.K_F9: "f9", pygame.K_F10: "f10", pygame.K_F11: "f11", pygame.K_F12: "f12",
}

# String name aliases to standard stems
KEY_NAME_ALIASES = {
    "space": "space",
    "enter": "enter",
    "return": "enter",
    "esc": "esc",
    "escape": "esc",
    "shift": "shift",
    "left shift": "shift",
    "right shift": "shift",
    "ctrl": "ctrl",
    "control": "ctrl",
    "left ctrl": "ctrl",
    "right ctrl": "ctrl",
    "alt": "alt",
    "left alt": "alt",
    "right alt": "alt",
    "tab": "tab",
    "backspace": "backspace",
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
    "delete": "delete",
    "del": "delete",
}

DEFAULT_ICON_SIZE = 21  # Native is 16x16; default scaled up by 5px to 21x21

class ButtonManager:
    """Manages cached button prompt sprites for keyboard and controllers."""
    def __init__(self):
        self._key_cache = {}        # (stem, state, size) -> Surface
        self._ctrl_cache = {}       # (c_type, btn, state, size) -> Surface

    def _resolve_key_stem(self, key):
        if isinstance(key, int):
            if key in KEY_MAPPINGS:
                return KEY_MAPPINGS[key]
            # fallback to pygame key name
            name = pygame.key.name(key).lower()
        else:
            name = str(key).lower().strip()

        if name in KEY_NAME_ALIASES:
            return KEY_NAME_ALIASES[name]
        return name

    def get_key_icon(self, key, state="outline_idle", size=None):
        """Retrieve a Pygame Surface for a keyboard key sprite.
        
        Args:
            key: int keycode (e.g. pygame.K_SPACE) or str ('a', 'space', 'esc', etc.)
            state: 'idle', 'outline_idle', 'pressed', or 'outline_pressed'
            size: optional (width, height) tuple or int square size (defaults to 21)
        """
        if size is None:
            size = DEFAULT_ICON_SIZE
        elif size == "native":
            size = None
        stem = self._resolve_key_stem(key)
        cache_key = (stem, state, size)
        if cache_key in self._key_cache:
            return self._key_cache[cache_key]

        filenames = []
        if state in ("outline_idle", "default"):
            filenames.append(f"{stem}.png")
            filenames.append(f"{stem}_outline_idle.png")
        else:
            filenames.append(f"{stem}_{state}.png")
            filenames.append(f"{stem}.png")

        surf = None
        for fn in filenames:
            p = os.path.join(KEYBOARD_DIR, fn)
            if os.path.exists(p):
                try:
                    loaded = pygame.image.load(p)
                    if pygame.display.get_surface() is not None:
                        try:
                            surf = loaded.convert_alpha()
                        except pygame.error:
                            surf = loaded
                    else:
                        surf = loaded
                    break
                except pygame.error:
                    pass

        if surf is not None and size is not None:
            sz = (size, size) if isinstance(size, int) else size
            surf = pygame.transform.scale(surf, sz)

        self._key_cache[cache_key] = surf
        return surf

    def get_controller_icon(self, controller_type, button_name, state="outline_idle", size=None):
        """Retrieve a Pygame Surface for a controller button sprite.
        
        Args:
            controller_type: 'xbox', 'ps', 'nintendo' (or 'switch'), 'minimal'
            button_name: 'a', 'b', 'x', 'y', 'lb', 'rb', 'cross', 'triangle', etc.
            state: 'idle', 'outline_idle', 'pressed', 'outline_pressed'
            size: optional (width, height) tuple or int square size (defaults to 21)
        """
        if size is None:
            size = DEFAULT_ICON_SIZE
        elif size == "native":
            size = None
        c_type = controller_type.lower()
        if c_type in ("switch",):
            c_type = "nintendo"
        btn = button_name.lower().strip()
        cache_key = (c_type, btn, state, size)
        if cache_key in self._ctrl_cache:
            return self._ctrl_cache[cache_key]

        c_dir = os.path.join(CONTROLLER_DIR, c_type)
        filenames = []
        if state in ("outline_idle", "default"):
            filenames.append(f"{btn}.png")
            filenames.append(f"{btn}_outline_idle.png")
        else:
            filenames.append(f"{btn}_{state}.png")
            filenames.append(f"{btn}.png")

        surf = None
        for fn in filenames:
            p = os.path.join(c_dir, fn)
            if os.path.exists(p):
                try:
                    loaded = pygame.image.load(p)
                    if pygame.display.get_surface() is not None:
                        try:
                            surf = loaded.convert_alpha()
                        except pygame.error:
                            surf = loaded
                    else:
                        surf = loaded
                    break
                except pygame.error:
                    pass

        if surf is not None and size is not None:
            sz = (size, size) if isinstance(size, int) else size
            surf = pygame.transform.scale(surf, sz)

        self._ctrl_cache[cache_key] = surf
        return surf

    def draw_key(self, screen, key, pos, state="outline_idle", size=None, align="topleft"):
        """Draws a keyboard key icon at `pos`."""
        surf = self.get_key_icon(key, state, size)
        if surf is not None:
            if align == "center":
                r = surf.get_rect(center=pos)
                screen.blit(surf, r)
            elif align == "midright":
                r = surf.get_rect(midright=pos)
                screen.blit(surf, r)
            elif align == "midleft":
                r = surf.get_rect(midleft=pos)
                screen.blit(surf, r)
            else:
                screen.blit(surf, pos)
            return True
        return False

    def draw_controller_button(self, screen, controller_type, button_name, pos, state="outline_idle", size=None, align="topleft"):
        """Draws a controller button icon at `pos`."""
        surf = self.get_controller_icon(controller_type, button_name, state, size)
        if surf is not None:
            if align == "center":
                r = surf.get_rect(center=pos)
                screen.blit(surf, r)
            elif align == "midright":
                r = surf.get_rect(midright=pos)
                screen.blit(surf, r)
            elif align == "midleft":
                r = surf.get_rect(midleft=pos)
                screen.blit(surf, r)
            else:
                screen.blit(surf, pos)
            return True
        return False

# Global singleton instance
_GLOBAL_MANAGER = None

def get_button_manager():
    global _GLOBAL_MANAGER
    if _GLOBAL_MANAGER is None:
        _GLOBAL_MANAGER = ButtonManager()
    return _GLOBAL_MANAGER

def get_key_icon(key, state="outline_idle", size=None):
    return get_button_manager().get_key_icon(key, state, size)

def get_controller_icon(controller_type, button_name, state="outline_idle", size=None):
    return get_button_manager().get_controller_icon(controller_type, button_name, state, size)

def draw_key(screen, key, pos, state="outline_idle", size=None, align="topleft"):
    return get_button_manager().draw_key(screen, key, pos, state, size, align)

def draw_controller_button(screen, controller_type, button_name, pos, state="outline_idle", size=None, align="topleft"):
    return get_button_manager().draw_controller_button(screen, controller_type, button_name, pos, state, size, align)

# Backwards compatibility so 'from ui import buttonmanager' works seamlessly
import types
_ui_mod = types.ModuleType("ui")
_ui_mod.buttonmanager = sys.modules[__name__]
sys.modules.setdefault("ui", _ui_mod)
sys.modules.setdefault("ui.buttonmanager", sys.modules[__name__])

__all__ = [
    "ButtonManager",
    "get_button_manager",
    "get_key_icon",
    "get_controller_icon",
    "draw_key",
    "draw_controller_button",
    "KEYBOARD_DIR",
    "CONTROLLER_DIR",
    "DEFAULT_ICON_SIZE",
]
