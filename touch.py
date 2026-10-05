"""On-screen touch controls for Steer (Android / mobile APK).

The game renders to a fixed 600x400 logical surface handed to SDL via pygame.SCALED.
Mouse coords are auto-mapped back to logical space, but raw FINGER* events are NOT --
they arrive normalised (0..1) against the physical window, which is letterboxed when the
device aspect != 3:2. We invert that letterbox transform here so touch buttons line up
with what is drawn.

Multitouch is required (steer + throttle + fire at once), so we track finger_id -> button
and never rely on SDL's single-pointer mouse emulation for gameplay.
"""

import os
import math
import pygame


def detect_mobile():
    """True on an Android build (buildozer/p4a sets ANDROID_ARGUMENT) or forced via env."""
    if os.environ.get("STEER_FORCE_TOUCH") == "1":
        return True
    if "ANDROID_ARGUMENT" in os.environ or "ANDROID_APP_PATH" in os.environ:
        return True
    try:
        import platform
        # Pygame's Android SDL2 port reports 'Linux' but p4a always sets the env above;
        # keep a cheap secondary check for the kivy/p4a bootstrap marker.
        return bool(getattr(platform, "ANDROID", False))
    except Exception:
        return False


def _letterbox_map(nx, ny, logical_w, logical_h):
    """Normalised window coords (0..1) -> logical 600x400 coords, undoing SCALED letterbox."""
    try:
        win_w, win_h = pygame.display.get_window_size()
    except Exception:
        win_w, win_h = logical_w, logical_h
    if win_w <= 0 or win_h <= 0:
        return nx * logical_w, ny * logical_h
    scale = min(win_w / logical_w, win_h / logical_h)
    off_x = (win_w - logical_w * scale) * 0.5
    off_y = (win_h - logical_h * scale) * 0.5
    lx = (nx * win_w - off_x) / scale
    ly = (ny * win_h - off_y) / scale
    return lx, ly


class _Btn:
    __slots__ = ("key", "rect", "label", "momentary", "color", "radius")

    def __init__(self, key, rect, label, momentary, color, radius):
        self.key = key
        self.rect = rect
        self.label = label
        self.momentary = momentary      # True = fires once per press (edge); False = held state
        self.color = color
        self.radius = radius            # >0 draws a circle, else rounded rect


class TouchControls:
    """Owns the on-screen pad: layout, finger tracking, draw, and per-frame control read."""

    def __init__(self, logical_w, logical_h, font):
        self.W = logical_w
        self.H = logical_h
        self.font = font
        self.visible = True
        self.opacity = 150
        self.use_steer_buttons = True   # show the L/R arrows (off when gyro is the steer source)
        self._buttons = []
        self._held = set()              # keys currently held by a finger
        self._edges = set()             # momentary keys pressed this frame (consumed by read())
        self._finger_btn = {}           # finger_id -> button key
        self._steer_finger = {}         # finger_id -> steer value from an arrow
        self._layout()

    # ---- layout --------------------------------------------------------------
    def _layout(self):
        W, H = self.W, self.H
        self._buttons = []
        b = self._buttons.append

        # Steering arrows, bottom-left (held)
        sw, sh = 78, 70
        pad = 14
        b(_Btn("steer_left", pygame.Rect(pad, H - sh - pad, sw, sh), "<", False, (90, 200, 255), 0))
        b(_Btn("steer_right", pygame.Rect(pad * 2 + sw, H - sh - pad, sw, sh), ">", False, (90, 200, 255), 0))

        # Action cluster, bottom-right
        r = 40
        cx = W - 60
        cy = H - 60
        b(_Btn("fire", pygame.Rect(cx - r, cy - r, r * 2, r * 2), "FIRE", True, (255, 90, 90), r))
        b(_Btn("hazard", pygame.Rect(cx - r - 92, cy - 24, 64, 48), "DROP", True, (255, 190, 80), 0))
        b(_Btn("ram", pygame.Rect(cx - 24, cy - r - 92, 48, 48), "RAM", True, (255, 240, 120), 0))
        b(_Btn("drift", pygame.Rect(cx - r - 92, cy - r - 66, 64, 48), "DRIFT", False, (150, 160, 255), 0))

        # Brake, left of the action cluster (held)
        b(_Btn("brake", pygame.Rect(W - 300, H - 66, 70, 52), "BRAKE", False, (255, 120, 120), 0))

        # Small utility buttons, top-right: recenter gyro + pause
        b(_Btn("recenter", pygame.Rect(W - 150, 12, 64, 30), "LEVEL", True, (120, 230, 170), 0))
        b(_Btn("pause", pygame.Rect(W - 78, 12, 64, 30), "II", True, (210, 210, 210), 0))

    def set_steer_buttons(self, on):
        self.use_steer_buttons = on

    def _active_buttons(self):
        for btn in self._buttons:
            if not self.use_steer_buttons and btn.key in ("steer_left", "steer_right"):
                continue
            yield btn

    # ---- event handling ------------------------------------------------------
    def handle_event(self, ev):
        """Feed FINGERDOWN / FINGERMOTION / FINGERUP. Returns True if the touch was consumed."""
        if ev.type == pygame.FINGERDOWN:
            lx, ly = _letterbox_map(ev.x, ev.y, self.W, self.H)
            for btn in self._active_buttons():
                if btn.rect.collidepoint(lx, ly):
                    self._finger_btn[ev.finger_id] = btn.key
                    if btn.momentary:
                        if btn.key not in self._held:
                            self._edges.add(btn.key)
                        self._held.add(btn.key)
                    else:
                        self._held.add(btn.key)
                    return True
            return False
        if ev.type == pygame.FINGERMOTION:
            # allow sliding between the two steer arrows without lifting
            if ev.finger_id in self._finger_btn:
                lx, ly = _letterbox_map(ev.x, ev.y, self.W, self.H)
                cur = self._finger_btn[ev.finger_id]
                if cur in ("steer_left", "steer_right"):
                    for btn in self._active_buttons():
                        if btn.key in ("steer_left", "steer_right") and btn.rect.collidepoint(lx, ly):
                            if cur != btn.key:
                                self._held.discard(cur)
                                self._held.add(btn.key)
                                self._finger_btn[ev.finger_id] = btn.key
                            break
                return True
            return False
        if ev.type == pygame.FINGERUP:
            key = self._finger_btn.pop(ev.finger_id, None)
            if key is not None:
                # only release the held flag if no other finger still holds this key
                if key not in self._finger_btn.values():
                    self._held.discard(key)
                return True
            return False
        return False

    # ---- per-frame control read ---------------------------------------------
    def read(self):
        """Return a dict of this frame's control intents and clear edge triggers."""
        steer = 0.0
        if "steer_left" in self._held:
            steer -= 1.0
        if "steer_right" in self._held:
            steer += 1.0
        out = {
            "steer": steer,
            "drift": "drift" in self._held,
            "brake": "brake" in self._held,
            "fire": "fire" in self._edges,
            "hazard": "hazard" in self._edges,
            "ram": "ram" in self._edges,
            "recenter": "recenter" in self._edges,
            "pause": "pause" in self._edges,
        }
        self._edges.clear()
        return out

    def release_all(self):
        self._held.clear()
        self._edges.clear()
        self._finger_btn.clear()

    # ---- rendering -----------------------------------------------------------
    def draw(self, screen):
        if not self.visible:
            return
        surf = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
        for btn in self._active_buttons():
            down = btn.key in self._held
            a = self.opacity + (70 if down else 0)
            col = (*btn.color, min(255, a))
            edge = (255, 255, 255, min(255, a + 40))
            if btn.radius > 0:
                center = btn.rect.center
                pygame.draw.circle(surf, col, center, btn.radius)
                pygame.draw.circle(surf, edge, center, btn.radius, 2)
            else:
                pygame.draw.rect(surf, col, btn.rect, border_radius=10)
                pygame.draw.rect(surf, edge, btn.rect, 2, border_radius=10)
            if btn.label:
                t = self.font.render(btn.label, True, (15, 20, 25))
                surf.blit(t, t.get_rect(center=btn.rect.center))
        screen.blit(surf, (0, 0))
