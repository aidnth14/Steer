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

PLAYER_COLOR = (230, 60, 60)
BOT_COLORS = [(60, 140, 230), (230, 200, 60), (160, 80, 220), (240, 140, 40), (90, 220, 190)]
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
    def __init__(self, rect, label):
        self.rect = pygame.Rect(rect)
        self.label = label

    def draw(self, screen, font, hover):
        bg = (90, 90, 95) if hover else (60, 60, 65)
        pygame.draw.rect(screen, bg, self.rect, border_radius=8)
        pygame.draw.rect(screen, (230, 230, 230), self.rect, 2, border_radius=8)
        text = font.render(self.label, True, (255, 255, 255))
        screen.blit(text, text.get_rect(center=self.rect.center))

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

    font_big = sim.get_font(64)
    font = sim.get_font(40)
    font_small = sim.get_font(26)

    state = "menu"
    menu_sel = 0                # highlighted menu row for controller / keyboard nav
    current_seed = sim.ROAD_SEED
    player_name = "Player"      # last name typed; prefilled on the name screen
    flag_idx = sim.FLAG_CODES.index("us") if "us" in sim.FLAG_CODES else 0
    name_next = "single"        # where the name screen goes on confirm: "single" or "mp"

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

    cars, player, cam = [], None, None
    final_order = []        # frozen leaderboard shown on the results screen
    last_mtime = os.path.getmtime(SIM_PATH)

    def start_game():
        nonlocal cars, player, cam, current_seed, state, countdown, go_timer, online
        sim.NET_ROLE = "off"
        online = False
        bot_count = random.randint(5, 7)        # 5-7 bots per race
        current_seed = random.randint(0, 1_000_000)
        print(f"track seed: {current_seed}  bots: {bot_count}")
        sim.new_map(current_seed)   # whole track + scenery built right now, not as-you-drive
        cars = sim.spawn_grid(1 + bot_count)
        player = cars[min(PLAYER_SLOT, len(cars) - 1)]
        player.color = PLAYER_COLOR
        player.name = player_name.strip() or "Player"
        player.flag = sim.FLAG_CODES[flag_idx] if sim.FLAG_CODES else None
        for i, bot in enumerate(c for c in cars if c is not player):
            sim.make_bot(bot, i, BOT_COLORS[i % len(BOT_COLORS)])
        cam = sim.Camera(player)
        countdown, go_timer = 3.0, 0.0
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

        # menu layout depends on whether a paused race exists (Resume/New Race vs just Play);
        # build it once per frame so clicks and drawing always agree
        menu_buttons = []
        y = 100
        if player is not None:
            menu_buttons.append(("resume", Button((sim.W / 2 - 100, y, 200, 46), "Resume")))
            y += 56
            menu_buttons.append(("play", Button((sim.W / 2 - 100, y, 200, 46), "New Race")))
        else:
            menu_buttons.append(("play", Button((sim.W / 2 - 100, y, 200, 46), "Play")))
        y += 56
        menu_buttons.append(("settings", Button((sim.W / 2 - 100, y, 200, 46), "Settings")))
        y += 56
        menu_buttons.append(("quit", Button((sim.W / 2 - 100, y, 200, 46), "Quit")))
        menu_sel = max(0, min(menu_sel, len(menu_buttons) - 1))

        action = None   # the player's bash this frame, if any
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if state == "playing":
                    if event.key == pygame.K_r:
                        reload_and_migrate()
                    elif event.key == pygame.K_ESCAPE:
                        state = "menu"          # pauses; the race stays alive for Resume
                    elif event.key == pygame.K_q:
                        action = "left"
                    elif event.key == pygame.K_e:
                        action = "right"
                    elif event.key == pygame.K_SPACE:
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
                elif event.key == pygame.K_ESCAPE and state in ("mode", "mp_menu", "host_setup"):
                    if state == "mode":
                        state = "menu"
                    elif state == "host_setup":
                        state = "mp_menu"
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
                    if sp_btn.clicked(mouse_pos):
                        name_next = "single"
                        state = "name_entry"
                    elif mp_btn.clicked(mouse_pos):
                        name_next = "mp"
                        state = "name_entry"
                    elif back_btn.clicked(mouse_pos):
                        state = "menu"
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
                        state = "menu"
                elif state == "results":
                    if back_btn.clicked(mouse_pos):
                        player = None
                        state = "menu"
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
                        name_next = "single"
                        state = "name_entry"
                    elif b == PAD_BACK:
                        state = "menu"
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
                if keys[pygame.K_LEFT] or keys[pygame.K_a]:
                    steer -= 1
                if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
                    steer += 1
                steer = max(-1.0, min(1.0, steer + pad_steer()))

                spectating = online and player.dead
                if spectating:
                    steer, action = 0.0, None

                if online:
                    # I drive my car; bots are mine too if I'm host; every other car is a
                    # remote puppet corrected from the net
                    controls = []
                    for c in cars:
                        if c is player:
                            controls.append((steer, action))
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
                    controls = [(steer, action) if c is player else sim.bot_control(c, cars, dt)
                                for c in cars]
                    sim.step(dt, cars, controls)

                # camera follows the leader while spectating, else your own car
                cam_target = player
                if spectating:
                    live = [c for c in cars if not c.dead]
                    cam_target = max(live, key=lambda c: c.progress) if live else player
                cam.update(dt, cam_target)

                sim.draw_world(screen, cam, cars)
                sim.draw_hud(screen, player, font_small, cars)
                go_timer = max(0.0, go_timer - dt)
                if go_timer > 0:
                    go = font_big.render("GO!", True, (120, 255, 120))
                    screen.blit(go, go.get_rect(center=(sim.W / 2, sim.H / 2 - 20)))
                if spectating:
                    ov = font.render("YOU'RE OUT - spectating", True, (255, 120, 120))
                    screen.blit(ov, ov.get_rect(center=(sim.W / 2, 40)))

                if not online and sim.lap_of(player) >= sim.TOTAL_LAPS:
                    final_order = sorted(cars, key=lambda c: (c.dead, -c.progress))
                    end_title = "FINISH"
                    state = "results"
                elif not online and player.dead:
                    final_order = sorted(cars, key=lambda c: (c.dead, -c.progress))
                    end_title = "GAME OVER"
                    state = "results"

        elif state == "menu":
            screen.fill((30, 60, 30))
            title = font_big.render("STEER", True, (255, 255, 255))
            screen.blit(title, title.get_rect(center=(sim.W / 2, 55)))
            for i, (_, btn) in enumerate(menu_buttons):
                btn.draw(screen, font, btn.clicked(mouse_pos) or i == menu_sel)
            for i, line in enumerate(HELP_LINES):
                text = font_small.render(line, True, (200, 220, 200))
                screen.blit(text, text.get_rect(center=(sim.W / 2, sim.H - 66 + i * 22)))

        elif state == "name_entry":
            screen.fill((30, 60, 30))
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
            screen.fill((30, 60, 30))
            title = font_big.render("SETTINGS", True, (255, 255, 255))
            screen.blit(title, title.get_rect(center=(sim.W / 2, 80)))
            label = font.render("Bots per race: 5-7 (random)", True, (255, 255, 255))
            screen.blit(label, label.get_rect(center=(sim.W / 2, 150)))
            back_btn.draw(screen, font, back_btn.clicked(mouse_pos))

        elif state == "results":
            screen.fill((30, 60, 30))
            title = font_big.render(end_title, True, (255, 255, 255))
            screen.blit(title, title.get_rect(center=(sim.W / 2, 40)))
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
            screen.fill((30, 60, 30))
            title = font_big.render("PLAY", True, (255, 255, 255))
            screen.blit(title, title.get_rect(center=(sim.W / 2, 60)))
            sp_btn.draw(screen, font, sp_btn.clicked(mouse_pos))
            mp_btn.draw(screen, font, mp_btn.clicked(mouse_pos))
            back_btn.draw(screen, font, back_btn.clicked(mouse_pos))

        elif state == "mp_menu":
            screen.fill((30, 60, 30))
            title = font_big.render("MULTIPLAYER", True, (255, 255, 255))
            screen.blit(title, title.get_rect(center=(sim.W / 2, 60)))
            host_btn.draw(screen, font, host_btn.clicked(mouse_pos))
            join_btn.draw(screen, font, join_btn.clicked(mouse_pos))
            back_btn.draw(screen, font, back_btn.clicked(mouse_pos))
            if net_msg:
                msg = font_small.render(net_msg, True, (240, 180, 120))
                screen.blit(msg, msg.get_rect(center=(sim.W / 2, 262)))

        elif state == "host_setup":
            screen.fill((30, 60, 30))
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
            screen.fill((30, 60, 30))
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
            screen.fill((30, 60, 30))
            title = font.render("LOBBY", True, (255, 255, 255))
            screen.blit(title, title.get_rect(center=(sim.W / 2, 34)))
            if lobby:
                is_host = lobby.get("host") == lobby.get("self")
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
                    if is_host and not is_me:
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
