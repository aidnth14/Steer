import os
import random
import sys
import pygame
from pygame._sdl2 import controller as sdlctrl

import sim

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

    back_btn = Button((sim.W / 2 - 100, 306, 200, 44), "Back")
    start_btn = Button((sim.W / 2 - 100, 256, 200, 42), "Start Race")
    flag_prev = Button((sim.W / 2 - 120, 198, 40, 40), "<")
    flag_next = Button((sim.W / 2 + 80, 198, 40, 40), ">")

    cars, player, cam = [], None, None
    final_order = []        # frozen leaderboard shown on the results screen
    last_mtime = os.path.getmtime(SIM_PATH)

    def start_game():
        nonlocal cars, player, cam, current_seed, state
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
        state = "playing"

    def reload_and_migrate():
        nonlocal cars, player, cam
        if try_reload():
            sim.new_map(current_seed)
            slot = cars.index(player)
            cars = [migrate_car(c) for c in cars]
            player = cars[slot]
            cam = migrate_cam(cam, player)

    running = True
    while running:
        dt = min(clock.tick(60) / 1000.0, 1 / 30)   # clamp so a freeze/stall can't teleport the car
        mouse_pos = pygame.mouse.get_pos()

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
                        start_game()
                    elif event.key == pygame.K_ESCAPE:
                        state = "menu"
                    elif event.key == pygame.K_BACKSPACE:
                        player_name = player_name[:-1]
                    elif event.key == pygame.K_LEFT and sim.FLAG_CODES:
                        flag_idx = (flag_idx - 1) % len(sim.FLAG_CODES)
                    elif event.key == pygame.K_RIGHT and sim.FLAG_CODES:
                        flag_idx = (flag_idx + 1) % len(sim.FLAG_CODES)
                    elif event.unicode and event.unicode.isprintable() and len(player_name) < 12:
                        player_name += event.unicode
                elif event.key == pygame.K_ESCAPE and state in ("settings", "results"):
                    if state == "results":
                        player = None
                    state = "menu"
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if state == "menu":
                    for name, btn in menu_buttons:
                        if not btn.clicked(mouse_pos):
                            continue
                        if name == "resume":
                            state = "playing"
                        elif name == "play":
                            state = "name_entry"        # pick a name before racing
                        elif name == "settings":
                            state = "settings"
                        elif name == "quit":
                            running = False
                        break
                elif state == "name_entry":
                    if start_btn.clicked(mouse_pos):
                        start_game()
                    elif back_btn.clicked(mouse_pos):
                        state = "menu"
                    elif flag_prev.clicked(mouse_pos) and sim.FLAG_CODES:
                        flag_idx = (flag_idx - 1) % len(sim.FLAG_CODES)
                    elif flag_next.clicked(mouse_pos) and sim.FLAG_CODES:
                        flag_idx = (flag_idx + 1) % len(sim.FLAG_CODES)
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
                            state = "name_entry"
                        elif name == "settings":
                            state = "settings"
                        elif name == "quit":
                            running = False
                    elif b == PAD_PAUSE and player is not None:
                        state = "playing"
                elif state == "name_entry":
                    if b == PAD_CONFIRM:
                        start_game()
                    elif b == PAD_BACK:
                        state = "menu"
                    elif b == PAD_LEFT and sim.FLAG_CODES:
                        flag_idx = (flag_idx - 1) % len(sim.FLAG_CODES)
                    elif b == PAD_RIGHT and sim.FLAG_CODES:
                        flag_idx = (flag_idx + 1) % len(sim.FLAG_CODES)
                elif state == "settings":
                    if b in (PAD_CONFIRM, PAD_BACK):
                        state = "menu"
                elif state == "results":
                    if b in (PAD_CONFIRM, PAD_BACK):
                        player = None
                        state = "menu"

        if state == "playing":
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

            controls = [(steer, action) if c is player else sim.bot_control(c, cars, dt) for c in cars]
            sim.step(dt, cars, controls)
            cam.update(dt, player)

            sim.draw_world(screen, cam, cars)
            sim.draw_hud(screen, player, font_small, cars)

            if sim.lap_of(player) >= sim.TOTAL_LAPS:
                final_order = sorted(cars, key=lambda c: c.progress, reverse=True)
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
            title = font_big.render("FINISH", True, (255, 255, 255))
            screen.blit(title, title.get_rect(center=(sim.W / 2, 44)))
            for i, c in enumerate(final_order):
                me = c is player or (player is None and c.name == player_name)
                tag = f"{i + 1}.  {c.name}" + ("  (you)" if me else "")
                color = (255, 235, 120) if me else (235, 235, 235)
                row = font_small.render(tag, True, color)
                screen.blit(row, row.get_rect(midleft=(sim.W / 2 - 120, 96 + i * 24)))
            back_btn.draw(screen, font, back_btn.clicked(mouse_pos))

        pygame.display.flip()

    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()
