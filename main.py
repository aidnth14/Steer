import math
import os
import random
import socket
import subprocess
import sys
from urllib.parse import urlparse
import webbrowser
import pygame
from pygame._sdl2 import controller as sdlctrl

import sim
import net
import buttonmanager
import ui

VERSION = "1.2.0"
CREDIT = "made by @AidenShoroz · v" + VERSION
# the icons in the menu's bottom-right corner: (icon, link). An icon only shows once its link is
# filled in. Icons: "store" (bag), "video" (screen + play), "photo" (camera), "chat" (bubble).
SOCIAL_LINKS = [
    ("store", "https://aiden-shoroz.itch.io/"),
    ("video", "https://www.youtube.com/@aidnth14"),
    ("photo", "https://www.instagram.com/aidnth14/"),
    ("chat", "https://discord.com/users/1125415771737182310"),
]

# Shown on the connect/cold-start loading screen to keep the ~30s free-tier wake entertaining.
LOADING_TIPS = [
    "Hold DRIFT through corners to carry speed out of the apex.",
    "Tuck in behind a rival to slipstream, then slingshot past.",
    "Bash left or right to knock rivals off the racing line.",
    "Grab mystery boxes for boosts, oil slicks and homing items.",
    "Drop a hazard behind you to trip up whoever's chasing.",
    "The free server naps when idle — first connect wakes it up.",
    "Tilt-to-steer? Enable Gyro Steering on your phone in Settings.",
    "Press F11 any time to go fullscreen.",
]

# gamepad: SDL's game-controller layer maps Xbox / PlayStation / Nintendo pads to one
# standard layout (A = bottom face button, LB/RB = shoulders, etc.), so one mapping works
# for all three. Buttons/axes are the pygame CONTROLLER_* constants.
PAD_DEADZONE = 0.35
PAD_STEER_AXIS = pygame.CONTROLLER_AXIS_LEFTX
PAD_BASH_L = pygame.CONTROLLER_BUTTON_LEFTSHOULDER    # LB / L1 / L
PAD_BASH_R = pygame.CONTROLLER_BUTTON_RIGHTSHOULDER   # RB / R1 / R
PAD_RAM = pygame.CONTROLLER_BUTTON_A                  # A / Cross / B(south)
PAD_SHOOT = pygame.CONTROLLER_BUTTON_X                # X / Square / Y(west)
PAD_ITEM = pygame.CONTROLLER_BUTTON_Y                 # Y / Triangle / X(north)
PAD_PAUSE = pygame.CONTROLLER_BUTTON_START            # Start / Options / Menu
PAD_SELECT = pygame.CONTROLLER_BUTTON_BACK            # Back / Select / Share / View
PAD_CONFIRM = pygame.CONTROLLER_BUTTON_A
PAD_BACK = pygame.CONTROLLER_BUTTON_B
PAD_UP = pygame.CONTROLLER_BUTTON_DPAD_UP
PAD_DOWN = pygame.CONTROLLER_BUTTON_DPAD_DOWN
PAD_LEFT = pygame.CONTROLLER_BUTTON_DPAD_LEFT
PAD_RIGHT = pygame.CONTROLLER_BUTTON_DPAD_RIGHT
PAD_L3 = pygame.CONTROLLER_BUTTON_LEFTSTICK
PAD_R3 = pygame.CONTROLLER_BUTTON_RIGHTSTICK

SIM_PATH = os.path.join(os.path.dirname(__file__), "sim.py")
MAIN_PATH = os.path.abspath(__file__)
# Frozen (PyInstaller) builds have no .py source on disk, so the live hot-reload must be off.
FROZEN = bool(getattr(sys, "frozen", False))

def _safe_mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0
SERVER_PATH = os.path.join(os.path.dirname(__file__), "server.py")
PROFILE_PATH = os.path.join(os.path.expanduser("~"), ".steer_profile.json")

def ensure_local_server():
    # autostarts server.py so Host/Join work with zero setup; no-op if STEER_SERVER_URL
    # points at a remote server, or something (us from a prior launch, docker-compose, a
    # manual run) is already listening on the local port
    url = urlparse(net.DEFAULT_URL)
    if url.hostname not in ("localhost", "127.0.0.1"):
        return
    host, port = url.hostname, url.port or 8765
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        if s.connect_ex((host, port)) == 0:
            return
    try:
        log = open(os.path.join(os.path.dirname(__file__), "server.log"), "a")
        subprocess.Popen([sys.executable, SERVER_PATH],
                          env=dict(os.environ, PORT=str(port)),
                          stdout=log, stderr=log, start_new_session=True)
        print(f"Started local multiplayer server on {host}:{port} (log: server.log)")
    except OSError as e:
        print("Could not start local multiplayer server:", e)

# rebindable keyboard actions (defaults); stored per-user in the profile
DEFAULT_KEYS = {
    "left": pygame.K_a, "right": pygame.K_d, "ram": pygame.K_SPACE,
    "brake": pygame.K_s, "drift": pygame.K_LSHIFT,
    "bashL": pygame.K_q, "bashR": pygame.K_e, "shoot": pygame.K_f,
    "cone": pygame.K_c, "oil": pygame.K_v, "drop_hazard": pygame.K_v,
}
KEY_ACTIONS = [
    ("left", "Steer Left"),
    ("right", "Steer Right"),
    ("ram", "Accelerate / Ram"),
    ("brake", "Brake / Reverse"),
    ("drift", "Drift (Hold)"),
    ("bashL", "Bash Left"),
    ("bashR", "Bash Right"),
    ("shoot", "Use Item / Shoot"),
    ("drop_hazard", "Drop Hazard Behind"),
]

GAME_MODES = [("race", "Race"), ("trial", "Time Trial"), ("elim", "Elimination"),
              ("team", "Team Race")]
ELIM_INTERVAL = 8.0     # seconds between eliminations in Elimination mode
TEAM_COLORS = [(230, 70, 70), (70, 120, 235)]   # red / blue teams
MENU_STATES = {"menu", "mode", "gamemode", "mp_menu",
               "settings", "name_entry", "results", "lobby"}

def load_profile():
    import json
    d = {
        "name": "Player", "flag": "us", "races": 0, "wins": 0,
        "best_lap": 0.0, "master_volume": 1.0, "sfx_volume": 0.8,
        "music_volume": 0.6, "engine_volume": 0.8, "ui_volume": 0.8,
        "laps": 3, "hud_mode": "Classic", "steer_rate": 1.0,
        "steer_curve": 1.0, "stick_deadzone": 0.05, "drift_assist": 0.4,
        "invert_steer": False, "look_ahead_cam": False, "ghost_opacity": 0.6,
        "display_mode": "Windowed", "pixel_perfect": False, "fps_cap": "60 FPS",
        "show_fps": False, "pad_preset": "Arcade Classic", "mouse_aim": True,
        "gyro_steer": False, "gyro_sens": 0.5,
        "keys": {}, "shaders": dict(sim.SHADER_SETTINGS),
        "bot_aggression": "Casual", "track_type": "meadow_dirt"
    }
    try:
        with open(PROFILE_PATH) as f:
            d.update(json.load(f))
    except (OSError, ValueError):
        pass
    if "shaders" in d and isinstance(d["shaders"], dict):
        sim.set_shader_settings(d["shaders"])
    return d

def apply_profile_to_sim(d):
    # sim.py keeps these settings as module globals, and a hot reload of sim.py resets them to
    # sim's defaults -- so they're pushed in here at startup AND again after every reload
    if isinstance(d.get("shaders"), dict):
        sim.set_shader_settings(d["shaders"])
    sim.MASTER_VOLUME = float(d.get("master_volume", 1.0))
    sim.set_sfx_volume(d.get("sfx_volume", d.get("volume", 0.8)))
    sim.set_music_volume(d.get("music_volume", 0.6))
    sim.ENGINE_VOLUME = float(d.get("engine_volume", 0.8))
    sim.UI_VOLUME = float(d.get("ui_volume", 0.8))
    sim.set_master_mute(bool(d.get("mute", False)))
    sim.STEER_CURVE = float(d.get("steer_curve", 1.0))
    sim.STICK_DEADZONE = float(d.get("stick_deadzone", 0.05))
    sim.DYNAMIC_LOOK_AHEAD = bool(d.get("look_ahead_cam", False))
    sim.GHOST_OPACITY = float(d.get("ghost_opacity", 0.6))
    sim.set_steer_rate(d.get("steer_rate", sim.steer_rate_frac()))
    sim.set_drift_assist(d.get("drift_assist", sim.drift_assist_frac()))
    sim.set_shake_intensity(d.get("shake", sim.shake_intensity_frac()))
    sim.set_zoom(d.get("zoom", sim.zoom_frac()))
    sim.INVERT_STEER = bool(d.get("invert_steer", False))
    if "fog_density" in d:
        sim.set_fog_density(d["fog_density"])
    if "bot_aggression" in d:
        sim.set_bot_aggression(d["bot_aggression"])
    if "track_type" in d:
        sim.set_track_type(d["track_type"])
    sim.TOTAL_LAPS = int(d.get("laps", 3))

def save_profile(d):
    import json
    try:
        d["shaders"] = dict(sim.SHADER_SETTINGS)
        with open(PROFILE_PATH, "w") as f:
            json.dump(d, f, indent=2)
    except OSError as e:
        print("profile save failed:", e)

PLAYER_COLOR = (230, 60, 60)
# one distinct colour per bot (races have up to 7 bots); none of them the player's red
BOT_COLORS = [(60, 140, 230), (230, 200, 60), (160, 80, 220), (240, 140, 40),
              (90, 220, 190), (235, 120, 180), (120, 200, 90), (80, 200, 235)]
PLAYER_SLOT = 2     # start grid position: 0/1 = front row, 2 = second row left, ...

# one distinct colour per multiplayer slot (up to 12 players)
PLAYER_PALETTE = [
    (230, 60, 60), (60, 140, 230), (230, 200, 60), (160, 80, 220),
    (240, 140, 40), (90, 220, 190), (235, 120, 180), (120, 200, 90),
    (80, 200, 235), (200, 120, 80), (180, 180, 180), (150, 110, 70),
]
BCAST_HZ = 20       # how often each client broadcasts its car state

HELP_LINES = [
    "A / D or arrows / left stick: steer (the kart always drives)",
    "Q / E or LB / RB: side-bash     SPACE or (A): ram",
    "Shift / RT: drift   L-Click / X: shoot forward   R-Click / C: cone/oil",
    "Esc or Start: menu     R: reload sim.py",
]

def try_reload():
    # Validate the edited file in a throwaway namespace first; only if it executes
    # cleanly do we apply it, so a broken edit can't leave the live module half old /
    # half new. We apply by exec-ing into sim's own __dict__ (not update()-ing from a
    # scratch dict) so the reloaded functions' __globals__ ARE sim.__dict__ -- otherwise
    # module-level mutations like new_map() setting ROAD/GROUND_SURF would land in the
    # scratch dict and never be visible via sim.ROAD from here.
    try:
        src = open(SIM_PATH).read()
        code = compile(src, SIM_PATH, "exec")
    except SyntaxError as e:
        print("sim.py syntax error, skipped reload:", e)
        return False
    try:
        exec(code, {"__name__": "sim", "__file__": SIM_PATH})   # dry run to catch runtime errors
    except Exception as e:
        print("sim.py reload failed, kept previous version:", e)
        return False
    sim.__dict__.clear()
    sim.__dict__["__name__"] = "sim"
    sim.__dict__["__file__"] = SIM_PATH
    exec(code, sim.__dict__)
    sim.load_assets()
    print("sim.py reloaded")
    return True

def migrate(old, new):
    # carry all live state across a reload; fields that are new in the edited sim.py keep
    # their fresh defaults
    for key, value in old.__dict__.items():
        if key in new.__dict__:
            new.__dict__[key] = value
    return new

def migrate_car(old):
    return migrate(old, sim.Car(old.x, old.y, old.angle, old.color))

def migrate_cam(old, car):
    return migrate(old, sim.Camera(car))

UI_HIGHLIGHT = (80, 190, 255)   # blue: ONLY for highlighting menu buttons
UI_ACCENT = (255, 210, 70)      # yellow: every other emphasis (codes, you-markers, HUD, etc.)
UI_POINTER = None

class Button:
    def __init__(self, rect, label, align="center"):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.align = align

    def draw(self, screen, font, hover):
        # a ui-kit slab: dark when idle, racing red when highlighted (font is unused, kept for callers)
        ui.slab(screen, self.rect, hover)
        t = ui.text(self.label, 2, ui.WHITE if hover else ui.STEEL_L, bold=True)
        if self.align == "left":
            ui.put(screen, t, self.rect.x + 14, self.rect.centery - 1, "midleft")
        else:
            ui.put(screen, t, self.rect.centerx, self.rect.centery - 1, "center")

    def clicked(self, pos):
        return self.rect.collidepoint(pos)

def load_social_buttons():
    socials_path = os.path.join(sim.ASSET_DIR, "UI", "socials")
    sheets = []
    for i in (1, 2, 3):
        p = os.path.join(socials_path, f"socials_{i}.png")
        if os.path.exists(p):
            try:
                sheets.append(pygame.image.load(p).convert_alpha())
            except pygame.error:
                sheets.append(None)
        else:
            sheets.append(None)

    config = [
        {"name": "itchio", "r": 1, "c": 1, "url": "https://aiden-shoroz.itch.io/", "tooltip": "itch.io"},
        {"name": "youtube", "r": 0, "c": 2, "url": "https://www.youtube.com/@aidnth14", "tooltip": "YouTube"},
        {"name": "instagram", "r": 0, "c": 3, "url": "https://www.instagram.com/aidnth14/", "tooltip": "Instagram"},
        {"name": "discord", "r": 0, "c": 4, "url": "https://discord.com/users/1125415771737182310", "tooltip": "Discord"},
    ]

    btn_size = 24  # native 16x16 scaled to fill the social button slot
    buttons = []
    for item in config:
        r, c = item["r"], item["c"]
        rect = pygame.Rect(c * 16, r * 16, 16, 16)
        states = []
        for s in sheets:
            if s is not None:
                try:
                    sub = s.subsurface(rect).copy()
                    states.append(pygame.transform.scale(sub, (btn_size, btn_size)))
                except Exception:
                    states.append(None)
            else:
                states.append(None)
        idle = states[0]
        hover = states[1] if len(states) > 1 and states[1] is not None else idle
        pressed = states[2] if len(states) > 2 and states[2] is not None else hover
        if idle is not None:
            buttons.append({
                "name": item["name"],
                "url": item["url"],
                "tooltip": item["tooltip"],
                "idle": idle,
                "hover": hover,
                "pressed": pressed,
                "rect": pygame.Rect(0, 0, btn_size, btn_size),
            })
    return buttons

def draw_masters_scoreboard(screen, final_order, player, game_mode="", team_result="", end_title="FINISH"):
    """Renders the end-of-race results in a classic golf/tournament scoreboard aesthetic."""
    if not final_order:
        return

    n_rows = min(8, len(final_order))
    row_h = 21
    arch_h = 36
    sub_h = 18
    bh = arch_h + sub_h + n_rows * row_h + 8
    bw = 376
    bx = (sim.W - bw) // 2
    by = 20

    # Soft drop shadow
    shadow_surf = pygame.Surface((bw + 12, bh + 12), pygame.SRCALPHA)
    pygame.draw.rect(shadow_surf, (0, 0, 0, 95), (4, 4, bw + 4, bh + 4), border_radius=6)
    screen.blit(shadow_surf, (bx - 2, by - 2))

    # Support posts on left and right sides (white poles with caps)
    pole_w = 6
    pole_h = bh + 26
    for px in (bx - 10, bx + bw + 4):
        pygame.draw.rect(screen, (232, 234, 232), (px, by - 6, pole_w, pole_h), border_radius=3)
        pygame.draw.rect(screen, (35, 38, 40), (px, by - 6, pole_w, pole_h), 1, border_radius=3)
        # Cap
        pygame.draw.rect(screen, (246, 246, 244), (px - 1, by - 9, pole_w + 2, 4), border_radius=1)
        pygame.draw.rect(screen, (35, 38, 40), (px - 1, by - 9, pole_w + 2, 4), 1, border_radius=1)

    # Yellow top-left badge (SUN / FINAL)
    badge_rect = pygame.Rect(bx - 12, by - 14, 32, 14)
    pygame.draw.rect(screen, (248, 215, 60), badge_rect, border_radius=2)
    pygame.draw.rect(screen, (30, 30, 30), badge_rect, 1, border_radius=2)
    f_badge = sim.get_font(13)
    badge_label = "FINAL" if end_title == "FINISH" else "SUN"
    b_txt = f_badge.render(badge_label, True, (25, 25, 25))
    screen.blit(b_txt, b_txt.get_rect(center=badge_rect.center))

    # Board background (Off-white enamel plate)
    board_rect = pygame.Rect(bx, by, bw, bh)
    pygame.draw.rect(screen, (246, 247, 244), board_rect, border_top_left_radius=8, border_top_right_radius=8)

    # Arched header polygon
    header_pts = [
        (bx, by + arch_h),
        (bx, by + 8),
        (bx + 8, by + 2),
        (bx + bw // 2, by - 3),
        (bx + bw - 8, by + 2),
        (bx + bw, by + 8),
        (bx + bw, by + arch_h),
    ]
    pygame.draw.polygon(screen, (248, 249, 246), header_pts)
    pygame.draw.lines(screen, (35, 38, 40), False, header_pts, 2)
    pygame.draw.line(screen, (35, 38, 40), (bx, by + arch_h), (bx + bw, by + arch_h), 2)

    # Bold 'LEADERS' title
    f_leaders = sim.get_font(30)
    title_txt = "LEADERS"
    t_lead = f_leaders.render(title_txt, True, (20, 24, 25))
    screen.blit(t_lead, t_lead.get_rect(center=(bx + bw // 2, by + 18)))

    # Subheader row
    sub_y = by + arch_h + 2
    pygame.draw.line(screen, (35, 38, 40), (bx, sub_y + sub_h), (bx + bw, sub_y + sub_h), 2)

    col_pos_w = 36
    col_name_w = 204
    col_gap_w = 54
    col_best_w = 64
    gap_x = 4

    c1_x = bx + 6
    c2_x = c1_x + col_pos_w + gap_x
    c3_x = c2_x + col_name_w + gap_x
    c4_x = c3_x + col_gap_w + gap_x

    # Vertical divider grid lines spanning subheader and all rows
    pygame.draw.line(screen, (35, 38, 40), (c3_x - 2, sub_y - 2), (c3_x - 2, by + bh), 2)
    pygame.draw.line(screen, (35, 38, 40), (c4_x - 2, sub_y - 2), (c4_x - 2, by + bh), 2)

    f_sub = sim.get_font(15)
    round_label = team_result if team_result else ("FINAL CLASSIFICATION" if game_mode != "trial" else "TIME TRIAL CLASSIFICATION")
    h_round = f_sub.render(round_label, True, (35, 40, 45))
    screen.blit(h_round, (c1_x + 6, sub_y + 2))

    h_gap = f_sub.render("GAP", True, (45, 50, 55))
    screen.blit(h_gap, h_gap.get_rect(center=(c3_x + col_gap_w // 2, sub_y + 9)))

    h_best = f_sub.render("BEST (FL)", True, (45, 50, 55))
    screen.blit(h_best, h_best.get_rect(center=(c4_x + col_best_w // 2, sub_y + 9)))

    # Outer border of whole board
    pygame.draw.rect(screen, (35, 38, 40), board_rect, 2, border_top_left_radius=8, border_top_right_radius=8)

    # Grid Rows
    row_y0 = sub_y + sub_h + 3
    f_pos = sim.get_font(18)
    f_name = sim.get_font(17)
    f_scores = sim.get_font(18)

    winner_lap = final_order[0].best_lap if final_order else 0.0
    best_overall_lap = min((c.best_lap for c in final_order if c.best_lap > 0), default=0.0)

    for i in range(n_rows):
        c = final_order[i]
        ry = row_y0 + i * row_h
        # Horizontal divider line
        pygame.draw.line(screen, (190, 195, 192), (bx + 4, ry + row_h - 1), (bx + bw - 4, ry + row_h - 1), 1)

        # 1. POS slot (recessed white plaque)
        pos_r = pygame.Rect(c1_x, ry + 1, col_pos_w, row_h - 3)
        pygame.draw.rect(screen, (252, 252, 250), pos_r)
        pygame.draw.rect(screen, (160, 165, 160), pos_r, 1)
        pygame.draw.line(screen, (200, 205, 200), (pos_r.left + 1, pos_r.bottom - 2), (pos_r.right - 2, pos_r.bottom - 2))
        p_str = "DNF" if c.dead else f"P{i + 1}"
        p_col = (195, 45, 45) if c.dead else (25, 28, 30)
        p_txt = f_pos.render(p_str, True, p_col)
        screen.blit(p_txt, p_txt.get_rect(center=pos_r.center))

        # 2. DRIVER slot (recessed white enamel plate)
        name_r = pygame.Rect(c2_x, ry + 1, col_name_w, row_h - 3)
        is_p = (c is player)
        bg_col = (255, 252, 226) if is_p else (252, 252, 250)
        border_col = (210, 165, 40) if is_p else (160, 165, 160)
        pygame.draw.rect(screen, bg_col, name_r)
        pygame.draw.rect(screen, border_col, name_r, 1)

        tx = name_r.left + 5
        flag = sim.get_flag(c.flag, 11) if c.flag else None
        if flag:
            screen.blit(flag, (tx, name_r.centery - flag.get_height() // 2))
            pygame.draw.rect(screen, (60, 60, 60), (tx, name_r.centery - flag.get_height() // 2, flag.get_width(), flag.get_height()), 1)
            tx += flag.get_width() + 5

        tag = c.name.upper() + (" (YOU)" if is_p else "")
        nm_col = (180, 50, 40) if c.dead else ((160, 105, 15) if is_p else (20, 24, 25))
        nm_txt = f_name.render(tag, True, nm_col)
        screen.blit(nm_txt, nm_txt.get_rect(midleft=(tx, name_r.centery)))

        # 3. TOTAL / GAP slot (RED digits)
        gap_r = pygame.Rect(c3_x, ry + 1, col_gap_w, row_h - 3)
        pygame.draw.rect(screen, (252, 252, 250), gap_r)
        pygame.draw.rect(screen, (160, 165, 160), gap_r, 1)
        if c.dead:
            g_str = "DNF"
        elif i == 0:
            g_str = "LEADER" if game_mode != "trial" else "P1"
        else:
            diff = round(c.best_lap - winner_lap, 2)
            g_str = f"+{diff:.2f}s" if diff > 0 else "INT"
        g_txt = f_scores.render(g_str, True, (215, 35, 35))
        screen.blit(g_txt, g_txt.get_rect(center=gap_r.center))

        # 4. RD / BEST LAP slot (Green or Red digits, Purple for FL)
        best_r = pygame.Rect(c4_x, ry + 1, col_best_w, row_h - 3)
        pygame.draw.rect(screen, (252, 252, 250), best_r)
        pygame.draw.rect(screen, (160, 165, 160), best_r, 1)
        is_fl = (c.best_lap > 0 and abs(c.best_lap - best_overall_lap) < 0.001)
        b_str = sim.fmt_time(c.best_lap) if c.best_lap > 0 else "--"
        if is_fl:
            b_col = (165, 45, 215)      # F1 purple for fastest lap
            b_txt = f_scores.render(f"{b_str} FL", True, b_col)
        else:
            b_col = (38, 135, 48)
            b_txt = f_scores.render(b_str, True, b_col)
        screen.blit(b_txt, b_txt.get_rect(center=best_r.center))

def main():
    global UI_POINTER
    ensure_local_server()
    net.prewarm()
    pygame.init()
    profile = load_profile()
    display_mode = profile.get("display_mode", "Exclusive Fullscreen" if profile.get("fullscreen") else "Windowed")
    pixel_perfect = bool(profile.get("pixel_perfect", False))
    fps_cap_setting = profile.get("fps_cap", "60 FPS")
    hud_mode = profile.get("hud_mode", "Classic" if profile.get("hud_mode") not in ("Classic", "Immersive", "Hidden") else profile["hud_mode"])
    pad_preset = profile.get("gamepad_preset", "Arcade Classic")
    mouse_aim = bool(profile.get("mouse_aim", False))
    show_fps = bool(profile.get("show_fps", False))

    # The game renders at a fixed 600x400; pygame.SCALED hands that logical surface to SDL,
    # which scales it (GPU, aspect-preserved, letterboxed) to any window size or fullscreen and
    # auto-maps mouse coords back to 600x400 -- so all UI hit-testing stays in logical space.
    def apply_display(mode=None, px_perf=None, vsync_opt=None):
        nonlocal display_mode, pixel_perfect, fps_cap_setting, screen
        if mode is not None: display_mode = mode
        if px_perf is not None: pixel_perfect = px_perf
        if vsync_opt is not None: fps_cap_setting = vsync_opt

        # nearest-neighbour when pixel-perfect, else smooth linear filtering
        os.environ["SDL_HINT_RENDER_SCALE_QUALITY"] = "0" if pixel_perfect else "1"
        vsync_val = 1 if fps_cap_setting == "V-Sync On" else 0
        flags = pygame.SCALED
        if display_mode == "Exclusive Fullscreen":
            flags |= pygame.FULLSCREEN
        elif display_mode == "Borderless Windowed":
            flags |= pygame.NOFRAME
        else:
            flags |= pygame.RESIZABLE
        try:
            screen = pygame.display.set_mode((sim.W, sim.H), flags, vsync=vsync_val)
        except (TypeError, pygame.error):
            # headless / dummy video drivers can't build a SCALED renderer: fall back plain
            try:
                screen = pygame.display.set_mode((sim.W, sim.H), flags & ~pygame.SCALED)
            except pygame.error:
                screen = pygame.display.set_mode((sim.W, sim.H))
        return screen

    def toggle_fullscreen():
        apply_display("Windowed" if display_mode == "Exclusive Fullscreen"
                      else "Exclusive Fullscreen")
        profile["display_mode"] = display_mode
        profile["fullscreen"] = (display_mode == "Exclusive Fullscreen")
        save_profile(profile)

    screen = apply_display()
    pygame.display.set_caption("Steer")
    screen.fill((0, 0, 0))              # paint black now so loading never flashes a stale buffer
    pygame.display.flip()
    clock = pygame.time.Clock()
    sim.load_assets()
    social_buttons = load_social_buttons()
    cursor_hand = False

    ptr_path = os.path.join(sim.FX_DIR, "Sprite-0001.png")
    if not os.path.exists(ptr_path):
        ptr_path = os.path.join(sim.ASSET_DIR, "Sprite-0001.png")
    if os.path.exists(ptr_path):
        try:
            UI_POINTER = pygame.image.load(ptr_path).convert_alpha()
        except pygame.error:
            UI_POINTER = None

    sdlctrl.init()
    pads = {}       # instance id -> open Controller

    def _pad_name(pad, device_index):
        # pygame-ce exposes Controller.name; classic pygame has module-level name_forindex.
        nm = getattr(pad, "name", None)
        if callable(nm):
            try:
                nm = nm()
            except Exception:
                nm = None
        if not nm and hasattr(sdlctrl, "name_forindex"):
            try:
                nm = sdlctrl.name_forindex(device_index)
            except Exception:
                nm = None
        return nm or "controller"

    def open_pad(device_index):
        if not sdlctrl.is_controller(device_index):
            return
        pad = sdlctrl.Controller(device_index)
        pads[pad.id] = pad
        print("controller connected:", _pad_name(pad, device_index))

    for i in range(sdlctrl.get_count()):
        open_pad(i)

    def pad_steer():
        s = 0.0
        for pad in pads.values():
            try:
                axis = pygame.CONTROLLER_AXIS_RIGHTX if pad_preset == "Southpaw" else PAD_STEER_AXIS
                s += pad.get_axis(axis) / 32768.0
                if pad_preset != "Southpaw":
                    s -= 1 if pad.get_button(PAD_LEFT) else 0
                    s += 1 if pad.get_button(PAD_RIGHT) else 0
            except pygame.error:
                pass
        deadzone = sim.STICK_DEADZONE
        if abs(s) < deadzone:
            return 0.0
        return max(-1.0, min(1.0, s))

    def pad_drift():
        for pad in pads.values():
            try:
                if pad_preset == "Trigger Drive":
                    if pad.get_button(PAD_BASH_R):
                        return True
                else:
                    if pad.get_button(PAD_BACK):    # B / Circle held = drift
                        return True
                    rt = pad.get_axis(pygame.CONTROLLER_AXIS_TRIGGERRIGHT) / 32767.0
                    if rt > 0.3:
                        return True
            except pygame.error:
                pass
        return False

    def pad_brake():
        for pad in pads.values():
            try:
                if pad_preset == "Trigger Drive":
                    lt = pad.get_axis(pygame.CONTROLLER_AXIS_TRIGGERLEFT) / 32767.0
                    if lt > 0.3:
                        return True
                else:
                    lt = pad.get_axis(pygame.CONTROLLER_AXIS_TRIGGERLEFT) / 32767.0
                    if lt > 0.3 or pad.get_button(PAD_DOWN):
                        return True
            except pygame.error:
                pass
        return False

    def get_input_device_name():
        if pads:
            try:
                for p in pads.values():
                    name = p.get_name().lower()
                    if "xbox" in name or "x-box" in name:
                        return "XBOX CONTROLLER"
                    elif "playstation" in name or "dual" in name or "ps" in name:
                        return "PLAYSTATION PAD"
                    elif "switch" in name or "nintendo" in name or "joy-con" in name:
                        return "NINTENDO SWITCH"
                    return p.get_name()[:16].upper()
            except Exception:
                return "GAMEPAD DETECTED"
        return "KEYBOARD & MOUSE"

    # Gyroscope / mobile device tilt detection for steering
    gyro_state = {
        "tilt": 0.0,
        "smooth_steer": 0.0,
        "source": "none",
        "active": False,
        "enabled": bool(profile.get("gyro_steer", False)),  # user toggle (Settings -> Controls)
        "sens": float(profile.get("gyro_sens", 0.5)),        # 0..1, higher = less tilt for full lock
        "neutral": 0.0,                                      # calibrated level-hold offset
    }

    # 1. HTML5 / Pygbag / Emscripten browser DeviceOrientation
    try:
        import platform
        if platform.system() == "Emscripten":
            import js
            js.eval("""
            (function() {
                if (window._steer_gyro_init) return;
                window._steer_gyro_init = true;
                window._steer_tilt = 0.0;
                function onOrientation(e) {
                    var angle = (screen.orientation && screen.orientation.angle) || window.orientation || 0;
                    var t = 0.0;
                    if (angle === 90) {
                        t = -e.beta;
                    } else if (angle === -90 || angle === 270) {
                        t = e.beta;
                    } else {
                        t = e.gamma;
                    }
                    if (t !== null && !isNaN(t)) {
                        window._steer_tilt = t;
                    }
                }
                if (typeof window.DeviceOrientationEvent !== 'undefined') {
                    if (typeof window.DeviceOrientationEvent.requestPermission === 'function') {
                        document.addEventListener('touchstart', function() {
                            window.DeviceOrientationEvent.requestPermission().then(function(res) {
                                if (res === 'granted') {
                                    window.addEventListener('deviceorientation', onOrientation, true);
                                }
                            }).catch(function() {});
                        }, { once: true });
                    } else {
                        window.addEventListener('deviceorientation', onOrientation, true);
                    }
                }
            })();
            """)
            gyro_state["source"] = "web"
            gyro_state["active"] = True
    except Exception:
        pass

    # 2. SDL2 Joystick / Accelerometer Sensor (Android / iOS Pygame ports)
    accel_sensors = []
    try:
        if not pygame.joystick.get_init():
            pygame.joystick.init()
        for idx in range(pygame.joystick.get_count()):
            try:
                j = pygame.joystick.Joystick(idx)
                j.init()
                name = j.get_name().lower()
                if any(k in name for k in ("accelerometer", "gyro", "sensor", "tilt")):
                    accel_sensors.append(j)
                    gyro_state["source"] = "joystick_sensor"
                    gyro_state["active"] = True
            except Exception:
                pass
    except Exception:
        pass

    # 3. Android JNI / Plyer fallback
    try:
        from plyer import accelerometer
        accelerometer.enable()
        gyro_state["source"] = "plyer"
        gyro_state["active"] = True
    except Exception:
        pass

    GYRO_DEADZONE = 0.06       # ~3.5 deg deadzone
    GYRO_SMOOTH = 0.25         # smoothing factor

    def gyro_max_deg():
        # sensitivity 0..1 -> 40 deg (gentle) down to 12 deg (twitchy) for full steering lock
        return 40.0 - gyro_state["sens"] * 28.0

    def gyro_recenter():
        # capture the current held tilt as the new neutral ("level") point
        gyro_state["neutral"] = _gyro_raw()

    def _gyro_raw():
        raw = 0.0
        md = gyro_max_deg()
        if gyro_state["source"] == "web":
            try:
                import js
                deg = float(js.window._steer_tilt or 0.0)
                raw = max(-1.0, min(1.0, deg / md))
            except Exception:
                raw = 0.0
        elif gyro_state["source"] == "joystick_sensor":
            for j in accel_sensors:
                try:
                    if j.get_numaxes() > 0:
                        raw += j.get_axis(0)
                except Exception:
                    pass
            raw = max(-1.0, min(1.0, raw))
        elif gyro_state["source"] == "plyer":
            try:
                from plyer import accelerometer
                val = accelerometer.acceleration
                if val and val[0] is not None:
                    # accel X in m/s^2 -> tilt degrees (asin), then normalise to the lock angle
                    import math as _m
                    g = max(-9.81, min(9.81, val[0]))
                    deg = _m.degrees(_m.asin(g / 9.81))
                    raw = max(-1.0, min(1.0, deg / md))
            except Exception:
                pass
        # Allow programmatic / simulated tilt for tests and mobile companions (already normalised)
        sim_tilt = getattr(sim, "MOBILE_TILT", None)
        if sim_tilt is not None:
            raw = max(-1.0, min(1.0, float(sim_tilt)))
        return raw

    def gyro_steer():
        if not gyro_state["enabled"]:
            gyro_state["smooth_steer"] = 0.0
            return 0.0
        raw = max(-1.0, min(1.0, _gyro_raw() - gyro_state["neutral"]))
        if abs(raw) < GYRO_DEADZONE:
            raw = 0.0
        gyro_state["smooth_steer"] += (raw - gyro_state["smooth_steer"]) * GYRO_SMOOTH
        return gyro_state["smooth_steer"]

    font_big = sim.get_font(56)
    font = sim.get_font(34)
    font_btn = sim.get_font(24)
    font_small = sim.get_font(20)
    font_credits = sim.get_font(16)

    # gameplay screenshot used as the backdrop for menus / results, dimmed for legibility
    try:
        _bg = pygame.image.load(os.path.join(sim.UI_DIR, "menu_bg.png")).convert()
        menu_bg = pygame.transform.scale(_bg, (sim.W, sim.H))
        _shade = pygame.Surface((sim.W, sim.H))
        _shade.set_alpha(140)
        _shade.fill((10, 18, 12))
        menu_bg.blit(_shade, (0, 0))
    except (pygame.error, FileNotFoundError):
        menu_bg = None

    _dim = pygame.Surface((sim.W, sim.H))
    _dim.set_alpha(130)
    _dim.fill((10, 18, 12))

    def draw_bg():
        # live gameplay behind the menus: a paused race if one exists, else the attract bots
        if player is not None and cam is not None and cars:
            sim.draw_world(screen, cam, cars)
            screen.blit(_dim, (0, 0))
        elif attract_cam is not None and attract_cars:
            sim.draw_world(screen, attract_cam, attract_cars)
            screen.blit(_dim, (0, 0))
        elif menu_bg is not None:
            screen.blit(menu_bg, (0, 0))
        else:
            screen.fill((30, 60, 30))

    # STEER logo for the top-left of the menu / mode screens (enlarged)
    try:
        _logo = pygame.image.load(os.path.join(sim.UI_DIR, "logo.png")).convert_alpha()
        lh = 110
        logo = pygame.transform.scale(_logo, (round(_logo.get_width() * lh / _logo.get_height()), lh))
    except (pygame.error, FileNotFoundError):
        logo = None

    def draw_logo():
        if logo is not None:
            screen.blit(logo, (18, 16))
        else:
            screen.blit(sim.get_font(72).render("STEER", True, (255, 255, 255)), (18, 16))

    _dim_more = pygame.Surface((sim.W, sim.H))     # settings sit on a darker backdrop
    _dim_more.set_alpha(90)
    _dim_more.fill((10, 12, 22))

    def menu_extras():
        # the bits of the title / pause menu that depend on the game: tag line, social icons
        links = [k for k, url in SOCIAL_LINKS if url]
        # brand icons (itch.io / YouTube / Instagram / Discord) draw separately when available;
        # fall back to the built-in vector glyphs only if the sprite sheet failed to load
        ex = {"credit": CREDIT, "socials": () if social_buttons else links, "pad": bool(pads)}
        if player is not None and cars:
            order = sorted(cars, key=lambda c: (c.dead, -c.progress))
            pos = order.index(player) + 1 if player in order else 0
            suf = "TH" if 10 <= pos % 100 <= 20 else {1: "ST", 2: "ND", 3: "RD"}.get(pos % 10, "TH")
            lap = min(sim.TOTAL_LAPS, sim.lap_of(player) + 1)
            ex.update(chip="PAUSED", tag=f"LAP {lap}/{sim.TOTAL_LAPS} · {pos}{suf} OF {len(cars)}")
        else:
            ex["tag"] = "DRIFT · BASH · WIN"
        return ex

    def draw_social_brand_icons():
        # draw the itch.io / YouTube / Instagram / Discord sprite-sheet icons at the social slots,
        # bobbing up on hover with a brand tooltip (mirrors ui.draw_menu's generic-icon behaviour)
        if not social_buttons:
            return
        rects = ui.social_layout(len(social_buttons), sim.W, sim.H)
        hover = None
        for btn, r in zip(social_buttons, rects):
            hot = r.collidepoint(mouse_pos)
            img = btn["hover"] if hot else btn["idle"]
            if img is not None:
                screen.blit(img, img.get_rect(center=(r.centerx, r.centery - (2 if hot else 0))))
            if hot:
                hover = (btn["tooltip"], r)
        if hover:
            lbl, r = hover
            t = font_credits.render(lbl, True, (240, 248, 255))
            screen.blit(t, t.get_rect(midbottom=(min(sim.W - 8, r.centerx), r.y - 4)))

    def results_buttons():
        return ["MENU"] if race_was_online else ["RACE AGAIN", "MENU"]

    def results_rows():
        # the finish board's rows: order, flags, gap to the winner, best laps, fastest lap
        if not final_order:
            return []
        lead = final_order[0]
        laps = [c.best_lap for c in final_order if c.best_lap > 0]
        fastest = min(laps) if laps else 0.0
        rows = []
        for c in final_order:
            avg = c.progress / c.race_t if getattr(c, "race_t", 0) > 0 else 0.0
            gap = (lead.progress - c.progress) / avg if avg > 1.0 else None
            rows.append({"name": c.name, "flag": sim.get_flag(c.flag, 10) if c.flag else None,
                         "gap": max(0.0, gap) if gap is not None else None, "best": c.best_lap,
                         "laps_down": int((lead.progress - c.progress) // max(1.0, sim.ROAD_LEN)),
                         "out": c.dead, "you": c is player,
                         "fastest": fastest > 0 and c.best_lap == fastest})
        return rows

    def results_text():
        mode_name = dict(GAME_MODES).get(game_mode, "Race").upper()
        sub = f"{mode_name} · {sim.TOTAL_LAPS} LAPS" if game_mode not in ("battle", "elim") else mode_name
        rows = results_rows()
        me = next((i for i, r in enumerate(rows) if r["you"]), None)
        if team_result:
            foot = team_result.split("   ")[0]
        elif me is None:
            foot = None
        elif me == 0:
            foot = "YOU WON!"
        else:
            p = me + 1
            suf = "TH" if 10 <= p % 100 <= 20 else {1: "ST", 2: "ND", 3: "RD"}.get(p % 10, "TH")
            g = rows[me]["gap"]
            foot = f"YOU FINISHED {p}{suf} OF {len(rows)}"
            if rows[me]["laps_down"] >= 1 and not rows[me]["out"]:
                n = rows[me]["laps_down"]
                foot += f" · {n} LAP{'S' if n > 1 else ''} DOWN"
            elif g is not None and not rows[me]["out"] and game_mode not in ("battle", "elim"):
                foot += f" · +{g:.2f}S BEHIND {rows[0]['name'].upper()}"
        return sub, foot, rows

    def results_choose(i):
        nonlocal player, state
        btns = results_buttons()
        idx = min(max(0, i), len(btns) - 1)
        label = btns[idx]
        if label == "RACE AGAIN":
            start_game()
        else:
            player = None
            state = "menu"

    # cold-start loading screen: Render's free plan sleeps when idle and takes ~30s to wake,
    # so while we're mid-connect we take over the whole screen with an estimated progress bar
    # and rotating tips -- it reads as an intentional "loading" rather than a frozen menu.
    COLD_START_EST = 32.0           # seconds we pace the bar over before holding near full

    def draw_connect_overlay():
        if netc is None or lobby is not None:
            return
        # solid backdrop so the menu behind never bleeds through the loader
        screen.fill((12, 14, 22))
        cx = sim.W / 2
        t = pygame.time.get_ticks() / 1000.0
        elapsed = netc.connect_elapsed()
        waking = netc.waking()

        logo_drawn = False
        if logo is not None:
            screen.blit(logo, logo.get_rect(center=(cx, 92)))
            logo_drawn = True
        if not logo_drawn:
            screen.blit(sim.get_font(48).render("STEER", True, (255, 255, 255)),
                        sim.get_font(48).render("STEER", True, (255, 255, 255)).get_rect(center=(cx, 92)))

        title_txt = "WAKING THE SERVER" if waking else "CONNECTING"
        title = font.render(title_txt, True, (255, 255, 255))
        screen.blit(title, title.get_rect(center=(cx, 168)))

        # progress bar: ease toward ~95% across the estimated cold-start window, finish on connect
        bw, bh, by = 320, 16, 206
        bx = cx - bw / 2
        frac = min(0.95, elapsed / COLD_START_EST) if elapsed > 0 else 0.0
        pygame.draw.rect(screen, (30, 34, 46), (bx, by, bw, bh), border_radius=8)
        fillw = max(bh, int(bw * frac))
        pygame.draw.rect(screen, UI_ACCENT, (bx, by, fillw, bh), border_radius=8)
        # moving sheen on the fill so it never looks stalled
        sheen_x = bx + (t * 120 % max(1, fillw))
        pygame.draw.rect(screen, (255, 255, 255), (sheen_x, by + 2, 10, bh - 4), border_radius=4)
        pygame.draw.rect(screen, (70, 82, 104), (bx, by, bw, bh), 1, border_radius=8)

        sub = font_small.render("First connect after idle can take up to ~30s", True, (200, 210, 195))
        screen.blit(sub, sub.get_rect(center=(cx, by + 40)))

        # rotating tip, swapping every ~3.5s
        if LOADING_TIPS:
            tip = LOADING_TIPS[int(t / 3.5) % len(LOADING_TIPS)]
            tip_s = font_small.render("TIP: " + tip, True, (150, 180, 160))
            screen.blit(tip_s, tip_s.get_rect(center=(cx, 300)))

        esc_icon = buttonmanager.get_key_icon('esc')
        if esc_icon:
            txt_cancel = font_small.render("to cancel", True, (160, 170, 155))
            tot_w = esc_icon.get_width() + 6 + txt_cancel.get_width()
            sx = cx - tot_w // 2
            cy_hint = sim.H - 24
            screen.blit(esc_icon, esc_icon.get_rect(midleft=(sx, cy_hint)))
            screen.blit(txt_cancel, txt_cancel.get_rect(midleft=(sx + esc_icon.get_width() + 6, cy_hint)))
        else:
            hint = font_small.render("ESC to cancel", True, (160, 170, 155))
            screen.blit(hint, hint.get_rect(center=(cx, sim.H - 24)))

    profile = load_profile()
    keybinds = dict(DEFAULT_KEYS)
    keybinds.update({k: int(v) for k, v in profile.get("keys", {}).items() if k in DEFAULT_KEYS})
    apply_profile_to_sim(profile)
    sim.start_music()
    show_fps = bool(profile.get("show_fps", False))

    state = "menu"
    menu_sel = mode_sel = gamemode_sel = 0  # highlighted menu row for controller / keyboard nav
    results_sel = 0             # results screen: 0 = Race Again, 1 = Menu
    results_t = 0.0             # seconds the results board has been up (rows slide in)
    race_was_online = False     # the last race was multiplayer (no Race Again on its results)
    current_seed = sim.ROAD_SEED
    player_name = profile.get("name", "Player")
    _pf = profile.get("flag", "us")
    flag_idx = sim.FLAG_CODES.index(_pf) if _pf in sim.FLAG_CODES else (
        sim.FLAG_CODES.index("us") if "us" in sim.FLAG_CODES else 0)
    name_next = "single"        # where the name screen goes on confirm: "single" or "mp"
    game_mode = "race"          # race | trial | elim | battle | team

    # per-race mode runtime
    elim_timer = 0.0
    ghost_best = None           # [(x, y, angle), ...] sampled from your best lap (Time Trial)
    ghost_rec = []              # samples for the lap in progress
    ghost_time = 0.0            # lap time of the stored ghost
    trial_lap = 0               # last lap index seen (to detect a new lap in Time Trial)
    last_ranks = {}             # car -> last leaderboard rank, for position popups
    popup = None                # (text, color, seconds-left)
    awaiting_key = None         # action name being rebound in Settings

    # multiplayer state
    online = False              # True once a networked race is running
    netc = None                 # net.Net while hosting/joined
    lobby = None                # latest room dict from the server
    mp_max = 4                  # host's chosen player cap
    mp_tab = "host"              # which panel is showing on the combined multiplayer screen
    join_code = ""              # code being typed on the join screen
    net_msg = ""                # status / error line for the MP screens
    pending_net = None          # ("host", max) or ("join", code) to send once connected
    my_ready = False
    slot_by_id = {}             # player id -> grid slot (during a race)
    snap_by_slot = {}           # grid slot -> latest car snapshot dict
    bcast_t = 0.0
    mp_players = []             # [{id,name,flag,slot}] for the current race
    mp_bots = []                # [{slot,name,flag,ci}] bots the host added
    countdown = 0.0             # 3..0 pre-race lock
    go_timer = 0.0              # brief "GO!" flash
    end_title = "FINISH"        # results-screen title ("FINISH" / "GAME OVER")
    team_result = ""            # winning-team line shown on results in Team Race
    letterbox_h = 0.0           # current cinematic letterbox bar height (px)
    target_letterbox_h = 0.0    # target letterbox height
    slowmo_timer = 0.0          # bullet time remaining (s)
    slowmo_active = False       # currently running slow motion finish
    finish_pending = False      # true once race finish detected
    final_lap_announced = False # true once FINAL LAP banner triggered
    reported_dead = set()       # car uids reported dead (for takedown banners)
    hud_mode = profile.get("hud_mode", "FULL")  # "FULL" or "IMMERSIVE"
    hud_alpha = 1.0             # current opacity of HUD (0..1)
    hud_reveal_timer = 3.0      # timer keeping HUD visible in immersive mode
    prev_player_hearts = sim.HEART_COUNT
    prev_player_rank = 1
    prev_player_lap = 0

    back_btn = Button((sim.W / 2 - 100, 306, 200, 44), "Back")
    start_btn = Button((sim.W / 2 - 100, 256, 200, 42), "Start Race")
    flag_prev = Button((sim.W / 2 - 120, 198, 40, 40), "<")
    flag_next = Button((sim.W / 2 + 80, 198, 40, 40), ">")
    host_btn = Button((sim.W / 2 - 160, 90, 150, 40), "HOST")
    join_btn = Button((sim.W / 2 + 10, 90, 150, 40), "JOIN")
    sp_btn = Button((sim.W / 2 - 110, 120, 220, 48), "Singleplayer")
    mp_btn = Button((sim.W / 2 - 110, 182, 220, 48), "Multiplayer")
    minus_btn = Button((sim.W / 2 - 100, 198, 40, 40), "-")   # left of the number, no overlap
    plus_btn = Button((sim.W / 2 + 60, 198, 40, 40), "+")      # right of the number, symmetric
    create_btn = Button((sim.W / 2 - 100, 256, 200, 42), "Create Lobby")
    confirm_join_btn = Button((sim.W / 2 - 100, 256, 200, 42), "Join")
    ready_btn = Button((sim.W / 2 - 150, 344, 140, 36), "Ready")   # below the host-rules panel
    leave_btn = Button((sim.W / 2 + 10, 344, 140, 36), "Leave")
    host_track_btn = Button((316, 96, 264, 22), "")
    host_rot_btn   = Button((316, 120, 264, 22), "")
    host_laps_btn  = Button((316, 144, 264, 22), "")
    host_bots_btn  = Button((316, 168, 264, 22), "")
    host_aggr_btn  = Button((316, 192, 264, 22), "")
    host_coll_btn  = Button((316, 216, 264, 22), "")
    host_slip_btn  = Button((316, 240, 264, 22), "")
    host_items_btn = Button((316, 264, 264, 22), "")
    host_priv_btn  = Button((316, 288, 264, 22), "")
    lobby_settings = {
        "track": profile.get("track_type", "meadow_dirt"),
        "rotation": "Host Choice",
        "laps": 3,
        "bot_count": "Fill to 8",
        "bot_aggression": "Casual",
        "collision": "Full Contact",
        "slipstream": "ON",
        "items": "Standard",
        "privacy": "Public",
        "spectate": "Allowed",
    }
    # general-tab sliders: each a 0..1 value with a getter/setter + profile key
    SL_X, SL_W, SL_H = 24, 150, 8
    sliders = [
        {"label": "Master Vol",   "get": lambda: sim.MASTER_VOLUME, "set": sim.set_master_volume, "key": "master_volume",  "val_label": lambda: f"{int(round(sim.MASTER_VOLUME * 100))}%"},
        {"label": "Music Vol",    "get": lambda: sim.MUSIC_VOLUME,  "set": sim.set_music_volume,  "key": "music_volume",   "val_label": lambda: f"{int(round(sim.MUSIC_VOLUME * 100))}%"},
        {"label": "Engine Vol",   "get": lambda: sim.ENGINE_VOLUME, "set": sim.set_engine_volume, "key": "engine_volume",  "val_label": lambda: f"{int(round(sim.ENGINE_VOLUME * 100))}%"},
        {"label": "SFX Vol",      "get": lambda: sim.SFX_VOLUME,    "set": sim.set_sfx_volume,    "key": "sfx_volume",     "val_label": lambda: f"{int(round(sim.SFX_VOLUME * 100))}%"},
        {"label": "UI Audio",     "get": lambda: sim.UI_VOLUME,     "set": sim.set_ui_volume,     "key": "ui_volume",      "val_label": lambda: f"{int(round(sim.UI_VOLUME * 100))}%"},
        {"label": "Laps",         "get": lambda: (sim.TOTAL_LAPS - 1) / 9.0, "set": lambda v: setattr(sim, "TOTAL_LAPS", max(1, min(10, int(round(1.0 + v * 9.0))))), "key": "laps", "val_label": lambda: str(sim.TOTAL_LAPS)},
        {"label": "Steer Rate",   "get": sim.steer_rate_frac,       "set": sim.set_steer_rate,    "key": "steer_rate",     "val_label": lambda: f"{round(0.5 + sim.steer_rate_frac() * 1.5, 2):.1f}x"},
        {"label": "Steer Curve",  "get": lambda: (sim.STEER_CURVE - 1.0) / 1.5, "set": lambda v: setattr(sim, "STEER_CURVE", round(1.0 + v * 1.5, 2)), "key": "steer_curve", "val_label": lambda: f"{sim.STEER_CURVE:.1f}"},
        {"label": "Deadzone",     "get": lambda: sim.STICK_DEADZONE / 0.25, "set": lambda v: setattr(sim, "STICK_DEADZONE", round(v * 0.25, 3)), "key": "stick_deadzone", "val_label": lambda: f"{int(round(sim.STICK_DEADZONE * 100))}%"},
        {"label": "Gyro Sens",    "get": lambda: gyro_state["sens"], "set": lambda v: gyro_state.__setitem__("sens", round(v, 3)), "key": "gyro_sens", "val_label": lambda: f"{int(round(gyro_state['sens'] * 100))}%"},
        {"label": "Drift Assist", "get": sim.drift_assist_frac,     "set": sim.set_drift_assist,  "key": "drift_assist",   "val_label": lambda: f"{round(sim.drift_assist_frac(), 2):.1f}"},
        {"label": "Ghost Opacity","get": lambda: sim.GHOST_OPACITY, "set": lambda v: setattr(sim, "GHOST_OPACITY", round(v, 2)), "key": "ghost_opacity", "val_label": lambda: f"{int(round(sim.GHOST_OPACITY * 100))}%"},
        {"label": "Camera Zoom",  "get": sim.zoom_frac,             "set": sim.set_zoom,          "key": "zoom",           "val_label": lambda: f"{round(0.6 + sim.zoom_frac() * 1.0, 2):.1f}x"},
        {"label": "Camera Shake", "get": sim.shake_intensity_frac,  "set": sim.set_shake_intensity,"key": "shake",          "val_label": lambda: f"{round(sim.shake_intensity_frac() * 2.0, 2):.1f}x"},
        {"label": "Fog Density",  "get": lambda: sim.FOG_DENSITY,   "set": sim.set_fog_density,   "key": "fog_density",    "val_label": lambda: f"{int(round(sim.FOG_DENSITY * 100))}%"},
    ]
    for i, s in enumerate(sliders):
        s["track"] = pygame.Rect(SL_X, 74 + i * 30, SL_W, SL_H)   # moved to the row's spot when drawn
    active_slider = None        # the slider dict currently being dragged, or None
    slider_by_key = {s["key"]: s for s in sliders}

    # ---- settings: four tabs of rows, all driven the same way by mouse, keys and pad -------
    SET_TABS = ["RACE", "SOUND", "VIDEO", "CONTROLS"]
    set_tab = 0                 # active tab index
    set_sel = 0                 # highlighted row in that tab
    set_mouse = None            # last mouse position seen on the settings screen (hover = select)

    def _cycle(opts, cur, delta):
        i = opts.index(cur) if cur in opts else 0
        return opts[(i + delta) % len(opts)]

    def _save_shaders():
        profile["shaders"] = dict(sim.SHADER_SETTINGS)
        profile["fog_density"] = round(sim.FOG_DENSITY, 3)
        save_profile(profile)

    def ch_track(d):
        topts = list(sim.TILESETS) + ["random"]
        cur = sim.get_track_type()
        nxt = _cycle(topts, cur, d)
        sim.set_track_type(nxt)
        profile["track_type"] = nxt
        save_profile(profile)

    def ch_bots(d):
        nxt = _cycle(sim.BOT_AGGRESSION_LEVELS, sim.get_bot_aggression(), d)
        sim.set_bot_aggression(nxt)
        profile["bot_aggression"] = nxt
        save_profile(profile)

    def ch_hud(d):
        nonlocal hud_mode
        hud_mode = _cycle(["Classic", "Immersive", "Hidden"], hud_mode, d)
        profile["hud_mode"] = hud_mode
        save_profile(profile)

    def ch_invert(d):
        sim.INVERT_STEER = not sim.INVERT_STEER
        profile["invert_steer"] = sim.INVERT_STEER
        save_profile(profile)

    def ch_lookahead(d):
        sim.DYNAMIC_LOOK_AHEAD = not sim.DYNAMIC_LOOK_AHEAD
        profile["look_ahead_cam"] = sim.DYNAMIC_LOOK_AHEAD
        save_profile(profile)

    def ch_mute(d):
        sim.set_master_mute(not sim.MASTER_MUTE)
        profile["mute"] = sim.MASTER_MUTE
        save_profile(profile)

    def ch_display_mode(d):
        nonlocal screen
        modes = ["Windowed", "Borderless Windowed", "Exclusive Fullscreen"]
        apply_display(mode=_cycle(modes, display_mode, d))
        profile["display_mode"] = display_mode
        profile["fullscreen"] = (display_mode == "Exclusive Fullscreen")
        save_profile(profile)

    def ch_pixel_perfect(d):
        nonlocal screen
        apply_display(px_perf=not pixel_perfect)
        profile["pixel_perfect"] = pixel_perfect
        save_profile(profile)

    def ch_fps_cap(d):
        nonlocal screen
        fps_opts = ["60 FPS", "120 FPS", "144 FPS", "Unlimited", "V-Sync On"]
        apply_display(vsync_opt=_cycle(fps_opts, fps_cap_setting, d))
        profile["fps_cap"] = fps_cap_setting
        save_profile(profile)

    def ch_fps(d):
        nonlocal show_fps
        show_fps = not show_fps
        profile["show_fps"] = show_fps
        save_profile(profile)

    def ch_pad_preset(d):
        nonlocal pad_preset
        pad_preset = _cycle(["Arcade Classic", "Trigger Drive", "Southpaw"], pad_preset, d)
        profile["gamepad_preset"] = pad_preset
        save_profile(profile)

    def ch_mouse_aim(d):
        nonlocal mouse_aim
        mouse_aim = not mouse_aim
        profile["mouse_aim"] = mouse_aim
        save_profile(profile)

    def ch_gyro(d):
        gyro_state["enabled"] = not gyro_state["enabled"]
        profile["gyro_steer"] = gyro_state["enabled"]
        save_profile(profile)

    def ch_gyro_recenter(d):
        gyro_recenter()

    SHADER_DESCRIPTIONS = {
        "NONE": "Clean raw pixels without shaders",
        "CRT": "Arcade monitor scanlines + phosphor curvature",
        "CYBERPUNK": "Vibrant neon blues and bloom flares",
        "NOIR": "High-contrast monochrome with red color isolation",
        "CINEMATIC": "Teal-orange grade, mist, vignette and film grain",
        "SUNSET": "Golden-hour wash with warm haze and grain",
        "ACTION": "Punchy warm high-contrast with heavy vignette and grain",
        "VHS": "Washed cool tape look with scanlines and grain",
    }

    def cycle_shader_option(idx, delta):
        if idx == 0:
            opts = sim.SHADER_PRESETS
            cur = sim.SHADER_SETTINGS.get("preset", "CINEMATIC")
            i = opts.index(cur) if cur in opts else 0
            sim.apply_shader_preset(opts[(i + delta) % len(opts)])
        elif idx == 1:
            opts = sim.FOG_OPTIONS
            cur = sim.SHADER_SETTINGS.get("fog", "MEDIUM")
            i = opts.index(cur) if cur in opts else 0
            sim.set_shader_option("fog", opts[(i + delta) % len(opts)])
        elif idx == 2:
            opts = sim.CRT_OPTIONS
            cur = sim.SHADER_SETTINGS.get("crt", "OFF")
            i = opts.index(cur) if cur in opts else 0
            sim.set_shader_option("crt", opts[(i + delta) % len(opts)])
        elif idx == 3:
            opts = sim.VIGNETTE_OPTIONS
            cur = sim.SHADER_SETTINGS.get("vignette", "ON")
            i = opts.index(cur) if cur in opts else 0
            sim.set_shader_option("vignette", opts[(i + delta) % len(opts)])
        elif idx == 4:
            opts = sim.SHADOWS_OPTIONS
            cur = sim.SHADER_SETTINGS.get("shadows", "ON")
            i = opts.index(cur) if cur in opts else 0
            sim.set_shader_option("shadows", opts[(i + delta) % len(opts)])

    def ch_shader(idx):
        def f(d):
            cycle_shader_option(idx, d)
            _save_shaders()
        return f

    def ch_onoff(key):
        def f(d):
            sim.set_shader_option(key, "OFF" if sim.SHADER_SETTINGS.get(key, "ON") == "ON" else "ON")
            _save_shaders()
        return f

    def SL(key, help_):
        return {"kind": "slider", "slider": slider_by_key[key], "label": slider_by_key[key]["label"], "help": help_}

    def settings_rows(tab):
        """The rows of one settings tab: kind, label, help, the live value, and how to change it."""
        name = SET_TABS[tab]
        if name == "RACE":
            rows = [
                {"kind": "cycle", "label": "Track", "get": lambda: sim.get_tileset_title(), "change": ch_track,
                 "help": "Which circuit the next race runs on."},
                {"kind": "cycle", "label": "Bots", "get": sim.get_bot_aggression, "change": ch_bots,
                 "help": "Chill follows waypoints; Demolition actively rams and bashes."},
                SL("laps", "Laps per race (1 to 10)."),
                {"kind": "cycle", "label": "HUD Mode", "get": lambda: hud_mode, "change": ch_hud,
                 "help": "Classic pins UI; Immersive reveals on changes; Hidden hides all."},
                SL("steer_rate", "Angular turning rate (0.5x to 2.0x)."),
                SL("steer_curve", "Input curve (1.0 Linear to 2.5 Exponential)."),
                SL("stick_deadzone", "Clamps joystick drift below threshold (0% to 25%)."),
                SL("drift_assist", "Counter-steer yaw dampener during handbrake slides."),
                {"kind": "toggle", "label": "Invert Steer", "get": lambda: sim.INVERT_STEER,
                 "change": ch_invert, "help": "Swaps left and right steering direction."},
                {"kind": "toggle", "label": "Look-Ahead Cam", "get": lambda: sim.DYNAMIC_LOOK_AHEAD,
                 "change": ch_lookahead, "help": "Offsets camera forward along velocity vector at speed."},
                SL("ghost_opacity", "Transparency of personal-best ghost in Time Trial."),
            ]
        elif name == "SOUND":
            rows = [
                SL("master_volume", "Primary audio bus output volume."),
                {"kind": "toggle", "label": "Master Mute", "get": lambda: sim.MASTER_MUTE,
                 "change": ch_mute, "help": "Silences all audio immediately. Hotkey: M."},
                SL("music_volume", "Playback volume for chiptune racing soundtrack."),
                SL("engine_volume", "Real-time pitch-shifted kart RPM loop volume."),
                SL("sfx_volume", "Impacts, bashes, pickups, tire squeals, and crashes."),
                SL("ui_volume", "Countdown horns, menu blips, and lap chimes."),
            ]
        elif name == "VIDEO":
            rows = [
                {"kind": "cycle", "label": "Display Mode", "get": lambda: display_mode, "change": ch_display_mode,
                 "help": "Windowed, Borderless Windowed, or Exclusive Fullscreen."},
                {"kind": "toggle", "label": "Pixel-Perfect", "get": lambda: pixel_perfect, "change": ch_pixel_perfect,
                 "help": "Constrains scaling to integer multipliers for razor-sharp pixels."},
                {"kind": "cycle", "label": "FPS Cap", "get": lambda: fps_cap_setting, "change": ch_fps_cap,
                 "help": "Match refresh rate or lock frames (60, 120, 144, Unlimited, V-Sync)."},
                SL("zoom", "Camera FOV and height above the track (0.6x to 1.6x)."),
                SL("shake", "Amplitude of camera shake trauma from impacts and boosts."),
                SL("fog_density", "Depth fog density across the circuit."),
                {"kind": "cycle", "label": "Look", "get": lambda: sim.SHADER_SETTINGS.get("preset", "CINEMATIC"),
                 "change": ch_shader(0),
                 "help": SHADER_DESCRIPTIONS.get(sim.SHADER_SETTINGS.get("preset", ""), "Post-processing shader style.")},
                {"kind": "cycle", "label": "Scanlines", "get": lambda: sim.SHADER_SETTINGS.get("crt", "OFF"),
                 "change": ch_shader(2), "help": "CRT scanlines opacity (OFF, LOW, MED, HIGH)."},
                {"kind": "toggle", "label": "Vignette", "get": lambda: sim.SHADER_SETTINGS.get("vignette") == "ON",
                 "change": ch_onoff("vignette"), "help": "Darkens screen corners for cinematic focus."},
                {"kind": "toggle", "label": "Shadows", "get": lambda: sim.SHADER_SETTINGS.get("shadows") == "ON",
                 "change": ch_onoff("shadows"), "help": "Directional dynamic drop shadows under karts and props."},
                {"kind": "toggle", "label": "FPS Counter", "get": lambda: show_fps,
                 "change": ch_fps, "help": "Displays live frame rate in top-left corner."},
            ]
        else: # CONTROLS
            rows = [
                {"kind": "cycle", "label": "Pad Preset", "get": lambda: pad_preset, "change": ch_pad_preset,
                 "help": "Arcade Classic, Trigger Drive, or Southpaw preset."},
                {"kind": "toggle", "label": "Mouse Aim", "get": lambda: mouse_aim, "change": ch_mouse_aim,
                 "help": "Aim items with cursor within 170° arc (L-Click fire, R-Click hazard)."},
                {"kind": "toggle", "label": "Gyro Steering", "get": lambda: gyro_state["enabled"], "change": ch_gyro,
                 "help": "Tilt a phone/tablet left-right to steer (mobile and web builds)."},
                SL("gyro_sens", "Tilt sensitivity: higher needs less tilt for a full turn."),
                {"kind": "cycle", "label": "Recenter Gyro", "get": lambda: "hold level · tap", "change": ch_gyro_recenter,
                 "help": "Sets the phone's current tilt as straight-ahead."},
            ] + [{"kind": "bind", "id": ak, "label": albl, "help": "Press Enter or Click to rebind key."}
                 for ak, albl in KEY_ACTIONS]
        for i, r in enumerate(rows):
            if r["kind"] == "slider":
                r["slider"]["track"] = ui.slider_track(i, len(rows))
                r["get"] = r["slider"]["get"]
                if "val_label" in r["slider"]:
                    r["val_label"] = r["slider"]["val_label"]
        return rows

    def settings_view(rows):
        out = []
        for r in rows:
            if r["kind"] == "bind":
                v = ui.key_label(pygame.key.name(keybinds[r["id"]]))
                vl = None
            else:
                v = r["get"]()
                vl = r.get("val_label")() if "val_label" in r and callable(r["val_label"]) else None
            out.append({"kind": r["kind"], "label": r["label"], "value": v, "help": r["help"],
                        "id": r.get("id"), "val_label": vl})
        return out

    def settings_change(row, d, sound=True):
        if row["kind"] == "slider":
            sl = row["slider"]
            sl["set"](max(0.0, min(1.0, round((sl["get"]() + 0.05 * d) * 20) / 20)))
            if sl["key"] == "laps":
                profile["laps"] = sim.TOTAL_LAPS
            elif sl["key"] == "steer_curve":
                profile["steer_curve"] = sim.STEER_CURVE
            elif sl["key"] == "stick_deadzone":
                profile["stick_deadzone"] = sim.STICK_DEADZONE
            elif sl["key"] == "ghost_opacity":
                profile["ghost_opacity"] = sim.GHOST_OPACITY
            else:
                profile[sl["key"]] = round(sl["get"](), 3)
            if sl["key"] == "fog_density":
                profile["shaders"] = dict(sim.SHADER_SETTINGS)
            save_profile(profile)
        elif row["kind"] in ("cycle", "toggle"):
            row["change"](d)
        if sound and row["kind"] != "bind":
            sim.play_ui("ui_move" if row["kind"] == "slider" else "ui_click")

    def settings_activate(row):
        # Enter / A / a click on the row (the caller's click blip covers the sound)
        nonlocal awaiting_key
        if row["kind"] == "bind":
            awaiting_key = row["id"]
        elif row["kind"] != "slider":
            settings_change(row, 1, sound=False)

    def settings_tab_to(t, sound=True):
        nonlocal set_tab, set_sel, awaiting_key
        t %= len(SET_TABS)
        if t != set_tab:
            set_tab, set_sel, awaiting_key = t, 0, None     # the selection tick plays the blip

    cars, player, cam = [], None, None
    attract_cars, attract_cam = [], None    # live bots racing behind the menu
    final_order = []        # frozen leaderboard shown on the results screen
    last_mtime = _safe_mtime(SIM_PATH)
    main_mtime = _safe_mtime(MAIN_PATH)

    def restart():
        # relaunch the whole process so edits to main.py (menus / UI / game loop) take effect
        print("main.py changed -> restarting for UI hot reload")
        try:
            pygame.quit()
        except pygame.error:
            pass
        os.execv(sys.executable, [sys.executable, MAIN_PATH] + sys.argv[1:])

    def start_game():
        nonlocal cars, player, cam, current_seed, state, countdown, go_timer, online
        nonlocal elim_timer, ghost_rec, last_ranks, trial_lap, ghost_best, ghost_time, popup
        nonlocal letterbox_h, target_letterbox_h, slowmo_timer, slowmo_active, finish_pending
        nonlocal final_lap_announced, reported_dead, hud_alpha, hud_reveal_timer
        nonlocal prev_player_hearts, prev_player_rank, prev_player_lap, race_was_online
        sim.NET_ROLE = "off"
        online = False
        race_was_online = False
        bot_count = 0 if game_mode == "trial" else random.randint(5, 7)
        current_seed = random.randint(0, 1_000_000)
        sim.set_bot_aggression(profile.get("bot_aggression", "Normal"))
        print(f"track seed: {current_seed}  mode: {game_mode}  bots: {bot_count}  aggr: {sim.get_bot_aggression()}  track: {sim.get_tileset_title()}")
        sim.new_map(current_seed)   # whole track + scenery built right now, not as-you-drive
        track_title = sim.get_tileset_title(sim.CURRENT_TILESET)
        sim.trigger_banner(track_title.upper(), (255, 230, 70), sub=f"{game_mode.upper()} - {sim.TOTAL_LAPS} LAPS", dur=2.0)
        cars = sim.spawn_grid(1 + bot_count)
        player = cars[min(PLAYER_SLOT, len(cars) - 1)]
        player.is_player = True
        player.is_remote = False
        player.color = PLAYER_COLOR
        player.name = player_name.strip() or "Player"
        player.flag = sim.FLAG_CODES[flag_idx] if sim.FLAG_CODES else None
        for i, bot in enumerate(c for c in cars if c is not player):
            sim.make_bot(bot, i, BOT_COLORS[i % len(BOT_COLORS)])
        if game_mode == "team":     # alternate cars into two teams, colour by team
            for i, c in enumerate(cars):
                c.team = i % 2
                c.color = TEAM_COLORS[c.team]
        cam = sim.Camera(player)
        countdown, go_timer = 3.0, 0.0
        letterbox_h = 0.0
        target_letterbox_h = 44.0
        slowmo_timer = 0.0
        slowmo_active = False
        finish_pending = False
        final_lap_announced = False
        reported_dead = set()
        hud_alpha = 1.0
        hud_reveal_timer = 3.0
        prev_player_hearts = player.hearts
        prev_player_rank = 1
        prev_player_lap = 0
        elim_timer, ghost_rec, last_ranks, trial_lap, popup = 0.0, [], {}, 0, None
        ghost_best, ghost_time = None, 0.0
        attract_cars.clear()        # its map is gone; rebuild the backdrop when we return
        state = "playing"

    def reload_and_migrate():
        nonlocal cars, player, cam
        if try_reload():
            apply_profile_to_sim(profile)
            sim.new_map(current_seed)
            slot = cars.index(player)
            cars = [migrate_car(c) for c in cars]
            player = cars[slot]
            cam = migrate_cam(cam, player)

    def setup_attract():
        # a fresh bots-only race used as the live menu backdrop (no player)
        nonlocal attract_cars, attract_cam
        sim.new_map(random.randint(0, 1_000_000))
        attract_cars = sim.spawn_grid(6)
        for i, b in enumerate(attract_cars):
            sim.make_bot(b, i, PLAYER_PALETTE[i % len(PLAYER_PALETTE)])
        attract_cam = sim.Camera(attract_cars[0])

    def step_attract(dt):
        if not attract_cars:
            setup_attract()
        ctrls = [sim.bot_control(c, attract_cars, dt) for c in attract_cars]
        sim.step(dt, attract_cars, ctrls)
        # follow the leader so the backdrop always shows action
        lead = max(attract_cars, key=lambda c: c.progress)
        attract_cam.update(dt, lead)

    def my_flag():
        return sim.FLAG_CODES[flag_idx] if sim.FLAG_CODES else None

    def net_disconnect():
        nonlocal netc, lobby, online, my_ready
        if netc is not None:
            netc.close()
        netc, lobby, online, my_ready = None, None, False, False
        sim.NET_ROLE = "off"        # else the menu backdrop keeps queueing "host" box pickups
        sim.BOX_EVENTS.clear()      # that the next hosted race would broadcast to everyone

    def is_host():
        return bool(lobby) and lobby.get("host") == lobby.get("self")

    def make_bots(nplayers, mode="fill"):
        mode = str(mode).lower()
        if mode == "none":
            nb = 0
        elif mode in ("2", 2):
            nb = min(2, 12 - nplayers)
        elif mode in ("4", 4):
            nb = min(4, 12 - nplayers)
        else:   # "fill"
            target = 6      # aim for a reasonably full grid
            nb = max(0, min(12 - nplayers, target - nplayers))
        return [{"slot": nplayers + k,
                 "name": sim.BOT_NAMES[k % len(sim.BOT_NAMES)],
                 "flag": random.choice(sim.FLAG_CODES) if sim.FLAG_CODES else None,
                 "ci": k} for k in range(nb)]

    def rebuild_grid():
        # (re)build the car list from mp_players + mp_bots; I drive my slot, everyone else is
        # remote — except the host, which also simulates the bots
        nonlocal cars, player, cam, slot_by_id, snap_by_slot
        total = len(mp_players) + len(mp_bots)
        cars = sim.spawn_grid(total)
        slot_by_id = {p["id"]: p["slot"] for p in mp_players}
        snap_by_slot = {}
        my_id = lobby["self"]
        host = is_host()
        player = None
        for p in mp_players:
            c = cars[p["slot"]]
            c.name, c.flag = p["name"], p["flag"]
            c.color = PLAYER_PALETTE[p["slot"] % len(PLAYER_PALETTE)]
            if p["id"] == my_id:
                player = c
                c.is_player = True
                c.is_remote = False
            else:
                c.is_remote = True
                c.is_player = False
        for bd in mp_bots:
            c = cars[bd["slot"]]
            sim.make_bot(c, bd["ci"], PLAYER_PALETTE[bd["slot"] % len(PLAYER_PALETTE)])
            c.name, c.flag = bd["name"], bd["flag"]
            c.is_remote = not host      # host runs bot AI; clients puppet them
            c.is_player = False
        cam = sim.Camera(player)

    def start_mp_race(start_msg):
        nonlocal current_seed, state, online, bcast_t, countdown, go_timer, end_title, mp_players, mp_bots
        nonlocal letterbox_h, target_letterbox_h, slowmo_timer, slowmo_active, finish_pending
        nonlocal final_lap_announced, reported_dead, hud_alpha, hud_reveal_timer
        nonlocal prev_player_hearts, prev_player_rank, prev_player_lap, race_was_online
        race_was_online = True
        mp_players = start_msg["players"]
        current_seed = start_msg["seed"]
        st = start_msg.get("settings") or (lobby.get("settings") if lobby else {}) or {}
        tr_type = st.get("track") or lobby_settings.get("track", "meadow_dirt")
        sim.set_track_type(tr_type)
        sim.set_tileset(tr_type)
        sim.new_map(current_seed, tileset=tr_type)
        track_title = sim.get_tileset_title(tr_type)
        sim.trigger_banner(track_title.upper(), (255, 230, 70), sub=f"MULTIPLAYER - {st.get('laps', 3)} LAPS", dur=2.0)
        sim.NET_ROLE = "host" if is_host() else "client"
        sim.TOTAL_LAPS = int(st.get("laps", 3))
        sim.set_bot_aggression(st.get("bot_aggression", "Normal"))
        b_mode = st.get("bot_count", "fill")
        mp_bots = make_bots(len(mp_players), b_mode) if is_host() else []
        rebuild_grid()
        if is_host() and mp_bots:
            netc.send({"t": "bots", "list": mp_bots})
        online, bcast_t, end_title = True, 0.0, "FINISH"
        countdown, go_timer = 3.0, 0.0
        letterbox_h = 0.0
        target_letterbox_h = 44.0
        slowmo_timer = 0.0
        slowmo_active = False
        finish_pending = False
        final_lap_announced = False
        reported_dead = set()
        hud_alpha = 1.0
        hud_reveal_timer = 3.0
        prev_player_hearts = player.hearts if player else sim.HEART_COUNT
        prev_player_rank = 1
        prev_player_lap = 0
        attract_cars.clear()
        state = "playing"

    def apply_finished(order):
        nonlocal final_order, state, end_title, slowmo_active, slowmo_timer, target_letterbox_h, finish_pending
        final_order = [cars[i] for i in order if 0 <= i < len(cars)]
        end_title = "FINISH"
        if not finish_pending and cars:
            finish_pending = True
            slowmo_active = True
            slowmo_timer = 1.5
            target_letterbox_h = 48.0
            if cam is not None:
                cam.override_zoom = 1.55
            sim.trigger_banner("FINISH!", (255, 230, 70), sub="RACE COMPLETE", dur=2.0)
            sim.play_ui("finish")
        elif not finish_pending:
            net_disconnect()
            state = "results"

    def confirm_name():
        nonlocal state
        if name_next == "single":
            start_game()
        else:
            state = "mp_menu"

    def host_create():
        nonlocal netc, pending_net, net_msg, my_ready
        net_msg, my_ready = "Connecting...", False
        lobby_settings["track"] = profile.get("track_type", sim.get_track_type())
        netc = net.Net()
        netc.connect()
        pending_net = ("host", mp_max)

    def join_create():
        nonlocal netc, pending_net, net_msg, my_ready
        if len(join_code) != 6:
            net_msg = "Enter the 6-character code"
            return
        net_msg, my_ready = "Connecting...", False
        netc = net.Net()
        netc.connect()
        pending_net = ("join", join_code)

    def toggle_ready():
        nonlocal my_ready
        my_ready = not my_ready
        if netc is not None:
            netc.send({"t": "ready", "v": my_ready})

    running = True
    last_sel = None             # (state, selections) last frame, for the menu tick sound
    stick_nav_timer = 0.0
    # STEER_SMOKE=<frames>: run headless for N frames then quit 0 (CI launch self-test)
    smoke_frames = int(os.environ.get("STEER_SMOKE", "0") or "0")
    frame_no = 0
    while running:
        frame_no += 1
        if smoke_frames and frame_no >= smoke_frames:
            print(f"SMOKE OK: survived {frame_no} frames")
            running = False
        fps_target = 60
        if fps_cap_setting == "120 FPS":
            fps_target = 120
        elif fps_cap_setting == "144 FPS":
            fps_target = 144
        elif fps_cap_setting == "Unlimited":
            fps_target = 0
        dt = min(clock.tick(fps_target) / 1000.0, 1 / 30)   # clamp so a freeze/stall can't teleport the car
        mouse_pos = pygame.mouse.get_pos()
        sim.SFX_MUTED = state != "playing"   # menus + attract-mode race run silent
        frame_state = state                  # to hear pause / resume once events are handled

        # hot reload: main.py edits restart the process; sim.py edits reload live. In a race,
        # sim.py is handled below (state carries over); everywhere else, reload it in place so
        # menu / HUD draw-code changes show without a restart.
        mm, sm = (_safe_mtime(MAIN_PATH), _safe_mtime(SIM_PATH)) if not FROZEN else (main_mtime, last_mtime)
        if not FROZEN and mm and mm != main_mtime:
            restart()
        if sm != last_mtime and state != "playing" and player is None:
            # (with a race paused this waits: the in-race check reloads it properly on Resume,
            # rebuilding that race's track -- reloading here would wipe it and crash on Resume)
            last_mtime = sm
            if try_reload():
                apply_profile_to_sim(profile)
                if state in MENU_STATES:
                    setup_attract()

        # advance the live menu backdrop (only when no race is in progress to resume)
        if state in MENU_STATES and player is None:
            step_attract(dt)

        # ---- drain anything the server sent since last frame ----------------------
        if netc is not None:
            if netc.waking():
                net_msg = "Waking the server..."
            for m in netc.poll():
                mt = m.get("t")
                if mt == "netopen":
                    net_msg = "Connected"
                    if pending_net:
                        if pending_net[0] == "host":
                            netc.send({"t": "host", "name": player_name.strip() or "Player",
                                       "flag": my_flag(), "max": pending_net[1],
                                       "settings": lobby_settings})
                        else:
                            netc.send({"t": "join", "code": pending_net[1],
                                       "name": player_name.strip() or "Player", "flag": my_flag()})
                        pending_net = None
                elif mt == "neterr":
                    net_msg = "Connection failed: " + m.get("msg", "")
                    netc, lobby = None, None
                    state = "mp_menu"
                elif mt == "err":
                    net_msg = m.get("msg", "Error")
                elif mt == "room":
                    prev_self = lobby.get("self") if lobby else None
                    lobby = m
                    if "self" not in lobby and prev_self is not None:
                        lobby["self"] = prev_self   # server only sends self on the first ack
                    if "settings" in m and isinstance(m["settings"], dict):
                        lobby_settings.update(m["settings"])
                    if not m.get("started") and state in ("mp_menu", "lobby"):
                        state = "lobby"
                    elif online and is_host() and sim.NET_ROLE == "client":
                        # the host left mid-race and I was promoted: take over bots + boxes
                        sim.NET_ROLE = "host"
                        for bd in mp_bots:
                            if bd["slot"] < len(cars):
                                cars[bd["slot"]].is_remote = False
                elif mt == "kicked":
                    net_msg = "You were kicked from the lobby"
                    net_disconnect()
                    state = "mp_menu"
                elif mt == "left":
                    if online:          # drop the departed player's car from the race
                        slot = slot_by_id.get(m.get("id"))
                        if slot is not None and slot < len(cars):
                            cars[slot].dead = True
                elif mt == "start":
                    start_mp_race(m)
                elif mt == "bots" and online:
                    mp_bots = m.get("list", [])
                    rebuild_grid()
                elif mt == "box" and online:
                    idx, slot, kind = m.get("i"), m.get("slot"), m.get("kind")
                    sim.apply_box_event(idx, kind)
                    if player is not None and slot == slot_by_id.get(lobby.get("self")):
                        sim.give_powerup(player, kind)   # my pickup: apply to my own car
                elif mt == "finished" and online:
                    apply_finished(m.get("order", []))
                elif mt == "state" and online:
                    slot = m.get("slot", slot_by_id.get(m.get("id")))
                    if slot is not None:
                        snap_by_slot[slot] = m.get("car")

        # menu layout: buttons stacked in the bottom-left corner, left-aligned, no background
        items = []
        if player is not None:
            items += [("resume", "Resume"), ("play", "New Race")]
        else:
            items.append(("play", "Play"))
        items += [("settings", "Settings"), ("quit", "Quit")]
        menu_buttons = [(nm, Button(r, lbl, align="left"))
                        for (nm, lbl), r in zip(items, ui.menu_layout(len(items), sim.H))]
        menu_sel = max(0, min(menu_sel, len(menu_buttons) - 1))

        # mode screen (Singleplayer / Multiplayer / Back), same bottom-left stack
        mode_items = [("single", "Singleplayer"), ("multi", "Multiplayer"), ("back", "Back")]
        mode_buttons = [(nm, Button(r, lbl, align="left"))
                        for (nm, lbl), r in zip(mode_items, ui.menu_layout(len(mode_items), sim.H))]
        mode_sel = max(0, min(mode_sel, len(mode_buttons) - 1))

        gamemode_buttons = []
        gy = 90
        for mk, mlabel in GAME_MODES:
            gamemode_buttons.append((mk, Button((sim.W / 2 - 110, gy, 220, 36), mlabel)))
            gy += 42
        gamemode_sel = max(0, min(gamemode_sel, len(gamemode_buttons)))

        # Mouse hover updates selection index so keyboard and pointer stay synchronized
        if state == "menu":
            for i, (_, btn) in enumerate(menu_buttons):
                if btn.clicked(mouse_pos):
                    menu_sel = i
                    break
            links = [(k, url) for k, url in SOCIAL_LINKS if url]
            if any(r.collidepoint(mouse_pos) for r in ui.social_layout(len(links), sim.W, sim.H)):
                if not cursor_hand:
                    try:
                        pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_HAND)
                        cursor_hand = True
                    except Exception:
                        pass
            elif cursor_hand:
                try:
                    pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_ARROW)
                    cursor_hand = False
                except Exception:
                    pass
        elif cursor_hand:
            try:
                pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_ARROW)
                cursor_hand = False
            except Exception:
                pass
        elif state == "mode":
            for i, (_, btn) in enumerate(mode_buttons):
                if btn.clicked(mouse_pos):
                    mode_sel = i
                    break
        elif state == "gamemode":
            for i, (_, btn) in enumerate(gamemode_buttons):
                if btn.clicked(mouse_pos):
                    gamemode_sel = i
                    break
            if back_btn.clicked(mouse_pos):
                gamemode_sel = len(gamemode_buttons)
        elif state == "results":
            for i, r in enumerate(ui.results_buttons(results_buttons())):
                if r.collidepoint(mouse_pos):
                    results_sel = i
        elif state == "settings":
            if mouse_pos != set_mouse:      # only a moving mouse steals the highlight from the keys
                if set_mouse is not None and awaiting_key is None:
                    hit = ui.hit_row(mouse_pos, len(settings_rows(set_tab)), SET_TABS[set_tab] == "CONTROLS")
                    if hit is not None:
                        set_sel = hit
                set_mouse = mouse_pos

        # menu sounds: a tick whenever the highlighted button changes (mouse or keys)
        cur_sel = (state, menu_sel, mode_sel, gamemode_sel, set_tab, set_sel, results_sel)
        if state in MENU_STATES and last_sel is not None and last_sel[0] == state and cur_sel != last_sel:
            sim.play_ui("ui_move")
        last_sel = cur_sel

        action = None   # the player's bash this frame, if any
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == sim.MUSIC_END:
                sim.next_track()
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_F11 and awaiting_key is None:
                toggle_fullscreen()
                continue
            elif event.type == pygame.KEYDOWN:
                if state == "settings" and awaiting_key is not None:
                    if event.key != pygame.K_ESCAPE:    # Esc cancels the rebind
                        keybinds[awaiting_key] = event.key
                        profile.setdefault("keys", {})[awaiting_key] = event.key
                        save_profile(profile)
                    sim.play_ui("ui_click" if event.key != pygame.K_ESCAPE else "ui_back")
                    awaiting_key = None
                    continue
                if state in MENU_STATES:
                    typing = state in ("name_entry", "join_entry")
                    if event.key == pygame.K_ESCAPE:
                        sim.play_ui("ui_back")
                    elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER) or \
                            (event.key == pygame.K_SPACE and not typing):
                        sim.play_ui("ui_click")
                    elif typing and event.unicode and event.unicode.isprintable():
                        sim.play_ui("ui_move", 0.6)
                if event.key == pygame.K_m and state not in ("name_entry", "join_entry"):   # global mute toggle (not while typing)
                    sim.set_master_mute(not sim.MASTER_MUTE)
                    profile["mute"] = sim.MASTER_MUTE
                    save_profile(profile)
                if state == "playing":
                    if event.key == pygame.K_r and not online:
                        reload_and_migrate()
                    elif event.key == pygame.K_ESCAPE:
                        state = "menu"          # pauses; the race stays alive for Resume
                    elif event.key == keybinds.get("bashL"):
                        action = "left"
                    elif event.key == keybinds.get("bashR"):
                        action = "right"
                    elif event.key == keybinds.get("ram"):
                        action = "ram"
                    elif event.key == keybinds.get("shoot"):
                        action = "shoot"
                    elif event.key == keybinds.get("cone", pygame.K_c):
                        pressed = pygame.key.get_pressed()
                        down_pressed = pressed[pygame.K_DOWN] or pressed[pygame.K_s]
                        action = "drop_cone" if down_pressed else "cone"
                    elif event.key == keybinds.get("oil", pygame.K_v):
                        action = "oil"
                elif state == "menu":
                    if event.key in (pygame.K_DOWN, pygame.K_s):
                        menu_sel = (menu_sel + 1) % len(menu_buttons)
                    elif event.key in (pygame.K_UP, pygame.K_w):
                        menu_sel = (menu_sel - 1) % len(menu_buttons)
                    elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        name = menu_buttons[menu_sel][0]
                        if name == "resume":
                            state = "playing"
                        elif name == "play":
                            mode_sel = 0
                            state = "mode"
                        elif name == "settings":
                            state = "settings"
                        elif name == "quit":
                            running = False
                    elif event.key == pygame.K_ESCAPE and player is not None:
                        state = "playing"
                elif state == "mode":
                    if event.key in (pygame.K_DOWN, pygame.K_s):
                        mode_sel = (mode_sel + 1) % len(mode_buttons)
                    elif event.key in (pygame.K_UP, pygame.K_w):
                        mode_sel = (mode_sel - 1) % len(mode_buttons)
                    elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        nm = mode_buttons[mode_sel][0]
                        if nm == "single":
                            gamemode_sel = 0
                            state = "gamemode"
                        elif nm == "multi":
                            mp_tab, net_msg = "host", ""
                            state = "mp_menu"
                        elif nm == "back":
                            state = "menu"
                    elif event.key == pygame.K_ESCAPE:
                        state = "menu"
                elif state == "gamemode":
                    total_opts = len(gamemode_buttons) + 1
                    if event.key in (pygame.K_DOWN, pygame.K_s):
                        gamemode_sel = (gamemode_sel + 1) % total_opts
                    elif event.key in (pygame.K_UP, pygame.K_w):
                        gamemode_sel = (gamemode_sel - 1) % total_opts
                    elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        if gamemode_sel < len(gamemode_buttons):
                            mk = gamemode_buttons[gamemode_sel][0]
                            game_mode, name_next, state = mk, "single", "name_entry"
                        else:
                            state = "mode"
                    elif event.key == pygame.K_ESCAPE:
                        state = "mode"
                elif state == "mp_menu":
                    if event.key in (pygame.K_LEFT, pygame.K_a):
                        mp_tab = "host"
                    elif event.key in (pygame.K_RIGHT, pygame.K_d):
                        mp_tab = "join"
                    elif mp_tab == "host" and event.key in (pygame.K_UP, pygame.K_w):
                        mp_max = min(12, mp_max + 1)
                    elif mp_tab == "host" and event.key in (pygame.K_DOWN, pygame.K_s):
                        mp_max = max(2, mp_max - 1)
                    elif event.key == pygame.K_RETURN:
                        if mp_tab == "host":
                            host_create()
                        else:
                            join_create()
                    elif event.key == pygame.K_ESCAPE:
                        if netc is not None and lobby is None:
                            net_disconnect()   # cancel an in-flight connect, stay on this screen
                        else:
                            state = "mode"
                    elif mp_tab == "join" and event.key == pygame.K_BACKSPACE:
                        join_code = join_code[:-1]
                    elif mp_tab == "join" and event.unicode and event.unicode.isalnum() and len(join_code) < 6:
                        join_code += event.unicode.upper()
                elif state == "name_entry":
                    if event.key == pygame.K_RETURN:
                        confirm_name()
                    elif event.key == pygame.K_ESCAPE:
                        state = "mode"
                    elif event.key == pygame.K_BACKSPACE:
                        player_name = player_name[:-1]
                    elif event.key == pygame.K_LEFT and sim.FLAG_CODES:
                        flag_idx = (flag_idx - 1) % len(sim.FLAG_CODES)
                    elif event.key == pygame.K_RIGHT and sim.FLAG_CODES:
                        flag_idx = (flag_idx + 1) % len(sim.FLAG_CODES)
                    elif event.unicode and event.unicode.isprintable() and len(player_name) < 12:
                        player_name += event.unicode
                elif state == "settings":
                    rows = settings_rows(set_tab)
                    if event.key == pygame.K_ESCAPE:
                        save_profile(profile)
                        state = "menu"
                    elif event.key in (pygame.K_TAB, pygame.K_e, pygame.K_PAGEDOWN):
                        back = event.key == pygame.K_TAB and (event.mod & pygame.KMOD_SHIFT)
                        settings_tab_to(set_tab + (-1 if back else 1))
                    elif event.key in (pygame.K_q, pygame.K_PAGEUP):
                        settings_tab_to(set_tab - 1)
                    elif event.key in (pygame.K_DOWN, pygame.K_s):
                        set_sel = (set_sel + 1) % len(rows)
                    elif event.key in (pygame.K_UP, pygame.K_w):
                        set_sel = (set_sel - 1) % len(rows)
                    elif event.key in (pygame.K_LEFT, pygame.K_a):
                        settings_change(rows[set_sel], -1)
                    elif event.key in (pygame.K_RIGHT, pygame.K_d):
                        settings_change(rows[set_sel], 1)
                    elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                        settings_activate(rows[set_sel])
                elif state == "results":
                    nb = len(results_buttons())
                    if event.key == pygame.K_ESCAPE:
                        player = None
                        state = "menu"
                    elif event.key in (pygame.K_LEFT, pygame.K_a, pygame.K_UP, pygame.K_w):
                        results_sel = (results_sel - 1) % nb
                    elif event.key in (pygame.K_RIGHT, pygame.K_d, pygame.K_DOWN, pygame.K_s):
                        results_sel = (results_sel + 1) % nb
                    elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                        results_choose(min(results_sel, nb - 1))
                elif event.key == pygame.K_ESCAPE and state == "lobby":
                    net_disconnect()
                    state = "mp_menu"
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if state == "playing" and player is not None and not player.dead and not spectating:
                    if event.button == 1:
                        # Left click: Shoot projectile at mouse aim direction (front only)
                        mouse_x, mouse_y = event.pos
                        if cam is not None:
                            wx, wy = cam.to_world(mouse_x, mouse_y)
                            dx = sim.wrap_delta(player.x, wx)
                            dy = sim.wrap_delta(player.y, wy)
                            aim_ang = math.degrees(math.atan2(dy, dx))
                            diff = (aim_ang - player.angle + 180) % 360 - 180
                            if abs(diff) <= 85.0:  # u can only shoot infront not back
                                action = ("shoot_aim", aim_ang)
                    elif event.button == 3:
                        # Right click: spawn cone or oil behind player
                        if player.item == "oil":
                            action = "oil"
                        elif player.item == "cone":
                            action = "drop_cone"
                        else:
                            last_sab = getattr(player, "_last_sab", "oil")
                            if last_sab == "oil":
                                action = "drop_cone"
                                player._last_sab = "cone"
                            else:
                                action = "oil"
                                player._last_sab = "oil"
                elif event.button == 1:
                    if state in MENU_STATES:
                        sim.play_ui("ui_click")
                    if state == "menu":
                        opened_social = False
                        links = [(k, url) for k, url in SOCIAL_LINKS if url]
                        opened_social = False
                        for (k, url), r in zip(links, ui.social_layout(len(links), sim.W, sim.H)):
                            if r.collidepoint(mouse_pos):
                                try:
                                    webbrowser.open(url)
                                except Exception as e:
                                    print("could not open", url, e)
                                opened_social = True
                                break
                        if opened_social:
                            continue
                        for name, btn in menu_buttons:
                            if not btn.clicked(mouse_pos):
                                continue
                            if name == "resume":
                                state = "playing"
                            elif name == "play":
                                state = "mode"              # Singleplayer / Multiplayer
                            elif name == "settings":
                                state = "settings"
                            elif name == "quit":
                                running = False
                            break
                    elif state == "name_entry":
                        if start_btn.clicked(mouse_pos):
                            confirm_name()
                        elif back_btn.clicked(mouse_pos):
                            state = "mode"
                        elif flag_prev.clicked(mouse_pos) and sim.FLAG_CODES:
                            flag_idx = (flag_idx - 1) % len(sim.FLAG_CODES)
                        elif flag_next.clicked(mouse_pos) and sim.FLAG_CODES:
                            flag_idx = (flag_idx + 1) % len(sim.FLAG_CODES)
                    elif state == "mode":
                        for nm, btn in mode_buttons:
                            if not btn.clicked(mouse_pos):
                                continue
                            if nm == "single":
                                state = "gamemode"
                            elif nm == "multi":
                                name_next = "mp"
                                state = "name_entry"
                            elif nm == "back":
                                state = "menu"
                            break
                    elif state == "gamemode":
                        hit_mode = False
                        for mk, btn in gamemode_buttons:
                            if btn.clicked(mouse_pos):
                                game_mode, name_next, state = mk, "single", "name_entry"
                                hit_mode = True
                                break
                        if not hit_mode and back_btn.clicked(mouse_pos):
                            state = "mode"
                    elif state == "mp_menu":
                        if host_btn.clicked(mouse_pos):
                            mp_tab = "host"
                        elif join_btn.clicked(mouse_pos):
                            mp_tab = "join"
                        elif back_btn.clicked(mouse_pos):
                            if netc is not None and lobby is None:
                                net_disconnect()
                            else:
                                state = "mode"
                        elif mp_tab == "host" and minus_btn.clicked(mouse_pos):
                            mp_max = max(2, mp_max - 1)
                        elif mp_tab == "host" and plus_btn.clicked(mouse_pos):
                            mp_max = min(12, mp_max + 1)
                        elif mp_tab == "host" and create_btn.clicked(mouse_pos):
                            host_create()
                        elif mp_tab == "join" and confirm_join_btn.clicked(mouse_pos):
                            join_create()
                    elif state == "lobby":
                        if ready_btn.clicked(mouse_pos):
                            toggle_ready()
                        elif leave_btn.clicked(mouse_pos):
                            net_disconnect()
                            state = "mp_menu"
                        elif lobby and lobby.get("host") == lobby.get("self"):
                            if host_track_btn.clicked(mouse_pos):
                                topts = list(sim.TILESETS) + ["random"]
                                cur = lobby_settings.get("track", "meadow_dirt")
                                idx = topts.index(cur) if cur in topts else 0
                                lobby_settings["track"] = topts[(idx + 1) % len(topts)]
                            elif host_rot_btn.clicked(mouse_pos):
                                ropts = ["Host Choice", "Player Vote", "Random Circuit", "5-World Cup"]
                                cur = lobby_settings.get("rotation", "Host Choice")
                                idx = ropts.index(cur) if cur in ropts else 0
                                lobby_settings["rotation"] = ropts[(idx + 1) % len(ropts)]
                            elif host_laps_btn.clicked(mouse_pos):
                                lopts = [1, 3, 5, 7]
                                cur = int(lobby_settings.get("laps", 3))
                                idx = lopts.index(cur) if cur in lopts else 1
                                lobby_settings["laps"] = lopts[(idx + 1) % len(lopts)]
                            elif host_bots_btn.clicked(mouse_pos):
                                bopts = ["Fill to 8", "Fill to 12", "No Bots"]
                                cur = lobby_settings.get("bot_count", "Fill to 8")
                                idx = bopts.index(cur) if cur in bopts else 0
                                lobby_settings["bot_count"] = bopts[(idx + 1) % len(bopts)]
                            elif host_aggr_btn.clicked(mouse_pos):
                                levels = ["Chill", "Casual", "Feisty", "Demolition"]
                                cur = lobby_settings.get("bot_aggression", "Casual")
                                idx = levels.index(cur) if cur in levels else 1
                                lobby_settings["bot_aggression"] = levels[(idx + 1) % len(levels)]
                            elif host_coll_btn.clicked(mouse_pos):
                                copts = ["Full Contact", "Solid (No Spun Damage)", "Ghost (Time Trial)"]
                                cur = lobby_settings.get("collision", "Full Contact")
                                idx = copts.index(cur) if cur in copts else 0
                                lobby_settings["collision"] = copts[(idx + 1) % len(copts)]
                            elif host_slip_btn.clicked(mouse_pos):
                                lobby_settings["slipstream"] = "OFF" if lobby_settings.get("slipstream", "ON") == "ON" else "ON"
                            elif host_items_btn.clicked(mouse_pos):
                                iopts = ["Standard", "High Explosives / Kinetic Only", "Hazards Only", "Pure Racing (No Items)"]
                                cur = lobby_settings.get("items", "Standard")
                                idx = iopts.index(cur) if cur in iopts else 0
                                lobby_settings["items"] = iopts[(idx + 1) % len(iopts)]
                            elif host_priv_btn.clicked(mouse_pos):
                                popts = ["Public", "Friends Only", "Invite Code Only"]
                                cur = lobby_settings.get("privacy", "Public")
                                idx = popts.index(cur) if cur in popts else 0
                                lobby_settings["privacy"] = popts[(idx + 1) % len(popts)]
                            else:
                                for i, p in enumerate(lobby.get("players", [])):
                                    if p["id"] == lobby.get("self"):
                                        continue
                                    kr = pygame.Rect(256, 88 + i * 28, 20, 20)
                                    br = pygame.Rect(280, 88 + i * 28, 20, 20)
                                    if kr.collidepoint(mouse_pos):
                                        netc.send({"t": "kick", "id": p["id"]})
                                        break
                                    if br.collidepoint(mouse_pos):
                                        netc.send({"t": "ban", "id": p["id"]})
                                        break
                            if netc is not None:
                                netc.send({"t": "settings", "settings": lobby_settings})
                    elif state == "settings":
                        rows = settings_rows(set_tab)
                        is_keys = SET_TABS[set_tab] == "CONTROLS"
                        hit = ui.hit_row(mouse_pos, len(rows), is_keys)
                        tab_hit = next((i for i, r in enumerate(ui.tab_layout(SET_TABS))
                                        if r.collidepoint(mouse_pos)), None)
                        if ui.BACK.collidepoint(mouse_pos):
                            save_profile(profile)
                            state = "menu"
                        elif tab_hit is not None:
                            settings_tab_to(tab_hit, sound=False)
                        elif hit is not None:
                            set_sel = hit
                            row = rows[hit]
                            if row["kind"] == "slider":
                                if row["slider"]["track"].inflate(24, 16).collidepoint(mouse_pos):
                                    active_slider = row["slider"]
                                    tr = active_slider["track"]
                                    v = max(0.0, min(1.0, (mouse_pos[0] - tr.x) / tr.w))
                                    active_slider["set"](v)
                                    settings_change(row, 0, sound=True)
                            elif row["kind"] == "cycle":
                                c = ui.ctrl_rect(hit, len(rows), is_keys)
                                settings_change(row, -1 if (c.collidepoint(mouse_pos)
                                                            and mouse_pos[0] < c.centerx) else 1, sound=False)
                            else:
                                settings_activate(row)
                    elif state == "results":
                        for i, r in enumerate(ui.results_buttons(results_buttons())):
                            if r.collidepoint(mouse_pos):
                                results_choose(i)
                                break
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if active_slider is not None:
                    if active_slider["key"] == "laps":
                        profile["laps"] = sim.TOTAL_LAPS
                    elif active_slider["key"] == "steer_curve":
                        profile["steer_curve"] = sim.STEER_CURVE
                    elif active_slider["key"] == "stick_deadzone":
                        profile["stick_deadzone"] = sim.STICK_DEADZONE
                    elif active_slider["key"] == "ghost_opacity":
                        profile["ghost_opacity"] = sim.GHOST_OPACITY
                    else:
                        profile[active_slider["key"]] = round(active_slider["get"](), 3)
                    active_slider = None
                    save_profile(profile)
            elif event.type == pygame.CONTROLLERDEVICEADDED:
                open_pad(event.device_index)
            elif event.type == pygame.CONTROLLERDEVICEREMOVED:
                pads.pop(event.instance_id, None)
            elif event.type == pygame.CONTROLLERBUTTONDOWN:
                b = event.button
                if state in MENU_STATES:
                    if b == PAD_CONFIRM:
                        sim.play_ui("ui_click")
                    elif b == PAD_BACK:
                        sim.play_ui("ui_back")
                if state == "playing":
                    if b == PAD_BASH_L:
                        action = "left"
                    elif b == PAD_BASH_R:
                        action = "right"
                    elif b == PAD_RAM:
                        action = "ram"
                    elif b == PAD_SHOOT:
                        action = "shoot"
                    elif b == PAD_ITEM:
                        down_pressed = False
                        try:
                            for p in pads.values():
                                if p.get_button(PAD_DOWN) or (p.get_axis(pygame.CONTROLLER_AXIS_LEFTY) / 32768.0 > 0.5):
                                    down_pressed = True
                                    break
                        except Exception:
                            pass
                        action = "drop_cone" if down_pressed else "cone"
                    elif b == PAD_DOWN:
                        action = "oil"
                    elif b in (PAD_SELECT, PAD_L3):
                        if player is not None and not player.dead:
                            player.rescue()
                    elif b == PAD_PAUSE:
                        state = "menu"
                elif state == "menu":
                    if b == PAD_DOWN:
                        menu_sel = (menu_sel + 1) % len(menu_buttons)
                    elif b == PAD_UP:
                        menu_sel = (menu_sel - 1) % len(menu_buttons)
                    elif b == PAD_CONFIRM:
                        name = menu_buttons[menu_sel][0]
                        if name == "resume":
                            state = "playing"
                        elif name == "play":
                            state = "mode"
                        elif name == "settings":
                            state = "settings"
                        elif name == "quit":
                            running = False
                    elif b == PAD_PAUSE and player is not None:
                        state = "playing"
                elif state == "name_entry":
                    if b == PAD_CONFIRM:
                        confirm_name()
                    elif b == PAD_BACK:
                        state = "mode"
                    elif b == PAD_LEFT and sim.FLAG_CODES:
                        flag_idx = (flag_idx - 1) % len(sim.FLAG_CODES)
                    elif b == PAD_RIGHT and sim.FLAG_CODES:
                        flag_idx = (flag_idx + 1) % len(sim.FLAG_CODES)
                    elif b in (PAD_SHOOT, PAD_ITEM):
                        preset_names = ["VIPER", "TURBO", "APEX", "BLAZE", "LIGHTNING", "SHADOW", "DRIFTER", "MAX", "LEWIS", "FERNANDO", "CHARLES"]
                        cur = player_name.strip()
                        idx = preset_names.index(cur) if cur in preset_names else -1
                        player_name = preset_names[(idx + 1) % len(preset_names)]
                        sim.play_ui("ui_move")
                elif state == "mode":
                    if b == PAD_DOWN:
                        mode_sel = (mode_sel + 1) % len(mode_buttons)
                    elif b == PAD_UP:
                        mode_sel = (mode_sel - 1) % len(mode_buttons)
                    elif b == PAD_CONFIRM:
                        nm = mode_buttons[mode_sel][0]
                        if nm == "single":
                            gamemode_sel = 0
                            state = "gamemode"
                        elif nm == "multi":
                            mp_tab, net_msg = "host", ""
                            name_next = "mp"
                            state = "name_entry"
                        elif nm == "back":
                            state = "menu"
                    elif b == PAD_BACK:
                        state = "menu"
                elif state == "gamemode":
                    total_opts = len(gamemode_buttons) + 1
                    if b == PAD_DOWN:
                        gamemode_sel = (gamemode_sel + 1) % total_opts
                    elif b == PAD_UP:
                        gamemode_sel = (gamemode_sel - 1) % total_opts
                    elif b == PAD_CONFIRM:
                        if gamemode_sel < len(gamemode_buttons):
                            mk = gamemode_buttons[gamemode_sel][0]
                            game_mode, name_next, state = mk, "single", "name_entry"
                        else:
                            state = "mode"
                    elif b == PAD_BACK:
                        state = "mode"
                elif state == "mp_menu":
                    if b in (PAD_LEFT, PAD_BASH_L):
                        mp_tab = "host"
                    elif b in (PAD_RIGHT, PAD_BASH_R):
                        mp_tab = "join"
                    elif b == PAD_UP and mp_tab == "host":
                        mp_max = min(12, mp_max + 1)
                    elif b == PAD_DOWN and mp_tab == "host":
                        mp_max = max(2, mp_max - 1)
                    elif b == PAD_CONFIRM:
                        if mp_tab == "host":
                            host_create()
                        else:
                            join_create()
                    elif b == PAD_BACK:
                        if netc is not None and lobby is None:
                            net_disconnect()
                        else:
                            state = "mode"
                elif state == "lobby":
                    if b == PAD_CONFIRM:
                        toggle_ready()
                    elif b == PAD_BACK:
                        net_disconnect()
                        state = "mp_menu"
                    elif lobby and lobby.get("host") == lobby.get("self"):
                        if b == PAD_ITEM:
                            levels = sim.BOT_AGGRESSION_LEVELS
                            cur = lobby_settings.get("bot_aggression", "Normal")
                            idx = levels.index(cur) if cur in levels else 1
                            lobby_settings["bot_aggression"] = levels[(idx + 1) % len(levels)]
                            if netc is not None:
                                netc.send({"t": "settings", "settings": lobby_settings})
                            sim.play_ui("ui_click")
                        elif b == PAD_SHOOT:
                            bopts = ["fill", "4", "2", "none"]
                            cur = str(lobby_settings.get("bot_count", "fill")).lower()
                            idx = bopts.index(cur) if cur in bopts else 0
                            lobby_settings["bot_count"] = bopts[(idx + 1) % len(bopts)]
                            if netc is not None:
                                netc.send({"t": "settings", "settings": lobby_settings})
                            sim.play_ui("ui_click")
                        elif b in (PAD_UP, PAD_DOWN, PAD_BASH_R):
                            lopts = [1, 3, 5, 7]
                            cur = int(lobby_settings.get("laps", 3))
                            idx = lopts.index(cur) if cur in lopts else 1
                            lobby_settings["laps"] = lopts[(idx + 1) % len(lopts)]
                            if netc is not None:
                                netc.send({"t": "settings", "settings": lobby_settings})
                            sim.play_ui("ui_click")
                elif state == "settings":
                    rows = settings_rows(set_tab)
                    if b == PAD_BACK:
                        awaiting_key = None
                        save_profile(profile)
                        state = "menu"
                    elif b == PAD_BASH_L:
                        settings_tab_to(set_tab - 1)
                    elif b == PAD_BASH_R:
                        settings_tab_to(set_tab + 1)
                    elif b == PAD_DOWN:
                        set_sel = (set_sel + 1) % len(rows)
                    elif b == PAD_UP:
                        set_sel = (set_sel - 1) % len(rows)
                    elif b == PAD_LEFT:
                        settings_change(rows[set_sel], -1)
                    elif b == PAD_RIGHT:
                        settings_change(rows[set_sel], 1)
                    elif b == PAD_CONFIRM:
                        settings_activate(rows[set_sel])
                elif state == "results":
                    nb = len(results_buttons())
                    if b == PAD_BACK:
                        player = None
                        state = "menu"
                    elif b in (PAD_LEFT, PAD_UP):
                        results_sel = (results_sel - 1) % nb
                    elif b in (PAD_RIGHT, PAD_DOWN):
                        results_sel = (results_sel + 1) % nb
                    elif b == PAD_CONFIRM:
                        results_choose(min(results_sel, nb - 1))

        # Analog left-stick menu navigation
        if stick_nav_timer > 0.0:
            stick_nav_timer = max(0.0, stick_nav_timer - dt)
        if state in MENU_STATES and pads:
            max_sx, max_sy = 0.0, 0.0
            for p in pads.values():
                try:
                    sx = p.get_axis(pygame.CONTROLLER_AXIS_LEFTX) / 32768.0
                    sy = p.get_axis(pygame.CONTROLLER_AXIS_LEFTY) / 32768.0
                    if abs(sx) > abs(max_sx): max_sx = sx
                    if abs(sy) > abs(max_sy): max_sy = sy
                except Exception:
                    pass
            stick_btn = None
            if abs(max_sx) < 0.25 and abs(max_sy) < 0.25:
                stick_nav_timer = 0.0
            elif stick_nav_timer <= 0.0:
                if max_sy > 0.55:
                    stick_btn = PAD_DOWN
                    stick_nav_timer = 0.22
                elif max_sy < -0.55:
                    stick_btn = PAD_UP
                    stick_nav_timer = 0.22
                elif max_sx > 0.55:
                    stick_btn = PAD_RIGHT
                    stick_nav_timer = 0.22
                elif max_sx < -0.55:
                    stick_btn = PAD_LEFT
                    stick_nav_timer = 0.22
            if stick_btn is not None:
                if state == "menu":
                    if stick_btn == PAD_DOWN:
                        menu_sel = (menu_sel + 1) % len(menu_buttons)
                    elif stick_btn == PAD_UP:
                        menu_sel = (menu_sel - 1) % len(menu_buttons)
                elif state == "mode":
                    if stick_btn == PAD_DOWN:
                        mode_sel = (mode_sel + 1) % len(mode_buttons)
                    elif stick_btn == PAD_UP:
                        mode_sel = (mode_sel - 1) % len(mode_buttons)
                elif state == "gamemode":
                    tot = len(gamemode_buttons) + 1
                    if stick_btn == PAD_DOWN:
                        gamemode_sel = (gamemode_sel + 1) % tot
                    elif stick_btn == PAD_UP:
                        gamemode_sel = (gamemode_sel - 1) % tot
                elif state == "name_entry":
                    if stick_btn == PAD_LEFT and sim.FLAG_CODES:
                        flag_idx = (flag_idx - 1) % len(sim.FLAG_CODES)
                    elif stick_btn == PAD_RIGHT and sim.FLAG_CODES:
                        flag_idx = (flag_idx + 1) % len(sim.FLAG_CODES)
                elif state == "settings":
                    if stick_btn == PAD_DOWN:
                        settings_sel = (settings_sel + 1) % 16
                    elif stick_btn == PAD_UP:
                        settings_sel = (settings_sel - 1) % 16
                    elif stick_btn == PAD_LEFT:
                        if settings_sel < 7:
                            s = sliders[settings_sel]
                            s["set"](max(0.0, s["get"]() - 0.05))
                            profile[s["key"]] = round(s["get"](), 3)
                            save_profile(profile)
                            sim.play_ui("ui_move")
                        elif 7 <= settings_sel < 15:
                            apply_setting_toggle(settings_sel - 7, -1)
                    elif stick_btn == PAD_RIGHT:
                        if settings_sel < 7:
                            s = sliders[settings_sel]
                            s["set"](min(1.0, s["get"]() + 0.05))
                            profile[s["key"]] = round(s["get"](), 3)
                            save_profile(profile)
                            sim.play_ui("ui_move")
                        elif 7 <= settings_sel < 15:
                            apply_setting_toggle(settings_sel - 7, 1)

        # pause / resume blips (Esc, Start or the menu's Resume button)
        if frame_state == "playing" and state == "menu":
            sim.play_ui("pause")
        elif frame_state == "menu" and state == "playing" and countdown <= 0:
            sim.play_ui("resume")

        if state == "playing":
            target_letterbox_h = 44.0 if (countdown > 0 or slowmo_active) else 0.0
            letterbox_h += (target_letterbox_h - letterbox_h) * min(1.0, dt * 5.5)
            if cam is not None:     # positional sounds are heard from the camera
                sim.LISTENER = (cam.x, cam.y, cam.angle)

            if countdown > 0:
                # pre-race lock: 3..2..1..GO, cars frozen (no step)
                beat = int(math.ceil(countdown))
                if countdown >= 3.0:
                    sim.play_ui("count_beep")           # "3"
                countdown -= dt
                if countdown <= 0:
                    go_timer = 0.8
                    sim.play_ui("count_go")
                elif int(math.ceil(countdown)) != beat:
                    sim.play_ui("count_beep")           # "2", "1"
                cam.update(dt, player)
                sim.draw_world(screen, cam, cars)
                sim.draw_hud(screen, player, font_small, cars, hud_opacity=1.0)
                n = int(math.ceil(countdown))
                big = font_big.render(str(n), True, (255, 255, 255))
                screen.blit(big, big.get_rect(center=(sim.W / 2, sim.H / 2 - 20)))
                sim.draw_callout_banner(screen)
                sim.draw_letterbox(screen, letterbox_h)
            else:
                if not online and not FROZEN:   # hot reload: local single-player, source on disk
                    mtime = _safe_mtime(SIM_PATH)
                    if mtime and mtime != last_mtime:
                        last_mtime = mtime
                        reload_and_migrate()

                keys = pygame.key.get_pressed()
                steer = 0.0
                if keys[pygame.K_LEFT] or keys[keybinds.get("left", pygame.K_a)]:
                    steer -= 1
                if keys[pygame.K_RIGHT] or keys[keybinds.get("right", pygame.K_d)]:
                    steer += 1
                steer = max(-1.0, min(1.0, steer + pad_steer() + gyro_steer()))
                if sim.INVERT_STEER:
                    steer = -steer
                steer = sim.apply_steer_controls(steer)
                drift = keys[keybinds.get("drift", pygame.K_LSHIFT)] or pad_drift()
                brake = keys[keybinds.get("brake", pygame.K_s)] or pad_brake()
                if keys[keybinds.get("drop_hazard", pygame.K_v)] and action is None:
                    last_sab = getattr(player, "_last_sab", "oil")
                    action = "drop_cone" if last_sab == "oil" else "oil"
                    player._last_sab = "cone" if last_sab == "oil" else "oil"

                spectating = online and player.dead
                dt_sim = dt * 0.25 if slowmo_active else dt
                if slowmo_active:
                    slowmo_timer -= dt
                    if slowmo_timer <= 0.0:
                        slowmo_active = False

                if online and finish_pending and slowmo_timer <= 0.0:
                    profile["races"] = profile.get("races", 0) + 1
                    if final_order and final_order[0] is player:
                        profile["wins"] = profile.get("wins", 0) + 1
                    if player is not None and player.best_lap > 0 and (profile.get("best_lap", 0) <= 0 or player.best_lap < profile["best_lap"]):
                        profile["best_lap"] = player.best_lap
                    save_profile(profile)
                    net_disconnect()
                    state = "results"

                if spectating:
                    steer, action, drift, brake = 0.0, None, False, False

                if online:
                    # I drive my car; bots are mine too if I'm host; every other car is a
                    # remote puppet corrected from the net
                    controls = []
                    for c in cars:
                        if c is player:
                            controls.append((steer, action, drift, brake))
                        elif not c.is_remote:           # host-owned bot
                            controls.append(sim.bot_control(c, cars, dt_sim))
                        else:
                            controls.append((0, None, False, False))
                    sim.step(dt_sim, cars, controls)
                    lerp = min(1.0, 10.0 * dt_sim)
                    for slot, c in enumerate(cars):
                        if c.is_remote and slot in snap_by_slot:
                            sim.apply_net_state(c, snap_by_slot[slot], lerp)
                    # the host owns box pickups: broadcast each one it resolved this frame
                    if sim.NET_ROLE == "host" and sim.BOX_EVENTS and netc is not None:
                        for idx, slot, kind in sim.BOX_EVENTS:
                            netc.send({"t": "box", "i": idx, "slot": slot, "kind": kind})
                    sim.BOX_EVENTS.clear()
                    # broadcast my car (+ any bots I own) ~BCAST_HZ
                    bcast_t += dt
                    if bcast_t >= 1.0 / BCAST_HZ and netc is not None:
                        for slot, c in enumerate(cars):
                            if not c.is_remote:
                                netc.send({"t": "state", "slot": slot, "car": sim.car_net_state(c)})
                        bcast_t = 0.0
                    # host decides when the race is over -> tell everyone
                    if sim.NET_ROLE == "host" and not finish_pending:
                        alive = [c for c in cars if not c.dead]
                        done = any(sim.lap_of(c) >= sim.TOTAL_LAPS for c in cars)
                        if (done or len(alive) <= 1) and netc is not None:
                            order = sorted(range(len(cars)),
                                           key=lambda i: (cars[i].dead, -cars[i].progress))
                            netc.send({"t": "finished", "order": order})
                            apply_finished(order)
                else:
                    pc = (steer, action, drift, brake)
                    controls = [pc if c is player else sim.bot_control(c, cars, dt_sim) for c in cars]
                    sim.step(dt_sim, cars, controls)

                    # ---- single-player game-mode logic --------------------------------
                    if game_mode == "elim":         # cull the last-place living kart periodically
                        elim_timer += dt_sim
                        living = [c for c in cars if not c.dead]
                        if elim_timer >= ELIM_INTERVAL and len(living) > 1:
                            elim_timer = 0.0
                            loser = min(living, key=lambda c: c.progress)
                            loser.dead = True
                            if loser is not player:
                                popup = (f"{loser.name} - DNF (ELIMINATED)", (255, 150, 120), 2.0)
                            sim.play("eliminated")
                    if game_mode == "trial":        # record the ghost path; bank it on a new best lap
                        ghost_rec.append((player.x, player.y, player.angle))
                        if player.cur_lap > trial_lap:
                            if player.last_lap > 0 and (ghost_time <= 0 or player.last_lap <= ghost_time):
                                ghost_best, ghost_time = list(ghost_rec), player.last_lap
                            ghost_rec = []
                            trial_lap = player.cur_lap

                sim.update_banner(dt)

                # Callout banner triggers: TAKEDOWN! / WRECKED!
                for c in cars:
                    if c.dead and c not in reported_dead:
                        reported_dead.add(c)
                        if c is player:
                            sim.trigger_banner("DNF!", (255, 60, 60), sub="RETIRED - TOTAL VEHICLE LOSS", dur=2.0)
                        elif player is not None:
                            d_player = math.hypot(c.x - player.x, c.y - player.y)
                            if d_player < 180.0:
                                sim.trigger_banner("TAKEDOWN!", (255, 200, 40), sub=f"{c.name.upper()} - DNF (RETIRED)", dur=1.8)
                                sim.play("takedown")

                # Callout banner triggers: FINAL LAP!
                if player is not None and not final_lap_announced and sim.TOTAL_LAPS > 1:
                    if sim.lap_of(player) >= sim.TOTAL_LAPS - 1:
                        final_lap_announced = True
                        sim.trigger_banner("FINAL LAP!", (255, 75, 75), sub="DECIDING ROUND", dur=2.2)
                        sim.play("final_lap")

                # Immersive / Diegetic HUD Mode logic
                if hud_mode == "FULL":
                    hud_alpha = 1.0
                else:
                    cur_rank = 1
                    if player is not None:
                        order_now = sorted(cars, key=lambda c: (c.dead, -c.progress))
                        if player in order_now:
                            cur_rank = order_now.index(player) + 1
                    cur_lap = sim.lap_of(player) if player is not None else 0
                    cur_hearts = player.hearts if player is not None else 0

                    hud_changed = (cur_hearts != prev_player_hearts or
                                   cur_rank != prev_player_rank or
                                   cur_lap != prev_player_lap)
                    if hud_changed:
                        hud_reveal_timer = 2.8
                        prev_player_hearts = cur_hearts
                        prev_player_rank = cur_rank
                        prev_player_lap = cur_lap

                    near_danger = False
                    if player is not None and not player.dead:
                        if player.hearts <= 1 or getattr(player, "off_road", False):
                            near_danger = True
                        elif abs(getattr(cam, "trauma_x", 0.0)) > 3.0 or abs(getattr(cam, "trauma_y", 0.0)) > 3.0:
                            near_danger = True
                        else:
                            for other in cars:
                                if other is not player and not other.dead:
                                    if math.hypot(other.x - player.x, other.y - player.y) < 75.0:
                                        near_danger = True
                                        break

                    if hud_mode == "Hidden":
                        hud_alpha = 0.0
                    elif hud_mode == "Classic":
                        hud_alpha = 1.0
                    else: # Immersive
                        if near_danger or countdown > 0 or slowmo_active or spectating:
                            hud_target_alpha = 1.0
                        elif hud_reveal_timer > 0.0:
                            hud_reveal_timer -= dt
                            hud_target_alpha = 1.0
                        else:
                            hud_target_alpha = 0.0
                        hud_alpha += (hud_target_alpha - hud_alpha) * min(1.0, dt * 5.0)

                # camera follows the leader while spectating, else your own car
                cam_target = player
                if spectating:
                    live = [c for c in cars if not c.dead]
                    cam_target = max(live, key=lambda c: c.progress) if live else player
                cam.update(dt, cam_target)

                sim.draw_world(screen, cam, cars)
                # Time Trial ghost: replay your best lap by time index
                if game_mode == "trial" and ghost_best:
                    gi = min(len(ghost_best) - 1, len(ghost_rec))
                    gx, gy, ga = ghost_best[gi]
                    sim.draw_ghost(screen, cam, gx, gy, ga)
                if hud_alpha > 0.01:
                    sim.draw_hud(screen, player, font_small, cars, hud_opacity=hud_alpha)
                go_timer = max(0.0, go_timer - dt)
                if go_timer > 0:
                    go = font_big.render("GO!", True, (120, 255, 120))
                    screen.blit(go, go.get_rect(center=(sim.W / 2, sim.H / 2 - 20)))
                if spectating:
                    ov = font.render("DNF - RETIRED (SPECTATING)", True, (255, 120, 120))
                    screen.blit(ov, ov.get_rect(center=(sim.W / 2, 40)))

                # position-change popups (your rank in the live order)
                if not spectating:
                    order = sorted(cars, key=lambda c: (c.dead, -c.progress))
                    rank = order.index(player) + 1
                    prev = last_ranks.get("me", rank)
                    if rank < prev:
                        popup = (f"UP to P{rank}", (150, 255, 150), 1.5)
                        sim.play("pos_up")
                    elif rank > prev:
                        popup = (f"down to P{rank}", (255, 180, 120), 1.5)
                        sim.play("pos_down")
                    last_ranks["me"] = rank
                if popup:
                    txt, col, tleft = popup
                    tleft -= dt
                    popup = (txt, col, tleft) if tleft > 0 else None
                    if popup:
                        ps = font.render(txt, True, col)
                        screen.blit(ps, ps.get_rect(center=(sim.W / 2, 70)))

                sim.draw_callout_banner(screen)
                sim.draw_letterbox(screen, letterbox_h)

                # ---- single-player end conditions ---------------------------------
                if not online:
                    end = False
                    if game_mode == "trial":
                        if sim.lap_of(player) >= sim.TOTAL_LAPS:
                            end, end_title = True, "FINISH"
                    elif game_mode in ("battle", "elim"):
                        if len([c for c in cars if not c.dead]) <= 1:
                            end, end_title = True, ("BATTLE OVER" if game_mode == "battle" else "FINISH")
                    else:                       # race / team
                        if any(sim.lap_of(c) >= sim.TOTAL_LAPS for c in cars):
                            end, end_title = True, "FINISH"
                    if not end and player.dead and game_mode not in ("battle", "elim"):
                        end, end_title = True, "GAME OVER"
                    if end:
                        if not finish_pending:
                            finish_pending = True
                            slowmo_active = True
                            slowmo_timer = 1.5
                            target_letterbox_h = 48.0
                            if cam is not None:
                                cam.override_zoom = 1.55
                            sim.trigger_banner(end_title + "!", (255, 230, 70), sub="RACE COMPLETE" if end_title == "FINISH" else "", dur=2.0)
                            sim.play("game_over" if end_title == "GAME OVER" else "finish")
                        elif slowmo_timer <= 0.0:
                            final_order = sorted(cars, key=lambda c: (c.dead, -c.progress))
                            team_result = ""
                            if game_mode == "team":     # finishing-position points, lower = better
                                sc = {0: 0, 1: 0}
                                for pos, c in enumerate(final_order):
                                    if c.team in sc:
                                        sc[c.team] += pos + 1
                                win = "RED" if sc[0] < sc[1] else "BLUE" if sc[1] < sc[0] else "TIED"
                                team_result = (f"{win} TEAM WINS" if win != "TIED" else "TEAMS TIED") + \
                                    f"   (red {sc[0]} / blue {sc[1]}, lower is better)"
                            profile["races"] = profile.get("races", 0) + 1
                            if final_order and final_order[0] is player:
                                profile["wins"] = profile.get("wins", 0) + 1
                            if player.best_lap > 0 and (profile["best_lap"] <= 0
                                                        or player.best_lap < profile["best_lap"]):
                                profile["best_lap"] = player.best_lap
                            profile["name"], profile["flag"] = player_name, (
                                sim.FLAG_CODES[flag_idx] if sim.FLAG_CODES else "us")
                            save_profile(profile)
                            state = "results"

        elif state == "menu":
            draw_bg()
            ui.draw_menu(screen, [b_.label for _, b_ in menu_buttons], menu_sel, mouse_pos, **menu_extras())
            draw_social_brand_icons()

        elif state == "name_entry":
            draw_bg()
            title = font_big.render("STEER", True, (255, 255, 255))
            screen.blit(title, title.get_rect(center=(sim.W / 2, 44)))
            prompt = font_small.render("Enter your name:", True, (220, 230, 210))
            screen.blit(prompt, prompt.get_rect(center=(sim.W / 2, 96)))
            # text box with a blinking caret
            box = pygame.Rect(sim.W / 2 - 150, 112, 300, 40)
            pygame.draw.rect(screen, (20, 35, 20), box, border_radius=6)
            pygame.draw.rect(screen, (230, 230, 230), box, 2, border_radius=6)
            caret = "_" if (pygame.time.get_ticks() // 400) % 2 == 0 else " "
            shown = font.render(player_name + caret, True, (255, 255, 255))
            screen.blit(shown, shown.get_rect(midleft=(box.x + 12, box.centery)))
            # flag picker: < [flag] >  with the country code underneath
            flag_label = font_small.render("Choose your flag:", True, (220, 230, 210))
            screen.blit(flag_label, flag_label.get_rect(center=(sim.W / 2, 178)))
            if sim.FLAG_CODES:
                code = sim.FLAG_CODES[flag_idx]
                flag = sim.get_flag(code, 40)
                if flag:
                    fr = flag.get_rect(center=(sim.W / 2, 218))
                    screen.blit(flag, fr)
                    pygame.draw.rect(screen, (230, 230, 230), fr, 1)
                ctext = font_small.render(code.upper(), True, UI_ACCENT)
                screen.blit(ctext, ctext.get_rect(center=(sim.W / 2, 242)))
            flag_prev.draw(screen, font, flag_prev.clicked(mouse_pos))
            flag_next.draw(screen, font, flag_next.clicked(mouse_pos))
            start_btn.draw(screen, font, start_btn.clicked(mouse_pos))
            back_btn.draw(screen, font, back_btn.clicked(mouse_pos))
            left_icon = buttonmanager.get_key_icon('left')
            right_icon = buttonmanager.get_key_icon('right')
            enter_icon = buttonmanager.get_key_icon('enter')
            esc_icon = buttonmanager.get_key_icon('esc')
            if pads:
                pad_type = "xbox"
                try:
                    pname = list(pads.values())[0].get_name().lower()
                    if "playstation" in pname or "dual" in pname or "ps" in pname:
                        pad_type = "ps"
                    elif "switch" in pname or "nintendo" in pname or "joy-con" in pname:
                        pad_type = "nintendo"
                except Exception:
                    pad_type = "xbox"
                dpad_ic = buttonmanager.get_controller_icon(pad_type, "dpad", size=21)
                a_ic = buttonmanager.get_controller_icon(pad_type, "a" if pad_type != "ps" else "cross", size=21)
                b_ic = buttonmanager.get_controller_icon(pad_type, "b" if pad_type != "ps" else "circle", size=21)
                x_ic = buttonmanager.get_controller_icon(pad_type, "x" if pad_type != "ps" else "square", size=21)
                txt_flag = font_small.render("flag", True, (180, 200, 180))
                txt_name = font_small.render("name", True, (180, 200, 180))
                txt_race = font_small.render("race", True, (180, 200, 180))
                txt_back = font_small.render("back", True, (180, 200, 180))
                elements = []
                if dpad_ic: elements += [(dpad_ic, 6), (txt_flag, 18)]
                if x_ic: elements += [(x_ic, 6), (txt_name, 18)]
                if a_ic: elements += [(a_ic, 6), (txt_race, 18)]
                if b_ic: elements += [(b_ic, 6), (txt_back, 0)]
                tot_w = sum(it[0].get_width() + it[1] for it in elements)
                cur_x = (sim.W - tot_w) // 2
                cy_nav = sim.H - 24
                for item_surf, gap in elements:
                    screen.blit(item_surf, item_surf.get_rect(midleft=(cur_x, cy_nav)))
                    cur_x += item_surf.get_width() + gap
            elif left_icon and right_icon and enter_icon and esc_icon:
                txt_flag = font_small.render("flag", True, (180, 200, 180))
                txt_race = font_small.render("race", True, (180, 200, 180))
                txt_back = font_small.render("back", True, (180, 200, 180))
                elements = [
                    (left_icon, 6), (right_icon, 8), (txt_flag, 24),
                    (enter_icon, 8), (txt_race, 24),
                    (esc_icon, 8), (txt_back, 0)
                ]
                tot_w = sum(it[0].get_width() + it[1] for it in elements)
                cur_x = (sim.W - tot_w) // 2
                cy_nav = sim.H - 24
                for item_surf, gap in elements:
                    screen.blit(item_surf, item_surf.get_rect(midleft=(cur_x, cy_nav)))
                    cur_x += item_surf.get_width() + gap
            else:
                hint = font_small.render("Arrows: flag   Enter: race   Esc: back", True, (180, 200, 180))
                screen.blit(hint, hint.get_rect(center=(sim.W / 2, sim.H - 24)))

        elif state == "settings":
            draw_bg()
            screen.blit(_dim_more, (0, 0))
            if active_slider is not None:       # dragging: the knob follows the mouse
                tr = active_slider["track"]
                active_slider["set"](max(0.0, min(1.0, (mouse_pos[0] - tr.x) / tr.w)))
            rows = settings_rows(set_tab)
            set_sel = max(0, min(set_sel, len(rows) - 1))
            if pad_preset == "Trigger Drive":
                ctrl_pad = [("STEER", ["LS", "DPAD"]), ("GAS / ACCEL", ["RT"]), ("BRAKE", ["LT"]),
                            ("DRIFT", ["RB"]), ("BASH", ["L3", "R3"]), ("ITEM / SHOOT", ["X"]),
                            ("DROP HAZARD", ["Y"]), ("PAUSE", ["START"])]
            elif pad_preset == "Southpaw":
                ctrl_pad = [("STEER", ["RS"]), ("RAM / GAS", ["A"]), ("BRAKE", ["LT", "↓"]),
                            ("DRIFT", ["B"]), ("BASH L/R", ["LB", "RB"]), ("ITEM / SHOOT", ["X"]),
                            ("DROP HAZARD", ["Y"]), ("PAUSE", ["START"])]
            else:
                ctrl_pad = [("STEER", ["LS", "DPAD"]), ("RAM / GAS", ["A"]), ("BRAKE", ["LT", "↓"]),
                            ("DRIFT", ["B"]), ("BASH L/R", ["LB", "RB"]), ("ITEM / SHOOT", ["X"]),
                            ("DROP HAZARD", ["Y"]), ("PAUSE", ["START"])]
            ui.draw_settings(screen, SET_TABS, set_tab, settings_view(rows), set_sel, mouse_pos,
                             awaiting=awaiting_key, pad=bool(pads), pad_rows=ctrl_pad,
                             chip="PAUSED" if player is not None else None,
                             device_name=get_input_device_name())

        elif state == "results":
            if frame_state != "results":        # just arrived: replay the slide-in, Race Again first
                results_t, results_sel = 0.0, 0
            results_t += dt
            draw_bg()
            screen.blit(_dim_more, (0, 0))
            sub, foot, rows = results_text()
            ui.draw_results(screen, end_title, rows, t=results_t, sub=sub, chip="FINAL", footer=foot,
                            buttons=results_buttons(), sel=min(results_sel, len(results_buttons()) - 1),
                            mouse=mouse_pos, pad=bool(pads), status_col=game_mode in ("battle", "elim"))

        elif state == "mode":
            draw_bg()
            ui.draw_menu(screen, [b_.label for _, b_ in mode_buttons], mode_sel, mouse_pos,
                         **dict(menu_extras(), socials=()))

        elif state == "gamemode":
            draw_bg()
            title = font.render("CHOOSE MODE", True, (255, 255, 255))
            screen.blit(title, title.get_rect(center=(sim.W / 2, 56)))
            for i, (mk, btn) in enumerate(gamemode_buttons):
                btn.draw(screen, font_small, i == gamemode_sel)
            back_btn.draw(screen, font, gamemode_sel == len(gamemode_buttons))

        elif state == "mp_menu":
            draw_bg()
            title = font_big.render("MULTIPLAYER", True, (255, 255, 255))
            screen.blit(title, title.get_rect(center=(sim.W / 2, 50)))
            host_btn.draw(screen, font, mp_tab == "host")
            join_btn.draw(screen, font, mp_tab == "join")
            tabw = pygame.Rect(sim.W / 2 - 160 if mp_tab == "host" else sim.W / 2 + 10, 132, 150, 3)
            pygame.draw.rect(screen, UI_ACCENT, tabw)

            if mp_tab == "host":
                lbl = font_small.render(f"Lobby: {player_name.strip() or 'Player'}", True, (220, 230, 210))
                screen.blit(lbl, lbl.get_rect(center=(sim.W / 2, 150)))
                cap = font_small.render("Max players:", True, (220, 230, 210))
                screen.blit(cap, cap.get_rect(center=(sim.W / 2, 192)))
                num = font.render(str(mp_max), True, UI_ACCENT)
                screen.blit(num, num.get_rect(center=(sim.W / 2, 228)))
                minus_btn.rect.y = plus_btn.rect.y = 208
                minus_btn.draw(screen, font, minus_btn.clicked(mouse_pos))
                plus_btn.draw(screen, font, plus_btn.clicked(mouse_pos))
                create_btn.draw(screen, font, create_btn.clicked(mouse_pos))
            else:
                prompt = font_small.render("Enter 6-character code:", True, (220, 230, 210))
                screen.blit(prompt, prompt.get_rect(center=(sim.W / 2, 150)))
                box = pygame.Rect(sim.W / 2 - 150, 176, 300, 48)
                pygame.draw.rect(screen, (20, 35, 20), box, border_radius=6)
                pygame.draw.rect(screen, (230, 230, 230), box, 2, border_radius=6)
                caret = "_" if (pygame.time.get_ticks() // 400) % 2 == 0 else " "
                codetxt = font_big.render((join_code + caret), True, (255, 255, 255))
                screen.blit(codetxt, codetxt.get_rect(center=box.center))
                confirm_join_btn.draw(screen, font, confirm_join_btn.clicked(mouse_pos))

            back_btn.draw(screen, font, back_btn.clicked(mouse_pos))
            if net_msg:
                msg = font_small.render(net_msg, True, (240, 180, 120))
                screen.blit(msg, msg.get_rect(center=(sim.W / 2, sim.H - 24)))

        elif state == "lobby":
            draw_bg()
            title = font.render("LOBBY", True, (255, 255, 255))
            screen.blit(title, title.get_rect(center=(sim.W / 2, 26)))
            if lobby:
                i_am_host = lobby.get("host") == lobby.get("self")   # not "is_host": that would overwrite is_host()
                head = font_small.render(
                    f"{lobby.get('name','')}'s lobby    CODE: {lobby.get('code','')}"
                    f"    ({len(lobby.get('players', []))}/{lobby.get('max','?')})",
                    True, UI_ACCENT)
                screen.blit(head, head.get_rect(center=(sim.W / 2, 54)))

                # Players on left
                for i, p in enumerate(lobby.get("players", [])):
                    y = 86 + i * 28
                    x = 24
                    is_me = p["id"] == lobby.get("self")
                    fl = sim.get_flag(p.get("flag"), 14)
                    if fl:
                        screen.blit(fl, (x, y + 2))
                    nm = p["name"] + ("  (you)" if is_me else "") + ("  [host]" if p["id"] == lobby.get("host") else "")
                    nmcol = UI_ACCENT if is_me else (235, 235, 235)
                    screen.blit(font_small.render(nm, True, nmcol), (x + 24, y))
                    rtxt = "READY" if p["ready"] else "not ready"
                    rcol = (120, 230, 120) if p["ready"] else (200, 120, 120)
                    rsurf = font_small.render(rtxt, True, rcol)
                    screen.blit(rsurf, (x + 185, y))
                    if i_am_host and not is_me:
                        kr = pygame.Rect(256, y + 2, 20, 20)
                        pygame.draw.rect(screen, (170, 50, 50), kr, border_radius=4)
                        xk = font_credits.render("K", True, (255, 255, 255))
                        screen.blit(xk, xk.get_rect(center=kr.center))
                        br = pygame.Rect(280, y + 2, 20, 20)
                        pygame.draw.rect(screen, (120, 30, 30), br, border_radius=4)
                        xb = font_credits.render("B", True, (255, 255, 255))
                        screen.blit(xb, xb.get_rect(center=br.center))

                # Match settings on right
                panel = pygame.Rect(308, 66, 280, 268)
                pygame.draw.rect(screen, (20, 28, 24), panel, border_radius=6)
                pygame.draw.rect(screen, (55, 80, 65), panel, 1, border_radius=6)
                ps = font_credits.render("HOST MATCH RULES", True, UI_ACCENT)
                screen.blit(ps, ps.get_rect(center=(panel.centerx, 80)))

                t_lbl = sim.TILESET_TITLES.get(lobby_settings.get('track', 'meadow_dirt'), 'Meadow Dirt')
                host_track_btn.label = f"Track: {t_lbl}" + (" >" if i_am_host else "")
                host_rot_btn.label = f"Rotation: {lobby_settings.get('rotation', 'Host Choice')}" + (" >" if i_am_host else "")
                host_laps_btn.label = f"Laps: {lobby_settings.get('laps', 3)}" + (" >" if i_am_host else "")
                host_bots_btn.label = f"Bots: {lobby_settings.get('bot_count', 'Fill to 8')}" + (" >" if i_am_host else "")
                host_aggr_btn.label = f"AI Aggr: {lobby_settings.get('bot_aggression', 'Casual')}" + (" >" if i_am_host else "")
                host_coll_btn.label = f"Contact: {lobby_settings.get('collision', 'Full Contact')}" + (" >" if i_am_host else "")
                host_slip_btn.label = f"Slipstream: {lobby_settings.get('slipstream', 'ON')}" + (" >" if i_am_host else "")
                host_items_btn.label = f"Items: {lobby_settings.get('items', 'Standard')}" + (" >" if i_am_host else "")
                host_priv_btn.label = f"Privacy: {lobby_settings.get('privacy', 'Public')}" + (" >" if i_am_host else "")
                for btn in (host_track_btn, host_rot_btn, host_laps_btn, host_bots_btn, host_aggr_btn,
                            host_coll_btn, host_slip_btn, host_items_btn, host_priv_btn):
                    pygame.draw.rect(screen, (35, 50, 42), btn.rect, border_radius=4)
                    pygame.draw.rect(screen, (70, 100, 80), btn.rect, 1, border_radius=4)
                    btn.draw(screen, font_credits, i_am_host and btn.clicked(mouse_pos))

                hint_txt = "(Host click to cycle · K=Kick B=Ban)" if i_am_host else "(Host-controlled rules)"
                hint_s = font_credits.render(hint_txt, True, (150, 180, 160))
                screen.blit(hint_s, hint_s.get_rect(center=(panel.centerx, 320)))

                ready_btn.label = "Unready" if my_ready else "Ready"
                ready_btn.draw(screen, font_small, my_ready or ready_btn.clicked(mouse_pos))
                leave_btn.draw(screen, font_small, leave_btn.clicked(mouse_pos))
                tip = "All players ready -> race starts automatically"
                tip_s = font_credits.render(tip, True, (180, 200, 180))
                screen.blit(tip_s, tip_s.get_rect(center=(sim.W / 2, 392)))

        draw_connect_overlay()

        if show_fps:
            fps = font_small.render(f"{clock.get_fps():.0f} FPS", True, (255, 210, 70))
            screen.blit(fps, (6, 4))

        # engine / skid / gravel / boost loops follow your kart while you're actually driving
        driving = state == "playing" and countdown <= 0 and player is not None and not player.dead
        sim.update_loops(player if driving else None, dt)
        if state != "playing":
            sim.LISTENER = None

        pygame.display.flip()

    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()
