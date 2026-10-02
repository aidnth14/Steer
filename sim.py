import math
import os
import random
from bisect import bisect_right
from collections import deque
import pygame

W, H = 600, 400
WORLD = 4800          # world wraps at this size; the fences keep cars well inside it

# ---- track ---------------------------------------------------------------------
ROAD_SEED = 7         # default track seed (main.py picks a random one for each race)
ROAD_WIDTH = 240      # width of the dirt road in px (15 tiles)
OFFROAD_RANGE = 50.0  # px past the road edge over which the grass penalty ramps up to full
EDGE_GRACE = 6.0      # px a car's centre may stray past the last road tile before it counts as
                      # off-road; the square tiles make the edge a staircase, and clipping a
                      # step's corner by a pixel or two shouldn't cost a heart

# ---- tiles ---------------------------------------------------------------------
# The map is built only from the dirt-on-grass road tiles in assets/track_tiles/ and the
# fence pieces in assets/fence_tiles/ (two fences, one each side of the road, as barriers).
TILE = 16                       # px size of one tile, and of one cell of the track grid
GRID_N = WORLD // TILE          # world is a GRID_N x GRID_N grid of cells (keep WORLD a multiple of TILE)
ASSET_DIR = os.path.join(os.path.dirname(__file__), "assets")
TRACK_TILE_DIR = os.path.join(ASSET_DIR, "track_tiles")
TRACK_TILE_NAMES = [            # [row][col]; row 0 = grass above, col 0 = grass to the left
    ["dirt_corner_tl", "dirt_edge_top", "dirt_corner_tr"],
    ["dirt_edge_left", "dirt_center", "dirt_edge_right"],
    ["dirt_corner_bl", "dirt_edge_bottom", "dirt_corner_br"],
]
INNER_TILE_NAMES = [            # [qy][qx]: dirt tile with grass only in that corner
    ["dirt_inner_tl", "dirt_inner_tr"],
    ["dirt_inner_bl", "dirt_inner_br"],
]
FENCE_TILE_DIR = os.path.join(ASSET_DIR, "fence_tiles")
# Each fence piece is a post with rails out to the neighbouring posts. The file name says which
# way the rails go (u/d/l/r). Whether there's a rail going up only changes the tile's top pixel
# row, so these 11 cover all 16 combinations: (down, left, right) -> file to start from.
FENCE_SOURCES = {
    (1, 0, 1): "fence_dr", (1, 1, 1): "fence_dlr", (1, 1, 0): "fence_dl", (1, 0, 0): "fence_ud",
    (0, 0, 0): "fence_u", (0, 0, 1): "fence_ur", (0, 1, 1): "fence_ulr", (0, 1, 0): "fence_ul",
}
FENCE_UP_ROW_FROM = "fence_ud"  # its top row is the rail going up
FENCE_COLOR = (117, 83, 56)     # flat fallback if the fence tiles are missing

# ---- UI assets (icons + pixel font) ------------------------------------------------
UI_DIR = os.path.join(ASSET_DIR, "UI")
FLAGS_DIR = os.path.join(ASSET_DIR, "flags")
UI_ICON_NAMES = ["contrast", "gear", "heart", "mic", "mute_red", "save"]
FLAGS = {}          # code -> raw flag surface
FLAG_CODES = []     # sorted list of available flag codes
_FLAG_CACHE = {}    # (code, h) -> scaled surface

def load_flags():
    FLAGS.clear()
    del FLAG_CODES[:]
    _FLAG_CACHE.clear()
    if not os.path.isdir(FLAGS_DIR):
        return
    for fn in sorted(os.listdir(FLAGS_DIR)):
        if not fn.endswith(".png") or fn.startswith("_"):
            continue
        code = fn[:-4]
        try:
            FLAGS[code] = pygame.image.load(os.path.join(FLAGS_DIR, fn)).convert_alpha()
            FLAG_CODES.append(code)
        except (pygame.error, FileNotFoundError):
            pass

def get_flag(code, h):
    # flag scaled to height h (keeps aspect), cached; None if unknown
    img = FLAGS.get(code)
    if img is None:
        return None
    key = (code, h)
    if key not in _FLAG_CACHE:
        w = max(1, round(img.get_width() * h / img.get_height()))
        _FLAG_CACHE[key] = pygame.transform.scale(img, (w, h))
    return _FLAG_CACHE[key]

# ---- sound -------------------------------------------------------------------------
SOUND_DIR = os.path.join(ASSET_DIR, "sound")
SOUND_FILES = {
    "bash":     "bash.mp3",
    "death":    "death.mp3",
    "powerup":  "powerup.mp3",
    "powerup2": "powerup2.mp3",
    "crash":    "break.wav",
    "bump":     "bullet_collision.mp3",
}
SOUND_VOL = {"bash": 0.5, "death": 0.9, "powerup": 0.7, "powerup2": 0.7, "crash": 0.6, "bump": 0.4}
SOUNDS = {}
_mixer_ready = False

def init_audio():
    global _mixer_ready
    if _mixer_ready:
        return
    try:
        pygame.mixer.init()
        _mixer_ready = True
    except pygame.error as e:
        print("audio unavailable:", e)

def load_sounds():
    SOUNDS.clear()
    if not _mixer_ready:
        return
    for key, fn in SOUND_FILES.items():
        try:
            s = pygame.mixer.Sound(os.path.join(SOUND_DIR, fn))
            s.set_volume(SOUND_VOL.get(key, 0.6) * MASTER_VOLUME)
            SOUNDS[key] = s
        except (pygame.error, FileNotFoundError):
            pass

MASTER_VOLUME = 0.8

def set_master_volume(v):
    global MASTER_VOLUME
    MASTER_VOLUME = max(0.0, min(1.0, v))
    for key, s in SOUNDS.items():
        s.set_volume(SOUND_VOL.get(key, 0.6) * MASTER_VOLUME)

def play(name):
    s = SOUNDS.get(name)
    if s is not None:
        try:
            s.play()
        except pygame.error:
            pass
FONT_PATH = os.path.join(ASSET_DIR, "font", "Jersey25-Regular.ttf")
UI = {}             # UI icon surfaces by name
_FONT_CACHE = {}

def get_font(size):
    # Jersey 25 pixel font, cached per size; falls back to the pygame default if missing
    key = int(size)
    if key not in _FONT_CACHE:
        try:
            _FONT_CACHE[key] = pygame.font.Font(FONT_PATH, key)
        except (pygame.error, FileNotFoundError, OSError):
            _FONT_CACHE[key] = pygame.font.Font(None, key)
    return _FONT_CACHE[key]

# flat colours; load_assets() replaces these with the exact colours sampled from the tiles
GRASS_COLOR = (62, 137, 72)
DIRT_COLOR = (184, 111, 80)

# ---- fences ---------------------------------------------------------------------
# A fence runs along each side of the road (outside the loop and around the infield),
# FENCE_OFFSET cells out from the road, so there's a strip of grass to run wide onto (and
# lose a heart) before you hit it. 4 = three tiles (48 px) of grass, then the fence.
FENCE_OFFSET = 4
# a fence cell's collision box within its 16 px cell: the post (x0, y0, x1, y1), stretched to
# the cell edge on every side a rail continues, so a run of fence is one flat wall to scrape along
FENCE_POST = (3, 1, 14, 14)
ARENA_MARGIN = 360.0    # px of grass baked around the road's bounding box (the camera never sees past it)
BAKE_PAD = 96           # extra px of grass baked around that

# ---- hearts -----------------------------------------------------------------------
HEART_COUNT = 3
HEART_PENALTY = 0.5   # hearts lost each time you drive off the road
HEART_COOLDOWN = 1.0  # seconds before another penalty can apply

# ---- mystery boxes ----------------------------------------------------------------
BOX_COUNT = 10        # floating "?" boxes scattered around the loop
BOX_SIZE = 20         # px, on-screen box size
BOX_PICKUP = 18.0     # px pickup radius (plus the car's half-width)
BOX_RESPAWN = 6.0     # seconds a box stays gone after being taken
BOX_FLOAT_AMP = 3.5   # px vertical bob
BOX_FLOAT_SPEED = 3.0 # bob rad/s
BOX_LATERAL = 0.30    # how far off centre a box may sit, as a fraction of road half-width
BOOST_TIME = 1.8      # seconds of engine boost from a box
BOOST_PACE = 0.9      # extra engine while boosting (+90%)
BOOST_KICK = 90.0     # instant forward px/s on pickup
# three box types: colour tells you the power-up inside
BOX_TYPES = ["boost", "heart", "bash"]
BOX_COLORS = {"boost": (255, 205, 60),      # yellow = speed boost
              "heart": (70, 150, 255),       # blue   = +1 heart
              "bash":  (235, 70, 70)}         # red    = instant bash recharge
BOX_LETTER = {"boost": "!", "heart": "+", "bash": "x"}

# ---- laps -------------------------------------------------------------------------
TOTAL_LAPS = 3        # laps to finish a race

# ---- car body ---------------------------------------------------------------------
# units are px, seconds and "kart masses"; +x = forward, +y = the kart's right side
CAR_HL = 14.0          # half length of the kart's collision box
CAR_HW = 9.0           # half width
AXLE_FRONT = 9.5       # centre of mass -> front axle
AXLE_REAR = 8.5        # centre of mass -> rear axle (a bit more weight on the driven rear)
WHEELBASE = AXLE_FRONT + AXLE_REAR
WHEEL_Y = 8.5          # wheel distance from the centre line (drawing + skid marks)
CAR_MASS = 1.0
CAR_INERTIA = 1.6 * (4 * CAR_HL * CAR_HL + 4 * CAR_HW * CAR_HW) / 12   # per unit mass; >1 = steadier spins
CAR_BOUND = math.hypot(CAR_HL, CAR_HW)

# ---- engine + resistance (always on: the kart always drives forward) -----------------
MAX_SPEED = 380.0
ENGINE_ACCEL = 430.0    # push at standstill, px/s^2
ENGINE_FALLOFF = 0.3    # fraction of that push lost at MAX_SPEED
ROLL_RESIST = 25.0      # constant rolling resistance
AIR_DRAG = 0.0019       # grows with speed^2; tuned so top speed settles near MAX_SPEED

# ---- tyres --------------------------------------------------------------------------
GRIP = 560.0            # px/s^2 of sideways grip on dirt: how hard you can corner before sliding
TIRE_PEAK_SLIP = 0.14   # slip angle (rad) where a tyre grips hardest; past it, it slides
TIRE_SHAPE = 1.45       # >1: grip drops off past the peak (so slides happen and must be caught)
DRIVE_GRIP_USE = 0.45   # how much of the rear tyres' grip the always-on engine uses up -> rear steps out first
STEER_MAX = 0.6         # front wheel lock at low speed, rad (~34 deg)
STEER_GRIP_RATIO = 1.2  # at speed, full lock asks for this x the available grip -> full lock = a slide
STEER_RATE = 5.0        # how fast the front wheels turn, rad/s
V_FLOOR = 40.0          # px/s; keeps slip angles sane when nearly stopped
YAW_DAMP = 0.6          # a little rotational damping, 1/s
STABILITY = 3.0         # 1/s: pulls the spin rate toward what the steering asks for, so a slide can
                        # be caught instead of snapping into a spin (off while staggered by a hit)
PHYS_SUBSTEPS = 4       # physics steps per frame (stable collisions + tyres)

# ---- grass ---------------------------------------------------------------------------
GRASS_GRIP = 0.6        # grip multiplier on grass
GRASS_ENGINE_LOSS = 0.5 # engine push lost on grass
GRASS_RESIST = 2.5      # extra resistance on grass (x(1 + this))

# ---- collisions -------------------------------------------------------------------------
CAR_RESTITUTION = 0.45  # bounciness of kart-vs-kart hits
CAR_FRICTION = 0.3
WALL_RESTITUTION = 0.3  # fences give a little: karts bounce off softer than off each other
WALL_FRICTION = 0.5
CONTACT_SLOP = 0.3      # px of overlap allowed before pushing apart

# ---- drifting -----------------------------------------------------------------------------
DRIFT_GRIP = 0.55       # rear-tyre grip while drifting (lower -> slides more)
DRIFT_MIN_SPEED = 120.0 # px/s below which you can't charge a drift
DRIFT_CHARGE_RATE = 1.0 # charge per second of clean drift
DRIFT_MIN_CHARGE = 0.35 # charge needed to get any mini-boost on release
DRIFT_MAX_CHARGE = 1.6  # charge caps here
DRIFT_BOOST_TIME = 1.1  # boost seconds at full charge
DRIFT_BOOST_KICK = 70.0 # instant forward px/s on release at full charge

# ---- bashing ------------------------------------------------------------------------------
BASH_COOLDOWN = 1.5     # seconds between bashes
BASH_TIME = 0.18        # side-bash active window
BASH_SIDE_SPEED = 190.0 # sideways lunge, px/s
RAM_TIME = 0.3          # ram active window
RAM_SPEED = 150.0       # forward lunge, px/s
BASH_MASS = 2.5         # the basher counts as this many karts while bashing (hits hard, barely recoils)
BASH_KNOCK = 150.0      # extra shove given to whoever gets bashed, px/s
BASH_TIRE = 0.35        # the basher's tyre grip during the lunge, so it carries instead of twisting
BASH_SPIN = 0.3         # scales the spin a bash adds (hit the rear quarter -> spin-out)
MAX_SPIN = 9.0          # rad/s cap on how fast any kart can spin (~1.4 turns a second)
STAGGER_TIME = 0.45     # seconds a bashed kart's tyres are loose
STAGGER_GRIP = 0.5      # grip multiplier while staggered

# ---- getting unstuck -----------------------------------------------------------------------
STUCK_SPEED = 25.0      # below this px/s ...
STUCK_TIME = 0.8        # ... for this long -> the kart backs up on its own
REVERSE_TIME = 0.7
REVERSE_ACCEL = 260.0
REVERSE_SPEED = 90.0
RESCUE_TIME = 3.0       # still wedged after this long (even backing up) -> put back on the road

# ---- bots ------------------------------------------------------------------------------------
AI_LOOK_BASE = 60.0     # px ahead a bot aims at, plus ...
AI_LOOK_SPEED = 0.35    # ... this much per px/s of speed
AI_EDGE_MARGIN = 30.0   # bots keep their chosen lane at least this far inside the road edge
AI_LANE_RATE = 1.5      # how quickly a bot moves across to a new lane
AI_BASH_RATE = 5.0      # side-bash attempts per second for a fully aggressive bot alongside a rival
AI_RAM_RATE = 3.0       # ram attempts per second with a rival just ahead
AI_SEARCH = 16          # road samples searched around the last known position
AI_PACK_RANGE = 500.0   # px: bots further than this behind / ahead of you get the full pace change ...
AI_CATCHUP = 0.18       # ... up to this much extra engine when behind (keeps the fight around you)
AI_EASE = 0.12          # ... and this much less when they've run away ahead
BOT_PROFILES = [        # aggression 0..1, how wide they roam, engine pace, weight (heavier pushes harder)
    {"name": "Brute", "aggression": 0.95, "lanes": 0.5, "pace": 0.98, "mass": 1.35},
    {"name": "Dash", "aggression": 0.35, "lanes": 0.9, "pace": 1.03, "mass": 0.85},
    {"name": "Shove", "aggression": 0.75, "lanes": 0.6, "pace": 1.0, "mass": 1.15},
    {"name": "Rival", "aggression": 0.7, "lanes": 0.4, "pace": 1.01, "mass": 1.0, "hunts_player": True},
    {"name": "Rook", "aggression": 0.5, "lanes": 0.8, "pace": 1.0, "mass": 1.0},
]
# auto-assigned bot names (one each, so up to 7 bots never repeat a name)
BOT_NAMES = ["Brute", "Dash", "Shove", "Rival", "Rook", "Nitro", "Vex", "Blitz", "Turbo", "Crash"]

# ---- start grid ----------------------------------------------------------------------------------
GRID_START = 24         # road sample the front row starts on (bottom straight)
GRID_ROW_GAP = 46.0     # px between grid rows
GRID_LANE = 36.0        # px either side of the centre line

# ---- effects ---------------------------------------------------------------------------------------
SKID_SLIP = 55.0        # tyre sideways slip (px/s) above which it leaves a mark
TRAIL_LIFE = 1.6        # seconds a skid mark stays visible
TRAIL_MAX_POINTS = 600
MAX_PARTICLES = 400
SHAKE_PX = 6.0          # screen shake at full strength
SHAKE_IMPULSE = 260.0   # hit strength that gives full shake

CAM_POS_SMOOTH = 6.0    # higher = camera position snaps to the car faster
CAM_ROT_SMOOTH = 4.0    # higher = camera rotation snaps faster
CAM_VEL_FOLLOW = 0.7    # 0 = camera faces where the kart points, 1 = where it's actually going


def lerp_angle(a, b, t):
    diff = (b - a + 180) % 360 - 180
    return a + diff * t

def wrap_delta(a, b):
    # shortest signed distance from a to b on a world that wraps at WORLD
    return (b - a + WORLD / 2) % WORLD - WORLD / 2


# =================================================================================================
# assets
# =================================================================================================
TILES = None        # 3x3 road tiles, [row][col] as in TRACK_TILE_NAMES
INNER = None        # 2x2 inner-corner road tiles, [qy][qx]
CHECK = None        # checkered finish-line tile
FENCE = {}          # (up, down, left, right) -> 16 px fence piece, all 16 combinations

def load_assets():
    # needs a display surface to exist (convert); called at startup and after each hot reload
    global TILES, INNER, GRASS_COLOR, DIRT_COLOR
    TILES = INNER = None
    FENCE.clear()

    grid = [[None] * 3 for _ in range(3)]
    global CHECK
    try:
        CHECK = _load(TRACK_TILE_DIR, "checktile", alpha=True)
    except (pygame.error, FileNotFoundError):
        CHECK = None
    try:
        for r in range(3):
            for c in range(3):
                grid[r][c] = _load(TRACK_TILE_DIR, TRACK_TILE_NAMES[r][c], alpha=False)
    except (pygame.error, FileNotFoundError) as e:
        print("road tiles missing, drawing the road as flat colour instead:", e)
        grid = None
    if grid:
        TILES = grid
        GRASS_COLOR = tuple(TILES[0][0].get_at((0, 0)))[:3]
        DIRT_COLOR = tuple(TILES[1][1].get_at((TILE // 2, TILE // 2)))[:3]
        try:
            INNER = [[_load(TRACK_TILE_DIR, INNER_TILE_NAMES[qy][qx], alpha=False) for qx in (0, 1)]
                     for qy in (0, 1)]
        except (pygame.error, FileNotFoundError) as e:
            print("inner-corner tiles missing, building them from the edge tiles:", e)
            INNER = [[_make_inner_corner(qx, qy) for qx in (0, 1)] for qy in (0, 1)]

    try:
        _build_fence_tiles({name: _load(FENCE_TILE_DIR, name, alpha=True)
                            for name in set(FENCE_SOURCES.values()) | {FENCE_UP_ROW_FROM}})
    except (pygame.error, FileNotFoundError) as e:
        print("fence tiles missing, drawing fences as flat colour instead:", e)
        FENCE.clear()

    UI.clear()
    for name in UI_ICON_NAMES:
        try:
            UI[name] = _load(UI_DIR, name, alpha=True)
        except (pygame.error, FileNotFoundError) as e:
            print(f"UI icon {name} missing:", e)
    load_flags()
    init_audio()
    load_sounds()

def _build_fence_tiles(src):
    # all 16 (up, down, left, right) pieces: take the file with the right down/left/right rails,
    # then draw or clear the top pixel row, which is the only part a rail going up changes
    up_row = [src[FENCE_UP_ROW_FROM].get_at((x, 0)) for x in range(TILE)]
    for (d, l, r), name in FENCE_SOURCES.items():
        for u in (0, 1):
            tile = src[name].copy()
            for x in range(TILE):
                tile.set_at((x, 0), up_row[x] if u else (0, 0, 0, 0))
            FENCE[(u, d, l, r)] = tile

def _load(folder, name, alpha):
    img = pygame.image.load(os.path.join(folder, name + ".png"))
    return img.convert_alpha() if alpha else img.convert()

def _make_inner_corner(qx, qy):
    # fallback if the inner-corner tiles are missing: a full tile whose (qx, qy) quarter is
    # built from the two edge tiles, split along the diagonal so their borders meet in a mitre
    tile = TILES[1][1].copy()
    half = TILE // 2
    horiz = TILES[0 if qy == 0 else 2][1]
    vert = TILES[1][0 if qx == 0 else 2]
    for py in range(half):
        for px in range(half):
            tx, ty = qx * half + px, qy * half + py
            depth_v = ty if qy == 0 else TILE - 1 - ty
            depth_h = tx if qx == 0 else TILE - 1 - tx
            src = horiz if depth_v > depth_h else vert
            tile.set_at((tx, ty), src.get_at((tx, ty)))
    return tile

# =================================================================================================
# track
# =================================================================================================
ROAD = []           # centre line points, in driving order
ROAD_S = [0.0]      # arc length at each point (+ the loop length at the end)
ROAD_T = []         # unit direction of each segment
ROAD_LEN = 1.0
DIRT = bytearray(GRID_N * GRID_N)       # 1 = road cell
ROAD_NEAR = bytearray(GRID_N * GRID_N)  # cells from the nearest road cell (capped); fences go where it's FENCE_OFFSET

def generate_road(seed):
    # a "stadium" loop: two straights + two semicircle turns, so it can never cross or pass
    # close to itself; a gentle sideways wobble on the straights keeps it from being a plain oval
    rnd = random.Random(seed)
    cx, cy = WORLD / 2, WORLD / 2
    A = rnd.uniform(550, 750)   # half-length of each straight
    R = rnd.uniform(420, 550)   # turn radius
    wobble_amp = R * 0.12
    wobble_freq = rnd.choice([2, 3])
    wobble_phase = rnd.uniform(0, math.tau)

    def wob(u):
        return wobble_amp * math.sin(wobble_freq * u + wobble_phase)

    n_straight, n_arc = 80, 60
    pts = []
    for i in range(n_straight):   # bottom straight, left -> right
        t = i / n_straight
        taper = math.sin(math.pi * t)   # fades to 0 at both ends so it meets the turns cleanly
        pts.append((cx - A + 2 * A * t, cy + R + wob(t * math.tau) * taper))
    for i in range(n_arc):        # right turn
        t = i / n_arc
        ang = math.pi / 2 - math.pi * t
        pts.append((cx + A + R * math.cos(ang), cy + R * math.sin(ang)))
    for i in range(n_straight):   # top straight, right -> left
        t = i / n_straight
        taper = math.sin(math.pi * t)
        pts.append((cx + A - 2 * A * t, cy - R + wob(t * math.tau + math.pi) * taper))
    for i in range(n_arc):        # left turn
        t = i / n_arc
        ang = -math.pi / 2 - math.pi * t
        pts.append((cx - A + R * math.cos(ang), cy + R * math.sin(ang)))
    return pts

def _road_tables(road):
    n = len(road)
    S, T = [0.0], []
    for i in range(n):
        ax, ay = road[i]
        bx, by = road[(i + 1) % n]
        seg = math.hypot(bx - ax, by - ay) or 1e-9
        S.append(S[-1] + seg)
        T.append(((bx - ax) / seg, (by - ay) / seg))
    return S, T

def road_pose(s, lateral=0.0):
    # point on the road at arc length s, shifted `lateral` px to the right of the centre line;
    # also returns the road's heading there in degrees
    s %= ROAD_LEN
    i = min(bisect_right(ROAD_S, s) - 1, len(ROAD) - 1)
    ax, ay = ROAD[i]
    tx, ty = ROAD_T[i]
    d = s - ROAD_S[i]
    return (ax + tx * d - ty * lateral, ay + ty * d + tx * lateral, math.degrees(math.atan2(ty, tx)))

def track_coords(x, y, hint=None):
    # (arc length, px right of the centre line, nearest road sample) for a world point
    n = len(ROAD)
    best_i, best_d = 0, None
    rng = range(n) if hint is None else range(hint - AI_SEARCH, hint + AI_SEARCH + 1)
    for j in rng:
        i = j % n
        rx, ry = ROAD[i]
        dx, dy = wrap_delta(rx, x), wrap_delta(ry, y)
        d = dx * dx + dy * dy
        if best_d is None or d < best_d:
            best_d, best_i = d, i
    if hint is not None and best_d > 260 * 260:
        return track_coords(x, y, None)     # lost track of it: search the whole loop
    # project onto the segment that starts at that sample, or the one before if we're behind it
    i = best_i
    ax, ay = ROAD[i]
    tx, ty = ROAD_T[i]
    dx, dy = wrap_delta(ax, x), wrap_delta(ay, y)
    along = dx * tx + dy * ty
    if along < 0:
        i = (i - 1) % n
        ax, ay = ROAD[i]
        tx, ty = ROAD_T[i]
        dx, dy = wrap_delta(ax, x), wrap_delta(ay, y)
        along = dx * tx + dy * ty
    along = min(max(along, 0.0), ROAD_S[i + 1] - ROAD_S[i])
    return ROAD_S[i] + along, -dx * ty + dy * tx, best_i

# ---- the road as a grid of 16px cells ----------------------------------------------------------
# DIRT decides which tiles are drawn AND what counts as on/off the road, so physics always
# matches what you see.

def build_dirt_grid(road):
    # a cell is road if its centre is within ROAD_WIDTH / 2 of the centre line
    grid = bytearray(GRID_N * GRID_N)
    half = ROAD_WIDTH / 2
    half_sq = half * half
    n = len(road)
    for i in range(n):
        ax, ay = road[i]
        bx, by = road[(i + 1) % n]
        ex, ey = bx - ax, by - ay
        seg_sq = ex * ex + ey * ey or 1e-9
        gx0, gx1 = int((min(ax, bx) - half) // TILE), int((max(ax, bx) + half) // TILE)
        gy0, gy1 = int((min(ay, by) - half) // TILE), int((max(ay, by) + half) // TILE)
        for gy in range(gy0, gy1 + 1):
            cy = (gy + 0.5) * TILE
            row = (gy % GRID_N) * GRID_N
            for gx in range(gx0, gx1 + 1):
                idx = row + gx % GRID_N
                if grid[idx]:
                    continue
                cx = (gx + 0.5) * TILE
                t = ((cx - ax) * ex + (cy - ay) * ey) / seg_sq
                t = 0.0 if t < 0.0 else 1.0 if t > 1.0 else t
                dx, dy = ax + ex * t - cx, ay + ey * t - cy
                if dx * dx + dy * dy <= half_sq:
                    grid[idx] = 1
    _clean_grid(grid)
    return grid

def _clean_grid(grid):
    # The tiles can't draw a dirt strip one cell wide (grass on both opposite sides) or a
    # one-cell grass sliver between dirt. Remove any such cells until none are left.
    n = GRID_N

    def d(gx, gy):
        return grid[(gy % n) * n + gx % n]

    for _ in range(10):
        cand = set()
        for i, v in enumerate(grid):
            if v:
                gx, gy = i % n, i // n
                cand.update(((gx, gy), (gx - 1, gy), (gx + 1, gy), (gx, gy - 1), (gx, gy + 1)))
        flips = []
        for gx, gy in cand:
            up, down, left, right = d(gx, gy - 1), d(gx, gy + 1), d(gx - 1, gy), d(gx + 1, gy)
            if d(gx, gy):
                if (not up and not down) or (not left and not right):
                    flips.append((gx, gy, 0))
            elif (up and down) or (left and right):
                flips.append((gx, gy, 1))
        if not flips:
            return
        for gx, gy, v in flips:
            grid[(gy % n) * n + gx % n] = v

def _near_road_grid(dirt, cap=20):
    # for every cell, how many cells (8-way steps) it is from the nearest road cell, up to cap
    n = GRID_N
    near = bytearray([255]) * (n * n)
    q = deque()
    for i, v in enumerate(dirt):
        if v:
            near[i] = 0
            q.append(i)
    while q:
        i = q.popleft()
        dist = near[i] + 1
        if dist > cap:
            continue
        gx, gy = i % n, i // n
        for ox in (-1, 0, 1):
            for oy in (-1, 0, 1):
                j = ((gy + oy) % n) * n + (gx + ox) % n
                if near[j] > dist:
                    near[j] = dist
                    q.append(j)
    return near

def is_dirt(gx, gy):
    return DIRT[(gy % GRID_N) * GRID_N + gx % GRID_N] == 1

def dist_to_dirt(x, y, max_dist):
    # distance in px from (x, y) to the nearest road cell, capped at max_dist (0 = on the road)
    gx, gy = int(x // TILE), int(y // TILE)
    if is_dirt(gx, gy):
        return 0.0
    r = int(max_dist // TILE) + 1
    best = max_dist
    for j in range(gy - r, gy + r + 1):
        top = j * TILE
        dy = top - y if y < top else (y - top - TILE if y > top + TILE else 0.0)
        if dy >= best:
            continue
        for i in range(gx - r, gx + r + 1):
            if not is_dirt(i, j):
                continue
            left = i * TILE
            dx = left - x if x < left else (x - left - TILE if x > left + TILE else 0.0)
            dist = math.hypot(dx, dy)
            if dist < best:
                best = dist
    return best

def offroad_factor(x, y):
    # 0.0 on a road tile (or within EDGE_GRACE of one), ramps up to 1.0 further onto the grass
    past = dist_to_dirt(x, y, OFFROAD_RANGE + EDGE_GRACE) - EDGE_GRACE
    return max(past, 0.0) / OFFROAD_RANGE


# =================================================================================================
# fences: placement, colliders, baked ground image
# =================================================================================================
FENCES = []         # (gx, gy, (up, down, left, right)) one per fence cell
STATICS = []        # solid boxes: ("box", x0, y0, x1, y1) in world px
_STATIC_CELL = 64
_STATIC_HASH = {}   # (cx, cy) -> indices into STATICS
ARENA = (0, 0, WORLD, WORLD)

def _road_bbox():
    xs, ys = [], []
    for i, v in enumerate(DIRT):
        if v:
            xs.append(i % GRID_N)
            ys.append(i // GRID_N)
    return min(xs) * TILE, min(ys) * TILE, (max(xs) + 1) * TILE, (max(ys) + 1) * TILE

def _shape_bbox(shape):
    return shape[1], shape[2], shape[3], shape[4]

def _tidy_fence(cells):
    # Where the road edge has a one-tile dip, the fence line can double up for a moment: a stub
    # post sticking off it, or a little 2x2 box. Trim stubs and collapse boxes back to a single
    # line (never breaking it), until there are none left.
    def nbrs(c):
        x, y = c
        return [p for p in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)) if p in cells]

    for _ in range(20):
        changed = False
        for c in [c for c in cells if len(nbrs(c)) <= 1]:      # stubs (and lone posts)
            cells.discard(c)
            changed = True
        for x, y in sorted(cells):
            block = [(x, y), (x + 1, y), (x, y + 1), (x + 1, y + 1)]
            if not all(b in cells for b in block):
                continue
            # which corners of the box carry the fence on beyond it
            ext = [b for b in block if any(p not in block for p in nbrs(b))]
            inner = [b for b in block if b not in ext]
            if len(ext) == 2 and abs(ext[0][0] - ext[1][0]) + abs(ext[0][1] - ext[1][1]) == 2:
                inner = inner[:1]       # line enters and leaves at opposite corners: keep one path
            if len(ext) >= 2 and inner:
                for b in inner:
                    cells.discard(b)
                changed = True
        if not changed:
            return

def generate_fences():
    # Two fences, one each side of the road: every cell exactly FENCE_OFFSET steps (counting
    # diagonals) from the nearest road cell. That traces a closed line outside the loop and
    # another round the infield, each one cell thick, following the road's shape. Each fence
    # cell gets rails toward whichever of its 4 neighbours are fence too.
    global FENCES, STATICS, ARENA
    n = GRID_N
    cells = {(i % n, i // n) for i, v in enumerate(ROAD_NEAR) if v == FENCE_OFFSET}
    _tidy_fence(cells)
    is_fence = lambda gx, gy: (gx, gy) in cells
    fences, statics = [], []
    px0, py0, px1, py1 = FENCE_POST
    for gx, gy in sorted(cells):
        u, d = is_fence(gx, gy - 1), is_fence(gx, gy + 1)
        l, r = is_fence(gx - 1, gy), is_fence(gx + 1, gy)
        fences.append((gx, gy, (int(u), int(d), int(l), int(r))))
        x, y = gx * TILE, gy * TILE
        statics.append(("box", x + (0 if l else px0), y + (0 if u else py0),
                        x + (TILE if r else px1), y + (TILE if d else py1)))

    rx0, ry0_, rx1, ry1_ = _road_bbox()
    m = ARENA_MARGIN
    ARENA = (int((rx0 - m) // TILE) * TILE, int((ry0_ - m) // TILE) * TILE,
             int(math.ceil((rx1 + m) / TILE)) * TILE, int(math.ceil((ry1_ + m) / TILE)) * TILE)

    FENCES = fences
    STATICS = statics
    _STATIC_HASH.clear()
    for idx, shape in enumerate(statics):
        x0, y0, x1, y1 = _shape_bbox(shape)
        for cx in range(int(x0 // _STATIC_CELL), int(x1 // _STATIC_CELL) + 1):
            for cy in range(int(y0 // _STATIC_CELL), int(y1 // _STATIC_CELL) + 1):
                _STATIC_HASH.setdefault((cx, cy), []).append(idx)


GROUND_SURF = None      # grass + tiled road + fences, baked once per map
GROUND_ORIGIN = (0, 0)  # world coords of GROUND_SURF's top-left pixel

def _bake_finish(surf, ox, oy):
    # checkered start/finish line baked across the road at the start, aligned to the road
    if CHECK is None or not ROAD:
        return
    s0 = ROAD_S[GRID_START]
    _, _, heading = road_pose(s0)
    tile = pygame.transform.rotate(CHECK, -heading)     # face along the road
    half = ROAD_WIDTH / 2
    d = -half
    while d <= half:
        for along in (-TILE * 0.5, TILE * 0.5):         # a two-tile-deep band
            wx, wy, _ = road_pose(s0 + along, d)
            surf.blit(tile, tile.get_rect(center=(wx - ox, wy - oy)))
        d += TILE

def build_ground():
    # Bake the whole map into one image once, so each frame we just rotate the part around
    # the camera (rotating individual 16px tiles would leave seams). Needs a display surface.
    global GROUND_SURF, GROUND_ORIGIN
    ax0, ay0, ax1, ay1 = ARENA
    ox, oy = ax0 - BAKE_PAD, ay0 - BAKE_PAD
    gw, gh = (ax1 - ax0) + 2 * BAKE_PAD, (ay1 - ay0) + 2 * BAKE_PAD
    GROUND_ORIGIN = (ox, oy)
    surf = pygame.Surface((gw, gh)).convert()
    surf.fill(GRASS_COLOR)

    half = TILE // 2
    for i, v in enumerate(DIRT):
        if not v:
            continue
        gx, gy = i % GRID_N, i // GRID_N
        px, py = gx * TILE - ox, gy * TILE - oy
        if TILES is None:
            surf.fill(DIRT_COLOR, (px, py, TILE, TILE))
            continue
        # tile by which sides have grass: row from above/below, column from left/right
        up, down = is_dirt(gx, gy - 1), is_dirt(gx, gy + 1)
        left, right = is_dirt(gx - 1, gy), is_dirt(gx + 1, gy)
        row = 0 if not up else (2 if not down else 1)
        col = 0 if not left else (2 if not right else 1)
        surf.blit(TILES[row][col], (px, py))
        # inner corners: dirt on both sides of a corner but grass on the diagonal -> copy that
        # quarter of the matching inner-corner tile
        for qx, qy, dx, dy in ((0, 0, -1, -1), (1, 0, 1, -1), (0, 1, -1, 1), (1, 1, 1, 1)):
            if is_dirt(gx + dx, gy) and is_dirt(gx, gy + dy) and not is_dirt(gx + dx, gy + dy):
                surf.blit(INNER[qy][qx], (px + qx * half, py + qy * half),
                          (qx * half, qy * half, half, half))

    _bake_finish(surf, ox, oy)

    # fences, top row first so each post's cap overlaps the shadow of the post above it
    for gx, gy, links in sorted(FENCES, key=lambda f: f[1]):
        px, py = gx * TILE - ox, gy * TILE - oy
        tile = FENCE.get(links)
        if tile is None:
            surf.fill(FENCE_COLOR, (px + 3, py + 1, 11, 13))
        else:
            surf.blit(tile, (px, py))
    GROUND_SURF = surf


# ---- minimap -----------------------------------------------------------------------
# Just the road layout (white strokes + ~22% black fill) and the kart markers -- no
# grass/dirt texture. Prebaked once per track; markers drawn per frame.
MINIMAP = None
MINIMAP_MAX = 118       # longest side in px
MM_SCALE = 1.0
MM_MINX = MM_MINY = 0.0
MM_PAD = 7
MM_SIZE = (0, 0)

def _build_minimap():
    global MINIMAP, MM_SCALE, MM_MINX, MM_MINY, MM_SIZE
    if not ROAD:
        MINIMAP = None
        return
    half = ROAD_WIDTH / 2
    left, right = [], []
    for (rx, ry), (tx, ty) in zip(ROAD, ROAD_T):
        nx, ny = -ty, tx                 # road normal
        left.append((rx + nx * half, ry + ny * half))
        right.append((rx - nx * half, ry - ny * half))
    xs = [p[0] for p in left + right]
    ys = [p[1] for p in left + right]
    MM_MINX, MM_MINY = min(xs), min(ys)
    span = max(max(xs) - MM_MINX, max(ys) - MM_MINY)
    MM_SCALE = (MINIMAP_MAX - 2 * MM_PAD) / span
    sw = round((max(xs) - MM_MINX) * MM_SCALE) + 2 * MM_PAD
    sh = round((max(ys) - MM_MINY) * MM_SCALE) + 2 * MM_PAD
    MM_SIZE = (sw, sh)

    def tp(p):
        return (round((p[0] - MM_MINX) * MM_SCALE) + MM_PAD,
                round((p[1] - MM_MINY) * MM_SCALE) + MM_PAD)

    L, R = [tp(p) for p in left], [tp(p) for p in right]
    surf = pygame.Surface((sw, sh), pygame.SRCALPHA)
    pygame.draw.polygon(surf, (0, 0, 0, 55), L + R[::-1])   # ~22% black road fill
    pygame.draw.lines(surf, (255, 255, 255, 255), True, L, 2)
    pygame.draw.lines(surf, (255, 255, 255, 255), True, R, 2)
    MINIMAP = surf

def _mm_point(x, y):
    return (round((x - MM_MINX) * MM_SCALE) + MM_PAD, round((y - MM_MINY) * MM_SCALE) + MM_PAD)

def draw_minimap(screen, cars, player):
    if MINIMAP is None:
        return
    mw, mh = MM_SIZE
    px, py = W - mw - 12, H - mh - 12            # bottom-right corner
    screen.blit(MINIMAP, (px, py))
    for c in cars:
        mx, my = _mm_point(c.x, c.y)
        mx = min(max(px + 2, mx + px), px + mw - 2)     # keep markers inside the minimap
        my = min(max(py + 2, my + py), py + mh - 2)
        if c is player:
            pygame.draw.circle(screen, (255, 255, 255), (mx, my), 4)
            pygame.draw.circle(screen, (20, 20, 20), (mx, my), 4, 1)
        elif not c.dead:
            pygame.draw.circle(screen, c.color, (mx, my), 3)
            pygame.draw.circle(screen, (20, 20, 20), (mx, my), 3, 1)


def new_map(seed):
    # builds the whole track + fences in one shot (no incremental generation)
    global ROAD, ROAD_S, ROAD_T, ROAD_LEN, DIRT, ROAD_NEAR, MAP_SEED
    MAP_SEED = seed     # so boxes land identically for every player on this track
    ROAD = generate_road(seed)
    ROAD_S, ROAD_T = _road_tables(ROAD)
    ROAD_LEN = ROAD_S[-1]
    DIRT = build_dirt_grid(ROAD)
    ROAD_NEAR = _near_road_grid(DIRT, FENCE_OFFSET + 1)
    generate_fences()
    build_ground()
    _build_minimap()
    spawn_boxes()
    del PARTICLES[:]


# =================================================================================================
# karts
# =================================================================================================
_TIRE_B = math.tan(math.pi / (2 * TIRE_SHAPE)) / TIRE_PEAK_SLIP
_next_uid = [1]

def tire_curve(alpha):
    # sideways grip vs slip angle, as a fraction of the maximum: rises to 1 at TIRE_PEAK_SLIP,
    # then falls off (to ~80%) as the tyre slides
    return math.sin(TIRE_SHAPE * math.atan(_TIRE_B * alpha))

def steer_limit(v):
    # full lock at low speed; at speed, just enough lock to ask for a bit more than the
    # tyres have, so full lock = a slide rather than an instant spin
    v = max(v, 1.0)
    return min(STEER_MAX, math.atan(STEER_GRIP_RATIO * GRIP * WHEELBASE / (v * v)))

class Car:
    def __init__(self, x, y, angle, color):
        self.x, self.y = x, y
        self.angle = angle          # heading in degrees, 0 = facing right, + = clockwise
        self.vx, self.vy = 0.0, 0.0
        self.omega = 0.0            # spin rate, rad/s, + = clockwise
        self.steer_angle = 0.0      # front wheel angle, rad, + = right
        self.color = color
        self.mass = CAR_MASS
        self.pace = 1.0             # engine multiplier (bots: personality + pack pacing)
        self.base_pace = 1.0
        self.uid = _next_uid[0]
        _next_uid[0] += 1
        self.progress = 0.0         # px driven along the track since the start (laps * ROAD_LEN + ...)
        self.track_s = None         # where on the loop the kart is now
        self.track_idx = None
        self.trail = []             # skid marks: [x, y, life]
        self.hearts = HEART_COUNT
        self.dead = False           # out of the race (hearts hit 0)
        self.was_on_road = True
        self.heart_cooldown = 0.0
        # lap timing
        self.race_t = 0.0           # seconds since GO
        self.cur_lap = 0            # laps completed so far (for detecting a new lap)
        self.last_lap_t = 0.0       # race_t at the last lap crossing
        self.last_lap = 0.0         # most recent completed lap time (s)
        self.best_lap = 0.0         # best lap time this race (0 = none yet)
        self.off_f = self.off_r = 0.0   # how far onto the grass each axle is (0..1)
        self.slip_f = self.slip_r = 0.0 # tyre sideways slip, px/s (skid marks)
        self.boost_time = 0.0       # > 0 while a mystery-box speed boost is active
        self.drift = False          # drift held this frame
        self.was_drifting = False
        self.drift_charge = 0.0     # builds while drifting, spent as a mini-boost on release
        self.team = -1              # team index in team races, else -1
        # bashing
        self.bash_cd = 0.0          # seconds until the next bash is ready
        self.bash_time = 0.0        # > 0 while a bash/ram is active
        self.bash_kind = None
        self.bash_hits = set()      # who this bash has already hit (each victim once per bash)
        self.stagger = 0.0          # > 0 after being bashed: tyres are loose
        self.flash = 0.0            # white flash after a hit
        self.impact = 0.0           # hardest hit this frame (camera shake)
        self.last_hit_by = 0
        # getting unstuck
        self.slow_time = 0.0
        self.reverse_time = 0.0
        self.wedged = 0.0           # seconds spent barely moving (backing up included)
        self.rescues = 0            # how many times this kart has been put back on the road
        # bots only
        self.is_bot = False
        self.is_remote = False      # true for other players' cars in multiplayer (driven by net)
        self.name = "You"
        self.flag = None            # 2-letter flag code, or None
        self.aggression = 0.0
        self.lanes = 0.5
        self.hunts_player = False
        self.lane = 0.0
        self.lane_target = 0.0
        self.ai_index = None
        self.ai_think = 0.0
        self.grudge = 0
        self.grudge_time = 0.0
        self.rng = random.Random(self.uid)

    # ---- per frame -------------------------------------------------------------------------
    def prepare(self):
        rad = math.radians(self.angle)
        c, s = math.cos(rad), math.sin(rad)
        self.off_f = offroad_factor(self.x + c * AXLE_FRONT, self.y + s * AXLE_FRONT)
        self.off_r = offroad_factor(self.x - c * AXLE_REAR, self.y - s * AXLE_REAR)
        self.impact = 0.0

    def start_bash(self, kind):
        # kind: "left" / "right" = side-bash, "ram" = forward lunge
        if self.bash_cd > 0 or self.reverse_time > 0:
            return False
        rad = math.radians(self.angle)
        c, s = math.cos(rad), math.sin(rad)
        if kind == "ram":
            self.vx += c * RAM_SPEED
            self.vy += s * RAM_SPEED
            self.bash_time = RAM_TIME
            spawn_particles(self.x - c * CAR_HL, self.y - s * CAR_HL, 6, 60, (200, 170, 120), 0.4)
        else:
            side = 1 if kind == "right" else -1
            self.vx += -s * side * BASH_SIDE_SPEED
            self.vy += c * side * BASH_SIDE_SPEED
            self.bash_time = BASH_TIME
            spawn_particles(self.x + s * side * CAR_HW, self.y - c * side * CAR_HW, 6, 60,
                            (200, 170, 120), 0.4)
        self.bash_kind = kind
        self.bash_cd = BASH_COOLDOWN
        self.bash_hits = set()
        play("bash")
        return True

    def integrate(self, h, steer_in):
        rad = math.radians(self.angle)
        c, s = math.cos(rad), math.sin(rad)
        vx, vy = self.vx, self.vy
        v_long = vx * c + vy * s        # forward speed
        v_lat = -vx * s + vy * c        # sideways speed (+ = sliding right)

        # front wheels turn toward the commanded angle; less lock is available at speed
        target = max(-1.0, min(1.0, steer_in)) * steer_limit(abs(v_long))
        step = STEER_RATE * h
        self.steer_angle += max(-step, min(step, target - self.steer_angle))
        cd, sd = math.cos(self.steer_angle), math.sin(self.steer_angle)

        m = self.mass
        loose = STAGGER_GRIP if self.stagger > 0 else 1.0
        if self.bash_time > 0:
            loose *= BASH_TIRE
        rear = loose * (DRIFT_GRIP if self.drift else 1.0)      # drifting loosens the rear tyres
        cap_f = GRIP * (1 - self.off_f * (1 - GRASS_GRIP)) * loose * m * AXLE_REAR / WHEELBASE
        cap_r = GRIP * (1 - self.off_r * (1 - GRASS_GRIP)) * rear * m * AXLE_FRONT / WHEELBASE

        # engine: always pushing forward (backs up only while getting unstuck)
        if self.reverse_time > 0:
            drive = -REVERSE_ACCEL * m if v_long > -REVERSE_SPEED else 0.0
        else:
            frac = min(max(v_long, 0.0) / MAX_SPEED, 1.0)
            boost = (1 + BOOST_PACE) if self.boost_time > 0 else 1.0
            drive = (ENGINE_ACCEL * m * self.pace * boost * (1 - frac * ENGINE_FALLOFF)
                     * (1 - self.off_r * GRASS_ENGINE_LOSS))
        if self.dead:
            drive = 0.0             # eliminated: coast to a stop

        # front tyres: slip angle between where the wheels point and where they're moving
        lat_f = v_lat + self.omega * AXLE_FRONT
        u_f = -v_long * sd + lat_f * cd             # sideways speed in the wheel's own frame
        w_f = v_long * cd + lat_f * sd
        f_f = -tire_curve(math.atan2(u_f, max(abs(w_f), V_FLOOR))) * cap_f
        # rear tyres: the engine uses part of their grip, so they let go first (power oversteer)
        u_r = v_lat - self.omega * AXLE_REAR
        use = min(abs(drive) * DRIVE_GRIP_USE / cap_r, 0.95) if cap_r > 0 else 0.95
        if self.bash_time > 0:
            use = 0.0       # mid-lunge the engine doesn't load the rear, so the kart slides square
        f_r = -tire_curve(math.atan2(u_r, max(abs(v_long), V_FLOOR))) * cap_r * math.sqrt(1 - use * use)
        # a tyre can stop a slide but never flip it the other way within one step (stability)
        lim = 0.5 * m / h
        f_f = max(-lim * abs(u_f), min(lim * abs(u_f), f_f))
        f_r = max(-lim * abs(u_r), min(lim * abs(u_r), f_r))

        fx = drive - f_f * sd                   # in the kart's frame
        fy = f_f * cd + f_r
        torque = AXLE_FRONT * f_f * cd - AXLE_REAR * f_r
        if self.stagger <= 0:
            # stability assist: nudge the spin rate toward the one the wheels are steering for
            omega_kin = v_long * math.tan(self.steer_angle) / WHEELBASE
            torque -= STABILITY * (self.omega - omega_kin) * CAR_INERTIA * m

        wx = fx * c - fy * s                    # to world
        wy = fx * s + fy * c
        speed = math.hypot(vx, vy)
        if speed > 1e-6:
            off = 0.5 * (self.off_f + self.off_r)
            res = (ROLL_RESIST + AIR_DRAG * speed * speed) * (1 + off * GRASS_RESIST) * m
            res = min(res, speed * m / h)       # resistance can stop the kart, never reverse it
            wx -= vx / speed * res
            wy -= vy / speed * res

        self.vx += wx / m * h
        self.vy += wy / m * h
        self.omega += torque / (CAR_INERTIA * m) * h
        self.omega *= max(0.0, 1 - YAW_DAMP * h)
        self.omega = max(-MAX_SPIN, min(MAX_SPIN, self.omega))
        self.x = (self.x + self.vx * h) % WORLD
        self.y = (self.y + self.vy * h) % WORLD
        self.angle += math.degrees(self.omega * h)
        self.slip_f, self.slip_r = abs(u_f), abs(u_r)

    def post_frame(self, dt):
        self.race_t += dt
        self.bash_cd = max(0.0, self.bash_cd - dt)
        self.bash_time = max(0.0, self.bash_time - dt)
        self.boost_time = max(0.0, self.boost_time - dt)
        self.stagger = max(0.0, self.stagger - dt)
        self.flash = max(0.0, self.flash - dt)
        self.grudge_time = max(0.0, self.grudge_time - dt)
        if self.grudge_time <= 0:
            self.grudge = 0

        # lose half a heart the moment you leave the road (edge-triggered + a cooldown)
        on_road = offroad_factor(self.x, self.y) <= 0.0
        self.heart_cooldown = max(0.0, self.heart_cooldown - dt)
        if self.was_on_road and not on_road and self.heart_cooldown <= 0.0:
            self.hearts = max(0.0, self.hearts - HEART_PENALTY)
            self.heart_cooldown = HEART_COOLDOWN
            play("crash")
        if self.hearts <= 0.0 and not self.dead:
            self.dead = True
            play("death")
            spawn_particles(self.x, self.y, 20, 150, (90, 90, 95), 0.8)
        self.was_on_road = on_road

        # wedged against something? back up for a moment; still stuck after that -> rescue
        # (not for an eliminated kart: it's meant to coast to a stop and stay put, not keep
        # getting rescued back onto the road)
        speed = math.hypot(self.vx, self.vy)
        if self.dead:
            self.wedged = self.slow_time = self.reverse_time = 0.0
        elif speed < STUCK_SPEED:
            self.wedged += dt
        elif speed > 2 * STUCK_SPEED:
            self.wedged = 0.0
        if self.dead:
            pass
        elif self.wedged > RESCUE_TIME:
            self.rescue()
        elif self.reverse_time > 0:
            self.reverse_time = max(0.0, self.reverse_time - dt)
        elif speed < STUCK_SPEED:
            self.slow_time += dt
            if self.slow_time > STUCK_TIME:
                self.reverse_time = REVERSE_TIME
                self.slow_time = 0.0
        else:
            self.slow_time = 0.0

        # skid marks where the tyres slide on dirt; dust where they churn up grass
        self.trail = [[tx, ty, life - dt] for tx, ty, life in self.trail if life - dt > 0]
        rad = math.radians(self.angle)
        c, s = math.cos(rad), math.sin(rad)
        for slip, ax, off in ((self.slip_r, -AXLE_REAR, self.off_r), (self.slip_f, AXLE_FRONT, self.off_f)):
            if slip > SKID_SLIP and off < 0.5:
                for side in (-1, 1):
                    self.trail.append([self.x + c * ax - s * side * WHEEL_Y,
                                       self.y + s * ax + c * side * WHEEL_Y, TRAIL_LIFE])
        if len(self.trail) > TRAIL_MAX_POINTS:
            self.trail = self.trail[-TRAIL_MAX_POINTS:]
        if self.off_r > 0.3 and speed > 60 and self.rng.random() < 0.6:
            spawn_particles(self.x - c * AXLE_REAR, self.y - s * AXLE_REAR, 1, 30, (120, 150, 70), 0.5)
        elif self.slip_r > SKID_SLIP * 2 and self.rng.random() < 0.4:
            spawn_particles(self.x - c * AXLE_REAR, self.y - s * AXLE_REAR, 1, 25, (205, 150, 110), 0.5)

    def rescue(self):
        # back onto the road beside where it got stuck, pointing the right way, at rest
        self.rescues += 1
        s, lat, self.track_idx = track_coords(self.x, self.y, self.track_idx)
        half = ROAD_WIDTH / 2 - 2 * CAR_HW
        self.x, self.y, self.angle = road_pose(s, max(-half, min(half, lat * 0.5)))
        self.vx = self.vy = self.omega = self.steer_angle = 0.0
        self.track_s = s
        self.wedged = self.slow_time = self.reverse_time = 0.0
        self.flash = 0.6
        spawn_particles(self.x, self.y, 14, 80, (255, 255, 255), 0.5)

    def corners(self):
        rad = math.radians(self.angle)
        c, s = math.cos(rad), math.sin(rad)
        return [(self.x + px, self.y + py) for px, py in _corners_local(c, s, CAR_HL, CAR_HW)]


def make_bot(car, i, color):
    p = BOT_PROFILES[i % len(BOT_PROFILES)]
    car.is_bot = True
    car.name = BOT_NAMES[i % len(BOT_NAMES)]
    car.flag = random.choice(FLAG_CODES) if FLAG_CODES else None
    car.color = color
    car.aggression = p["aggression"]
    car.lanes = p["lanes"]
    car.base_pace = car.pace = p.get("pace", 1.0)
    car.mass = p.get("mass", 1.0)
    car.hunts_player = p.get("hunts_player", False)
    car.rng = random.Random(7919 * (i + 1))
    car.ai_think = car.rng.uniform(0.5, 2.0)
    return car

def spawn_grid(count):
    # start grid on the bottom straight: rows of two, front row first
    cars = []
    s0 = ROAD_S[GRID_START]
    for k in range(count):
        row, col = divmod(k, 2)
        x, y, ang = road_pose(s0 - row * GRID_ROW_GAP, GRID_LANE if col else -GRID_LANE)
        cars.append(Car(x, y, ang, (200, 200, 200)))
    return cars


# =================================================================================================
# collisions
# =================================================================================================
def _corners_local(c, s, hl, hw):
    return [(hl * c - hw * s, hl * s + hw * c), (hl * c + hw * s, hl * s - hw * c),
            (-hl * c + hw * s, -hl * s - hw * c), (-hl * c - hw * s, -hl * s + hw * c)]

def _deepest(pts, ux, uy):
    # the point furthest along (ux, uy); if two are nearly level (edge on edge), their middle
    proj = sorted(((px * ux + py * uy, px, py) for px, py in pts), reverse=True)
    (d0, x0, y0), (d1, x1, y1) = proj[0], proj[1]
    if d0 - d1 < 1.0:
        return (x0 + x1) / 2, (y0 + y1) / 2
    return x0, y0

def _collide_cars(cars):
    n = len(cars)
    for i in range(n):
        a = cars[i]
        for j in range(i + 1, n):
            b = cars[j]
            dx, dy = wrap_delta(a.x, b.x), wrap_delta(a.y, b.y)
            if dx * dx + dy * dy > 4 * CAR_BOUND * CAR_BOUND:
                continue
            ra, rb = math.radians(a.angle), math.radians(b.angle)
            ca, sa, cb, sb = math.cos(ra), math.sin(ra), math.cos(rb), math.sin(rb)
            best, nx, ny, bk = None, 0.0, 0.0, 0
            for k, (ux, uy) in enumerate(((ca, sa), (-sa, ca), (cb, sb), (-sb, cb))):
                pa = CAR_HL * abs(ca * ux + sa * uy) + CAR_HW * abs(-sa * ux + ca * uy)
                pb = CAR_HL * abs(cb * ux + sb * uy) + CAR_HW * abs(-sb * ux + cb * uy)
                d = dx * ux + dy * uy
                ov = pa + pb - abs(d)
                if ov <= 0:
                    best = None
                    break
                if best is None or ov < best:
                    best, bk = ov, k
                    nx, ny = (ux, uy) if d >= 0 else (-ux, -uy)
            if best is None:
                continue
            if bk < 2:      # pushing along one of a's faces: b's corner that's deepest in a
                px, py = _deepest([(dx + qx, dy + qy) for qx, qy in _corners_local(cb, sb, CAR_HL, CAR_HW)],
                                  -nx, -ny)
            else:           # along one of b's faces: a's corner that's deepest in b
                px, py = _deepest(_corners_local(ca, sa, CAR_HL, CAR_HW), nx, ny)
            _resolve_pair(a, b, nx, ny, best, px, py, dx, dy)

def _resolve_pair(a, b, nx, ny, depth, px, py, dx, dy):
    # n points from a to b; (px, py) is the contact point relative to a; (dx, dy) = b - a
    ma = a.mass * (BASH_MASS if a.bash_time > 0 else 1.0)
    mb = b.mass * (BASH_MASS if b.bash_time > 0 else 1.0)
    inv_ma, inv_mb = 1 / ma, 1 / mb
    inv_ia, inv_ib = 1 / (CAR_INERTIA * ma), 1 / (CAR_INERTIA * mb)

    corr = max(depth - CONTACT_SLOP, 0.0) / (inv_ma + inv_mb)
    a.x = (a.x - nx * corr * inv_ma) % WORLD
    a.y = (a.y - ny * corr * inv_ma) % WORLD
    b.x = (b.x + nx * corr * inv_mb) % WORLD
    b.y = (b.y + ny * corr * inv_mb) % WORLD

    rax, ray = px, py
    rbx, rby = px - dx, py - dy
    rvx = (b.vx - b.omega * rby) - (a.vx - a.omega * ray)
    rvy = (b.vy + b.omega * rbx) - (a.vy + a.omega * rax)
    vn = rvx * nx + rvy * ny
    if vn >= 0:
        return      # already moving apart
    ran, rbn = rax * ny - ray * nx, rbx * ny - rby * nx
    k = inv_ma + inv_mb + ran * ran * inv_ia + rbn * rbn * inv_ib
    j = -(1 + CAR_RESTITUTION) * vn / k
    tx, ty = -ny, nx
    vt = rvx * tx + rvy * ty
    rat, rbt = rax * ty - ray * tx, rbx * ty - rby * tx
    kt = inv_ma + inv_mb + rat * rat * inv_ia + rbt * rbt * inv_ib
    jt = max(-CAR_FRICTION * j, min(CAR_FRICTION * j, -vt / kt))
    ix, iy = nx * j + tx * jt, ny * j + ty * jt         # impulse on b (a gets the opposite)
    a.vx -= ix * inv_ma
    a.vy -= iy * inv_ma
    a.omega -= (rax * iy - ray * ix) * inv_ia
    b.vx += ix * inv_mb
    b.vy += iy * inv_mb
    b.omega += (rbx * iy - rby * ix) * inv_ib
    a.impact = max(a.impact, j)
    b.impact = max(b.impact, j)
    wx, wy = a.x + px, a.y + py
    if j > 60:
        spawn_particles(wx, wy, min(int(j / 25), 10), 90, (250, 230, 150), 0.35)

    # a bash adds an extra shove + loose tyres + spin to whoever it hits, once per bash
    for basher, victim, sgn, rx, ry in ((a, b, 1, rbx, rby), (b, a, -1, rax, ray)):
        if basher.bash_time > 0 and victim.uid not in basher.bash_hits:
            basher.bash_hits.add(victim.uid)
            kx, ky = nx * sgn * BASH_KNOCK, ny * sgn * BASH_KNOCK
            victim.vx += kx
            victim.vy += ky
            victim.omega += (rx * ky - ry * kx) / (CAR_INERTIA * victim.mass) * BASH_SPIN
            victim.stagger = STAGGER_TIME
            victim.flash = 0.25
            victim.last_hit_by = basher.uid
            victim.grudge, victim.grudge_time = basher.uid, 5.0
            victim.impact = max(victim.impact, BASH_KNOCK * 1.5)
            spawn_particles(wx, wy, 12, 140, (255, 240, 170), 0.45)

def _collide_statics(car):
    near = set()
    r = CAR_BOUND
    for cx in range(int((car.x - r) // _STATIC_CELL), int((car.x + r) // _STATIC_CELL) + 1):
        for cy in range(int((car.y - r) // _STATIC_CELL), int((car.y + r) // _STATIC_CELL) + 1):
            near.update(_STATIC_HASH.get((cx, cy), ()))
    for idx in near:
        _collide_box(car, *STATICS[idx][1:])

def _collide_box(car, x0, y0, x1, y1):
    hx, hy = (x1 - x0) / 2, (y1 - y0) / 2
    bx, by = x0 + hx, y0 + hy
    dx, dy = wrap_delta(bx, car.x), wrap_delta(by, car.y)     # box -> car
    if abs(dx) > hx + CAR_BOUND or abs(dy) > hy + CAR_BOUND:
        return
    rad = math.radians(car.angle)
    c, s = math.cos(rad), math.sin(rad)
    best, nx, ny, bk = None, 0.0, 0.0, 0
    for k, (ux, uy) in enumerate(((1.0, 0.0), (0.0, 1.0), (c, s), (-s, c))):
        pc = CAR_HL * abs(c * ux + s * uy) + CAR_HW * abs(-s * ux + c * uy)
        pb = hx * abs(ux) + hy * abs(uy)
        d = dx * ux + dy * uy
        ov = pc + pb - abs(d)
        if ov <= 0:
            return
        if best is None or ov < best:
            best, bk = ov, k
            nx, ny = (ux, uy) if d >= 0 else (-ux, -uy)
    if bk < 2:      # a face of the fence: the kart's corner that's deepest in it
        px, py = _deepest(_corners_local(c, s, CAR_HL, CAR_HW), -nx, -ny)
    else:           # a face of the kart: the fence's corner that's deepest in it
        px, py = _deepest([(-dx + sx * hx, -dy + sy * hy) for sx in (-1, 1) for sy in (-1, 1)], nx, ny)
    _resolve_static(car, nx, ny, best, px, py)

def _resolve_static(car, nx, ny, depth, px, py):
    # n points out of the obstacle into the kart; (px, py) = contact point relative to the kart
    m = car.mass
    inertia = CAR_INERTIA * m
    corr = max(depth - CONTACT_SLOP, 0.0)
    car.x = (car.x + nx * corr) % WORLD
    car.y = (car.y + ny * corr) % WORLD
    vx, vy = car.vx - car.omega * py, car.vy + car.omega * px
    vn = vx * nx + vy * ny
    if vn >= 0:
        return
    rn = px * ny - py * nx
    j = -(1 + WALL_RESTITUTION) * vn / (1 / m + rn * rn / inertia)
    tx, ty = -ny, nx
    vt = vx * tx + vy * ty
    rt = px * ty - py * tx
    jt = max(-WALL_FRICTION * j, min(WALL_FRICTION * j, -vt / (1 / m + rt * rt / inertia)))
    ix, iy = nx * j + tx * jt, ny * j + ty * jt
    car.vx += ix / m
    car.vy += iy / m
    car.omega += (px * iy - py * ix) / inertia
    car.impact = max(car.impact, j)
    if j > 80:
        spawn_particles(car.x + px, car.y + py, min(int(j / 30), 8), 70, (90, 150, 80), 0.4)


# =================================================================================================
# the world step
# =================================================================================================
def _ctrl(c):
    # controls entries may be (steer, action) or (steer, action, drift)
    return c[0], c[1], (c[2] if len(c) > 2 else False)

def step(dt, cars, controls):
    # controls: one (steer -1..1, action or None[, drift]) per car; action = "left"/"right"/"ram"
    for car, ctrl in zip(cars, controls):
        steer, action, drift = _ctrl(ctrl)
        car.prepare()
        car.drift = bool(drift) and not car.dead
        if action:
            car.start_bash(action)
    h = dt / PHYS_SUBSTEPS
    for _ in range(PHYS_SUBSTEPS):
        for car, ctrl in zip(cars, controls):
            car.integrate(h, ctrl[0])
        _collide_cars(cars)
        for car in cars:
            _collide_statics(car)
    for car in cars:
        car.omega = max(-MAX_SPIN, min(MAX_SPIN, car.omega))   # collisions can add spin too
        car.post_frame(dt)
        _update_drift(car, dt)
        _spawn_car_fx(car)
        # race progress along the loop (forward and backward both count, so it's honest)
        s, _, car.track_idx = track_coords(car.x, car.y, car.track_idx)
        if car.track_s is not None:
            car.progress += (s - car.track_s + ROAD_LEN / 2) % ROAD_LEN - ROAD_LEN / 2
        car.track_s = s
        lap = lap_of(car)
        if lap > car.cur_lap and not car.dead:      # crossed the line into a new lap
            car.last_lap = car.race_t - car.last_lap_t
            car.best_lap = car.last_lap if car.best_lap <= 0 else min(car.best_lap, car.last_lap)
            car.last_lap_t = car.race_t
            car.cur_lap = lap
    hit = max((c.impact for c in cars), default=0.0)   # one impact sound per frame, hardest hit
    if hit > 180:
        play("crash")
    elif hit > 80:
        play("bump")
    _pack_pacing(cars)
    _update_boxes(dt, cars)
    _update_particles(dt)

def _update_drift(car, dt):
    speed = math.hypot(car.vx, car.vy)
    turning = abs(car.steer_angle) > 0.08
    if car.drift and speed > DRIFT_MIN_SPEED and turning:
        car.drift_charge = min(DRIFT_MAX_CHARGE, car.drift_charge + DRIFT_CHARGE_RATE * dt)
    if car.was_drifting and not car.drift:      # released
        if car.drift_charge >= DRIFT_MIN_CHARGE:
            f = min(1.0, car.drift_charge / DRIFT_MAX_CHARGE)
            car.boost_time = max(car.boost_time, DRIFT_BOOST_TIME * f)
            rad = math.radians(car.angle)
            car.vx += math.cos(rad) * DRIFT_BOOST_KICK * f
            car.vy += math.sin(rad) * DRIFT_BOOST_KICK * f
            spawn_particles(car.x, car.y, 10, 90, (120, 200, 255), 0.5)
        car.drift_charge = 0.0
    car.was_drifting = car.drift

def _spawn_car_fx(car):
    # surface dust off-road, boost flames, and the drift smoke that tints as the charge builds
    speed = math.hypot(car.vx, car.vy)
    off = 0.5 * (car.off_f + car.off_r)
    rad = math.radians(car.angle)
    bx, by = car.x - math.cos(rad) * CAR_HL, car.y - math.sin(rad) * CAR_HL
    if off > 0.2 and speed > 60 and random.random() < 0.5:
        spawn_particles(bx, by, 1, 40, (210, 200, 170), 0.5)   # kicked-up dust/grass
    if car.drift and speed > DRIFT_MIN_SPEED and random.random() < 0.7:
        f = car.drift_charge / DRIFT_MAX_CHARGE
        col = (235, 235, 235) if f < 0.5 else (255, 190, 90) if f < 0.9 else (120, 200, 255)
        spawn_particles(bx, by, 1, 50, col, 0.4)
    if car.boost_time > 0 and random.random() < 0.6:
        spawn_particles(bx, by, 1, 70, (255, 160, 60), 0.35)
    if car.impact > 70:        # sparks on a hard scrape / collision
        spawn_particles(car.x, car.y, 6, 150, (255, 240, 150), 0.3)

def _pack_pacing(cars):
    # keep the bots around the player (or around each other with no player): a bot that's
    # fallen behind gets a bit more engine, one that's run away ahead a bit less
    humans = [c for c in cars if not c.is_bot]
    ref = humans[0].progress if humans else sum(c.progress for c in cars) / max(len(cars), 1)
    for c in cars:
        if c.is_bot:
            gap = max(-1.0, min(1.0, (ref - c.progress) / AI_PACK_RANGE))
            c.pace = c.base_pace * (1 + (AI_CATCHUP * gap if gap > 0 else AI_EASE * gap))


# =================================================================================================
# bots
# =================================================================================================
def bot_control(bot, cars, dt):
    # Race along a lane of the road, and pick fights: lean on a rival alongside to push them,
    # side-bash them (especially when they're near the edge), ram anyone just ahead.
    s_pos, lat, idx = track_coords(bot.x, bot.y, bot.ai_index)
    bot.ai_index = idx
    rad = math.radians(bot.angle)
    c, s = math.cos(rad), math.sin(rad)
    v_long = bot.vx * c + bot.vy * s
    speed = math.hypot(bot.vx, bot.vy)
    half = ROAD_WIDTH / 2 - AI_EDGE_MARGIN
    rnd = bot.rng

    bot.ai_think -= dt
    if bot.ai_think <= 0:
        bot.ai_think = rnd.uniform(1.2, 3.0)
        bot.lane_target = rnd.uniform(-1, 1) * half * bot.lanes

    # pick the rival to deal with: nearest one around/ahead, grudges and the player first
    action = None
    target, best = None, None
    for o in cars:
        if o is bot:
            continue
        dx, dy = wrap_delta(bot.x, o.x), wrap_delta(bot.y, o.y)
        fx, fy = dx * c + dy * s, -dx * s + dy * c
        if fx < -50 or fx > 170 or abs(fy) > 90:
            continue
        score = abs(fx) + 1.5 * abs(fy)
        if o.uid == bot.grudge:
            score *= 0.4
        if bot.hunts_player and not o.is_bot:
            score *= 0.5
        if best is None or score < best:
            best, target, tfx, tfy = score, o, fx, fy

    lane_goal = bot.lane_target
    if target is not None and bot.reverse_time <= 0:
        _, t_lat, _ = track_coords(target.x, target.y, idx)
        aggr = min(1.0, bot.aggression * (1.6 if target.uid == bot.grudge else 1.0))
        if aggr > 0.45 and -30 < tfx < 110:
            lane_goal = t_lat                       # lean on them: drive into their lane
        elif 0 < tfx < 110 and abs(t_lat - lat) < 30:
            lane_goal = t_lat + (40 if t_lat < 0 else -40)   # not a fighter: go round them
        if bot.bash_cd <= 0:
            if abs(tfx) < 30 and 8 < abs(tfy) < 50:
                # alongside: a side-bash pushes them across the road -- best when that's off it
                push = 1 if t_lat > lat else -1
                edge_gap = half + AI_EDGE_MARGIN - push * t_lat
                p = aggr * AI_BASH_RATE * dt * (3.0 if edge_gap < 70 else 1.0)
                if rnd.random() < p:
                    action = "right" if tfy > 0 else "left"
            elif 16 < tfx < 60 and abs(tfy) < 18:
                closing = v_long - (target.vx * c + target.vy * s)
                if closing > 20 and rnd.random() < aggr * AI_RAM_RATE * dt:
                    action = "ram"

    if bot.off_f > 0.2 or bot.off_r > 0.2:
        lane_goal = 0.0                             # off the road: head straight back on
    lane_goal = max(-half, min(half, lane_goal))
    bot.lane += (lane_goal - bot.lane) * min(1.0, AI_LANE_RATE * dt)

    look = AI_LOOK_BASE + AI_LOOK_SPEED * speed
    tx, ty, _ = road_pose(s_pos + look, bot.lane)
    dx, dy = wrap_delta(bot.x, tx), wrap_delta(bot.y, ty)
    lx, ly = dx * c + dy * s, -dx * s + dy * c
    if bot.reverse_time > 0:
        # backing out of a jam: steer so the nose swings toward the road
        return (-1.0 if ly > 0 else 1.0), None
    # pure pursuit: the wheel angle that arcs the kart through the aim point
    alpha = math.atan2(ly, lx)
    delta = math.atan2(2 * WHEELBASE * math.sin(alpha), look)
    steer = delta / steer_limit(max(abs(v_long), 1.0))
    return max(-1.0, min(1.0, steer)), action


# =================================================================================================
# camera
# =================================================================================================
class Camera:
    def __init__(self, car):
        self.x, self.y = car.x, car.y
        self.angle = car.angle
        self.shake = 0.0
        self.ox = self.oy = 0.0

    def update(self, dt, car):
        t_pos = min(CAM_POS_SMOOTH * dt, 1)
        t_rot = min(CAM_ROT_SMOOTH * dt, 1)
        self.x = (self.x + wrap_delta(self.x, car.x) * t_pos) % WORLD
        self.y = (self.y + wrap_delta(self.y, car.y) * t_pos) % WORLD
        # face partly where the kart is going rather than where it points, so a slide or a
        # spin-out doesn't whip the whole screen round
        target = car.angle
        speed = math.hypot(car.vx, car.vy)
        if speed > 60:
            w = min(1.0, (speed - 60) / 120) * CAM_VEL_FOLLOW
            target = lerp_angle(car.angle, math.degrees(math.atan2(car.vy, car.vx)), w)
        self.angle = lerp_angle(self.angle, target, t_rot)
        self.shake = min(1.0, max(0.0, self.shake - dt * 2.5) + car.impact / SHAKE_IMPULSE)
        mag = SHAKE_PX * self.shake * self.shake
        self.ox, self.oy = random.uniform(-mag, mag), random.uniform(-mag, mag)

    def to_screen(self, wx, wy):
        dx, dy = wrap_delta(self.x, wx), wrap_delta(self.y, wy)
        rad = -math.radians(self.angle + 90)   # camera's forward points to the top of the screen
        c, s = math.cos(rad), math.sin(rad)
        return (W / 2 + (dx * c - dy * s) * ZOOM + self.ox,
                H / 2 + (dx * s + dy * c) * ZOOM + self.oy)


# =================================================================================================
# particles
# =================================================================================================
PARTICLES = []      # [x, y, vx, vy, life, max_life, (r, g, b)]

def spawn_particles(x, y, count, speed, color, life):
    for _ in range(count):
        if len(PARTICLES) >= MAX_PARTICLES:
            return
        a = random.uniform(0, math.tau)
        v = random.uniform(0.3, 1.0) * speed
        ttl = random.uniform(0.6, 1.0) * life
        PARTICLES.append([x, y, math.cos(a) * v, math.sin(a) * v, ttl, ttl, color])

def _update_particles(dt):
    keep = []
    for p in PARTICLES:
        p[4] -= dt
        if p[4] > 0:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[2] *= max(0.0, 1 - 4 * dt)
            p[3] *= max(0.0, 1 - 4 * dt)
            keep.append(p)
    PARTICLES[:] = keep

# ---- mystery boxes -----------------------------------------------------------------
BOXES = []          # [dict(x, y, phase, timer)]  timer > 0 -> taken, counting down to respawn
NET_ROLE = "off"    # off (single-player) | host | client -- who decides box pickups
BOX_EVENTS = []     # host collects (box_index, slot, kind) here each frame to broadcast

def spawn_boxes():
    del BOXES[:]
    if ROAD_LEN <= 1.0:
        return
    rng = random.Random(MAP_SEED)       # deterministic: every player gets the same boxes
    for i in range(BOX_COUNT):
        s = (i + 0.5) / BOX_COUNT * ROAD_LEN                     # evenly spaced around the loop
        lateral = rng.uniform(-1, 1) * ROAD_WIDTH * 0.5 * BOX_LATERAL
        x, y, _ = road_pose(s, lateral)
        kind = BOX_TYPES[i % len(BOX_TYPES)]                     # cycle yellow / blue / red
        BOXES.append({"x": x % WORLD, "y": y % WORLD, "kind": kind,
                      "phase": rng.uniform(0, 2 * math.pi), "timer": 0.0})

def give_powerup(car, kind):
    if kind == "boost":
        car.boost_time = BOOST_TIME
        rad = math.radians(car.angle)
        car.vx += math.cos(rad) * BOOST_KICK
        car.vy += math.sin(rad) * BOOST_KICK
    elif kind == "heart":
        car.hearts = min(HEART_COUNT, car.hearts + 1)
    elif kind == "bash":
        car.bash_cd = 0.0               # instant bash recharge
    car.flash = max(car.flash, 0.25)
    play("powerup2" if kind == "heart" else "powerup")
    return kind

def _update_boxes(dt, cars):
    reach_sq = (BOX_PICKUP + CAR_HW) ** 2
    for idx, b in enumerate(BOXES):
        b["phase"] += BOX_FLOAT_SPEED * dt
        if b["timer"] > 0:
            b["timer"] -= dt
            continue
        if NET_ROLE == "client":
            continue            # the host owns pickups; clients just animate the boxes
        for slot, car in enumerate(cars):
            if car.dead:
                continue
            dx = wrap_delta(b["x"], car.x)
            dy = wrap_delta(b["y"], car.y)
            if dx * dx + dy * dy <= reach_sq:
                give_powerup(car, b["kind"])
                b["timer"] = BOX_RESPAWN
                spawn_particles(b["x"], b["y"], 14, 130, BOX_COLORS[b["kind"]], 0.6)
                if NET_ROLE == "host":
                    BOX_EVENTS.append((idx, slot, b["kind"]))
                break

def apply_box_event(idx, kind):
    # a client marks a box as taken + plays the effect; the recipient's own powerup is
    # applied separately (only the local player applies it to its own car)
    if 0 <= idx < len(BOXES):
        b = BOXES[idx]
        b["timer"] = BOX_RESPAWN
        spawn_particles(b["x"], b["y"], 14, 130, BOX_COLORS.get(kind, (255, 215, 70)), 0.6)

def lap_of(car):
    # laps completed since the start line; progress is px driven along the loop
    if ROAD_LEN <= 1.0:
        return 0
    return max(0, int(car.progress / ROAD_LEN))

# ---- multiplayer car sync ----------------------------------------------------------
_NET_SNAP = ("vx", "vy", "omega", "steer_angle", "flash", "bash_time",
             "boost_time", "hearts", "progress", "slip_f", "slip_r",
             "dead", "last_lap", "best_lap")

def car_net_state(car):
    d = {"x": car.x, "y": car.y, "angle": car.angle}
    for k in _NET_SNAP:
        d[k] = getattr(car, k)
    return d

def apply_net_state(car, d, t=1.0):
    # move a remote car toward the latest snapshot: lerp pose for smoothness, snap the rest
    if not d:
        return
    car.x = (car.x + wrap_delta(car.x, d["x"]) * t) % WORLD
    car.y = (car.y + wrap_delta(car.y, d["y"]) * t) % WORLD
    car.angle = lerp_angle(car.angle, d["angle"], t)
    for k in _NET_SNAP:
        if k in d:
            setattr(car, k, d[k])


# =================================================================================================
# drawing
# =================================================================================================
ZOOM = 1.3          # camera zoom; >1 shows less of the world, bigger karts
_CHUNK = int(math.hypot(W, H) / ZOOM) + 8 * TILE   # baked-map square that still covers the screen
_chunk_surf = None
_overlay = None

def draw_ground(screen, cam):
    # Grass everywhere, then the part of the baked map around the camera, rotated to match it.
    global _chunk_surf
    screen.fill(GRASS_COLOR)
    if GROUND_SURF is None:
        return
    if _chunk_surf is None:
        # per-pixel alpha so rotate() pads the corners with transparent (not black); any screen
        # area the rotated chunk doesn't cover then shows the grass fill underneath
        _chunk_surf = pygame.Surface((_CHUNK, _CHUNK), pygame.SRCALPHA)
    ox, oy = GROUND_ORIGIN
    left = math.floor(cam.x - ox - _CHUNK / 2)   # chunk's top-left in baked-image pixels
    top = math.floor(cam.y - oy - _CHUNK / 2)
    _chunk_surf.fill(GRASS_COLOR)
    _chunk_surf.blit(GROUND_SURF, (-left, -top))  # pygame clips this to the overlap
    rot = pygame.transform.rotozoom(_chunk_surf, cam.angle + 90, ZOOM)  # rotate + zoom in one
    # put the chunk's centre exactly where the camera maps that world point, so the ground
    # and the karts never drift apart by a pixel
    sx, sy = cam.to_screen(ox + left + _CHUNK / 2, oy + top + _CHUNK / 2)
    screen.blit(rot, rot.get_rect(center=(round(sx), round(sy))))

def _get_overlay():
    global _overlay
    if _overlay is None:
        _overlay = pygame.Surface((W, H), pygame.SRCALPHA)
    _overlay.fill((0, 0, 0, 0))
    return _overlay

def draw_trails(screen, cars, cam):
    overlay = None
    for car in cars:
        for wx, wy, life in car.trail:
            sx, sy = cam.to_screen(wx, wy)
            if -6 <= sx <= W + 6 and -6 <= sy <= H + 6:
                if overlay is None:
                    overlay = _get_overlay()
                alpha = max(0, min(150, int(150 * life / TRAIL_LIFE)))
                pygame.draw.rect(overlay, (60, 35, 30, alpha), (int(sx) - 1, int(sy) - 1, 3, 3))
    if overlay is not None:
        screen.blit(overlay, (0, 0))

def draw_particles(screen, cam):
    if not PARTICLES:
        return
    overlay = _get_overlay()
    for x, y, _, _, life, max_life, col in PARTICLES:
        sx, sy = cam.to_screen(x, y)
        if -4 <= sx <= W + 4 and -4 <= sy <= H + 4:
            f = life / max_life
            size = 2 if f < 0.5 else 3
            overlay.fill((col[0], col[1], col[2], int(230 * f)), (int(sx) - 1, int(sy) - 1, size, size))
    screen.blit(overlay, (0, 0))

KART_BODY = [(14, -4), (14, 4), (9, 7), (-12, 7), (-14, 5), (-14, -5), (-12, -7), (9, -7)]
CABIN_BODY = [(6, -4), (7, 0), (6, 4), (-6, 4), (-6, -4)]    # cockpit, sits on the top slice
STACK_LAYERS = 7        # stacked slices faking height (sprite stacking)
STACK_LIFT = 1          # px each slice is drawn above the one below

def _shade(col, f):
    return (int(col[0] * f), int(col[1] * f), int(col[2] * f))

def draw_car(screen, car, cam):
    rad = math.radians(car.angle)
    c, s = math.cos(rad), math.sin(rad)

    def pt(lx, ly):
        return cam.to_screen(car.x + lx * c - ly * s, car.y + lx * s + ly * c)

    # wheels (front ones turned by the steering) -- drawn flat on the ground, below the stack
    for ax, steer in ((AXLE_FRONT, car.steer_angle), (-AXLE_REAR, 0.0)):
        cw, sw = math.cos(steer), math.sin(steer)
        for side in (-1, 1):
            wy = side * WHEEL_Y
            pygame.draw.polygon(screen, (22, 22, 26), [
                pt(ax + wl * cw - ww * sw, wy + wl * sw + ww * cw)
                for wl, ww in ((3.5, 2.0), (3.5, -2.0), (-3.5, -2.0), (-3.5, 2.0))])

    body = [pt(lx, ly) for lx, ly in KART_BODY]
    lit = car.flash > 0 or car.bash_time > 0
    base_col = (90, 90, 95) if car.dead else car.color      # eliminated karts go grey
    # sprite stacking: the same body slice drawn bottom-to-top, each a pixel higher and
    # a little brighter, so the kart reads as a solid block with height
    for k in range(STACK_LAYERS):
        off = -k * STACK_LIFT
        f = 0.55 + 0.45 * (k / (STACK_LAYERS - 1))
        pygame.draw.polygon(screen, _shade(base_col, f), [(x, y + off) for x, y in body])
    top_off = -(STACK_LAYERS - 1) * STACK_LIFT
    top = [(x, y + top_off) for x, y in body]
    pygame.draw.polygon(screen, (255, 255, 255), top, 3 if lit else 2)   # white stroke on the roof
    cabin = [(pt(lx, ly)[0], pt(lx, ly)[1] + top_off) for lx, ly in CABIN_BODY]
    pygame.draw.polygon(screen, (40, 44, 58), cabin)
    pygame.draw.polygon(screen, (120, 160, 210), cabin, 1)
    hx, hy = pt(13, 0)                                   # headlight at the nose, up on the roof
    pygame.draw.circle(screen, (255, 250, 220), (int(hx), int(hy + top_off)), 2)

def _text_outlined(font, text, color, outline=(15, 15, 20)):
    # text with a 1px dark outline so it stays readable with no background box
    base = font.render(text, True, color)
    w, h = base.get_size()
    surf = pygame.Surface((w + 2, h + 2), pygame.SRCALPHA)
    edge = font.render(text, True, outline)
    for dx, dy in ((0, 1), (2, 1), (1, 0), (1, 2), (0, 0), (2, 0), (0, 2), (2, 2)):
        surf.blit(edge, (dx, dy))
    surf.blit(base, (1, 1))
    return surf

def draw_ghost(screen, cam, x, y, angle):
    # faint outline of your best-lap ghost in Time Trial
    rad = math.radians(angle)
    c, s = math.cos(rad), math.sin(rad)
    pts = [cam.to_screen(x + lx * c - ly * s, y + lx * s + ly * c) for lx, ly in KART_BODY]
    pygame.draw.polygon(screen, (190, 215, 255), pts, 2)

def draw_name_labels(screen, cars, cam):
    font = get_font(18)
    for car in cars:
        sx, sy = cam.to_screen(car.x, car.y)
        if not (-60 <= sx <= W + 60 and -40 <= sy <= H + 60):
            continue
        label = _text_outlined(font, car.name, (255, 255, 255))
        flag = get_flag(car.flag, 12) if car.flag else None
        lw, lh = label.get_size()
        fw = (flag.get_width() + 4) if flag else 0
        total = lw + fw
        x0 = int(sx - total / 2)
        y = int(sy - 26)
        if flag:
            fr = flag.get_rect()
            screen.blit(flag, (x0, y + (lh - fr.h) // 2))
            pygame.draw.rect(screen, (230, 230, 230), (x0, y + (lh - fr.h) // 2, fr.w, fr.h), 1)
        screen.blit(label, (x0 + fw, y))

def draw_box(screen, box, cam):
    sx, sy = cam.to_screen(box["x"], box["y"])
    if not (-BOX_SIZE <= sx <= W + BOX_SIZE and -BOX_SIZE <= sy <= H + BOX_SIZE):
        return
    bob = math.sin(box["phase"]) * BOX_FLOAT_AMP
    r = BOX_SIZE // 2
    cy = sy + bob
    # ground shadow stays put while the box bobs, so it reads as floating
    shadow = pygame.Surface((BOX_SIZE, 7), pygame.SRCALPHA)
    pygame.draw.ellipse(shadow, (0, 0, 0, 90), shadow.get_rect())
    screen.blit(shadow, (int(sx - r), int(sy + r)))
    rect = pygame.Rect(int(sx - r), int(cy - r), BOX_SIZE, BOX_SIZE)
    kind = box.get("kind", "boost")
    pygame.draw.rect(screen, BOX_COLORS[kind], rect, border_radius=5)
    pygame.draw.rect(screen, (255, 255, 255), rect, 2, border_radius=5)
    q = get_font(22).render(BOX_LETTER[kind], True, (25, 25, 30))
    screen.blit(q, q.get_rect(center=rect.center))

def draw_boxes(screen, cam):
    for box in BOXES:
        if box["timer"] <= 0:
            draw_box(screen, box, cam)

def draw_world(screen, cam, cars):
    draw_ground(screen, cam)
    draw_trails(screen, cars, cam)
    draw_boxes(screen, cam)
    for car in cars:
        draw_car(screen, car, cam)
    draw_particles(screen, cam)
    draw_name_labels(screen, cars, cam)

def _heart_points(x, y, size):
    s = size * 0.5
    norm = [
        (0, -0.3), (0.3, -0.75), (0.65, -0.95), (1.0, -0.7),
        (1.0, -0.25), (0.5, 0.35), (0, 0.9),
        (-0.5, 0.35), (-1.0, -0.25), (-1.0, -0.7),
        (-0.65, -0.95), (-0.3, -0.75),
    ]
    return [(x + px * s, y + py * s) for px, py in norm]

def draw_heart(screen, x, y, size, fill_frac):
    empty_color = (70, 70, 70)
    full_color = (220, 30, 60)
    pts = _heart_points(x, y, size)
    if fill_frac <= 0.0:
        pygame.draw.polygon(screen, empty_color, pts, 2)
        return
    pygame.draw.polygon(screen, full_color, pts)
    if fill_frac < 1.0:
        left = x - size * 0.5
        fill_w = fill_frac * size
        clip = pygame.Rect(int(left + fill_w), int(y - size), int(size - fill_w) + 1, int(size * 2))
        screen.set_clip(clip)
        pygame.draw.polygon(screen, empty_color, pts, 0)
        screen.set_clip(None)
        pygame.draw.polygon(screen, full_color, pts, 2)

HEART_SIZE = 26     # px, on-screen size of one heart icon

def draw_hearts(screen, hearts):
    img = UI.get("heart")
    if img is None:     # icon missing -> fall back to the old vector hearts
        for i in range(HEART_COUNT):
            frac = max(0.0, min(1.0, hearts - i))
            draw_heart(screen, 20 + i * 26, 20, 20, frac)
        return
    size, gap = HEART_SIZE, 4
    full = pygame.transform.scale(img, (size, size))    # scale (not smoothscale): keep crisp pixels
    empty = full.copy()
    empty.fill((70, 70, 70, 255), special_flags=pygame.BLEND_RGBA_MULT)  # dimmed = lost heart
    for i in range(HEART_COUNT):
        frac = max(0.0, min(1.0, hearts - i))
        x, y = 14 + i * (size + gap), 12
        screen.blit(empty, (x, y))
        if frac > 0:    # left slice of the full heart = how much of this one is left
            screen.blit(full, (x, y), pygame.Rect(0, 0, max(1, int(size * frac)), size))

def fmt_time(t):
    if t <= 0:
        return "--.---"
    m = int(t // 60)
    s = t - 60 * m
    return f"{m}:{s:06.3f}" if m else f"{s:.3f}"

def draw_leaderboard(screen, cars, player):
    # live running order (furthest along the loop = 1st); eliminated karts drop to the bottom
    order = sorted(cars, key=lambda c: (c.dead, -c.progress))
    font = get_font(22)
    row_h = 19
    w = 176
    x, y0 = W - w - 10, 14          # top-right corner, no background panel
    head = _text_outlined(font, "LEADERBOARD", (220, 230, 210))
    screen.blit(head, (x, y0 - 4))
    for i, c in enumerate(order):
        yc = y0 + 18 + i * row_h
        name = c.name                      # the player's row is already highlighted yellow
        color = (255, 235, 120) if c is player else (235, 235, 235)
        pygame.draw.circle(screen, c.color, (x + 6, yc + 8), 4)
        pygame.draw.circle(screen, (255, 255, 255), (x + 6, yc + 8), 4, 1)
        screen.blit(_text_outlined(font, f"{i + 1}.", color), (x + 12, yc))
        tx = x + 34
        flag = get_flag(c.flag, 11) if c.flag else None
        if flag:
            screen.blit(flag, (tx, yc + 4))
            pygame.draw.rect(screen, (30, 30, 30), (tx, yc + 4, flag.get_width(), flag.get_height()), 1)
            tx += flag.get_width() + 3
        screen.blit(_text_outlined(font, name, (170, 110, 110) if c.dead else color), (tx, yc))
        if c.dead:
            tag = _text_outlined(font, "OUT", (230, 110, 110))
        else:
            tag = _text_outlined(font, f"L{min(lap_of(c) + 1, TOTAL_LAPS)}", (185, 200, 180))
        screen.blit(tag, tag.get_rect(topright=(x + w - 6, yc)))

    # the player's lap count, x / y, under the board
    cur = min(lap_of(player) + 1, TOTAL_LAPS)
    lap_s = _text_outlined(get_font(26), f"LAP {cur}/{TOTAL_LAPS}", (255, 235, 120))
    screen.blit(lap_s, lap_s.get_rect(topright=(x + w - 6, y0 + 18 + len(order) * row_h + 4)))

def _pixel_bar(screen, color, rect, r=2):
    # a filled bar with chunky (pixel-art) rounded corners: a plus of two rects
    x, y, w, h = rect
    if w <= 0 or h <= 0:
        return
    if w <= 2 * r or h <= 2 * r:
        pygame.draw.rect(screen, color, rect)
        return
    pygame.draw.rect(screen, color, (x + r, y, w - 2 * r, h))
    pygame.draw.rect(screen, color, (x, y + r, w, h - 2 * r))

def draw_hud(screen, car, font=None, cars=None):
    draw_hearts(screen, car.hearts)
    # bash meter under the hearts: one blue bar, rounded pixel corners, no label
    x, y, w, h = 14, 44, 76, 9
    ready = 1.0 - car.bash_cd / BASH_COOLDOWN
    _pixel_bar(screen, (28, 30, 38), (x - 1, y - 1, w + 2, h + 2), r=2)
    _pixel_bar(screen, (70, 150, 255), (x, y, int(w * ready), h), r=2)
    # lap time (current) + best, top-centre
    tf = get_font(22)
    cur = max(0.0, car.race_t - car.last_lap_t)
    lap_s = tf.render(f"LAP  {fmt_time(cur)}", True, (255, 255, 255))
    best_s = tf.render(f"BEST {fmt_time(car.best_lap)}", True, (255, 235, 120))
    screen.blit(lap_s, lap_s.get_rect(midtop=(W / 2, 6)))
    screen.blit(best_s, best_s.get_rect(midtop=(W / 2, 24)))
    if cars is not None:
        draw_leaderboard(screen, cars, car)
        draw_minimap(screen, cars, car)
