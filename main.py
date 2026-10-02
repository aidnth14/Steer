import math
import os
import random
import sys
import pygame
from pygame._sdl2 import controller as sdlctrl

import sim
import net

# gamepad: SDL's game-controller layer maps Xbox / PlayStation / Nintendo pads to one
# standard layout (A = bottom face button, LB/RB = shoulders, etc.), so one mapping works
# for all three. Buttons/axes are the pygame CONTROLLER_* constants.
PAD_DEADZONE = 0.35
PAD_STEER_AXIS = pygame.CONTROLLER_AXIS_LEFTX
PAD_BASH_L = pygame.CONTROLLER_BUTTON_LEFTSHOULDER    # LB / L1 / L
PAD_BASH_R = pygame.CONTROLLER_BUTTON_RIGHTSHOULDER   # RB / R1 / R
PAD_RAM = pygame.CONTROLLER_BUTTON_A                  # A / Cross / B(south)
PAD_PAUSE = pygame.CONTROLLER_BUTTON_START
PAD_CONFIRM = pygame.CONTROLLER_BUTTON_A
PAD_BACK = pygame.CONTROLLER_BUTTON_B
PAD_UP = pygame.CONTROLLER_BUTTON_DPAD_UP
PAD_DOWN = pygame.CONTROLLER_BUTTON_DPAD_DOWN
PAD_LEFT = pygame.CONTROLLER_BUTTON_DPAD_LEFT
PAD_RIGHT = pygame.CONTROLLER_BUTTON_DPAD_RIGHT

SIM_PATH = os.path.join(os.path.dirname(__file__), "sim.py")
PROFILE_PATH = os.path.join(os.path.expanduser("~"), ".steer_profile.json")

# rebindable keyboard actions (defaults); stored per-user in the profile
DEFAULT_KEYS = {
    "left": pygame.K_a, "right": pygame.K_d, "bashL": pygame.K_q,
    "bashR": pygame.K_e, "ram": pygame.K_SPACE, "drift": pygame.K_LSHIFT,
}
KEY_ACTIONS = [("left", "Steer left"), ("right", "Steer right"), ("bashL", "Bash left"),
               ("bashR", "Bash right"), ("ram", "Ram"), ("drift", "Drift")]

GAME_MODES = [("race", "Race"), ("trial", "Time Trial"), ("elim", "Elimination"),
              ("battle", "Battle"), ("team", "Team Race")]
ELIM_INTERVAL = 8.0     # seconds between eliminations in Elimination mode
TEAM_COLORS = [(230, 70, 70), (70, 120, 235)]   # red / blue teams

def load_profile():
    import json
    d = {"name": "Player", "flag": "us", "races": 0, "wins": 0,
         "best_lap": 0.0, "volume": 0.8, "laps": 3, "keys": {}}
    try:
        with open(PROFILE_PATH) as f:
            d.update(json.load(f))
    except (OSError, ValueError):
        pass
    return d

def save_profile(d):
    import json
    try:
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
    "Shift or (B): drift (charge a mini-boost)",
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

class Button:
    def __init__(self, rect, label, align="center"):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.align = align

    def draw(self, screen, font, hover):
        # no background: just the label with a dark outline so it reads over anything
        col = (255, 235, 120) if hover else (255, 255, 255)
        base = font.render(self.label, True, col)
        edge = font.render(self.label, True, (20, 20, 25))
        if self.align == "left":
            r = base.get_rect(midleft=(self.rect.x + 2, self.rect.centery))
        else:
            r = base.get_rect(center=self.rect.center)
        for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2), (-2, -2), (2, -2), (-2, 2), (2, 2)):
            screen.blit(edge, (r.x + dx, r.y + dy))
        screen.blit(base, r)

    def clicked(self, pos):
        return self.rect.collidepoint(pos)

def main():
    pygame.init()
    screen = pygame.display.set_mode((sim.W, sim.H))
    pygame.display.set_caption("Steer")
    clock = pygame.time.Clock()
    sim.load_assets()

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
            except pygame.error:
                pass
        return False

    font_big = sim.get_font(64)
    font = sim.get_font(40)
    font_small = sim.get_font(26)

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

    def draw_bg():
        if menu_bg is not None:
            screen.blit(menu_bg, (0, 0))
        else:
            screen.fill((30, 60, 30))

    # STEER logo for the top-left of the menu / mode screens
    try:
        _logo = pygame.image.load(os.path.join(sim.UI_DIR, "logo.png")).convert_alpha()
        lh = 68
        logo = pygame.transform.scale(_logo, (round(_logo.get_width() * lh / _logo.get_height()), lh))
    except (pygame.error, FileNotFoundError):
        logo = None

    def draw_logo():
        if logo is not None:
            screen.blit(logo, (16, 12))
        else:
            screen.blit(font_big.render("STEER", True, (255, 255, 255)), (16, 12))

    profile = load_profile()
    keybinds = dict(DEFAULT_KEYS)
    keybinds.update({k: int(v) for k, v in profile.get("keys", {}).items() if k in DEFAULT_KEYS})
    sim.set_master_volume(profile.get("volume", 0.8))
    sim.TOTAL_LAPS = int(profile.get("laps", 3))

    state = "menu"
    menu_sel = 0                # highlighted menu row for controller / keyboard nav
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
    vol_dragging = False

    # multiplayer state
    online = False              # True once a networked race is running
    netc = None                 # net.Net while hosting/joined
    lobby = None                # latest room dict from the server
    mp_max = 4                  # host's chosen player cap
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

    back_btn = Button((sim.W / 2 - 100, 306, 200, 44), "Back")
    start_btn = Button((sim.W / 2 - 100, 256, 200, 42), "Start Race")
    flag_prev = Button((sim.W / 2 - 120, 198, 40, 40), "<")
    flag_next = Button((sim.W / 2 + 80, 198, 40, 40), ">")
    host_btn = Button((sim.W / 2 - 110, 120, 220, 48), "Host Game")
    join_btn = Button((sim.W / 2 - 110, 182, 220, 48), "Join Game")
    sp_btn = Button((sim.W / 2 - 110, 120, 220, 48), "Singleplayer")
    mp_btn = Button((sim.W / 2 - 110, 182, 220, 48), "Multiplayer")
    minus_btn = Button((sim.W / 2 - 30, 196, 40, 40), "-")
    plus_btn = Button((sim.W / 2 + 90, 196, 40, 40), "+")
    create_btn = Button((sim.W / 2 - 100, 256, 200, 42), "Create Lobby")
    confirm_join_btn = Button((sim.W / 2 - 100, 256, 200, 42), "Join")
    ready_btn = Button((sim.W / 2 - 170, 330, 150, 40), "Ready")
    leave_btn = Button((sim.W / 2 + 20, 330, 150, 40), "Leave")
    laps_btn = Button((sim.W / 2 + 10, 132, 150, 34), "Laps: 3")
    vol_track = pygame.Rect(sim.W / 2 + 10, 92, 150, 10)

    cars, player, cam = [], None, None
    final_order = []        # frozen leaderboard shown on the results screen
    last_mtime = os.path.getmtime(SIM_PATH)

    def start_game():
        nonlocal cars, player, cam, current_seed, state, countdown, go_timer, online
        nonlocal elim_timer, ghost_rec, last_ranks, trial_lap, ghost_best, ghost_time, popup
        sim.NET_ROLE = "off"
        online = False
        bot_count = 0 if game_mode == "trial" else random.randint(5, 7)
        current_seed = random.randint(0, 1_000_000)
        print(f"track seed: {current_seed}  mode: {game_mode}  bots: {bot_count}")
        sim.new_map(current_seed)   # whole track + scenery built right now, not as-you-drive
        cars = sim.spawn_grid(1 + bot_count)
        player = cars[min(PLAYER_SLOT, len(cars) - 1)]
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
        elim_timer, ghost_rec, last_ranks, trial_lap, popup = 0.0, [], {}, 0, None
        ghost_best, ghost_time = None, 0.0
        state = "playing"

    def reload_and_migrate():
        nonlocal cars, player, cam
        if try_reload():
            sim.new_map(current_seed)
            slot = cars.index(player)
            cars = [migrate_car(c) for c in cars]
            player = cars[slot]
            cam = migrate_cam(cam, player)

    def my_flag():
        return sim.FLAG_CODES[flag_idx] if sim.FLAG_CODES else None

    def net_disconnect():
        nonlocal netc, lobby, online, my_ready
        if netc is not None:
            netc.close()
        netc, lobby, online, my_ready = None, None, False, False

    def is_host():
        return bool(lobby) and lobby.get("host") == lobby.get("self")

    def make_bots(nplayers):
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
            else:
                c.is_remote = True
        for bd in mp_bots:
            c = cars[bd["slot"]]
            sim.make_bot(c, bd["ci"], PLAYER_PALETTE[bd["slot"] % len(PLAYER_PALETTE)])
            c.name, c.flag = bd["name"], bd["flag"]
            c.is_remote = not host      # host runs bot AI; clients puppet them
        cam = sim.Camera(player)

    def start_mp_race(start_msg):
        nonlocal current_seed, state, online, bcast_t, countdown, go_timer, end_title, mp_players, mp_bots
        mp_players = start_msg["players"]
        current_seed = start_msg["seed"]
        sim.new_map(current_seed)
        sim.NET_ROLE = "host" if is_host() else "client"
        mp_bots = make_bots(len(mp_players)) if is_host() else []
        rebuild_grid()
        if is_host() and mp_bots:
            netc.send({"t": "bots", "list": mp_bots})
        online, bcast_t, end_title = True, 0.0, "FINISH"
        countdown, go_timer = 3.0, 0.0
        state = "playing"

    def apply_finished(order):
        nonlocal final_order, state, end_title
        final_order = [cars[i] for i in order if 0 <= i < len(cars)]
        end_title = "FINISH"
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
    while running:
        dt = min(clock.tick(60) / 1000.0, 1 / 30)   # clamp so a freeze/stall can't teleport the car
        mouse_pos = pygame.mouse.get_pos()

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
                                       "flag": my_flag(), "max": pending_net[1]})
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
                    if state in ("host_setup", "join_entry"):
                        pass
                elif mt == "room":
                    prev_self = lobby.get("self") if lobby else None
                    lobby = m
                    if "self" not in lobby and prev_self is not None:
                        lobby["self"] = prev_self   # server only sends self on the first ack
                    if not m.get("started") and state in ("host_setup", "join_entry", "lobby"):
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
        bh = 42
        y0 = sim.H - 14 - bh * len(items)
        menu_buttons = [(nm, Button((16, y0 + i * bh, 240, bh), lbl, align="left"))
                        for i, (nm, lbl) in enumerate(items)]
        menu_sel = max(0, min(menu_sel, len(menu_buttons) - 1))

        # mode screen (Singleplayer / Multiplayer / Back), same bottom-left stack
        mode_items = [("single", "Singleplayer"), ("multi", "Multiplayer"), ("back", "Back")]
        mode_y0 = sim.H - 14 - bh * len(mode_items)
        mode_buttons = [(nm, Button((16, mode_y0 + i * bh, 260, bh), lbl, align="left"))
                        for i, (nm, lbl) in enumerate(mode_items)]

        gamemode_buttons = []
        gy = 90
        for mk, mlabel in GAME_MODES:
            gamemode_buttons.append((mk, Button((sim.W / 2 - 110, gy, 220, 36), mlabel)))
            gy += 42

        action = None   # the player's bash this frame, if any
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if state == "settings" and awaiting_key is not None:
                    if event.key != pygame.K_ESCAPE:    # Esc cancels the rebind
                        keybinds[awaiting_key] = event.key
                        profile.setdefault("keys", {})[awaiting_key] = event.key
                        save_profile(profile)
                    awaiting_key = None
                    continue
                if state == "playing":
                    if event.key == pygame.K_r and not online:
                        reload_and_migrate()
                    elif event.key == pygame.K_ESCAPE:
                        state = "menu"          # pauses; the race stays alive for Resume
                    elif event.key == keybinds["bashL"]:
                        action = "left"
                    elif event.key == keybinds["bashR"]:
                        action = "right"
                    elif event.key == keybinds["ram"]:
                        action = "ram"
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
                elif state == "join_entry":
                    if event.key == pygame.K_RETURN:
                        join_create()
                    elif event.key == pygame.K_ESCAPE:
                        state = "mp_menu"
                    elif event.key == pygame.K_BACKSPACE:
                        join_code = join_code[:-1]
                    elif event.unicode and event.unicode.isalnum() and len(join_code) < 6:
                        join_code += event.unicode.upper()
                elif event.key == pygame.K_ESCAPE and state in ("settings", "results"):
                    if state == "results":
                        player = None
                    state = "menu"
                elif event.key == pygame.K_ESCAPE and state in ("mode", "mp_menu", "host_setup", "gamemode"):
                    if state == "mode":
                        state = "menu"
                    elif state == "host_setup":
                        state = "mp_menu"
                    elif state == "gamemode":
                        state = "mode"
                    else:
                        state = "mode"
                elif event.key == pygame.K_ESCAPE and state == "lobby":
                    net_disconnect()
                    state = "mp_menu"
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if state == "menu":
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
                        state = "host_setup"
                    elif join_btn.clicked(mouse_pos):
                        join_code, net_msg = "", ""
                        state = "join_entry"
                    elif back_btn.clicked(mouse_pos):
                        state = "mode"
                elif state == "host_setup":
                    if minus_btn.clicked(mouse_pos):
                        mp_max = max(2, mp_max - 1)
                    elif plus_btn.clicked(mouse_pos):
                        mp_max = min(12, mp_max + 1)
                    elif create_btn.clicked(mouse_pos):
                        host_create()
                    elif back_btn.clicked(mouse_pos):
                        state = "mp_menu"
                elif state == "join_entry":
                    if confirm_join_btn.clicked(mouse_pos):
                        join_create()
                    elif back_btn.clicked(mouse_pos):
                        state = "mp_menu"
                elif state == "lobby":
                    if ready_btn.clicked(mouse_pos):
                        toggle_ready()
                    elif leave_btn.clicked(mouse_pos):
                        net_disconnect()
                        state = "mp_menu"
                    elif lobby and lobby.get("host") == lobby.get("self"):
                        # host: click another player's kick box to remove them
                        for i, p in enumerate(lobby.get("players", [])):
                            if p["id"] == lobby.get("self"):
                                continue
                            kr = pygame.Rect(sim.W / 2 + 150, 118 + i * 30, 22, 22)
                            if kr.collidepoint(mouse_pos):
                                netc.send({"t": "kick", "id": p["id"]})
                                break
                elif state == "settings":
                    if back_btn.clicked(mouse_pos):
                        save_profile(profile)
                        state = "menu"
                    elif laps_btn.clicked(mouse_pos):
                        nxt = {3: 5, 5: 7, 7: 3}
                        sim.TOTAL_LAPS = nxt.get(sim.TOTAL_LAPS, 3)
                        profile["laps"] = sim.TOTAL_LAPS
                    elif vol_track.collidepoint(mouse_pos):
                        vol_dragging = True
                    else:
                        for i, (ak, _) in enumerate(KEY_ACTIONS):
                            rr = pygame.Rect(sim.W / 2 - 170, 186 + i * 20, 340, 20)
                            if rr.collidepoint(mouse_pos):
                                awaiting_key = ak
                                break
                elif state == "results":
                    if back_btn.clicked(mouse_pos):
                        player = None
                        state = "menu"
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if vol_dragging:
                    vol_dragging = False
                    profile["volume"] = sim.MASTER_VOLUME
                    save_profile(profile)
            elif event.type == pygame.CONTROLLERDEVICEADDED:
                open_pad(event.device_index)
            elif event.type == pygame.CONTROLLERDEVICEREMOVED:
                pads.pop(event.instance_id, None)
            elif event.type == pygame.CONTROLLERBUTTONDOWN:
                b = event.button
                if state == "playing":
                    if b == PAD_BASH_L:
                        action = "left"
                    elif b == PAD_BASH_R:
                        action = "right"
                    elif b == PAD_RAM:
                        action = "ram"
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
                elif state == "mode":
                    if b == PAD_CONFIRM:
                        state = "gamemode"
                    elif b == PAD_BACK:
                        state = "menu"
                elif state == "gamemode":
                    if b == PAD_CONFIRM:        # A starts a plain Race; use mouse for other modes
                        game_mode, name_next, state = "race", "single", "name_entry"
                    elif b == PAD_BACK:
                        state = "mode"
                elif state == "mp_menu":
                    if b == PAD_CONFIRM:
                        state = "host_setup"
                    elif b == PAD_BACK:
                        state = "mode"
                elif state == "host_setup":
                    if b == PAD_LEFT:
                        mp_max = max(2, mp_max - 1)
                    elif b == PAD_RIGHT:
                        mp_max = min(12, mp_max + 1)
                    elif b == PAD_CONFIRM:
                        host_create()
                    elif b == PAD_BACK:
                        state = "mp_menu"
                elif state == "join_entry":
                    if b == PAD_BACK:
                        state = "mp_menu"
                elif state == "lobby":
                    if b == PAD_CONFIRM:
                        toggle_ready()
                    elif b == PAD_BACK:
                        net_disconnect()
                        state = "mp_menu"
                elif state == "settings":
                    if b in (PAD_CONFIRM, PAD_BACK):
                        state = "menu"
                elif state == "results":
                    if b in (PAD_CONFIRM, PAD_BACK):
                        player = None
                        state = "menu"

        if state == "playing":
            if countdown > 0:
                # pre-race lock: 3..2..1..GO, cars frozen (no step)
                countdown -= dt
                if countdown <= 0:
                    go_timer = 0.8
                cam.update(dt, player)
                sim.draw_world(screen, cam, cars)
                sim.draw_hud(screen, player, font_small, cars)
                n = int(math.ceil(countdown))
                big = font_big.render(str(n), True, (255, 255, 255))
                screen.blit(big, big.get_rect(center=(sim.W / 2, sim.H / 2 - 20)))
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
                steer = max(-1.0, min(1.0, steer + pad_steer()))
                drift = keys[keybinds["drift"]] or pad_drift()

                spectating = online and player.dead
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
                            controls.append(sim.bot_control(c, cars, dt))
                        else:
                            controls.append((0, None))
                    sim.step(dt, cars, controls)
                    lerp = min(1.0, 10.0 * dt)
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
                    if sim.NET_ROLE == "host":
                        alive = [c for c in cars if not c.dead]
                        done = any(sim.lap_of(c) >= sim.TOTAL_LAPS for c in cars)
                        if (done or len(alive) <= 1) and netc is not None:
                            order = sorted(range(len(cars)),
                                           key=lambda i: (cars[i].dead, -cars[i].progress))
                            netc.send({"t": "finished", "order": order})
                            apply_finished(order)
                else:
                    pc = (steer, action, drift)
                    controls = [pc if c is player else sim.bot_control(c, cars, dt) for c in cars]
                    sim.step(dt, cars, controls)

                    # ---- single-player game-mode logic --------------------------------
                    if game_mode == "elim":         # cull the last-place living kart periodically
                        elim_timer += dt
                        living = [c for c in cars if not c.dead]
                        if elim_timer >= ELIM_INTERVAL and len(living) > 1:
                            elim_timer = 0.0
                            loser = min(living, key=lambda c: c.progress)
                            loser.dead = True
                            if loser is not player:
                                popup = (f"{loser.name} eliminated!", (255, 150, 120), 2.0)
                    if game_mode == "trial":        # record the ghost path; bank it on a new best lap
                        ghost_rec.append((player.x, player.y, player.angle))
                        if player.cur_lap > trial_lap:
                            if player.last_lap > 0 and (ghost_time <= 0 or player.last_lap <= ghost_time):
                                ghost_best, ghost_time = list(ghost_rec), player.last_lap
                            ghost_rec = []
                            trial_lap = player.cur_lap

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
                sim.draw_hud(screen, player, font_small, cars)
                go_timer = max(0.0, go_timer - dt)
                if go_timer > 0:
                    go = font_big.render("GO!", True, (120, 255, 120))
                    screen.blit(go, go.get_rect(center=(sim.W / 2, sim.H / 2 - 20)))
                if spectating:
                    ov = font.render("YOU'RE OUT - spectating", True, (255, 120, 120))
                    screen.blit(ov, ov.get_rect(center=(sim.W / 2, 40)))

                # position-change popups (your rank in the live order)
                if not spectating:
                    order = sorted(cars, key=lambda c: (c.dead, -c.progress))
                    rank = order.index(player) + 1
                    prev = last_ranks.get("me", rank)
                    if rank < prev:
                        popup = (f"UP to P{rank}", (150, 255, 150), 1.5)
                    elif rank > prev:
                        popup = (f"down to P{rank}", (255, 180, 120), 1.5)
                    last_ranks["me"] = rank
                if popup:
                    txt, col, tleft = popup
                    tleft -= dt
                    popup = (txt, col, tleft) if tleft > 0 else None
                    if popup:
                        ps = font.render(txt, True, col)
                        screen.blit(ps, ps.get_rect(center=(sim.W / 2, 70)))

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
                btn.draw(screen, font, btn.clicked(mouse_pos) or i == menu_sel)

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
                ctext = font_small.render(code.upper(), True, (255, 235, 120))
                screen.blit(ctext, ctext.get_rect(center=(sim.W / 2, 242)))
            flag_prev.draw(screen, font, flag_prev.clicked(mouse_pos))
            flag_next.draw(screen, font, flag_next.clicked(mouse_pos))
            start_btn.draw(screen, font, start_btn.clicked(mouse_pos))
            back_btn.draw(screen, font, back_btn.clicked(mouse_pos))
            hint = font_small.render("Arrows: flag   Enter: race   Esc: back", True, (180, 200, 180))
            screen.blit(hint, hint.get_rect(center=(sim.W / 2, sim.H - 24)))

        elif state == "settings":
            draw_bg()
            title = font_big.render("SETTINGS", True, (255, 255, 255))
            screen.blit(title, title.get_rect(center=(sim.W / 2, 40)))
            # volume slider
            if vol_dragging:
                v = (mouse_pos[0] - vol_track.x) / vol_track.w
                sim.set_master_volume(v)
            screen.blit(font_small.render("Volume", True, (220, 230, 210)), (sim.W / 2 - 170, 88))
            pygame.draw.rect(screen, (40, 55, 40), vol_track, border_radius=4)
            fillw = int(vol_track.w * sim.MASTER_VOLUME)
            pygame.draw.rect(screen, (255, 200, 60), (vol_track.x, vol_track.y, fillw, vol_track.h),
                             border_radius=4)
            pygame.draw.circle(screen, (255, 255, 255), (vol_track.x + fillw, vol_track.centery), 7)
            # lap count
            screen.blit(font_small.render("Laps", True, (220, 230, 210)), (sim.W / 2 - 170, 140))
            laps_btn.label = f"Laps: {sim.TOTAL_LAPS}"
            laps_btn.draw(screen, font_small, laps_btn.clicked(mouse_pos))
            # controls (click a row, then press a key)
            screen.blit(font_small.render("Controls (click, then press a key):", True,
                                          (200, 220, 200)), (sim.W / 2 - 170, 168))
            for i, (ak, albl) in enumerate(KEY_ACTIONS):
                y = 186 + i * 20
                binding = "press a key..." if awaiting_key == ak else pygame.key.name(keybinds[ak])
                col = (255, 235, 120) if awaiting_key == ak else (230, 230, 230)
                screen.blit(font_small.render(albl, True, (210, 220, 210)), (sim.W / 2 - 170, y))
                b = font_small.render(binding, True, col)
                screen.blit(b, b.get_rect(midright=(sim.W / 2 + 170, y + 10)))
            back_btn.draw(screen, font, back_btn.clicked(mouse_pos))

        elif state == "results":
            draw_bg()
            title = font_big.render(end_title, True, (255, 255, 255))
            screen.blit(title, title.get_rect(center=(sim.W / 2, 36)))
            if team_result:
                tr = font_small.render(team_result, True, (255, 235, 120))
                screen.blit(tr, tr.get_rect(center=(sim.W / 2, 66)))
            hdr = font_small.render("best lap", True, (170, 185, 165))
            screen.blit(hdr, hdr.get_rect(midright=(sim.W / 2 + 170, 78)))
            for i, c in enumerate(final_order):
                me = c is player
                tag = f"{i + 1}.  {c.name}" + ("  (you)" if me else "") + ("  OUT" if c.dead else "")
                color = (255, 235, 120) if me else (235, 235, 235)
                y = 90 + i * 18
                row = font_small.render(tag, True, color)
                screen.blit(row, row.get_rect(midleft=(sim.W / 2 - 170, y)))
                bl = font_small.render(sim.fmt_time(c.best_lap), True, (190, 205, 185))
                screen.blit(bl, bl.get_rect(midright=(sim.W / 2 + 170, y)))
            back_btn.draw(screen, font, back_btn.clicked(mouse_pos))

        elif state == "mode":
            draw_bg()
            draw_logo()
            for _, btn in mode_buttons:
                btn.draw(screen, font, btn.clicked(mouse_pos))

        elif state == "gamemode":
            draw_bg()
            title = font.render("CHOOSE MODE", True, (255, 255, 255))
            screen.blit(title, title.get_rect(center=(sim.W / 2, 56)))
            for mk, btn in gamemode_buttons:
                btn.draw(screen, font_small, btn.clicked(mouse_pos))
            back_btn.draw(screen, font, back_btn.clicked(mouse_pos))

        elif state == "mp_menu":
            draw_bg()
            title = font_big.render("MULTIPLAYER", True, (255, 255, 255))
            screen.blit(title, title.get_rect(center=(sim.W / 2, 60)))
            host_btn.draw(screen, font, host_btn.clicked(mouse_pos))
            join_btn.draw(screen, font, join_btn.clicked(mouse_pos))
            back_btn.draw(screen, font, back_btn.clicked(mouse_pos))
            if net_msg:
                msg = font_small.render(net_msg, True, (240, 180, 120))
                screen.blit(msg, msg.get_rect(center=(sim.W / 2, 262)))

        elif state == "host_setup":
            draw_bg()
            title = font_big.render("HOST GAME", True, (255, 255, 255))
            screen.blit(title, title.get_rect(center=(sim.W / 2, 60)))
            lbl = font_small.render(f"Lobby: {player_name.strip() or 'Player'}", True, (220, 230, 210))
            screen.blit(lbl, lbl.get_rect(center=(sim.W / 2, 130)))
            cap = font_small.render("Max players:", True, (220, 230, 210))
            screen.blit(cap, cap.get_rect(center=(sim.W / 2, 176)))
            num = font.render(str(mp_max), True, (255, 235, 120))
            screen.blit(num, num.get_rect(center=(sim.W / 2, 216)))
            minus_btn.draw(screen, font, minus_btn.clicked(mouse_pos))
            plus_btn.draw(screen, font, plus_btn.clicked(mouse_pos))
            create_btn.draw(screen, font, create_btn.clicked(mouse_pos))
            back_btn.draw(screen, font, back_btn.clicked(mouse_pos))
            if net_msg:
                msg = font_small.render(net_msg, True, (240, 180, 120))
                screen.blit(msg, msg.get_rect(center=(sim.W / 2, sim.H - 24)))

        elif state == "join_entry":
            draw_bg()
            title = font_big.render("JOIN GAME", True, (255, 255, 255))
            screen.blit(title, title.get_rect(center=(sim.W / 2, 60)))
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
            screen.blit(title, title.get_rect(center=(sim.W / 2, 34)))
            if lobby:
                i_am_host = lobby.get("host") == lobby.get("self")   # not "is_host": that would overwrite is_host()
                head = font_small.render(
                    f"{lobby.get('name','')}'s lobby    CODE: {lobby.get('code','')}"
                    f"    ({len(lobby.get('players', []))}/{lobby.get('max','?')})",
                    True, (255, 235, 120))
                screen.blit(head, head.get_rect(center=(sim.W / 2, 70)))
                for i, p in enumerate(lobby.get("players", [])):
                    y = 110 + i * 30
                    x = sim.W / 2 - 180
                    is_me = p["id"] == lobby.get("self")
                    fl = sim.get_flag(p.get("flag"), 14)
                    if fl:
                        screen.blit(fl, (x, y + 2))
                    nm = p["name"] + ("  (you)" if is_me else "") + ("  [host]" if p["id"] == lobby.get("host") else "")
                    nmcol = (255, 235, 120) if is_me else (235, 235, 235)
                    screen.blit(font_small.render(nm, True, nmcol), (x + 26, y))
                    rtxt = "READY" if p["ready"] else "not ready"
                    rcol = (120, 230, 120) if p["ready"] else (200, 120, 120)
                    rsurf = font_small.render(rtxt, True, rcol)
                    screen.blit(rsurf, rsurf.get_rect(midright=(sim.W / 2 + 140, y + 10)))
                    if i_am_host and not is_me:
                        kr = pygame.Rect(sim.W / 2 + 150, y + 8, 22, 22)
                        pygame.draw.rect(screen, (150, 50, 50), kr, border_radius=4)
                        xk = font_small.render("x", True, (255, 255, 255))
                        screen.blit(xk, xk.get_rect(center=kr.center))
                ready_btn.label = "Unready" if my_ready else "Ready"
                ready_btn.draw(screen, font_small, my_ready or ready_btn.clicked(mouse_pos))
                leave_btn.draw(screen, font_small, leave_btn.clicked(mouse_pos))
                tip = "All players ready -> race starts automatically"
                screen.blit(font_small.render(tip, True, (180, 200, 180)),
                            (sim.W / 2 - 180, sim.H - 24))
            else:
                wait = font_small.render(net_msg or "Connecting...", True, (220, 220, 220))
                screen.blit(wait, wait.get_rect(center=(sim.W / 2, sim.H / 2)))

        pygame.display.flip()

    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()
