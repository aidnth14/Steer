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
    "left": pygame.K_a, "right": pygame.K_d, "bashL": pygame.K_q,
    "bashR": pygame.K_e, "ram": pygame.K_SPACE, "drift": pygame.K_LSHIFT,
    "shoot": pygame.K_f, "cone": pygame.K_c, "oil": pygame.K_v,
}
KEY_ACTIONS = [("left", "Steer left"), ("right", "Steer right"), ("bashL", "Bash left"),
               ("bashR", "Bash right"), ("ram", "Ram"), ("drift", "Drift"), ("shoot", "Shoot / Item"),
               ("cone", "Throw Cone"), ("oil", "Spill Oil")]

GAME_MODES = [("race", "Race"), ("trial", "Time Trial"), ("elim", "Elimination"),
              ("battle", "Battle"), ("team", "Team Race")]
ELIM_INTERVAL = 8.0     # seconds between eliminations in Elimination mode
TEAM_COLORS = [(230, 70, 70), (70, 120, 235)]   # red / blue teams
MENU_STATES = {"menu", "mode", "gamemode", "mp_menu",
               "settings", "name_entry", "results", "lobby"}

def load_profile():
    import json
    d = {"name": "Player", "flag": "us", "races": 0, "wins": 0,
         "best_lap": 0.0, "volume": 0.8, "laps": 3, "keys": {},
         "shaders": dict(sim.SHADER_SETTINGS),
         "bot_aggression": "Normal",
         "track_type": "meadow_dirt"}
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
    sim.set_sfx_volume(d.get("sfx_volume", d.get("volume", 0.8)))
    sim.set_music_volume(d.get("music_volume", 0.6))
    sim.set_steer_rate(d.get("steer_rate", sim.steer_rate_frac()))
    sim.set_drift_assist(d.get("drift_assist", sim.drift_assist_frac()))
    sim.set_shake_intensity(d.get("shake", sim.shake_intensity_frac()))
    sim.set_zoom(d.get("zoom", sim.zoom_frac()))
    sim.INVERT_STEER = bool(d.get("invert_steer", False))
    sim.set_master_mute(bool(d.get("mute", False)))
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
    "Shift or (B) or RT: drift     X: shoot     (Y): cone / item",
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
        # no background: just the label with a dark outline so it reads over anything
        col = UI_HIGHLIGHT if hover else (255, 255, 255)
        base = font.render(self.label, True, col)
        edge = font.render(self.label, True, (20, 20, 25))
        if self.align == "left":
            text_x = self.rect.x + (22 if UI_POINTER else 2)
            r = base.get_rect(midleft=(text_x, self.rect.centery))
            ptr_pos = (self.rect.x, self.rect.centery - (UI_POINTER.get_height() // 2 if UI_POINTER else 0))
        else:
            r = base.get_rect(center=self.rect.center)
            ptr_pos = (r.left - 20, self.rect.centery - (UI_POINTER.get_height() // 2 if UI_POINTER else 0))
        for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2), (-2, -2), (2, -2), (-2, 2), (2, 2)):
            screen.blit(edge, (r.x + dx, r.y + dy))
        screen.blit(base, r)
        if hover and UI_POINTER:
            screen.blit(UI_POINTER, ptr_pos)

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

    btn_size = 21  # Native 16x16 scaled up by 5px
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
    screen = pygame.display.set_mode((sim.W, sim.H))
    pygame.display.set_caption("Steer")

    def apply_display(fs):
        # windowed = fixed 600x400; fullscreen = SCALED so the logical surface upscales cleanly
        flags = (pygame.FULLSCREEN | pygame.SCALED) if fs else 0
        return pygame.display.set_mode((sim.W, sim.H), flags)
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

    def open_pad(device_index):
        if not sdlctrl.is_controller(device_index):
            return
        pad = sdlctrl.Controller(device_index)
        pads[pad.get_id()] = pad
        print("controller connected:", sdlctrl.name_forindex(device_index))

    for i in range(sdlctrl.get_count()):
        open_pad(i)

    def pad_steer():
        # left stick X plus the d-pad, summed across all pads, with a deadzone
        s = 0.0
        for pad in pads.values():
            try:
                s += pad.get_axis(PAD_STEER_AXIS) / 32768.0
                s -= 1 if pad.get_button(PAD_LEFT) else 0
                s += 1 if pad.get_button(PAD_RIGHT) else 0
            except pygame.error:
                pass
        if abs(s) < PAD_DEADZONE:
            return 0.0
        return max(-1.0, min(1.0, s))

    def pad_drift():
        for pad in pads.values():
            try:
                if pad.get_button(PAD_BACK):    # B / Circle held = drift
                    return True
                # RT / LT analog trigger pull (Xbox RT/LT, PS R2/L2, Nintendo ZR/ZL)
                rt = pad.get_axis(pygame.CONTROLLER_AXIS_TRIGGERRIGHT) / 32767.0
                lt = pad.get_axis(pygame.CONTROLLER_AXIS_TRIGGERLEFT) / 32767.0
                if rt > 0.3 or lt > 0.3:
                    return True
            except pygame.error:
                pass
        return False

    # Gyroscope / mobile device tilt detection for steering
    gyro_state = {
        "tilt": 0.0,
        "smooth_steer": 0.0,
        "source": "none",
        "active": False,
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
    GYRO_MAX_DEG = 25.0        # 25 degrees tilt = 100% full steering lock
    GYRO_SMOOTH = 0.25         # smoothing factor

    def gyro_steer():
        raw = 0.0
        if gyro_state["source"] == "web":
            try:
                import js
                deg = float(js.window._steer_tilt or 0.0)
                raw = max(-1.0, min(1.0, deg / GYRO_MAX_DEG))
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
                    raw = max(-1.0, min(1.0, (val[0] / 9.81) * 2.2))
            except Exception:
                pass

        # Allow programmatic / simulated tilt for tests and mobile companions
        sim_tilt = getattr(sim, "MOBILE_TILT", None)
        if sim_tilt is not None:
            raw = max(-1.0, min(1.0, sim_tilt))

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

    def draw_connect_overlay():
        # full-screen takeover while we're mid-connect, so a slow/cold-starting server reads
        # as "loading" rather than a frozen or broken menu
        if netc is None or lobby is not None:
            return
        screen.blit(_dim, (0, 0))
        cx, cy = sim.W / 2, sim.H / 2 - 10
        ang = (pygame.time.get_ticks() / 1000.0) * 4.0
        r = 22
        pygame.draw.arc(screen, UI_ACCENT, pygame.Rect(cx - r, cy - r, r * 2, r * 2), ang, ang + 4.0, 5)
        waking = netc.waking()
        title = font.render("Waking the server..." if waking else "Connecting...", True, (255, 255, 255))
        screen.blit(title, title.get_rect(center=(cx, cy + 62)))
        if waking:
            sub = font_small.render("First connect after idle can take up to ~30s", True, (200, 210, 195))
            screen.blit(sub, sub.get_rect(center=(cx, cy + 94)))
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
    fullscreen = bool(profile.get("fullscreen", False))
    show_fps = bool(profile.get("show_fps", False))
    if fullscreen:
        screen = apply_display(True)

    state = "menu"
    menu_sel = mode_sel = gamemode_sel = 0  # highlighted menu row for controller / keyboard nav
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
    ready_btn = Button((sim.W / 2 - 150, 290, 140, 36), "Ready")
    leave_btn = Button((sim.W / 2 + 10, 290, 140, 36), "Leave")
    host_aggr_btn = Button((336, 116, 228, 28), "")
    host_laps_btn = Button((336, 150, 228, 28), "")
    host_bots_btn = Button((336, 184, 228, 28), "")
    host_track_btn = Button((336, 218, 228, 28), "")
    lobby_settings = {"bot_aggression": "Normal", "laps": 3, "bot_count": "fill", "track": "meadow_dirt"}
    # general-tab sliders (left column): each a 0..1 value with a getter/setter + profile key
    SL_X, SL_W, SL_H = 24, 150, 8
    sliders = [
        {"label": "SFX",         "get": lambda: sim.SFX_VOLUME,   "set": sim.set_sfx_volume,    "key": "sfx_volume"},
        {"label": "Music",       "get": lambda: sim.MUSIC_VOLUME, "set": sim.set_music_volume,  "key": "music_volume"},
        {"label": "Fog",         "get": lambda: sim.FOG_DENSITY,  "set": sim.set_fog_density,   "key": "fog_density"},
        {"label": "Steering",    "get": sim.steer_rate_frac,      "set": sim.set_steer_rate,    "key": "steer_rate"},
        {"label": "Camera Zoom", "get": sim.zoom_frac,            "set": sim.set_zoom,          "key": "zoom"},
        {"label": "Drift Assist","get": sim.drift_assist_frac,    "set": sim.set_drift_assist,  "key": "drift_assist"},
        {"label": "Shake",       "get": sim.shake_intensity_frac, "set": sim.set_shake_intensity,"key": "shake"},
    ]
    for i, s in enumerate(sliders):
        s["track"] = pygame.Rect(SL_X, 74 + i * 30, SL_W, SL_H)
    active_slider = None        # the slider dict currently being dragged, or None
    # general-tab toggles (middle column)
    TGL_X = 210
    inv_btn = Button((TGL_X, 64, 170, 25), "")
    mute_btn = Button((TGL_X, 95, 170, 25), "")
    fs_btn = Button((TGL_X, 126, 170, 25), "")
    fps_btn = Button((TGL_X, 157, 170, 25), "")
    aggr_btn = Button((TGL_X, 188, 170, 25), "")
    laps_btn = Button((TGL_X, 219, 170, 25), "")
    hud_btn = Button((TGL_X, 250, 170, 25), "")
    track_btn = Button((TGL_X, 281, 170, 25), "")

    settings_tab = "general"
    shader_sel = 0
    tab_gen_btn = Button((sim.W / 2 - 160, 22, 150, 32), "GENERAL")
    tab_shd_btn = Button((sim.W / 2 + 10, 22, 150, 32), "SHADERS")
    shd_quick_btn = Button((sim.W / 2 + 10, 134, 150, 30), f"{sim.SHADER_SETTINGS['preset']} >")
    shd_row_btns = [
        Button((sim.W / 2 + 10, 74 + i * 38, 165, 32), "") for i in range(5)
    ]
    settings_back_btn = Button((sim.W // 2 - 80, 344, 160, 34), "Back")

    SHADER_DESCRIPTIONS = {
        "CINEMATIC": "Atmospheric mist + soft vignette corners",
        "SOFT MIST": "Gentle cool track fog layer",
        "RETRO CRT": "90s arcade scanlines + curved vignette",
        "FULL FX": "Combined fog + subtle scanlines + vignette",
        "OFF": "Clean raw pixels, no post-processing",
        "CUSTOM": "Customized shader parameters",
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

    settings_sel = 0

    def apply_setting_toggle(idx, d=1):
        nonlocal fullscreen, show_fps, hud_mode, screen
        if idx == 0:    # invert steer
            sim.INVERT_STEER = not sim.INVERT_STEER
            profile["invert_steer"] = sim.INVERT_STEER
        elif idx == 1:  # mute
            sim.set_master_mute(not sim.MASTER_MUTE)
            profile["mute"] = sim.MASTER_MUTE
        elif idx == 2:  # fullscreen
            fullscreen = not fullscreen
            screen = apply_display(fullscreen)
            profile["fullscreen"] = fullscreen
        elif idx == 3:  # fps
            show_fps = not show_fps
            profile["show_fps"] = show_fps
        elif idx == 4:  # bots
            levels = sim.BOT_AGGRESSION_LEVELS
            cur = sim.get_bot_aggression()
            i = levels.index(cur) if cur in levels else 1
            nxt = levels[(i + d) % len(levels)]
            sim.set_bot_aggression(nxt)
            profile["bot_aggression"] = nxt
        elif idx == 5:  # laps
            lopts = [3, 5, 7]
            cur = sim.TOTAL_LAPS
            i = lopts.index(cur) if cur in lopts else 0
            sim.TOTAL_LAPS = lopts[(i + d) % len(lopts)]
            profile["laps"] = sim.TOTAL_LAPS
        elif idx == 6:  # hud mode
            hud_mode = "IMMERSIVE" if hud_mode == "FULL" else "FULL"
            profile["hud_mode"] = hud_mode
        elif idx == 7:  # track type
            topts = ["meadow_dirt", "asphalt_circuit", "random"]
            cur = sim.get_track_type()
            i = topts.index(cur) if cur in topts else 0
            nxt = topts[(i + d) % len(topts)]
            sim.set_track_type(nxt)
            profile["track_type"] = nxt
        save_profile(profile)
        sim.play_ui("ui_click")

    cars, player, cam = [], None, None
    attract_cars, attract_cam = [], None    # live bots racing behind the menu
    final_order = []        # frozen leaderboard shown on the results screen
    last_mtime = os.path.getmtime(SIM_PATH)
    main_mtime = os.path.getmtime(MAIN_PATH)

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
        nonlocal prev_player_hearts, prev_player_rank, prev_player_lap
        sim.NET_ROLE = "off"
        online = False
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
        nonlocal prev_player_hearts, prev_player_rank, prev_player_lap
        mp_players = start_msg["players"]
        current_seed = start_msg["seed"]
        st = start_msg.get("settings") or (lobby.get("settings") if lobby else {}) or {}
        tr_type = st.get("track", "meadow_dirt")
        sim.new_map(current_seed, tileset=tr_type)
        track_title = sim.get_tileset_title(sim.CURRENT_TILESET)
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
    while running:
        dt = min(clock.tick(60) / 1000.0, 1 / 30)   # clamp so a freeze/stall can't teleport the car
        mouse_pos = pygame.mouse.get_pos()
        sim.SFX_MUTED = state != "playing"   # menus + attract-mode race run silent
        frame_state = state                  # to hear pause / resume once events are handled

        # hot reload: main.py edits restart the process; sim.py edits reload live. In a race,
        # sim.py is handled below (state carries over); everywhere else, reload it in place so
        # menu / HUD draw-code changes show without a restart.
        try:
            mm, sm = os.path.getmtime(MAIN_PATH), os.path.getmtime(SIM_PATH)
        except OSError:
            mm, sm = main_mtime, last_mtime
        if mm != main_mtime:
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
        bh = 32
        y0 = sim.H - 18 - bh * len(items)
        menu_buttons = [(nm, Button((18, y0 + i * bh, 200, bh), lbl, align="left"))
                        for i, (nm, lbl) in enumerate(items)]
        menu_sel = max(0, min(menu_sel, len(menu_buttons) - 1))

        # mode screen (Singleplayer / Multiplayer / Back), same bottom-left stack
        mode_items = [("single", "Singleplayer"), ("multi", "Multiplayer"), ("back", "Back")]
        mode_y0 = sim.H - 18 - bh * len(mode_items)
        mode_buttons = [(nm, Button((18, mode_y0 + i * bh, 220, bh), lbl, align="left"))
                        for i, (nm, lbl) in enumerate(mode_items)]
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
            if any(sb["rect"].collidepoint(mouse_pos) for sb in social_buttons):
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

        # menu sounds: a tick whenever the highlighted button changes (mouse or keys)
        cur_sel = (state, menu_sel, mode_sel, gamemode_sel, settings_sel)
        if state in MENU_STATES and last_sel is not None and last_sel[0] == state and cur_sel != last_sel:
            sim.play_ui("ui_move")
        last_sel = cur_sel

        action = None   # the player's bash this frame, if any
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == sim.MUSIC_END:
                sim.next_track()
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
                    if event.key == pygame.K_TAB:
                        settings_tab = "shaders" if settings_tab == "general" else "general"
                    elif event.key == pygame.K_ESCAPE:
                        save_profile(profile)
                        state = "menu"
                    elif settings_tab == "shaders":
                        if event.key in (pygame.K_DOWN, pygame.K_s):
                            shader_sel = (shader_sel + 1) % 6
                        elif event.key in (pygame.K_UP, pygame.K_w):
                            shader_sel = (shader_sel - 1) % 6
                        elif event.key in (pygame.K_LEFT, pygame.K_a):
                            if shader_sel < 5:
                                cycle_shader_option(shader_sel, -1)
                                profile["shaders"] = dict(sim.SHADER_SETTINGS)
                                save_profile(profile)
                        elif event.key in (pygame.K_RIGHT, pygame.K_d):
                            if shader_sel < 5:
                                cycle_shader_option(shader_sel, 1)
                                profile["shaders"] = dict(sim.SHADER_SETTINGS)
                                save_profile(profile)
                        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                            if shader_sel == 5:
                                save_profile(profile)
                                state = "menu"
                            else:
                                cycle_shader_option(shader_sel, 1)
                                profile["shaders"] = dict(sim.SHADER_SETTINGS)
                                save_profile(profile)
                elif event.key == pygame.K_ESCAPE and state == "results":
                    player = None
                    state = "menu"
                elif event.key == pygame.K_ESCAPE and state == "lobby":
                    net_disconnect()
                    state = "mp_menu"
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if state in MENU_STATES:
                    sim.play_ui("ui_click")
                if state == "menu":
                    opened_social = False
                    for sb in social_buttons:
                        if sb["rect"].collidepoint(mouse_pos):
                            try:
                                webbrowser.open(sb["url"])
                            except Exception as e:
                                print("failed to open social link:", e)
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
                        if host_aggr_btn.clicked(mouse_pos):
                            levels = sim.BOT_AGGRESSION_LEVELS
                            cur = lobby_settings.get("bot_aggression", "Normal")
                            idx = levels.index(cur) if cur in levels else 1
                            lobby_settings["bot_aggression"] = levels[(idx + 1) % len(levels)]
                            if netc is not None:
                                netc.send({"t": "settings", "settings": lobby_settings})
                        elif host_laps_btn.clicked(mouse_pos):
                            lopts = [1, 3, 5, 7]
                            cur = int(lobby_settings.get("laps", 3))
                            idx = lopts.index(cur) if cur in lopts else 1
                            lobby_settings["laps"] = lopts[(idx + 1) % len(lopts)]
                            if netc is not None:
                                netc.send({"t": "settings", "settings": lobby_settings})
                        elif host_bots_btn.clicked(mouse_pos):
                            bopts = ["fill", "4", "2", "none"]
                            cur = str(lobby_settings.get("bot_count", "fill")).lower()
                            idx = bopts.index(cur) if cur in bopts else 0
                            lobby_settings["bot_count"] = bopts[(idx + 1) % len(bopts)]
                            if netc is not None:
                                netc.send({"t": "settings", "settings": lobby_settings})
                        elif host_track_btn.clicked(mouse_pos):
                            topts = ["meadow_dirt", "asphalt_circuit"]
                            cur = lobby_settings.get("track", "meadow_dirt")
                            idx = topts.index(cur) if cur in topts else 0
                            lobby_settings["track"] = topts[(idx + 1) % len(topts)]
                            if netc is not None:
                                netc.send({"t": "settings", "settings": lobby_settings})
                        else:
                            for i, p in enumerate(lobby.get("players", [])):
                                if p["id"] == lobby.get("self"):
                                    continue
                                kr = pygame.Rect(265, 88 + i * 28, 20, 20)
                                if kr.collidepoint(mouse_pos):
                                    netc.send({"t": "kick", "id": p["id"]})
                                    break
                elif state == "settings":
                    if settings_back_btn.clicked(mouse_pos) or back_btn.clicked(mouse_pos):
                        save_profile(profile)
                        state = "menu"
                    elif inv_btn.clicked(mouse_pos):
                        sim.INVERT_STEER = not sim.INVERT_STEER
                        profile["invert_steer"] = sim.INVERT_STEER
                        save_profile(profile)
                    elif mute_btn.clicked(mouse_pos):
                        sim.set_master_mute(not sim.MASTER_MUTE)
                        profile["mute"] = sim.MASTER_MUTE
                        save_profile(profile)
                    elif fs_btn.clicked(mouse_pos):
                        fullscreen = not fullscreen
                        screen = apply_display(fullscreen)
                        profile["fullscreen"] = fullscreen
                        save_profile(profile)
                    elif fps_btn.clicked(mouse_pos):
                        show_fps = not show_fps
                        profile["show_fps"] = show_fps
                        save_profile(profile)
                    elif aggr_btn.clicked(mouse_pos):
                        levels = sim.BOT_AGGRESSION_LEVELS
                        cur = sim.get_bot_aggression()
                        idx = levels.index(cur) if cur in levels else 1
                        nxt = levels[(idx + 1) % len(levels)]
                        sim.set_bot_aggression(nxt)
                        profile["bot_aggression"] = nxt
                        save_profile(profile)
                    elif laps_btn.clicked(mouse_pos):
                        lopts = [3, 5, 7]
                        cur = sim.TOTAL_LAPS
                        idx = lopts.index(cur) if cur in lopts else 0
                        sim.TOTAL_LAPS = lopts[(idx + 1) % len(lopts)]
                        profile["laps"] = sim.TOTAL_LAPS
                        save_profile(profile)
                    elif hud_btn.clicked(mouse_pos):
                        hud_mode = "IMMERSIVE" if hud_mode == "FULL" else "FULL"
                        profile["hud_mode"] = hud_mode
                        save_profile(profile)
                    elif track_btn.clicked(mouse_pos):
                        apply_setting_toggle(7, 1)
                    elif any(s["track"].inflate(12, 12).collidepoint(mouse_pos) for s in sliders):
                        active_slider = next(s for s in sliders
                                             if s["track"].inflate(12, 12).collidepoint(mouse_pos))
                    else:
                        for i, (ak, _) in enumerate(KEY_ACTIONS):
                            rr = pygame.Rect(400, 78 + i * 25, sim.W - 416, 24)
                            if rr.collidepoint(mouse_pos):
                                awaiting_key = ak
                                break
                elif state == "results":
                    if back_btn.clicked(mouse_pos):
                        player = None
                        back_btn.rect = pygame.Rect(sim.W / 2 - 100, 306, 200, 44)
                        state = "menu"
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if active_slider is not None:
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
                    if b in (PAD_BASH_L, PAD_BASH_R):
                        if settings_sel < 7:
                            settings_sel += 7
                        elif settings_sel < 15:
                            settings_sel -= 7
                        sim.play_ui("ui_move")
                    elif b == PAD_DOWN:
                        settings_sel = (settings_sel + 1) % 16
                    elif b == PAD_UP:
                        settings_sel = (settings_sel - 1) % 16
                    elif b == PAD_LEFT:
                        if settings_sel < 7:
                            s = sliders[settings_sel]
                            s["set"](max(0.0, s["get"]() - 0.05))
                            profile[s["key"]] = round(s["get"](), 3)
                            save_profile(profile)
                            sim.play_ui("ui_move")
                        elif 7 <= settings_sel < 15:
                            apply_setting_toggle(settings_sel - 7, -1)
                    elif b == PAD_RIGHT:
                        if settings_sel < 7:
                            s = sliders[settings_sel]
                            s["set"](min(1.0, s["get"]() + 0.05))
                            profile[s["key"]] = round(s["get"](), 3)
                            save_profile(profile)
                            sim.play_ui("ui_move")
                        elif 7 <= settings_sel < 15:
                            apply_setting_toggle(settings_sel - 7, 1)
                    elif b == PAD_CONFIRM:
                        if settings_sel < 7:
                            sim.play_ui("ui_click")
                        elif 7 <= settings_sel < 15:
                            apply_setting_toggle(settings_sel - 7, 1)
                        elif settings_sel == 15:
                            save_profile(profile)
                            state = "menu"
                    elif b == PAD_BACK:
                        save_profile(profile)
                        state = "menu"
                elif state == "results":
                    if b == PAD_CONFIRM:
                        if not online:
                            start_game()
                        else:
                            player = None
                            back_btn.rect = pygame.Rect(sim.W / 2 - 100, 306, 200, 44)
                            state = "menu"
                    elif b == PAD_ITEM:
                        if not online:
                            sim.new_map(random.randint(0, 1_000_000))
                            start_game()
                    elif b == PAD_BACK:
                        player = None
                        back_btn.rect = pygame.Rect(sim.W / 2 - 100, 306, 200, 44)
                        state = "menu"

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
                if not online:      # hot reload only makes sense for the local single-player sim
                    mtime = os.path.getmtime(SIM_PATH)
                    if mtime != last_mtime:
                        last_mtime = mtime
                        reload_and_migrate()

                keys = pygame.key.get_pressed()
                steer = 0.0
                if keys[pygame.K_LEFT] or keys[keybinds["left"]]:
                    steer -= 1
                if keys[pygame.K_RIGHT] or keys[keybinds["right"]]:
                    steer += 1
                steer = max(-1.0, min(1.0, steer + pad_steer() + gyro_steer()))
                if sim.INVERT_STEER:
                    steer = -steer
                drift = keys[keybinds["drift"]] or pad_drift()

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
                    steer, action, drift = 0.0, None, False

                if online:
                    # I drive my car; bots are mine too if I'm host; every other car is a
                    # remote puppet corrected from the net
                    controls = []
                    for c in cars:
                        if c is player:
                            controls.append((steer, action, drift))
                        elif not c.is_remote:           # host-owned bot
                            controls.append(sim.bot_control(c, cars, dt_sim))
                        else:
                            controls.append((0, None))
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
                    pc = (steer, action, drift)
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
            draw_logo()
            for i, (_, btn) in enumerate(menu_buttons):
                btn.draw(screen, font_btn, btn.clicked(mouse_pos) or i == menu_sel)
            credit_txt = "made by @AidenShoroz v.1.2.0"
            cred_edge = font_credits.render(credit_txt, True, (20, 20, 25))
            cred_base = font_credits.render(credit_txt, True, (255, 255, 255))
            cr = cred_base.get_rect(bottomright=(sim.W - 14, sim.H - 12))

            # Social buttons: itch.io, youtube, instagram, discord before the credit
            gap = 10
            btn_w = 21
            total_btn_w = len(social_buttons) * btn_w + max(0, len(social_buttons) - 1) * gap
            start_x = cr.left - 18 - total_btn_w

            hovered_tip = None
            hovered_btn_rect = None
            try:
                mouse_down = pygame.mouse.get_pressed()[0]
            except Exception:
                mouse_down = False

            for i, sb in enumerate(social_buttons):
                sb["rect"].topleft = (start_x + i * (btn_w + gap), cr.centery - (btn_w // 2))
                is_hover = sb["rect"].collidepoint(mouse_pos)
                if is_hover:
                    hovered_tip = sb["tooltip"]
                    hovered_btn_rect = sb["rect"]
                spr = sb["pressed"] if (is_hover and mouse_down) else (sb["hover"] if is_hover else sb["idle"])
                screen.blit(spr, sb["rect"].topleft)

            if hovered_tip and hovered_btn_rect:
                tip_edge = font_credits.render(hovered_tip, True, (20, 20, 25))
                tip_base = font_credits.render(hovered_tip, True, (255, 235, 120))
                tr = tip_base.get_rect(midbottom=(hovered_btn_rect.centerx, hovered_btn_rect.top - 4))
                for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    screen.blit(tip_edge, (tr.x + dx, tr.y + dy))
                screen.blit(tip_base, tr)

            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (1, 1)):
                screen.blit(cred_edge, (cr.x + dx, cr.y + dy))
            screen.blit(cred_base, cr)

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
            title = font_big.render("SETTINGS", True, (255, 255, 255))
            screen.blit(title, title.get_rect(center=(sim.W / 2, 40)))
            # left column: sliders (SFX / Music / Fog / Steering)
            if active_slider is not None:
                v = (mouse_pos[0] - active_slider["track"].x) / active_slider["track"].w
                active_slider["set"](max(0.0, min(1.0, v)))
            for i, s in enumerate(sliders):
                tr = s["track"]
                screen.blit(font_small.render(s["label"], True, (220, 230, 210)),
                            (tr.x, tr.y - 16))
                pygame.draw.rect(screen, (40, 55, 40), tr, border_radius=4)
                frac = max(0.0, min(1.0, s["get"]()))
                fillw = int(tr.w * frac)
                pygame.draw.rect(screen, UI_ACCENT, (tr.x, tr.y, fillw, tr.h), border_radius=4)
                pygame.draw.circle(screen, (255, 255, 255), (tr.x + fillw, tr.centery), 7)
                pygame.draw.circle(screen, (30, 30, 35), (tr.x + fillw, tr.centery), 7, 1)
                if pads and settings_sel == i:
                    pygame.draw.rect(screen, (255, 230, 70), tr.inflate(12, 10), 2, border_radius=6)
            # middle column: toggles (ON/OFF buttons)
            inv_btn.label = f"Inverted Steer: {'ON' if sim.INVERT_STEER else 'OFF'}"
            mute_btn.label = f"Master Mute: {'ON' if sim.MASTER_MUTE else 'OFF'}"
            fs_btn.label = f"Fullscreen: {'ON' if fullscreen else 'OFF'}"
            fps_btn.label = f"FPS Counter: {'ON' if show_fps else 'OFF'}"
            aggr_btn.label = f"Bots: {sim.get_bot_aggression()} >"
            laps_btn.label = f"Laps: {sim.TOTAL_LAPS} >"
            hud_btn.label = f"HUD: {hud_mode}"
            track_btn.label = f"Track: {sim.get_tileset_title()} >"
            tgl_list = [(inv_btn, sim.INVERT_STEER, 7), (mute_btn, sim.MASTER_MUTE, 8),
                        (fs_btn, fullscreen, 9), (fps_btn, show_fps, 10),
                        (aggr_btn, False, 11), (laps_btn, False, 12),
                        (hud_btn, hud_mode == "IMMERSIVE", 13),
                        (track_btn, False, 14)]
            for btn, on, s_idx in tgl_list:
                is_sel = (pads and settings_sel == s_idx)
                btn.draw(screen, font_small, btn.clicked(mouse_pos) or on or is_sel)
                if is_sel:
                    pygame.draw.rect(screen, (255, 230, 70), btn.rect.inflate(6, 6), 2, border_radius=4)
            # right column: controls (click a row, then press a key)
            cx = 400
            screen.blit(font_small.render("Controls (click, then a key):", True,
                                          (200, 220, 200)), (cx, 56))
            for i, (ak, albl) in enumerate(KEY_ACTIONS):
                y = 78 + i * 25
                binding = "press a key..." if awaiting_key == ak else pygame.key.name(keybinds[ak])
                col = UI_ACCENT if awaiting_key == ak else (230, 230, 230)
                screen.blit(font_small.render(albl, True, (210, 220, 210)), (cx, y))
                if awaiting_key == ak:
                    b = font_small.render(binding, True, col)
                    screen.blit(b, b.get_rect(midright=(sim.W - 16, y + 11)))
                else:
                    k_icon = buttonmanager.get_key_icon(keybinds[ak], size=21)
                    if k_icon:
                        screen.blit(k_icon, k_icon.get_rect(midright=(sim.W - 20, y + 11)))
                    else:
                        b = font_small.render(binding, True, col)
                        screen.blit(b, b.get_rect(midright=(sim.W - 16, y + 11)))

            # Gamepad controls reference
            gy = 78 + len(KEY_ACTIONS) * 25 + 12
            pad_type = "xbox"
            if pads:
                try:
                    pname = list(pads.values())[0].get_name().lower()
                    if "playstation" in pname or "dual" in pname or "ps" in pname:
                        pad_type = "ps"
                    elif "switch" in pname or "nintendo" in pname or "joy-con" in pname:
                        pad_type = "nintendo"
                except Exception:
                    pad_type = "xbox"

            pad_title = f"Gamepad ({pad_type.capitalize()}):" if pads else "Gamepad (Xbox):"
            screen.blit(font_credits.render(pad_title, True, (190, 210, 195)), (cx, gy))
            pad_mappings = [
                ("Steer", "dpad"),
                ("Side-Bash", "lb" if pad_type != "ps" else "l1"),
                ("Ram", "a" if pad_type != "ps" else "cross"),
                ("Drift (hold)", "b" if pad_type != "ps" else "circle"),
                ("Shoot", "x" if pad_type != "ps" else "square"),
                ("Cone / Item", "y" if pad_type != "ps" else "triangle"),
            ]
            for j, (plbl, pbname) in enumerate(pad_mappings):
                py_pos = gy + 18 + j * 23
                screen.blit(font_credits.render(plbl, True, (165, 180, 170)), (cx, py_pos))
                p_icon = buttonmanager.get_controller_icon(pad_type, pbname, size=21)
                if p_icon:
                    screen.blit(p_icon, p_icon.get_rect(midright=(sim.W - 20, py_pos + 8)))
            back_is_sel = (pads and settings_sel == 15)
            settings_back_btn.draw(screen, font, settings_back_btn.clicked(mouse_pos) or back_is_sel)
            if back_is_sel:
                pygame.draw.rect(screen, (255, 230, 70), settings_back_btn.rect.inflate(8, 8), 2, border_radius=6)

        elif state == "results":
            draw_bg()
            draw_masters_scoreboard(screen, final_order, player, game_mode, team_result, end_title)
            n_rows = min(8, len(final_order)) if final_order else 5
            bh = 36 + 18 + n_rows * 21 + 8
            back_btn.rect = pygame.Rect(sim.W // 2 - 80, 20 + bh + 14, 160, 36)
            back_btn.draw(screen, font, back_btn.clicked(mouse_pos))
            if pads:
                hint_txt = "(A) Play Again     (Y) Next Track     (B) Menu"
                pad_hint = font_credits.render(hint_txt, True, (255, 235, 120))
                screen.blit(pad_hint, pad_hint.get_rect(center=(sim.W // 2, 20 + bh + 62)))

        elif state == "mode":
            draw_bg()
            draw_logo()
            for i, (_, btn) in enumerate(mode_buttons):
                btn.draw(screen, font_btn, i == mode_sel)

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
                        kr = pygame.Rect(265, y + 2, 20, 20)
                        pygame.draw.rect(screen, (150, 50, 50), kr, border_radius=4)
                        xk = font_small.render("x", True, (255, 255, 255))
                        screen.blit(xk, xk.get_rect(center=kr.center))

                # Match settings on right
                panel = pygame.Rect(324, 74, 252, 204)
                pygame.draw.rect(screen, (20, 28, 24), panel, border_radius=6)
                pygame.draw.rect(screen, (55, 80, 65), panel, 1, border_radius=6)
                ps = font_small.render("MATCH SETTINGS", True, UI_ACCENT)
                screen.blit(ps, ps.get_rect(center=(panel.centerx, 96)))

                host_aggr_btn.label = f"Bots: {lobby_settings.get('bot_aggression', 'Normal')}" + (" >" if i_am_host else "")
                host_laps_btn.label = f"Laps: {lobby_settings.get('laps', 3)}" + (" >" if i_am_host else "")
                host_bots_btn.label = f"Grid AI: {str(lobby_settings.get('bot_count', 'fill')).capitalize()}" + (" >" if i_am_host else "")
                t_lbl = sim.TILESET_TITLES.get(lobby_settings.get('track', 'meadow_dirt'), 'Meadow Dirt')
                host_track_btn.label = f"Track: {t_lbl}" + (" >" if i_am_host else "")
                for btn in (host_aggr_btn, host_laps_btn, host_bots_btn, host_track_btn):
                    pygame.draw.rect(screen, (35, 50, 42), btn.rect, border_radius=4)
                    pygame.draw.rect(screen, (70, 100, 80), btn.rect, 1, border_radius=4)
                    btn.draw(screen, font_credits, i_am_host and btn.clicked(mouse_pos))

                hint_txt = "(Host can click to change)" if i_am_host else "(Host-controlled rules)"
                hint_s = font_credits.render(hint_txt, True, (150, 180, 160))
                screen.blit(hint_s, hint_s.get_rect(center=(panel.centerx, 260)))

                ready_btn.label = "Unready" if my_ready else "Ready"
                ready_btn.draw(screen, font_small, my_ready or ready_btn.clicked(mouse_pos))
                leave_btn.draw(screen, font_small, leave_btn.clicked(mouse_pos))
                tip = "All players ready -> race starts automatically"
                tip_s = font_credits.render(tip, True, (180, 200, 180))
                screen.blit(tip_s, tip_s.get_rect(center=(sim.W / 2, 350)))

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
