import math
import os
import random
import time
from bisect import bisect_right
from collections import deque
import pygame

import sys

# ---- sprite-stack props (merged from ramps.py) -----------------------------
class _RampsModule:
    RAMP_NAMES = ("wood",)
    SCALE = 2
    SCALE_1X = ("tree_",)
    OUTLINED = ("tree_", "crate", "barrel", "vase", "cone")
    OUTLINE_COLOR = (20, 22, 26)
    OUTLINE_BY_NAME = {"mystery_box": (255, 255, 255)}
    SIZE_TRIM = {n: 10.0 for n in
                  ("tree_tall", "tree_round", "tree_bushy", "crate", "barrel", "vase", "cone")}
    ROT_STEPS = 90
    CACHE_MAX = 1500

    def __init__(self):
        self._SLICES = {}
        self._CONF = {}
        self._CACHE = {}

    def _load_strip(self, path):
        sheet = pygame.image.load(path).convert_alpha()
        n = sheet.get_height()
        return [sheet.subsurface((i * n, 0, n, n)).copy() for i in range(sheet.get_width() // n)]

    def load_stack(self, name, path, scale=None, outline=None):
        self._SLICES[name] = self._load_strip(path)
        if scale is None:
            scale = 1 if name.startswith(self.SCALE_1X) else self.SCALE
        if outline is None and name in self.OUTLINE_BY_NAME:
            outline = self.OUTLINE_BY_NAME[name]
        elif outline is None and name.startswith(self.OUTLINED):
            outline = self.OUTLINE_COLOR
        self._CONF[name] = (scale, outline)
        for key in [k for k in self._CACHE if k[1] == name]:
            del self._CACHE[key]

    def has(self, name):
        return name in self._SLICES

    def load(self, asset_dir):
        self._SLICES.clear()
        self._CONF.clear()
        self._CACHE.clear()
        folder = os.path.join(asset_dir, "props", "ramps")
        if not os.path.isdir(folder):
            folder = os.path.join(asset_dir, "ramps")
        for name in self.RAMP_NAMES:
            p = os.path.join(folder, f"ramp_{name}_stack.png")
            if os.path.exists(p):
                self.load_stack(name, p)
        props = os.path.join(asset_dir, "props")
        if os.path.isdir(props):
            for fn in sorted(os.listdir(props)):
                if fn.startswith("tire_stack_") and fn[-5].isdigit():
                    self.load_stack("tires" + fn[-5], os.path.join(props, fn))
                elif fn.endswith("_stack.png"):
                    self.load_stack(fn[:-len("_stack.png")], os.path.join(props, fn))

    def _width(self, name):
        z = globals().get("ZOOM", 1.68)
        base = self._SLICES[name][0].get_width() * self._CONF[name][0] - self.SIZE_TRIM.get(name, 0.0)
        return max(2, int(base * z))

    def _scaled(self, name, w):
        key = ("scaled", name, w)
        out = self._CACHE.get(key)
        if out is None:
            out = [pygame.transform.scale(s, (w, w)) for s in self._SLICES[name]]
            self._CACHE[key] = out
        return out

    def _bucket(self, deg):
        return int(round(deg / 360.0 * self.ROT_STEPS)) % self.ROT_STEPS

    def _remember(self, key, value):
        if len(self._CACHE) > self.CACHE_MAX:
            self._CACHE.clear()
        self._CACHE[key] = value
        return value

    def _composite(self, name, w, b):
        z = globals().get("ZOOM", 1.68)
        lift_val = 0.72 if name == "mystery_box" else globals().get("CAR_STACK_LIFT", 1.34)
        key = ("comp", name, w, b, z)
        hit = self._CACHE.get(key)
        if hit is not None:
            return hit
        rot = b * 360.0 / self.ROT_STEPS
        imgs = [pygame.transform.rotate(sl, rot) for sl in self._scaled(name, w)]
        rw, rh = imgs[0].get_size()
        lift = lift_val * z
        top = int(math.ceil((len(imgs) - 1) * lift))
        outline = self._CONF[name][1]
        stroke = max(1, int(round(z))) if outline else 0
        pad = stroke + 1
        body = pygame.Surface((rw + 2 * pad, rh + top + 2 * pad), pygame.SRCALPHA)
        for k, img in enumerate(imgs):
            body.blit(img, (pad, pad + top - int(round(k * lift))))
        if outline:
            mask = body.copy()
            mask.fill(outline + (255,), special_flags=pygame.BLEND_RGB_MAX)
            out = pygame.Surface(body.get_size(), pygame.SRCALPHA)
            for dx, dy in ((-stroke, 0), (stroke, 0), (0, -stroke), (0, stroke),
                           (-stroke, -stroke), (stroke, -stroke), (-stroke, stroke), (stroke, stroke)):
                out.blit(mask, (dx, dy))
            out.blit(body, (0, 0))
            body = out
        return self._remember(key, (body, pad + rw / 2.0, pad + top + rh / 2.0))

    def _screen_rot(self, cam, x, y, angle):
        sx0, sy0 = cam.to_screen(x, y)
        rad = math.radians(angle)
        sxf, syf = cam.to_screen(x + math.cos(rad), y + math.sin(rad))
        return sx0, sy0, -math.degrees(math.atan2(syf - sy0, sxf - sx0))

    def draw(self, screen, cam, name, x, y, angle=0.0, hover=0.0):
        if name not in self._SLICES:
            return
        sx0, sy0, rot = self._screen_rot(cam, x, y, angle)
        z = globals().get("ZOOM", 1.68)
        sy0 -= hover * z
        w = self._width(name)
        if not (-2 * w <= sx0 <= W + 2 * w and -2 * w <= sy0 <= H + 3 * w):
            return
        surf, ax, ay = self._composite(name, w, self._bucket(rot))
        screen.blit(surf, (round(sx0 - ax), round(sy0 - ay)))

    def draw_shadow(self, screen, cam, name, x, y, angle=0.0):
        return

ramps = _RampsModule()
sys.modules['ramps'] = ramps

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
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))   # load_assets falls back to ROOT_DIR/assets
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
TILESETS = ["meadow_dirt", "asphalt_circuit", "canyon_sand", "frost_pass", "harvest_mud", "neon_night"]
TILESET_TITLES = {
    "meadow_dirt": "Meadow Dirt",
    "asphalt_circuit": "Grand Prix Circuit",
    "canyon_sand": "Red Canyon",
    "frost_pass": "Frost Pass",
    "harvest_mud": "Harvest Mud",
    "neon_night": "Neon Night",
}
CURRENT_TILESET = "meadow_dirt"
TRACK_TYPE_MODE = "meadow_dirt"
SKID_ROAD_COLOR = (46, 28, 22)
SKID_GRASS_COLOR = (40, 42, 24)

def get_tileset_dir(tileset_name):
    d = os.path.join(ASSET_DIR, "tilesets", tileset_name, "track_tiles")
    if os.path.isdir(d):
        return d
    fallback = os.path.join(ASSET_DIR, "track_tiles")
    if os.path.isdir(fallback):
        return fallback
    return d

def get_tileset_oil_path(tileset_name):
    p = os.path.join(ASSET_DIR, "tilesets", tileset_name, "oil_track.png")
    if os.path.isfile(p):
        return p
    fallback = os.path.join(ASSET_DIR, "track_tiles", "oil_track.png")
    if os.path.isfile(fallback):
        return fallback
    fallback2 = os.path.join(ASSET_DIR, "oil_track.png")
    if os.path.isfile(fallback2):
        return fallback2
    return p

FENCE_TILE_DIR = os.path.join(ASSET_DIR, "fence_tiles")
FX_DIR = os.path.join(ASSET_DIR, "fx")
CAR_DIR = os.path.join(ASSET_DIR, "car")
DECOR_DIR = os.path.join(ASSET_DIR, "decor")
PROPS_DIR = os.path.join(ASSET_DIR, "props")
# Each fence piece is a post with rails out to the neighbouring posts. The file name says which
# way the rails go (u/d/l/r). Whether there's a rail going up only changes the tile's top pixel
# row, so these 11 cover all 16 combinations: (down, left, right) -> file to start from.
FENCE_SOURCES = {
    (1, 0, 1): "fence_dr", (1, 1, 1): "fence_dlr", (1, 1, 0): "fence_dl", (1, 0, 0): "fence_ud",
    (0, 0, 0): "fence_u", (0, 0, 1): "fence_ur", (0, 1, 1): "fence_ulr", (0, 1, 0): "fence_ul",
}
FENCE_UP_ROW_FROM = "fence_ud"  # its top row is the rail going up
FENCE_COLOR = (117, 83, 56)     # flat fallback if the fence tiles are missing

# ---- sun and shadows ----------------------------------------------------------------
SUN_ANGLE = 55.0            # world-space direction sunlight travels towards (degrees)
SUN_DIR_X = math.cos(math.radians(SUN_ANGLE))
SUN_DIR_Y = math.sin(math.radians(SUN_ANGLE))
FENCE_SHADOW_DIST = 16.0    # world px post shadow projection (bolder, longer)
FENCE_SHADOW_COLOR = (10, 12, 22, 175) # rich, dark, visible contrast
CAR_SHADOW_DIST = 9.0       # world px car shadow projection
CAR_SHADOW_COLOR = (10, 15, 25, 140)

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

# the synthesised sound set (assets/sound/sfx/*.wav): event name ->
# its variants (one is picked at random each time, so repeated hits don't sound identical)
SFX_DIR = os.path.join(SOUND_DIR, "sfx")
SFX = {
    "bash": ["bash"], "ram": ["ram"], "bash_hit": ["bash_hit1", "bash_hit2", "bash_hit3"],
    "bump": ["bump1", "bump2", "bump3"], "crash": ["crash1", "crash2"],
    "shoot": ["shoot"], "proj_hit": ["proj_hit"],
    "cone_throw": ["cone_throw"], "cone_drop": ["cone_drop"], "cone_hit": ["cone_hit1", "cone_hit2"],
    "cone_smack": ["cone_smack"], "oil_spill": ["oil_spill"], "oil_slip": ["oil_slip"],
    "pickup_boost": ["pickup_boost"], "pickup_heart": ["pickup_heart"], "pickup_bash": ["pickup_bash"],
    "pickup_item": ["pickup_item"],
    "drift_boost": ["drift_boost"], "drift_boost_max": ["drift_boost_max"],
    "drift_tick1": ["drift_tick1"], "drift_tick2": ["drift_tick2"], "slipstream": ["slipstream"],
    "ramp_launch": ["ramp_launch"], "land": ["land"], "tire_hit": ["tire_hit1", "tire_hit2"],
    "break_wood": ["break_wood1", "break_wood2"], "break_vase": ["break_vase"], "prop_bump": ["prop_bump"],
    "heart_lost": ["heart_lost"], "death": ["death"], "wreck": ["wreck"], "rescue": ["rescue"],
    "lap": ["lap"], "final_lap": ["final_lap"], "finish": ["finish"], "game_over": ["game_over"],
    "count_beep": ["count_beep"], "count_go": ["count_go"], "pos_up": ["pos_up"], "pos_down": ["pos_down"],
    "takedown": ["takedown"], "eliminated": ["eliminated"],
    "ui_move": ["ui_move"], "ui_click": ["ui_click"], "ui_back": ["ui_back"], "pause": ["pause"],
    "resume": ["resume"],
    # old names still used by a few call sites
    "powerup": ["pickup_item"], "powerup2": ["pickup_heart"],
}
SFX_VOL = {         # mix levels (x the SFX slider)
    "bash": 0.55, "ram": 0.6, "bash_hit": 0.8, "bump": 0.45, "crash": 0.75, "shoot": 0.45,
    "proj_hit": 0.65, "cone_throw": 0.5, "cone_drop": 0.5, "cone_hit": 0.55, "cone_smack": 0.6,
    "oil_spill": 0.55, "oil_slip": 0.5, "pickup_boost": 0.55, "pickup_heart": 0.6, "pickup_bash": 0.5,
    "pickup_item": 0.55, "drift_boost": 0.55, "drift_boost_max": 0.6, "drift_tick1": 0.35,
    "drift_tick2": 0.4, "slipstream": 0.45, "ramp_launch": 0.6, "land": 0.55, "tire_hit": 0.6,
    "break_wood": 0.65, "break_vase": 0.6, "prop_bump": 0.4, "heart_lost": 0.6, "death": 0.85,
    "wreck": 0.6, "rescue": 0.5, "lap": 0.6, "final_lap": 0.6, "finish": 0.65, "game_over": 0.6,
    "count_beep": 0.45, "count_go": 0.5, "pos_up": 0.3, "pos_down": 0.25, "takedown": 0.65,
    "eliminated": 0.4, "ui_move": 0.25, "ui_click": 0.35, "ui_back": 0.3, "pause": 0.35,
    "resume": 0.35, "powerup": 0.55, "powerup2": 0.6,
}
SFX_COOLDOWN = {    # min seconds between two plays of the same event (stops scrape spam)
    "bump": 0.07, "crash": 0.09, "bash_hit": 0.05, "tire_hit": 0.09, "cone_hit": 0.05,
    "prop_bump": 0.1, "oil_slip": 0.35, "land": 0.08, "drift_tick1": 0.1, "drift_tick2": 0.1,
    "pos_up": 1.2, "pos_down": 1.2, "ui_move": 0.03,   # the start scramble would chirp non-stop
}
SFX_RANGE = 650.0   # world px: positional sounds fade to nothing this far from the camera
LISTENER = None     # (x, y, camera angle) -- main.py sets it each frame during a race
_SFX_LAST = {}
_BANK = {}          # event -> [Sound, ...]
LOOP_NAMES = ("engine_1", "engine_2", "engine_3", "engine_4", "skid_loop", "gravel_loop", "boost_loop")
LOOP_VOL = {"engine": 0.32, "skid_loop": 0.35, "gravel_loop": 0.4, "boost_loop": 0.4}
_LOOPS = {}         # name -> (Sound, Channel)
_LOOP_LEVEL = {}

def init_audio():
    global _mixer_ready
    if _mixer_ready:
        return
    try:
        pygame.mixer.init()
        pygame.mixer.set_num_channels(32)
        pygame.mixer.set_reserved(len(LOOP_NAMES))     # the first channels belong to the loops
        _mixer_ready = True
    except pygame.error as e:
        print("audio unavailable:", e)

MASTER_VOLUME = 1.0     # primary audio bus volume (0.0 to 1.0)
SFX_VOLUME = 0.8        # combat & world effect volume (bashes, crashes, pickups)
MUSIC_VOLUME = 0.6      # background music volume
ENGINE_VOLUME = 0.8     # kart engine RPM loop volume
UI_VOLUME = 0.8         # menu & UI notification volume
SFX_MUTED = False       # True while in menus / attract mode -> silence all SFX
MASTER_MUTE = False     # player's global mute toggle (silences SFX + music)
_music_loaded = False
MUSIC_FILES = ("music.mp3", "music.ogg", "music.wav", "theme.mp3", "theme.ogg")
MUSIC_DIR = os.path.join(SOUND_DIR, "music")
MUSIC_END = pygame.USEREVENT + 1   # posted by pygame.mixer.music when a track finishes
_playlist = []
_playlist_i = 0

def _build_playlist():
    tracks = []
    if os.path.isdir(MUSIC_DIR):
        for fn in sorted(os.listdir(MUSIC_DIR)):
            if fn.lower().endswith((".mp3", ".ogg", ".wav")):
                tracks.append(os.path.join(MUSIC_DIR, fn))
    random.shuffle(tracks)
    return tracks

def _play_track(path):
    try:
        pygame.mixer.music.load(path)
        pygame.mixer.music.set_volume(0.0 if MASTER_MUTE else MUSIC_VOLUME)
        pygame.mixer.music.set_endevent(MUSIC_END)
        pygame.mixer.music.play()
    except pygame.error:
        pass

def next_track():
    # advances the shuffled playlist; called on MUSIC_END, reshuffles when it wraps
    global _playlist, _playlist_i
    if not _playlist:
        return
    _playlist_i += 1
    if _playlist_i >= len(_playlist):
        _playlist_i = 0
        random.shuffle(_playlist)
    _play_track(_playlist[_playlist_i])

def load_sounds():
    SOUNDS.clear()
    _BANK.clear()
    _LOOPS.clear()
    _LOOP_LEVEL.clear()
    if not _mixer_ready:
        return
    for key, fn in SOUND_FILES.items():     # fallback if sfx/ is missing
        try:
            s = pygame.mixer.Sound(os.path.join(SOUND_DIR, fn))
            s.set_volume(SOUND_VOL.get(key, 0.6) * SFX_VOLUME)
            SOUNDS[key] = s
        except (pygame.error, FileNotFoundError):
            pass
    for key, files in SFX.items():
        bank = []
        for fn in files:
            try:
                bank.append(pygame.mixer.Sound(os.path.join(SFX_DIR, fn + ".wav")))
            except (pygame.error, FileNotFoundError):
                pass
        if bank:
            _BANK[key] = bank
    for i, name in enumerate(LOOP_NAMES):
        try:
            _LOOPS[name] = (pygame.mixer.Sound(os.path.join(SFX_DIR, name + ".wav")), pygame.mixer.Channel(i))
        except (pygame.error, FileNotFoundError):
            pass
    _apply_sfx_volume()

def _apply_sfx_volume():
    for key, bank in _BANK.items():
        for snd in bank:
            snd.set_volume(SFX_VOL.get(key, 0.5) * SFX_VOLUME)

def set_master_volume(v):
    global MASTER_VOLUME
    MASTER_VOLUME = max(0.0, min(1.0, float(v)))
    set_sfx_volume(SFX_VOLUME)
    if _mixer_ready:
        try:
            pygame.mixer.music.set_volume(0.0 if MASTER_MUTE else MUSIC_VOLUME * MASTER_VOLUME)
        except pygame.error:
            pass

def set_engine_volume(v):
    global ENGINE_VOLUME
    ENGINE_VOLUME = max(0.0, min(1.0, float(v)))

def set_ui_volume(v):
    global UI_VOLUME
    UI_VOLUME = max(0.0, min(1.0, float(v)))

def set_sfx_volume(v):
    global SFX_VOLUME
    SFX_VOLUME = max(0.0, min(1.0, float(v)))
    for key, s in SOUNDS.items():
        s.set_volume(SOUND_VOL.get(key, 0.6) * SFX_VOLUME * MASTER_VOLUME)
    _apply_sfx_volume()

def set_music_volume(v):
    global MUSIC_VOLUME
    MUSIC_VOLUME = max(0.0, min(1.0, float(v)))
    if _mixer_ready:
        try:
            pygame.mixer.music.set_volume(0.0 if MASTER_MUTE else MUSIC_VOLUME * MASTER_VOLUME)
        except pygame.error:
            pass

def start_music():
    # plays a shuffled loop through assets/sound/music/*, falling back to a single
    # dropped-in soundtrack (music.* / theme.*) if no playlist is present
    global _music_loaded, _playlist, _playlist_i
    if not _mixer_ready or _music_loaded:
        return
    _playlist = _build_playlist()
    if _playlist:
        _playlist_i = 0
        if CURRENT_TILESET == "asphalt_circuit":
            gp = [i for i, t in enumerate(_playlist) if "07_grand_prix" in t]
            if gp:
                _playlist_i = gp[0]
        elif CURRENT_TILESET == "frost_pass":
            fp = [i for i, t in enumerate(_playlist) if "05_pursuit" in t]
            if fp:
                _playlist_i = fp[0]
        _play_track(_playlist[_playlist_i])
        _music_loaded = True
        return
    for fn in MUSIC_FILES:
        p = os.path.join(SOUND_DIR, fn)
        if os.path.exists(p):
            try:
                pygame.mixer.music.load(p)
                pygame.mixer.music.set_volume(MUSIC_VOLUME)
                pygame.mixer.music.play(-1)
                _music_loaded = True
            except pygame.error:
                pass
            return

def set_master_mute(on):
    global MASTER_MUTE
    MASTER_MUTE = bool(on)
    if _mixer_ready:
        try:
            pygame.mixer.music.set_volume(0.0 if MASTER_MUTE else MUSIC_VOLUME * MASTER_VOLUME)
        except pygame.error:
            pass

def _emit(name, vol=1.0, pan=0.0, bus="sfx"):
    now = time.monotonic()
    cd = SFX_COOLDOWN.get(name, 0.0)
    if cd and now - _SFX_LAST.get(name, -9.0) < cd:
        return
    _SFX_LAST[name] = now
    bank = _BANK.get(name)
    snd = random.choice(bank) if bank else SOUNDS.get(name)
    if snd is None:
        return
    try:
        ch = snd.play()
        if ch is not None:
            # constant-power pan, -1 = left, +1 = right (always set: channels keep their
            # last volume between sounds)
            a = (max(-1.0, min(1.0, pan)) + 1) * math.pi / 4
            bus_vol = UI_VOLUME if bus == "ui" else SFX_VOLUME
            eff_vol = vol * SFX_VOL.get(name, 0.5) * bus_vol * MASTER_VOLUME
            ch.set_volume(min(1.0, eff_vol * math.cos(a) * 1.414), min(1.0, eff_vol * math.sin(a) * 1.414))
    except pygame.error:
        pass

def play(name, vol=1.0):
    # gameplay sound (silent in menus / the attract-mode backdrop)
    if SFX_MUTED or MASTER_MUTE:
        return
    _emit(name, vol, bus="sfx")

def play_ui(name, vol=1.0):
    # menu sounds: these play while the gameplay SFX are muted
    if MASTER_MUTE:
        return
    _emit(name, vol, bus="ui")

def play_at(name, x, y, vol=1.0):
    # a sound that happens somewhere on the track: quieter with distance from the camera,
    # panned left/right by where it is on screen
    if SFX_MUTED or MASTER_MUTE:
        return
    if LISTENER is None:
        _emit(name, vol, bus="sfx")
        return
    lx, ly, la = LISTENER
    dx, dy = wrap_delta(lx, x), wrap_delta(ly, y)
    d = math.hypot(dx, dy)
    v = vol * max(0.0, 1.0 - d / SFX_RANGE) ** 1.5
    if v < 0.04:
        return
    r = math.radians(la + 90.0)          # the camera's "right", in world space
    pan = (dx * math.cos(r) + dy * math.sin(r)) / 260.0
    _emit(name, v, pan, bus="sfx")

def update_loops(car, dt):
    # continuous sounds for the local kart: engine (4 layers crossfaded by speed), tyre
    # screech, gravel off-road and boost roar. car=None fades them all out (menus, pause, out)
    if not _LOOPS:
        return
    tgt = {}
    if car is not None and not car.dead and not SFX_MUTED and not MASTER_MUTE:
        speed = math.hypot(car.vx, car.vy)
        f = min(1.0, speed / MAX_SPEED)
        pos = f * 3.0
        for i in range(4):
            tgt[f"engine_{i + 1}"] = (max(0.0, 1.0 - abs(pos - i)) * (0.6 + 0.4 * f) *
                                      LOOP_VOL["engine"] * ENGINE_VOLUME * MASTER_VOLUME)
        airborne = getattr(car, "airtime", 0.0) > 0.0
        slip = max(car.slip_r, car.slip_f * 0.8)
        skid = 0.0 if airborne else min(1.0, max(0.0, (slip - SKID_SLIP) / 160.0))
        if car.drift and speed > DRIFT_MIN_SPEED and not airborne:
            skid = max(skid, 0.7)
        off = 0.5 * (car.off_f + car.off_r)
        tgt["skid_loop"] = skid * (1.0 - 0.7 * off) * LOOP_VOL["skid_loop"] * SFX_VOLUME * MASTER_VOLUME
        tgt["gravel_loop"] = ((0.0 if airborne else off * min(1.0, speed / 120.0)) *
                              LOOP_VOL["gravel_loop"] * SFX_VOLUME * MASTER_VOLUME)
        tgt["boost_loop"] = (1.0 if car.boost_time > 0 else 0.0) * LOOP_VOL["boost_loop"] * SFX_VOLUME * MASTER_VOLUME
    k = min(1.0, dt * 12.0)
    for name, (snd, ch) in _LOOPS.items():
        cur = _LOOP_LEVEL.get(name, 0.0)
        cur += (tgt.get(name, 0.0) - cur) * k
        _LOOP_LEVEL[name] = cur
        try:
            if cur > 0.004:
                if not ch.get_busy():
                    ch.play(snd, loops=-1)
                ch.set_volume(min(1.0, cur * SFX_VOLUME * 1.6))
            elif ch.get_busy():
                ch.stop()
        except pygame.error:
            pass
M6X11_PATH = os.path.join(UI_DIR, "m6x11", "m6x11.ttf")
M6X11_ALT = os.path.join(ASSET_DIR, "m6x11", "m6x11.ttf")
PIXELLARI_PATH = os.path.join(ASSET_DIR, "pixellari", "Pixellari.ttf")
PIXELTA_PATH = os.path.join(ASSET_DIR, "pixelta", "Pixelta.ttf")
DAYDREAM_PATH = os.path.join(ASSET_DIR, "daydream", "Daydream.otf")
PIXEMON_PATH = os.path.join(ASSET_DIR, "pixemon", "Pixemon.otf")
JERSEY_PATH = os.path.join(ASSET_DIR, "font", "Jersey25-Regular.ttf")
FONT_PATH = next((p for p in (M6X11_PATH, M6X11_ALT, PIXELLARI_PATH, PIXELTA_PATH, DAYDREAM_PATH, PIXEMON_PATH, JERSEY_PATH) if os.path.exists(p)), JERSEY_PATH)
UI = {}             # UI icon surfaces by name
_FONT_CACHE = {}

def get_font(size):
    # Pixel font (Pixemon / Jersey), cached per size; falls back to default if missing
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
# lose a heart) before you hit it. 2 = one tile (16 px) of grass, then the fence -- close
# enough to the road that the fence sprites are actually visible while you drive.
FENCE_OFFSET = 2
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
BOX_SIZE = 38         # px, on-screen box size (further enlarged)
BOX_PICKUP = 26.0     # px pickup radius (plus the car's half-width)
BOX_RESPAWN = 6.0     # seconds a box stays gone after being taken
BOX_FLOAT_AMP = 4.0   # px vertical bob
BOX_FLOAT_SPEED = 3.0 # bob rad/s
BOX_HOVER = 12.0      # world px the 2.5D box floats above the road (it bobs around this)
BOX_SPIN = 1.0        # 2.5D box turns, rad/s
BOX_LATERAL = 0.30    # how far off centre a box may sit, as a fraction of road half-width
BOOST_TIME = 1.8      # seconds of engine boost from a box
BOOST_PACE = 0.9      # extra engine while boosting (+90%)
DRAFT_RANGE = 85.0     # px behind another car where slipstream starts helping
DRAFT_CONE = 0.5       # how tightly behind (vs beside) the car ahead must be, 0..1
DRAFT_PACE = 0.16      # extra engine at full draft (+16%)
DRAFT_RISE = 2.2       # how fast draft strength ramps up while tucked in, per second
DRAFT_FALL = 3.5       # how fast it decays once you're out of the slot

RAMP_LEN = 46.0         # px, along the road
RAMP_WIDTH = 60.0        # px, across the road
RAMP_KICK = 170.0        # forward speed added on launch, px/s
RAMP_AIR_TIME = 0.55     # seconds a kart is "airborne" after hitting a ramp
BOOST_KICK = 90.0     # instant forward px/s on pickup

# Single mystery box: arcade blue "?" box that dispenses random powerups
POWERUP_KINDS = ["boost", "heart", "bash", "cone", "oil"]
BOX_TYPES = ["mystery"]
BOX_COLORS = {
    "mystery": (45, 145, 255),    # vibrant arcade blue
    "boost":   (45, 145, 255),    # compatibility fallback
    "heart":   (45, 145, 255),
    "bash":    (45, 145, 255),
    "cone":    (255, 140, 30),
    "oil":     (45, 45, 55),
}
BOX_LETTER = {"mystery": "?", "boost": "?", "heart": "?", "bash": "?", "cone": "C", "oil": "O"}

# ---- laps -------------------------------------------------------------------------
TOTAL_LAPS = 3        # laps to finish a race

# ---- car body ---------------------------------------------------------------------
# units are px, seconds and "kart masses"; +x = forward, +y = the kart's right side
CAR_HL = 14.0          # half length of the kart's collision box
CAR_HW = 7.0           # half width (matches the sprite hull so contacts line up visually)
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
STEER_RATE = 5.0        # how fast the front wheels turn left/right, rad/s (steering responsiveness)
STEER_RATE_MIN = 2.5    # slider ends: slow, deliberate steering ...
STEER_RATE_MAX = 11.0   # ... to near-instant, twitchy steering

def set_steer_rate(v):
    # v in 0..1 -> STEER_RATE across the slider range
    global STEER_RATE
    v = max(0.0, min(1.0, v))
    STEER_RATE = STEER_RATE_MIN + (STEER_RATE_MAX - STEER_RATE_MIN) * v

def steer_rate_frac():
    return (STEER_RATE - STEER_RATE_MIN) / (STEER_RATE_MAX - STEER_RATE_MIN)
V_FLOOR = 40.0          # px/s; keeps slip angles sane when nearly stopped
YAW_DAMP = 0.6          # a little rotational damping, 1/s
STABILITY = 3.0         # 1/s: pulls the spin rate toward what the steering asks for, so a slide can
                        # be caught instead of snapping into a spin (off while staggered by a hit)
STABILITY_MIN = 0.0     # drift-assist slider ends: 0 = loose/driftly ...
STABILITY_MAX = 7.0     # ... to strongly planted (lots of assist)

def set_drift_assist(v):
    # slider 0..1 -> STABILITY (how hard the kart is held straight / caught out of a slide)
    global STABILITY
    v = max(0.0, min(1.0, v))
    STABILITY = STABILITY_MIN + (STABILITY_MAX - STABILITY_MIN) * v

def drift_assist_frac():
    return (STABILITY - STABILITY_MIN) / (STABILITY_MAX - STABILITY_MIN)

INVERT_STEER = False    # flip left/right steering input for the player
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
HIT_FLASH = 0.3         # seconds a kart's sprite flashes red after being bashed or hitting a wall
WALL_HIT_IMPULSE = 60.0 # min collision impulse with a fence to trigger the red flash
MAX_SPIN = 9.0          # rad/s cap on how fast any kart can spin (~1.4 turns a second)
STAGGER_TIME = 0.45     # seconds a bashed kart's tyres are loose
STAGGER_GRIP = 0.5      # grip multiplier while staggered

# ---- projectiles & oil slicks --------------------------------------------------------------
PROJ_SPEED = 430.0      # projectile muzzle speed, px/s
PROJ_LIFE = 1.4         # seconds a projectile lives
PROJ_COOLDOWN = 0.9     # seconds between shots
PROJ_R = 5.0            # projectile radius (collision + draw)
PROJ_KNOCK = 190.0      # shove given to a kart that gets hit
OIL_MAX = 16            # most oil slicks on the track at once
OIL_R = 22.0            # slick radius
OIL_SPAWN_CHANCE = 0.7  # chance to drop a cluster of oil when a kart starts a new lap

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
BOT_AGGRESSION_LEVELS = ["Chill", "Casual", "Feisty", "Demolition"]
BOT_AGGRESSION_MULTS = {
    "Chill": 0.55,
    "Casual": 1.0,
    "Normal": 1.0,
    "Feisty": 1.45,
    "Aggressive": 1.45,
    "Demolition": 1.9,
    "Brutal": 1.9,
}
BOT_AGGRESSION = "Casual"

def set_bot_aggression(level):
    global BOT_AGGRESSION
    if isinstance(level, str):
        level = level.capitalize()
    if level == "Normal":
        level = "Casual"
    elif level == "Aggressive":
        level = "Feisty"
    elif level == "Brutal":
        level = "Demolition"
    if level not in BOT_AGGRESSION_MULTS:
        level = "Casual"
    BOT_AGGRESSION = level

def get_bot_aggression():
    return BOT_AGGRESSION

def bot_aggression_mult():
    return BOT_AGGRESSION_MULTS.get(BOT_AGGRESSION, 1.0)

# ---- gameplay & physics settings -----------------------------------------------------------------
STEER_CURVE = 1.0           # 1.0 (linear) to 2.5 (exponential)
STICK_DEADZONE = 0.05       # 0.0 to 0.25 (percentage deadzone)
DYNAMIC_LOOK_AHEAD = False  # camera offset forward along velocity
GHOST_OPACITY = 0.6         # 0.0 (off) to 1.0 (opaque)
COLLISION_RULE = "full"     # "full" | "solid" | "ghost"
SLIPSTREAM_ASSIST = True    # 10% drafting corridor speed boost
ITEM_RULE = "standard"      # "standard" | "kinetic" | "hazards" | "none"
BRAKE_ACCEL = 480.0         # braking deceleration

def apply_steer_controls(raw_steer):
    if abs(raw_steer) < STICK_DEADZONE:
        return 0.0
    sign = math.copysign(1.0, raw_steer)
    mag = (abs(raw_steer) - STICK_DEADZONE) / max(0.001, (1.0 - STICK_DEADZONE))
    mag = min(1.0, max(0.0, mag))
    val = sign * (mag ** STEER_CURVE)
    return -val if INVERT_STEER else val

# ---- start grid ----------------------------------------------------------------------------------
GRID_START = 24         # road sample the front row starts on (bottom straight)
GRID_ROW_GAP = 46.0     # px between grid rows
GRID_LANE = 36.0        # px either side of the centre line

# ---- effects ---------------------------------------------------------------------------------------
SKID_SLIP = 55.0        # tyre sideways slip (px/s) above which it leaves a mark
TRAIL_LIFE = 13.0       # seconds a skid mark stays visible (remains for ~13s then fades out)
TRAIL_MAX_POINTS = 3000
MAX_PARTICLES = 1200
SHAKE_PX = 6.5          # screen shake at full strength
SHAKE_IMPULSE = 260.0   # hit strength that gives full shake
SHAKE_SCALE = 1.0       # player-set multiplier on shake (0 = off, up to 2x)
SHAKE_MAX = 2.0         # slider top end

def set_shake_intensity(v):
    # slider 0..1 -> SHAKE_SCALE across 0..SHAKE_MAX
    global SHAKE_SCALE
    SHAKE_SCALE = max(0.0, min(1.0, v)) * SHAKE_MAX

def shake_intensity_frac():
    return min(1.0, SHAKE_SCALE / SHAKE_MAX)

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
CHECK = None        # checkered finish-line tile (center)
CHECK_TILES = {}    # center, left, right, top, bottom check tiles
FENCE = {}          # (up, down, left, right) -> 16 px fence piece, all 16 combinations
FENCE_SHADOWS = {}  # (up, down, left, right) -> directional fence shadow surface
PARTICLE_RAW = None # 16x16 star particle graphic from assets/particle.png
_PARTICLE_CACHE = {} # (r, g, b, size, alpha_step) -> cached tinted pygame.Surface
CAR_STACK = None    # 7 slices 36x36 for the sprite-stacked red car
_CARSCALE_CACHE = {} # zoom-width -> list of scaled slices
_CARTINT_CACHE = {}  # (tint, zoom-width) -> list of scaled + effect-tinted slices
FX_SHEETS = {"dust1": "Dust_01", "dust2": "Dust_02", "fire1": "Fire_01", "fire2": "Fire_02",
             "poof_dark": "DarkVFX2"}
FX_FRAMES = {}      # name -> list of cropped animation frames
_FX_CACHE = {}      # (name, frame, zoom-width) -> scaled frame
FX = []             # active one-shot effects: [x, y, name, age, dur, world_w, rot]
BUSH_RAW = None     # 16x16 original green bush decoration from assets/bush.png
BUSH_SIZE = 24      # px size of scaled bushes on the map (increased from 16 to 24)
BUSH_SURF = None    # 24x24 green bush sprite
BUSH_SHADOW = None  # directional shadow for bushes
BUSHES = []         # (gx, gy) grid cells of decorative bushes on current map
TREE_RAW = None     # 48x64 tree sprite (Tree 1) from assets/tree.png
TREE2_RAW = None    # 48x64 tree sprite (Tree 2) from assets/tree2.png
TREE3_RAW = None    # 48x64 tree sprite (Tree 3) from assets/tree3.png
TREE_SURF = None    # 50x66 white-stroked Tree 1 sprite
TREE2_SURF = None   # 50x66 white-stroked Tree 2 sprite
TREE3_SURF = None   # 50x66 white-stroked Tree 3 sprite
TREE_SHADOW = None  # directional ground shadow for Tree 1
TREE2_SHADOW = None # directional ground shadow for Tree 2
TREE3_SHADOW = None # directional ground shadow for Tree 3
TREE_LOG_RAW = None # 16x16 tree log/stump sprite (Tree 1) from assets/tree_log.png
TREE3_LOG_RAW = None # 16x16 tree log/stump sprite (Tree 3) from assets/tree3_log.png
TREE_LOG_SHADOW = None # directional shadow for tree 1 logs
TREE3_LOG_SHADOW = None # directional shadow for tree 3 logs
TREES = []          # (gx, gy) grid cells of decorative trees on current map
TREE_LOGS = []      # (gx, gy) grid cells of decorative tree logs on current map
TREE_STACK_SEQ = []  # ramps.py stack names, same order as the tree_surfs list in _bake_bushes
CONE_RAW = None     # 32x32 raw traffic cone sprite from assets/traffic_cone.png
CONE_SURF = None    # 28x38 cropped & scaled traffic cone sprite (enlarged)
CONE_SHADOW = None  # directional ground shadow for traffic cones
CONES = []          # list of active traffic cone dicts on current map
DESTRUCT_RAW = {}    # name -> raw surface from assets/destructibles/
DESTRUCT_SURF = {}   # name -> stroked surface
DESTRUCT_SHADOW = {} # name -> directional ground shadow
DESTRUCTIBLES = []   # list of active destructibles: {"x", "y", "type", "destroyed", "wobble"}
RAMPS = []           # test jump ramps: {"x", "y", "angle", "w", "l"}
TIRES = []           # tyre piles: {"x", "y", "angle", "kind"} -- static, karts bounce off them
OIL_RAW = None      # 48x48 oil track sprite from assets/oil_track.png
OIL_TILES = {}      # 16x16 modular tile slices ("top", "bot", "left", "right", "center")
_OIL_SPRITE_CACHE = {} # (width, length) -> pygame.Surface
_OIL_ZOOM_CACHE = {}   # (width, length, zw, zl) -> scaled pygame.Surface

def _make_tree_stroked_and_shadow(raw_surf):
    if raw_surf is None:
        return None, None
    w, h = raw_surf.get_size()
    # Separate solid tree (alpha == 255) from baked shadow
    solid = pygame.Surface((w, h), pygame.SRCALPHA)
    for y in range(h):
        for x in range(w):
            c = raw_surf.get_at((x, y))
            if c.a == 255:
                solid.set_at((x, y), c)

    # 1px white outline with 1px padding (total size w+2, h+2)
    stroke_surf = pygame.Surface((w + 2, h + 2), pygame.SRCALPHA)
    mask = pygame.Surface((w, h), pygame.SRCALPHA)
    for y in range(h):
        for x in range(w):
            if solid.get_at((x, y)).a > 0:
                mask.set_at((x, y), (255, 255, 255, 255))
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1)):
        stroke_surf.blit(mask, (1 + dx, 1 + dy))
    stroke_surf.blit(solid, (1, 1))

    # Directional ground shadow: grounded base ellipse + skewed canopy silhouette in sun direction
    shad_surf = pygame.Surface((w + 30, h + 30), pygame.SRCALPHA)
    dx_s = round(SUN_DIR_X * 8)
    dy_s = round(SUN_DIR_Y * 8)
    pygame.draw.ellipse(shad_surf, (10, 15, 25, 110), (24 - 18 + dx_s, 58 - 9 + dy_s, 36, 18))
    for y in range(h):
        ht = (h - 1 - y) * 0.25
        sx = round(SUN_DIR_X * ht)
        sy = round(SUN_DIR_Y * ht)
        for x in range(w):
            if solid.get_at((x, y)).a > 0:
                nx = x + sx
                ny = y + sy
                if 0 <= nx < shad_surf.get_width() and 0 <= ny < shad_surf.get_height():
                    shad_surf.set_at((nx, ny), (10, 15, 25, 110))

    return stroke_surf, shad_surf

def _make_cone_stroked(cone_surf):
    w, h = cone_surf.get_size()
    stroke_surf = pygame.Surface((w + 2, h + 2), pygame.SRCALPHA)
    mask = pygame.Surface((w, h), pygame.SRCALPHA)
    for y in range(h):
        for x in range(w):
            if cone_surf.get_at((x, y)).a > 30:
                mask.set_at((x, y), (255, 255, 255, 255))
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1)):
        stroke_surf.blit(mask, (1 + dx, 1 + dy))
    stroke_surf.blit(cone_surf, (1, 1))
    return stroke_surf

def load_track_tileset(tileset_name="meadow_dirt"):
    global CURRENT_TILESET, TRACK_TILE_DIR, TILES, INNER, GRASS_COLOR, DIRT_COLOR
    global CHECK, CHECK_TILES, OIL_RAW, OIL_TILES, SKID_ROAD_COLOR, SKID_GRASS_COLOR, ROAD_WIDTH
    if tileset_name not in TILESETS and tileset_name != "random":
        tileset_name = "meadow_dirt"
    if tileset_name == "random":
        return

    CURRENT_TILESET = tileset_name
    TRACK_TILE_DIR = get_tileset_dir(tileset_name)
    if CURRENT_TILESET == "asphalt_circuit":
        SKID_ROAD_COLOR = (16, 18, 28)
        SKID_GRASS_COLOR = (40, 42, 24)
        ROAD_WIDTH = 288    # 18 tiles (at least 7 tiles, wider for grand prix circuit)
    elif CURRENT_TILESET == "canyon_sand":
        SKID_ROAD_COLOR = (180, 140, 70)   # #dab163 loose sand
        SKID_GRASS_COLOR = (148, 73, 58)   # #94493a canyon rock
        ROAD_WIDTH = 240
    elif CURRENT_TILESET == "frost_pass":
        SKID_ROAD_COLOR = (70, 74, 85)     # #464a55 packed snow skid
        SKID_GRASS_COLOR = (165, 190, 206) # #a5bece deep snow skid
        ROAD_WIDTH = 240    # 15 tiles
    elif CURRENT_TILESET == "harvest_mud":
        SKID_ROAD_COLOR = (80, 52, 32)     # #6e4c30 dark mud
        SKID_GRASS_COLOR = (190, 135, 60)  # #ce9248 golden field
        ROAD_WIDTH = 240
    elif CURRENT_TILESET == "neon_night":
        SKID_ROAD_COLOR = (50, 48, 85)     # #3e3b65 slate asphalt
        SKID_GRASS_COLOR = (23, 21, 36)    # #171524 dark night
        ROAD_WIDTH = 272
    else:
        SKID_ROAD_COLOR = (46, 28, 22)
        SKID_GRASS_COLOR = (40, 42, 24)
        ROAD_WIDTH = 240    # 15 tiles (meadow dirt)

    grid = [[None] * 3 for _ in range(3)]
    for key, fn in (("center", "checktile"), ("left", "checktile1"), ("right", "checktile2"),
                    ("top", "checktile3"), ("bottom", "checktile4")):
        try:
            CHECK_TILES[key] = _load(TRACK_TILE_DIR, fn, alpha=True)
        except (pygame.error, FileNotFoundError):
            CHECK_TILES[key] = None
    CHECK = CHECK_TILES.get("center")

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

    _OIL_SPRITE_CACHE.clear()
    _OIL_ZOOM_CACHE.clear()
    OIL_TILES.clear()
    try:
        oil_p = get_tileset_oil_path(tileset_name)
        if not os.path.exists(oil_p):
            oil_p = os.path.join(TRACK_TILE_DIR, "oil_track.png")
        if not os.path.exists(oil_p):
            oil_p = os.path.join(ASSET_DIR, "oil_track.png")
        if not os.path.exists(oil_p):
            oil_p = os.path.join(ROOT_DIR, "assets", "oil_track.png")
        if os.path.exists(oil_p):
            raw = pygame.image.load(oil_p).convert_alpha()
            w, h = raw.get_size()
            clean = pygame.Surface((w, h), pygame.SRCALPHA)
            dirt = (184, 111, 80)
            for y in range(h):
                for x in range(w):
                    c = raw.get_at((x, y))
                    if (c.r, c.g, c.b) != dirt:
                        clean.set_at((x, y), (c.r, c.g, c.b, 255))
            OIL_RAW = clean
            OIL_TILES["top"] = clean.subsurface((16, 0, 16, 16)).copy()
            OIL_TILES["bot"] = clean.subsurface((16, 32, 16, 16)).copy()
            OIL_TILES["left"] = clean.subsurface((0, 16, 16, 16)).copy()
            OIL_TILES["right"] = clean.subsurface((32, 16, 16, 16)).copy()
            OIL_TILES["center"] = clean.subsurface((16, 16, 16, 16)).copy()
        else:
            OIL_RAW = None
    except (pygame.error, FileNotFoundError) as e:
        print("oil track sprite missing, fallback to None:", e)
        OIL_RAW = None

def set_tileset(name):
    global CURRENT_TILESET
    if name not in TILESETS:
        name = "meadow_dirt"
    if name != CURRENT_TILESET or TILES is None:
        load_track_tileset(name)
        if GROUND_SURF is not None and ROAD:
            build_ground()
            _build_zoomed_ground()

def get_tileset():
    return CURRENT_TILESET

def get_track_type():
    return TRACK_TYPE_MODE

def set_track_type(mode):
    global TRACK_TYPE_MODE
    TRACK_TYPE_MODE = mode
    if mode in TILESETS:
        set_tileset(mode)

def get_tileset_title(key=None):
    k = key or TRACK_TYPE_MODE
    if k == "random":
        return "Random"
    return TILESET_TITLES.get(k, "Meadow Dirt")

def load_assets():
    # needs a display surface to exist (convert); called at startup and after each hot reload
    global TILES, INNER, GRASS_COLOR, DIRT_COLOR, CHECK, CHECK_TILES, PARTICLE_RAW, CAR_STACK
    global BUSH_RAW, BUSH_SURF, BUSH_SHADOW, TREE_RAW, TREE2_RAW, TREE3_RAW, TREE_LOG_RAW, TREE3_LOG_RAW, TREE_LOG_SHADOW, TREE3_LOG_SHADOW
    global TREE_SURF, TREE2_SURF, TREE3_SURF, TREE_SHADOW, TREE2_SHADOW, TREE3_SHADOW
    global CONE_RAW, CONE_SURF, CONE_SHADOW, CONES
    global DESTRUCT_RAW, DESTRUCT_SURF, DESTRUCT_SHADOW, DESTRUCTIBLES
    global OIL_RAW, OIL_TILES, _OIL_SPRITE_CACHE, _OIL_ZOOM_CACHE
    TILES = INNER = None
    FENCE.clear()
    CHECK_TILES.clear()
    _PARTICLE_CACHE.clear()
    _CARSCALE_CACHE.clear()
    _CARTINT_CACHE.clear()
    _CAR_ROT_CACHE.clear()
    FX_FRAMES.clear()
    _FX_CACHE.clear()

    try:
        p_path = os.path.join(FX_DIR, "particle.png")
        if not os.path.isfile(p_path):
            p_path = os.path.join(ASSET_DIR, "particle.png")
        if os.path.isfile(p_path):
            PARTICLE_RAW = pygame.image.load(p_path).convert_alpha()
        else:
            PARTICLE_RAW = _load(ASSET_DIR, "particle", alpha=True)
    except (pygame.error, FileNotFoundError) as e:
        print("particle sprite missing, using fallback:", e)
        PARTICLE_RAW = None

    try:
        car_path = os.path.join(CAR_DIR, "car_stack.png")
        if not os.path.isfile(car_path):
            car_path = os.path.join(ASSET_DIR, "cars", "redcar_stack.png")
        if not os.path.isfile(car_path):
            car_path = os.path.join(ASSET_DIR, "car_stack.png")
        if os.path.isfile(car_path):
            CAR_STACK = _build_car_stack(pygame.image.load(car_path).convert_alpha())
        else:
            CAR_STACK = _build_car_stack(_load(ASSET_DIR, "car_stack", alpha=True))
    except (pygame.error, FileNotFoundError) as e:
        print("car stack sprite missing, using vector kart:", e)
        CAR_STACK = None

    ramps.load(ASSET_DIR)      # the ramp + everything in assets/props (tyres, trees, breakables, cone)

    for name, fn in FX_SHEETS.items():
        try:
            FX_FRAMES[name] = _slice_sheet_cropped(_load(FX_DIR, fn, alpha=True))
        except (pygame.error, FileNotFoundError, ValueError) as e:
            print(f"fx sheet {fn} missing:", e)


    load_track_tileset(CURRENT_TILESET)

    try:
        _build_fence_tiles({name: _load(FENCE_TILE_DIR, name, alpha=True)
                            for name in set(FENCE_SOURCES.values()) | {FENCE_UP_ROW_FROM}})
        _build_fence_shadows()
    except (pygame.error, FileNotFoundError) as e:
        print("fence tiles missing, drawing fences as flat colour instead:", e)
        FENCE.clear()
        FENCE_SHADOWS.clear()

    try:
        bush_path = os.path.join(DECOR_DIR, "bush.png")
        if not os.path.exists(bush_path):
            bush_path = os.path.join(ASSET_DIR, "bush.png")
        if os.path.exists(bush_path):
            BUSH_RAW = pygame.image.load(bush_path).convert_alpha()
        else:
            bush1_path = os.path.join(ASSET_DIR, "Bush1.png")
            if os.path.exists(bush1_path):
                raw = pygame.image.load(bush1_path).convert_alpha()
                BUSH_RAW = raw.subsurface((0, 0, 16, 16)).copy()
            else:
                BUSH_RAW = _load(DECOR_DIR, "bush", alpha=True)
    except (pygame.error, FileNotFoundError) as e:
        print("bush sprite missing, fallback to None:", e)
        BUSH_RAW = None

    if BUSH_RAW is not None:
        BUSH_SURF = pygame.transform.scale(BUSH_RAW, (BUSH_SIZE, BUSH_SIZE))
        BUSH_SHADOW = pygame.Surface((BUSH_SIZE, BUSH_SIZE), pygame.SRCALPHA)
        for y in range(BUSH_SIZE):
            for x in range(BUSH_SIZE):
                if BUSH_SURF.get_at((x, y)).a > 0:
                    BUSH_SHADOW.set_at((x, y), (10, 15, 25, 110))
    else:
        BUSH_SURF = None
        BUSH_SHADOW = None

    for var_name, filename in (("TREE_RAW", "tree.png"), ("TREE2_RAW", "tree2.png"), ("TREE3_RAW", "tree3.png")):
        p = os.path.join(DECOR_DIR, filename)
        if not os.path.exists(p):
            p = os.path.join(ASSET_DIR, filename)
        if not os.path.exists(p):
            p = os.path.join(ROOT_DIR, "assets", filename)
        try:
            if os.path.exists(p):
                globals()[var_name] = pygame.image.load(p).convert_alpha()
            else:
                globals()[var_name] = _load(DECOR_DIR, os.path.splitext(filename)[0], alpha=True)
        except (pygame.error, FileNotFoundError) as e:
            globals()[var_name] = None

    TREE_SURF, TREE_SHADOW = _make_tree_stroked_and_shadow(TREE_RAW)
    TREE2_SURF, TREE2_SHADOW = _make_tree_stroked_and_shadow(TREE2_RAW)
    TREE3_SURF, TREE3_SHADOW = _make_tree_stroked_and_shadow(TREE3_RAW)

    # same order/filter as the tree_surfs list in _bake_bushes, so the stack variant picked
    # for a given grid cell always matches the (now unused) flat sprite it would have gotten
    global TREE_STACK_SEQ
    TREE_STACK_SEQ = [n for s, n in ((TREE_SURF, "tree_round"), (TREE2_SURF, "tree_tall"),
                                      (TREE3_SURF, "tree_bushy")) if s is not None]

    for var_name, shad_name, filename in (("TREE_LOG_RAW", "TREE_LOG_SHADOW", "tree_log.png"), ("TREE3_LOG_RAW", "TREE3_LOG_SHADOW", "tree3_log.png")):
        p = os.path.join(DECOR_DIR, filename)
        if not os.path.exists(p):
            p = os.path.join(ASSET_DIR, filename)
        if not os.path.exists(p):
            p = os.path.join(ROOT_DIR, "assets", filename)
        try:
            if os.path.exists(p):
                surf = pygame.image.load(p).convert_alpha()
            else:
                surf = _load(DECOR_DIR, os.path.splitext(filename)[0], alpha=True)
            globals()[var_name] = surf
            if surf is not None:
                lw, lh = surf.get_size()
                shad = pygame.Surface((lw, lh), pygame.SRCALPHA)
                for y in range(lh):
                    for x in range(lw):
                        if surf.get_at((x, y)).a > 0:
                            shad.set_at((x, y), (10, 15, 25, 110))
                globals()[shad_name] = shad
            else:
                globals()[shad_name] = None
        except (pygame.error, FileNotFoundError) as e:
            globals()[var_name] = None
            globals()[shad_name] = None

    try:
        cone_p = os.path.join(PROPS_DIR, "traffic_cone.png")
        if not os.path.exists(cone_p):
            cone_p = os.path.join(ASSET_DIR, "traffic_cone.png")
        if not os.path.exists(cone_p):
            cone_p = os.path.join(ROOT_DIR, "assets", "traffic_cone.png")
        if os.path.exists(cone_p):
            CONE_RAW = pygame.image.load(cone_p).convert_alpha()
            bbox = CONE_RAW.get_bounding_rect()
            cropped = CONE_RAW.subsurface(bbox).copy()
            cw, ch = cropped.get_size()
            scale = 24.0 / cw
            target_w = 24
            target_h = int(round(ch * scale))
            CONE_SURF = _make_cone_stroked(pygame.transform.smoothscale(cropped, (target_w, target_h)))
            sw_c = int(round(target_w * 0.92))
            sh_c = int(round(target_w * 0.44))
            CONE_SHADOW = pygame.Surface((sw_c + 4, sh_c + 4), pygame.SRCALPHA)
            pygame.draw.ellipse(CONE_SHADOW, (10, 15, 25, 110), (2, 2, sw_c, sh_c))
        else:
            CONE_RAW = CONE_SURF = CONE_SHADOW = None
    except (pygame.error, FileNotFoundError) as e:
        CONE_RAW = CONE_SURF = CONE_SHADOW = None

    DESTRUCT_RAW.clear()
    DESTRUCT_SURF.clear()
    DESTRUCT_SHADOW.clear()
    dest_dir = os.path.join(ASSET_DIR, "destructibles")
    if os.path.exists(dest_dir):
        for name in ("barrel", "box", "vase"):
            fp = os.path.join(dest_dir, f"{name}.png")
            if os.path.exists(fp):
                raw = pygame.image.load(fp).convert_alpha()
                DESTRUCT_RAW[name] = raw
                bw, bh = raw.get_size()
                scale = 2.5 if name in ("barrel", "box") else 1.75
                tw, th = int(round(bw * scale)), int(round(bh * scale))
                scaled = pygame.transform.scale(raw, (tw, th))
                DESTRUCT_SURF[name] = _make_cone_stroked(scaled)

                sw = int(round(tw * 0.95))
                sh = int(round(tw * 0.44))
                shad = pygame.Surface((sw + 4, sh + 4), pygame.SRCALPHA)
                pygame.draw.ellipse(shad, (10, 15, 25, 110), (2, 2, sw, sh))
                DESTRUCT_SHADOW[name] = shad

            # Load 4 break frames for FX_FRAMES
            break_frames = []
            for i in range(4):
                bfp = os.path.join(dest_dir, f"{name}_break_{i}.png")
                if os.path.exists(bfp):
                    braw = pygame.image.load(bfp).convert_alpha()
                    bbw, bbh = braw.get_size()
                    scale = 2.5 if name in ("barrel", "box") else 1.75
                    btw, bth = int(round(bbw * scale)), int(round(bbh * scale))
                    break_frames.append(pygame.transform.scale(braw, (btw, bth)))
            if break_frames:
                FX_FRAMES[f"{name}_break"] = break_frames

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

def _build_fence_shadows():
    FENCE_SHADOWS.clear()
    dx = round(SUN_DIR_X * FENCE_SHADOW_DIST)
    dy = round(SUN_DIR_Y * FENCE_SHADOW_DIST)
    sw, sh = TILE + dx + 6, TILE + dy + 6
    for links, tile in FENCE.items():
        s_surf = pygame.Surface((sw, sh), pygame.SRCALPHA)
        for y in range(TILE):
            for x in range(TILE):
                c = tile.get_at((x, y))
                if c[3] > 60:
                    is_rail = (x < 4 or x > 11)
                    fh = 0.8 if is_rail else max(0.2, (15 - y) / 12.0)
                    sx = fh * dx
                    sy = fh * dy
                    steps = max(2, int(round(fh * 6)))
                    for st in range(steps + 1):
                        t = st / steps
                        px = int(round(x + sx * t))
                        py = int(round(y + sy * t))
                        s_surf.set_at((px, py), FENCE_SHADOW_COLOR)
                        if not is_rail:
                            s_surf.set_at((px + 1, py), FENCE_SHADOW_COLOR)
                            s_surf.set_at((px, py + 1), FENCE_SHADOW_COLOR)
        FENCE_SHADOWS[links] = s_surf

def _load(folder, name, alpha):
    img = pygame.image.load(os.path.join(folder, name + ".png"))
    return img.convert_alpha() if alpha else img.convert()

def _slice_sheet_cropped(sheet):
    # a horizontal strip of square frames; crop all to one shared tight bbox (keeps them aligned)
    fh = sheet.get_height()
    nf = max(1, sheet.get_width() // fh)
    frames = [sheet.subsurface((i * fh, 0, fh, fh)).copy() for i in range(nf)]
    rects = [f.get_bounding_rect() for f in frames]
    union = rects[0].unionall(rects[1:]) if len(rects) > 1 else rects[0]
    if union.w > 0 and union.h > 0:
        frames = [f.subsurface(union).copy() for f in frames]
    return frames

def _build_car_stack(sheet):
    # a horizontal strip of square slices (bottom slice first) for a sprite-stacked car.
    # Preserve authentic pixel art colors so all players and bots use this exact sprite.
    fh = sheet.get_height()
    nf = max(1, sheet.get_width() // fh)
    return [sheet.subsurface((i * fh, 0, fh, fh)).copy() for i in range(nf)]

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

TRACK_SHAPES = ["stadium", "peanut", "teardrop", "tri_oval", "chicane", "kidney"]

def _catmull_rom(pts, total_samples=280):
    n = len(pts)
    res = []
    num_per_seg = total_samples // n
    rem = total_samples - num_per_seg * n
    for i in range(n):
        p0 = pts[(i - 1) % n]
        p1 = pts[i]
        p2 = pts[(i + 1) % n]
        p3 = pts[(i + 2) % n]
        steps = num_per_seg + (1 if i < rem else 0)
        for s in range(steps):
            t = s / steps
            t2 = t * t
            t3 = t2 * t
            x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
            y = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
            res.append((x, y))
    return res

def generate_road(seed):
    # Procedurally selects between distinct racing track shapes:
    # 0: Stadium Oval (gentle wobble on the back straight)
    # 1: Peanut / Dogbone (waisted top straight dipping into the infield)
    # 2: Teardrop (asymmetric: high-speed sweeper vs tight technical hairpin)
    # 3: Tri-Oval / Delta (3 banking corners with 3 straights)
    # 4: Technical Chicane / S-Loop (chicane complex on backstretch)
    # 5: Kidney Bean (sweeping outer bulge with indented curve)
    # All layouts maintain a flat bottom straight around GRID_START for clean starting alignment.
    rnd = random.Random(seed)
    shape_idx = rnd.randrange(len(TRACK_SHAPES))
    cx, cy = WORLD / 2, WORLD / 2
    if CURRENT_TILESET == "asphalt_circuit":
        A = rnd.uniform(690, 850)   # ~22% larger straight/extent
        R = rnd.uniform(500, 610)   # ~20% larger turn sweep radius
    else:
        A = rnd.uniform(560, 720)
        R = rnd.uniform(430, 520)
    n_straight, n_arc = 80, 60
    pts = []

    if shape_idx == 0:  # Stadium Oval
        wob_amp = R * rnd.uniform(0.08, 0.14)
        wob_f = rnd.choice([2, 3])
        wob_p = rnd.uniform(0, math.tau)
        for i in range(n_straight):
            t = i / n_straight
            w = wob_amp * math.sin(wob_f * t * math.tau + wob_p) * max(0.0, (t - 0.45) / 0.55)
            pts.append((cx - A + 2 * A * t, cy + R + w))
        for i in range(n_arc):
            t = i / n_arc
            ang = math.pi / 2 - math.pi * t
            pts.append((cx + A + R * math.cos(ang), cy + R * math.sin(ang)))
        for i in range(n_straight):
            t = i / n_straight
            w = wob_amp * math.sin(wob_f * t * math.tau + wob_p + math.pi) * math.sin(math.pi * t)
            pts.append((cx + A - 2 * A * t, cy - R + w))
        for i in range(n_arc):
            t = i / n_arc
            ang = -math.pi / 2 - math.pi * t
            pts.append((cx - A + R * math.cos(ang), cy + R * math.sin(ang)))

    elif shape_idx == 1:  # Peanut / Dogbone
        dip = rnd.uniform(160, 240)
        for i in range(n_straight):
            t = i / n_straight
            pts.append((cx - A + 2 * A * t, cy + R))
        for i in range(n_arc):
            t = i / n_arc
            ang = math.pi / 2 - math.pi * t
            pts.append((cx + A + R * math.cos(ang), cy + R * math.sin(ang)))
        for i in range(n_straight):
            t = i / n_straight
            w = dip * math.sin(math.pi * t)
            pts.append((cx + A - 2 * A * t, cy - R + w))
        for i in range(n_arc):
            t = i / n_arc
            ang = -math.pi / 2 - math.pi * t
            pts.append((cx - A + R * math.cos(ang), cy + R * math.sin(ang)))

    elif shape_idx == 2:  # Teardrop
        R_tight = rnd.uniform(340, 390)
        R_wide = rnd.uniform(540, 600)
        for i in range(n_straight):
            t = i / n_straight
            blend = 0.5 * (1 - math.cos(math.pi * max(0.0, (t - 0.4) / 0.6)))
            y = (cy + R_tight) + (R_wide - R_tight) * blend
            pts.append((cx - A + 2 * A * t, y))
        for i in range(n_arc):
            t = i / n_arc
            ang = math.pi / 2 - math.pi * t
            pts.append((cx + A + R_wide * math.cos(ang), cy + R_wide * math.sin(ang)))
        for i in range(n_straight):
            t = i / n_straight
            y = (cy - R_wide) + (R_wide - R_tight) * t
            pts.append((cx + A - 2 * A * t, y))
        for i in range(n_arc):
            t = i / n_arc
            ang = -math.pi / 2 - math.pi * t
            pts.append((cx - A + R_tight * math.cos(ang), cy + R_tight * math.sin(ang)))

    elif shape_idx == 3:  # Tri-Oval / Delta
        R_bot = rnd.uniform(430, 490)
        R_top = rnd.uniform(520, 600)
        ctrl_pts = [
            (cx - A, cy + R_bot),
            (cx - A / 3, cy + R_bot),
            (cx + A / 3, cy + R_bot),
            (cx + A, cy + R_bot),
            (cx + A + 240, cy + R_bot - 190),
            (cx + A / 2 + 100, cy - R_top / 2),
            (cx + 150, cy - R_top),
            (cx, cy - R_top - 50),
            (cx - 150, cy - R_top),
            (cx - A / 2 - 100, cy - R_top / 2),
            (cx - A - 240, cy + R_bot - 190),
        ]
        pts = _catmull_rom(ctrl_pts, 280)

    elif shape_idx == 4:  # Technical Chicane / S-Loop
        chicane_amp = rnd.uniform(140, 200)
        for i in range(n_straight):
            t = i / n_straight
            pts.append((cx - A + 2 * A * t, cy + R))
        for i in range(n_arc):
            t = i / n_arc
            ang = math.pi / 2 - math.pi * t
            pts.append((cx + A + R * math.cos(ang), cy + R * math.sin(ang)))
        for i in range(n_straight):
            t = i / n_straight
            w = chicane_amp * math.sin(2 * math.pi * t)
            pts.append((cx + A - 2 * A * t, cy - R + w))
        for i in range(n_arc):
            t = i / n_arc
            ang = -math.pi / 2 - math.pi * t
            pts.append((cx - A + R * math.cos(ang), cy + R * math.sin(ang)))

    elif shape_idx == 5:  # Kidney Bean
        bulge = rnd.uniform(150, 220)
        for i in range(n_straight):
            t = i / n_straight
            pts.append((cx - A + 2 * A * t, cy + R))
        for i in range(n_arc):
            t = i / n_arc
            ang = math.pi / 2 - math.pi * t
            r_curr = R + bulge * math.sin(math.pi * t)
            pts.append((cx + A + r_curr * math.cos(ang), cy + R * math.sin(ang)))
        for i in range(n_straight):
            t = i / n_straight
            w = -bulge * 0.7 * math.sin(math.pi * t)
            pts.append((cx + A - 2 * A * t, cy - R + w))
        for i in range(n_arc):
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
    if n == 0:
        return 0.0, 0.0, 0
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
GROUND_Z = None         # GROUND_SURF pre-scaled by ZOOM, so draw_ground only has to rotate
GROUND_ORIGIN = (0, 0)  # world coords of GROUND_SURF's top-left pixel

def _build_zoomed_ground():
    global GROUND_Z
    if GROUND_SURF is None:
        GROUND_Z = None
        return
    gw, gh = GROUND_SURF.get_size()
    GROUND_Z = pygame.transform.smoothscale(GROUND_SURF, (round(gw * ZOOM), round(gh * ZOOM)))
    GROUND_Z.fill((0, 0, 0, 255), special_flags=pygame.BLEND_RGBA_MAX)

def _bake_finish(surf, ox, oy):
    # checkered start/finish line baked across the road at the start, aligned to the road
    if not CHECK_TILES.get("center") or not ROAD:
        return
    s0 = ROAD_S[GRID_START]
    wx, wy, heading = road_pose(s0)

    tc = CHECK_TILES.get("center")
    rad = math.radians(heading)
    cos_h, sin_h = math.cos(rad), math.sin(rad)

    # Dynamically match full ROAD_WIDTH (288 on asphalt, 240 on dirt) without green grass artifacts
    road_w = ROAD_WIDTH
    num_tiles_across = int(round(road_w / 16))
    total_w = num_tiles_across * 16

    if abs(sin_h) < 0.707:
        # Road is mostly horizontal (East or West)
        band = pygame.Surface((32, total_w), pygame.SRCALPHA)
        for row in range(num_tiles_across):
            for col in range(2):
                band.blit(tc, (col * 16, row * 16))
        rot_angle = -heading if abs(heading) > 0.01 else 0
    else:
        # Road is mostly vertical (South or North)
        band = pygame.Surface((total_w, 32), pygame.SRCALPHA)
        for col in range(num_tiles_across):
            for row in range(2):
                band.blit(tc, (col * 16, row * 16))
        base_h = 90 if sin_h >= 0 else -90
        rot_angle = -(heading - base_h)
        if abs(rot_angle) < 0.01:
            rot_angle = 0

    if rot_angle != 0:
        band = pygame.transform.rotate(band, rot_angle)

    surf.blit(band, band.get_rect(center=(round(wx - ox), round(wy - oy))))

def _bake_bushes(surf, ox, oy):
    # Generates green bush decorations, trees, and tree logs across the grass outfield and infield.
    # Deterministic per MAP_SEED so all multiplayer clients share identical placement.
    global BUSHES, TREES, TREE_LOGS
    del BUSHES[:]
    del TREES[:]
    del TREE_LOGS[:]
    tree_surfs = [t for t in (TREE_SURF, TREE2_SURF, TREE3_SURF) if t is not None]
    tree_shads = [s for s in (TREE_SHADOW, TREE2_SHADOW, TREE3_SHADOW) if s is not None]
    log_pairs = [p for p in ((TREE_LOG_RAW, TREE_LOG_SHADOW), (TREE3_LOG_RAW, TREE3_LOG_SHADOW)) if p[0] is not None]

    if BUSH_SURF is None and not tree_surfs and not log_pairs:
        return

    ax0, ay0, ax1, ay1 = ARENA
    gw, gh = (ax1 - ax0) + 2 * BAKE_PAD, (ay1 - ay0) + 2 * BAKE_PAD
    gx0, gy0 = ox // TILE, oy // TILE
    gx1, gy1 = (ox + gw) // TILE, (oy + gh) // TILE

    fence_cells = {(f[0], f[1]) for f in FENCES}
    rng = random.Random(MAP_SEED + 777)

    eligible = set()
    fence_outer_border = set()

    for gy in range(gy0, gy1):
        for gx in range(gx0, gx1):
            if not is_dirt(gx, gy) and (gx, gy) not in fence_cells:
                idx = (gy % GRID_N) * GRID_N + gx % GRID_N
                if ROAD_NEAR[idx] == 1:
                    continue  # preserve clean grass verge between road and fence
                eligible.add((gx, gy))
                if any((gx + ox_, gy + oy_) in fence_cells for ox_, oy_ in ((-1, 0), (1, 0), (0, -1), (0, 1))):
                    fence_outer_border.add((gx, gy))

    bushes = set()
    trees = set()
    tree_logs = set()

    # 1. Fence-lining bushes (~28% of fence outer border cells)
    for cell in sorted(fence_outer_border):
        if rng.random() < 0.28:
            bushes.add(cell)

    # 2. Clusters of 1-4 bushes across the open infield and outfield grass (~7% of eligible)
    num_field_bushes = int(len(eligible) * 0.07)
    eligible_bush = list(eligible - bushes)
    rng.shuffle(eligible_bush)
    for center in eligible_bush:
        if len(bushes) >= num_field_bushes:
            break
        if center in bushes:
            continue
        clump_size = rng.choices([1, 2, 3, 4], weights=[25, 35, 25, 15])[0]
        cur_clump = [center]
        bushes.add(center)
        for _ in range(clump_size - 1):
            base = rng.choice(cur_clump)
            nbrs = [(base[0] + dx_, base[1] + dy_) for dx_, dy_ in ((-1, 0), (1, 0), (0, -1), (0, 1))]
            valid_nbrs = [n for n in nbrs if n in eligible and n not in bushes]
            if valid_nbrs:
                pick = rng.choice(valid_nbrs)
                bushes.add(pick)
                cur_clump.append(pick)

    # Safe tree check: ensure 48x64 tree sprite (3 tiles wide, 4 tiles high) and its shadow never
    # touch, overlap, or cross into fence cells or track/verge areas.
    def is_tree_safe(gx, gy):
        for dy_ in (-3, -2, -1, 0, 1):
            for dx_ in (-2, -1, 0, 1, 2):
                cx_, cy_ = gx + dx_, gy + dy_
                if (cx_, cy_) in fence_cells:
                    return False
                if is_dirt(cx_, cy_):
                    return False
                idx = (cy_ % GRID_N) * GRID_N + cx_ % GRID_N
                if ROAD_NEAR[idx] < 2:
                    return False
        return True

    # 3. Trees across outfield and open infield
    # Trees have a 48x64 sprite. Require ROAD_NEAR >= 3 and is_tree_safe so canopy never overhangs fences or road.
    if tree_surfs:
        eligible_tree_cells = [
            c for c in (eligible - bushes)
            if ROAD_NEAR[(c[1] % GRID_N) * GRID_N + c[0] % GRID_N] >= 3
            and is_tree_safe(c[0], c[1])
        ]
        rng.shuffle(eligible_tree_cells)
        num_target_trees = max(10, int(len(eligible) * 0.028))
        reserved_tree_area = set()
        for center in eligible_tree_cells:
            if len(trees) >= num_target_trees:
                break
            if center in reserved_tree_area or center in bushes:
                continue
            trees.add(center)
            # Reserve surrounding cells to prevent overly dense overlapping
            for rx in (-1, 0, 1):
                for ry in (-1, 0, 1):
                    reserved_tree_area.add((center[0] + rx, center[1] + ry))
            # 35% chance to add a companion tree nearby for natural groves
            if rng.random() < 0.35 and len(trees) < num_target_trees:
                cand_grove = [
                    (center[0] + dx_, center[1] + dy_)
                    for dx_, dy_ in ((-1, -1), (1, -1), (-1, 1), (1, 1), (0, 1), (1, 0))
                ]
                valid_grove = [
                    c for c in cand_grove
                    if c in eligible and c not in bushes and c not in trees
                    and ROAD_NEAR[(c[1] % GRID_N) * GRID_N + c[0] % GRID_N] >= 3
                    and is_tree_safe(c[0], c[1])
                ]
                if valid_grove:
                    comp = rng.choice(valid_grove)
                    trees.add(comp)
                    for rx in (-1, 0, 1):
                        for ry in (-1, 0, 1):
                            reserved_tree_area.add((comp[0] + rx, comp[1] + ry))

    # 4. Tree logs (fallen stumps/logs) scattered naturally (~0.6% of eligible)
    if log_pairs:
        num_target_logs = max(5, int(len(eligible) * 0.006))
        eligible_logs = [
            c for c in (eligible - bushes - trees)
            if ROAD_NEAR[(c[1] % GRID_N) * GRID_N + c[0] % GRID_N] >= 2
        ]
        rng.shuffle(eligible_logs)
        for c in eligible_logs:
            if len(tree_logs) >= num_target_logs:
                break
            tree_logs.add(c)

    def _pick_tree_surf(gx, gy):
        idx = (gx * 73856093 ^ gy * 19349663 ^ MAP_SEED) % len(tree_surfs)
        return tree_surfs[idx]

    def _pick_tree_shad(gx, gy):
        if not tree_shads:
            return None
        idx = (gx * 73856093 ^ gy * 19349663 ^ MAP_SEED) % len(tree_shads)
        return tree_shads[idx]

    def _pick_log_pair(gx, gy):
        idx = (gx * 374761393 ^ gy * 668265263 ^ MAP_SEED) % len(log_pairs)
        return log_pairs[idx]

    b_off = (BUSH_SIZE - TILE) // 2

    # Draw directional shadows first (on grass)
    if SHADER_SETTINGS.get("shadows", "ON") == "ON":
        if BUSH_SHADOW is not None:
            dx_b = round(SUN_DIR_X * (3.0 * BUSH_SIZE / 16.0))
            dy_b = round(SUN_DIR_Y * (3.0 * BUSH_SIZE / 16.0))
            for gx, gy in bushes:
                px, py = gx * TILE - ox - b_off, gy * TILE - oy - b_off
                surf.blit(BUSH_SHADOW, (px + dx_b, py + dy_b))

        if log_pairs:
            dx_l = round(SUN_DIR_X * 3.0)
            dy_l = round(SUN_DIR_Y * 3.0)
            for gx, gy in tree_logs:
                _, l_shad = _pick_log_pair(gx, gy)
                if l_shad is not None:
                    px, py = gx * TILE - ox, gy * TILE - oy
                    surf.blit(l_shad, (px + dx_l, py + dy_l))

        if tree_shads:
            for gx, gy in trees:
                t_shad = _pick_tree_shad(gx, gy)
                if t_shad is not None:
                    px, py = gx * TILE - ox - 16, gy * TILE - oy - 48
                    surf.blit(t_shad, (px, py))

    # Draw sprites sorted by ground base Y (gy) so foreground objects naturally overlap background objects
    # Bush base: gy * TILE + 16
    # Log base: gy * TILE + 16
    # Tree base: gy * TILE + 16
    # kinds: 0 = bush, 1 = log, 2 = tree
    items = [(gy, 0, gx, gy) for gx, gy in bushes] + \
            [(gy, 1, gx, gy) for gx, gy in tree_logs] + \
            [(gy, 2, gx, gy) for gx, gy in trees]

    for _, kind, gx, gy in sorted(items, key=lambda it: (it[0], it[2])):
        if kind == 0 and BUSH_SURF is not None:
            px, py = gx * TILE - ox - b_off, gy * TILE - oy - b_off
            surf.blit(BUSH_SURF, (px, py))
        elif kind == 1 and log_pairs:
            l_surf, _ = _pick_log_pair(gx, gy)
            if l_surf is not None:
                px, py = gx * TILE - ox, gy * TILE - oy
                surf.blit(l_surf, (px, py))
        # kind == 2 (tree): the flat canopy is no longer baked in -- draw_trees() draws a
        # sprite-stack tree there each frame instead, so it stands up straight from every
        # camera angle. The ground shadow above is still baked in, same as before.

    BUSHES.extend(sorted(bushes, key=lambda b: (b[1], b[0])))
    TREES.extend(sorted(trees, key=lambda t: (t[1], t[0])))
    TREE_LOGS.extend(sorted(tree_logs, key=lambda l: (l[1], l[0])))

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
    _bake_bushes(surf, ox, oy)

    # fence shadows on the ground (direction-based projection baked before fence posts)
    for gx, gy, links in FENCES:
        px, py = gx * TILE - ox, gy * TILE - oy
        s_tile = FENCE_SHADOWS.get(links)
        if s_tile is not None:
            surf.blit(s_tile, (px, py))
        elif not FENCE:
            # fallback if fence tiles missing
            dx = round(SUN_DIR_X * FENCE_SHADOW_DIST)
            dy = round(SUN_DIR_Y * FENCE_SHADOW_DIST)
            surf.fill(FENCE_SHADOW_COLOR, (px + 3 + dx, py + 1 + dy, 11, 13))

    # fences, top row first so each post's cap overlaps the post above it
    for gx, gy, links in sorted(FENCES, key=lambda f: f[1]):
        px, py = gx * TILE - ox, gy * TILE - oy
        tile = FENCE.get(links)
        if tile is None:
            surf.fill(FENCE_COLOR, (px + 3, py + 1, 11, 13))
        else:
            surf.blit(tile, (px, py))
    # blitting SRCALPHA tiles (fences + checkered line) zeroes out destination alpha in SDL;
    # restore full opacity so fences never black out under window composition or menu dimming
    surf.fill((0, 0, 0, 255), special_flags=pygame.BLEND_RGBA_MAX)
    GROUND_SURF = surf
    _build_zoomed_ground()


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


def new_map(seed, tileset=None):
    # builds the whole track + fences in one shot (no incremental generation)
    global ROAD, ROAD_S, ROAD_T, ROAD_LEN, DIRT, ROAD_NEAR, MAP_SEED
    if tileset is not None:
        set_tileset(tileset)
    elif TRACK_TYPE_MODE == "random":
        chosen = TILESETS[seed % len(TILESETS)]
        set_tileset(chosen)
    elif TRACK_TYPE_MODE in TILESETS:
        set_tileset(TRACK_TYPE_MODE)
    MAP_SEED = seed     # so boxes land identically for every player on this track
    ROAD = generate_road(seed)
    ROAD_S, ROAD_T = _road_tables(ROAD)
    ROAD_LEN = ROAD_S[-1]
    DIRT = build_dirt_grid(ROAD)
    ROAD_NEAR = _near_road_grid(DIRT, FENCE_OFFSET + 1)
    generate_fences()
    build_ground()
    _build_minimap()
    del BOX_EVENTS[:]   # pickups from a previous map (e.g. the menu backdrop) must never be broadcast
    del PARTICLES[:]
    del DEBRIS[:]
    del FX[:]
    global ACTIVE_BANNER
    ACTIVE_BANNER = None
    del PROJECTILES[:]
    del OIL[:]
    del CONES[:]
    del DESTRUCTIBLES[:]
    del TIRES[:]
    del RAMPS[:]
    spawn_boxes()
    spawn_test_ramps()
    spawn_test_tires(random.Random(seed + 222))
    spawn_traffic_cones(random.Random(seed + 999))
    spawn_destructibles(random.Random(seed + 777))
    rng_oil = random.Random(seed + 888)
    drop_oil(rng_oil.randint(3, 5), rng=rng_oil)


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
        self.last_wheel_pos = {}    # wheel_id -> (wx, wy) for continuous permanent ground tracks
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
        # bashing & sabotage
        self.bash_cd = 0.0          # seconds until the next bash is ready
        self.proj_cd = 0.0          # seconds until the next projectile can be fired
        self.item = None            # held powerup item: None | "cone" | "oil"
        self.sabotage_cd = 0.0      # cooldown between sabotages
        self.bash_time = 0.0        # > 0 while a bash/ram is active
        self.bash_kind = None
        self.bash_hits = set()      # who this bash has already hit (each victim once per bash)
        self.stagger = 0.0          # > 0 after being bashed: tyres are loose
        self.flash = 0.0            # white flash after a hit
        self.hit_flash = 0.0        # > 0 -> sprite flashes red (got bashed / hit a wall)
        self.impact = 0.0           # hardest hit this frame (camera shake)
        self.impact_vx = 0.0        # world-space impulse X of hardest hit
        self.impact_vy = 0.0        # world-space impulse Y of hardest hit
        self.draft = 0.0            # 0..1 slipstream strength, tucked in behind another kart
        self.airtime = 0.0          # > 0 while airborne off a ramp: off-road/oil can't touch you
        self.tire_bounce_grace = 0.0 # > 0 after colliding with rubber tire barrier: immune to damage/death
        self.wrong_way = False      # True when heading in reverse / opposite direction of the track
        self.wrong_way_time = 0.0   # seconds driving opposite way (triggers active deceleration and auto-turn)
        self.last_hit_by = 0
        # getting unstuck
        self.slow_time = 0.0
        self.reverse_time = 0.0
        self.wedged = 0.0           # seconds spent barely moving (backing up included)
        self.rescues = 0            # how many times this kart has been put back on the road
        # bots only
        self.is_bot = False
        self.is_remote = False      # true for other players' cars in multiplayer (driven by net)
        self.is_player = True       # true for local human player
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
        self.impact_vx = 0.0
        self.impact_vy = 0.0

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
        play_at("ram" if kind == "ram" else "bash", self.x, self.y)
        return True

    def start_shoot(self, aim_angle=None):
        # fire a projectile straight ahead from the nose or aimed forward in front hemisphere
        if self.proj_cd > 0 or self.reverse_time > 0 or self.dead:
            return False
        if aim_angle is not None:
            # "u can only shoot infront not back"
            diff = (aim_angle - self.angle + 180) % 360 - 180
            if abs(diff) > 85.0:
                return False
            fire_angle = aim_angle
        else:
            fire_angle = self.angle
        rad = math.radians(fire_angle)
        c, s = math.cos(rad), math.sin(rad)
        spawn_projectile(self.x + c * CAR_HL, self.y + s * CAR_HL,
                         c * PROJ_SPEED + self.vx, s * PROJ_SPEED + self.vy, self.uid)
        self.proj_cd = PROJ_COOLDOWN
        play_at("shoot", self.x, self.y)
        return True

    def use_sabotage(self, action_name, backward=False):
        if self.dead or self.reverse_time > 0:
            return False
        # When sabotaging with cone or oil, always spawn BEHIND the player, not in front
        if action_name in ("cone", "throw_cone", "drop_cone"):
            if self.item == "cone":
                self.item = None
                return throw_traffic_cone(self, forward=False)
            elif self.sabotage_cd <= 0:
                self.sabotage_cd = 1.6
                return throw_traffic_cone(self, forward=False)
        elif action_name in ("oil", "spill_oil"):
            if self.item == "oil":
                self.item = None
                return spill_oil(self)
            elif self.sabotage_cd <= 0:
                self.sabotage_cd = 1.8
                return spill_oil(self)
        elif action_name in ("drop_item", "drop_hazard"):
            if self.item == "cone":
                res = throw_traffic_cone(self, forward=False)
                self.item = None
                return res
            elif self.item == "oil":
                res = spill_oil(self)
                self.item = None
                return res
            elif self.sabotage_cd <= 0:
                self.sabotage_cd = 1.6
                return throw_traffic_cone(self, forward=False)
        elif action_name in ("item", "shoot"):
            if self.item == "cone":
                res = throw_traffic_cone(self, forward=False)
                self.item = None
                return res
            elif self.item == "oil":
                res = spill_oil(self)
                self.item = None
                return res
            elif action_name == "shoot":
                return self.start_shoot()
        return False

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
        rear_grip_mult = DRIFT_GRIP if self.drift else 1.0
        if CURRENT_TILESET == "canyon_sand":
            rear_grip_mult *= 0.82 if self.drift else 0.90
        rear = loose * rear_grip_mult      # drifting loosens the rear tyres
        cap_f = GRIP * (1 - self.off_f * (1 - GRASS_GRIP)) * loose * m * AXLE_REAR / WHEELBASE
        cap_r = GRIP * (1 - self.off_r * (1 - GRASS_GRIP)) * rear * m * AXLE_FRONT / WHEELBASE

        if CURRENT_TILESET == "canyon_sand":
            cap_f *= 0.88
            cap_r *= 0.88
        elif CURRENT_TILESET == "frost_pass" and not self.drift:
            # snow/ice physics: near-zero steering authority until counter-steering or drifting kicks in
            counter_steer = (steer_in * self.steer_angle < -0.04)
            if not counter_steer:
                cap_f *= 0.72
                cap_r *= 0.76

        # engine: forward acceleration, reverse, or braking
        if self.reverse_time > 0:
            drive = -REVERSE_ACCEL * m if v_long > -REVERSE_SPEED else 0.0
        elif getattr(self, "braking", False):
            if v_long > 15.0:
                drive = -BRAKE_ACCEL * m
            else:
                drive = -REVERSE_ACCEL * m if v_long > -REVERSE_SPEED else 0.0
        else:
            frac = min(max(v_long, 0.0) / MAX_SPEED, 1.0)
            boost = (1 + BOOST_PACE) if self.boost_time > 0 else (1 + (DRAFT_PACE if SLIPSTREAM_ASSIST else 0.0) * self.draft)
            drive = (ENGINE_ACCEL * m * self.pace * boost * (1 - frac * ENGINE_FALLOFF)
                     * (1 - self.off_r * GRASS_ENGINE_LOSS))
            if CURRENT_TILESET == "harvest_mud" and (self.off_f > 0.2 or self.off_r > 0.2):
                drive *= 0.82   # sludge drag
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
        self.proj_cd = max(0.0, self.proj_cd - dt)
        self.sabotage_cd = max(0.0, self.sabotage_cd - dt)
        self.bash_time = max(0.0, self.bash_time - dt)
        self.boost_time = max(0.0, self.boost_time - dt)
        self.stagger = max(0.0, self.stagger - dt)
        self.flash = max(0.0, self.flash - dt)
        self.hit_flash = max(0.0, self.hit_flash - dt)
        was_airborne = self.airtime > 0.0
        self.airtime = max(0.0, self.airtime - dt)
        if was_airborne and self.airtime <= 0.0:    # just landed -- a puff where the tyres touch down
            spawn_particles(self.x, self.y, 8, 70, (160, 150, 140), 0.35)
            play_at("land", self.x, self.y)
        self.grudge_time = max(0.0, self.grudge_time - dt)
        if self.grudge_time <= 0:
            self.grudge = 0

        # lose half a heart the moment you leave the road (edge-triggered + a cooldown)
        self.tire_bounce_grace = max(0.0, getattr(self, "tire_bounce_grace", 0.0) - dt)
        on_road = offroad_factor(self.x, self.y) <= 0.0 or self.airtime > 0.0 or self.tire_bounce_grace > 0.0
        self.heart_cooldown = max(0.0, self.heart_cooldown - dt)
        if self.was_on_road and not on_road and self.heart_cooldown <= 0.0 and self.tire_bounce_grace <= 0.0:
            self.hearts = max(0.0, self.hearts - HEART_PENALTY)
            self.heart_cooldown = HEART_COOLDOWN
            if getattr(self, "is_player", True) and not getattr(self, "is_remote", False):
                play("heart_lost")
        if self.hearts <= 0.0 and not self.dead:
            self.dead = True
            if getattr(self, "is_player", True) and not getattr(self, "is_remote", False):
                play("death")
            else:
                play_at("wreck", self.x, self.y)
            spawn_particles(self.x, self.y, 20, 150, (90, 90, 95), 0.8)
            spawn_fx(self.x, self.y - 10, "poof_dark", random.uniform(34, 42), dur=0.5)
        self.was_on_road = on_road

        # Wrong-way prevention: detect if human player is pointed or travelling backwards along the track
        if ROAD_T and not self.dead and self.airtime <= 0.0 and self.reverse_time <= 0 and not getattr(self, "is_bot", False):
            s_coord, lat_coord, tidx = track_coords(self.x, self.y, self.track_idx)
            tx, ty = ROAD_T[tidx]
            track_deg = math.degrees(math.atan2(ty, tx))
            ang_diff = (self.angle - track_deg + 180) % 360 - 180
            v_forward = self.vx * tx + self.vy * ty

            # Heading facing backwards (> 100 deg off track direction)
            is_wrong = (abs(ang_diff) > 100.0) and (v_forward < -30.0 or getattr(self, "throttle", 0.0) > 0.1)
            if is_wrong:
                self.wrong_way = True
                self.wrong_way_time = getattr(self, "wrong_way_time", 0.0) + dt
                # Strongly decelerate / brake backwards motion to prevent griefing
                brake_factor = max(0.15, 1.0 - 5.0 * dt)
                self.vx *= brake_factor
                self.vy *= brake_factor
                # Smoothly auto-steer / reorient the car back to the correct track heading if sustained
                if self.wrong_way_time > 0.6:
                    turn_dir = 1.0 if ang_diff < 0 else -1.0
                    reorient_rate = min(abs(ang_diff), 360.0 * dt)
                    self.angle = (self.angle + turn_dir * reorient_rate) % 360.0
                    self.omega *= 0.5
                    # Give a gentle nudge forward in the proper track direction
                    self.vx += tx * 140.0 * dt
                    self.vy += ty * 140.0 * dt
            else:
                self.wrong_way = False
                self.wrong_way_time = max(0.0, getattr(self, "wrong_way_time", 0.0) - dt * 2.0)

        # Fence boundary enforcement: kart must NEVER escape or get trapped in the outfield grass
        d_fence = dist_to_dirt(self.x, self.y, 400.0)
        max_fence_d = FENCE_OFFSET * TILE - 2.0
        if d_fence > max_fence_d and not self.dead:
            s, lat, tidx = track_coords(self.x, self.y, self.track_idx)
            safe_lat = max(-ROAD_WIDTH * 0.35, min(ROAD_WIDTH * 0.35, lat))
            rx, ry, heading = road_pose(s, safe_lat)
            self.x, self.y = rx % WORLD, ry % WORLD
            rad = math.radians(heading)
            spd = max(45.0, math.hypot(self.vx, self.vy) * 0.65)
            self.vx, self.vy = math.cos(rad) * spd, math.sin(rad) * spd
            self.omega = 0.0

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

        # Tyre tracks (continuous line segments that remain for TRAIL_LIFE=13s, then fade)
        keep = []
        for seg in self.trail:
            seg[4] -= dt
            if seg[4] > 0:
                keep.append(seg)
        self.trail = keep

        rad = math.radians(self.angle)
        c, s = math.cos(rad), math.sin(rad)
        skid_specs = (
            ("rl", -AXLE_REAR, -1, (self.slip_r > SKID_SLIP or self.drift), self.off_r),
            ("rr", -AXLE_REAR, 1, (self.slip_r > SKID_SLIP or self.drift), self.off_r),
            ("fl", AXLE_FRONT, -1, self.slip_f > SKID_SLIP * 1.35, self.off_f),
            ("fr", AXLE_FRONT, 1, self.slip_f > SKID_SLIP * 1.35, self.off_f),
        )
        for wname, ax, side, skidding, off in skid_specs:
            wx = self.x + c * ax - s * side * WHEEL_Y
            wy = self.y + s * ax + c * side * WHEEL_Y
            if skidding and not self.dead:
                prev = self.last_wheel_pos.get(wname)
                if prev is not None:
                    pwx, pwy = prev
                    dx, dy = wx - pwx, wy - pwy
                    dist_sq = dx * dx + dy * dy
                    # Normal frame motion (0.2px to 35px), ignore respawns / teleports
                    if 0.04 <= dist_sq < 1225.0:
                        w = 8 if self.drift else 6
                        self.trail.append([pwx, pwy, wx, wy, TRAIL_LIFE, w, off > 0.5])
                        if self.drift and self.rng.random() < 0.22:
                            spawn_tire_smoke(wx, wy, count=1, speed=30.0)
                self.last_wheel_pos[wname] = (wx, wy)
            else:
                self.last_wheel_pos[wname] = None

        if len(self.trail) > TRAIL_MAX_POINTS:
            self.trail = self.trail[-TRAIL_MAX_POINTS:]

        # Kicked up particles from wheels
        if self.off_r > 0.2 and speed > 50 and self.rng.random() < 0.7:
            if CURRENT_TILESET == "frost_pass":
                col = (240, 248, 255) if self.off_r > 0.5 else (165, 190, 206)
            else:
                col = (115, 175, 75) if self.off_r > 0.5 else (195, 140, 95)
            spawn_particles(self.x - c * AXLE_REAR, self.y - s * AXLE_REAR, 2, 45, col, 0.45)
        elif self.slip_r > SKID_SLIP * 1.4 and self.rng.random() < 0.6:
            slip_col = (180, 195, 205) if CURRENT_TILESET == "frost_pass" else (215, 160, 115)
            spawn_particles(self.x - c * AXLE_REAR, self.y - s * AXLE_REAR, 2, 35, slip_col, 0.45)

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
        if hasattr(self, "last_wheel_pos"):
            self.last_wheel_pos.clear()
        spawn_particles(self.x, self.y, 24, 100, (255, 255, 255), 0.6)
        spawn_particles(self.x, self.y, 12, 70, (255, 230, 130), 0.5)
        play_at("rescue", self.x, self.y, 1.0 if getattr(self, "is_player", False) else 0.5)

    def corners(self):
        rad = math.radians(self.angle)
        c, s = math.cos(rad), math.sin(rad)
        return [(self.x + px, self.y + py) for px, py in _corners_local(c, s, CAR_HL, CAR_HW)]


def make_bot(car, i, color, aggression_level=None):
    p = BOT_PROFILES[i % len(BOT_PROFILES)]
    car.is_bot = True
    car.is_player = False
    car.name = BOT_NAMES[i % len(BOT_NAMES)]
    car.flag = random.choice(FLAG_CODES) if FLAG_CODES else None
    car.color = color
    level = aggression_level or BOT_AGGRESSION
    if isinstance(level, str):
        level = level.capitalize()
    if level not in BOT_AGGRESSION_MULTS:
        level = "Normal"
    car.aggression_level = level
    mult = BOT_AGGRESSION_MULTS.get(level, 1.0)
    car.aggression = min(1.0, p["aggression"] * mult)
    car.lanes = p["lanes"]
    car.base_pace = car.pace = p.get("pace", 1.0) * (0.97 + 0.03 * mult)
    car.mass = p.get("mass", 1.0)
    car.hunts_player = p.get("hunts_player", False) or (level in ("Aggressive", "Brutal"))
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
    if COLLISION_RULE == "ghost":
        return
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
    if j > a.impact:
        a.impact = j
        a.impact_vx = -ix
        a.impact_vy = -iy
    if j > b.impact:
        b.impact = j
        b.impact_vx = ix
        b.impact_vy = iy
    wx, wy = a.x + px, a.y + py
    if j > 35:
        spawn_particles(wx, wy, min(int(j / 15), 18), 120, (255, 235, 140), 0.4)
        spawn_sparks(wx, wy, count=min(int(j / 4), 22), speed=210.0, normal=(nx, ny))

    # a bash adds an extra shove + loose tyres + spin to whoever it hits, once per bash
    if COLLISION_RULE != "solid":
        for basher, victim, sgn, rx, ry in ((a, b, 1, rbx, rby), (b, a, -1, rax, ray)):
            if basher.bash_time > 0 and victim.uid not in basher.bash_hits:
                basher.bash_hits.add(victim.uid)
                kx, ky = nx * sgn * BASH_KNOCK, ny * sgn * BASH_KNOCK
                victim.vx += kx
                victim.vy += ky
                victim.omega += (rx * ky - ry * kx) / (CAR_INERTIA * victim.mass) * BASH_SPIN
                victim.stagger = STAGGER_TIME
                victim.flash = 0.25
                victim.hit_flash = HIT_FLASH            # victim flashes red
                victim.last_hit_by = basher.uid
                victim.grudge, victim.grudge_time = basher.uid, 5.0
                victim.impact = max(victim.impact, BASH_KNOCK * 1.5)
                victim.impact_vx = kx
                victim.impact_vy = ky
                spawn_particles(wx, wy, 18, 160, (255, 240, 160), 0.5)
                spawn_sparks(wx, wy, count=24, speed=250.0, normal=(nx * sgn, ny * sgn))
                play_at("bash_hit", wx, wy)
                victim.bash_sounded = True      # step() skips its generic bump for this hit

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
    if j > car.impact:
        car.impact = j
        car.impact_vx = ix
        car.impact_vy = iy
    if j > WALL_HIT_IMPULSE:            # a real wall smack -> flash the sprite red
        car.hit_flash = HIT_FLASH
    if j > 45:
        spawn_particles(car.x + px, car.y + py, min(int(j / 18), 16), 110, (255, 230, 140), 0.45)
        spawn_wood_splinters(car.x + px, car.y + py, min(int(j / 8), 16), 160.0)


# =================================================================================================
# the world step
# =================================================================================================
def _ctrl(c):
    # controls entries may be (steer, action) or (steer, action, drift) or (steer, action, drift, brake)
    return (c[0], c[1],
            (c[2] if len(c) > 2 else False),
            (c[3] if len(c) > 3 else False))

def step(dt, cars, controls):
    # controls: one (steer -1..1, action or None[, drift, brake]) per car; action = "left"/"right"/"ram"
    for car, ctrl in zip(cars, controls):
        steer, action, drift, brake = _ctrl(ctrl)
        car.prepare()
        car.drift = bool(drift) and not car.dead
        car.braking = bool(brake) and not car.dead
        if action in ("cone", "throw_cone", "drop_cone", "oil", "spill_oil", "item", "drop_item", "drop_hazard"):
            car.use_sabotage(action)
        elif action == "shoot":
            if car.item:
                car.use_sabotage("item")
            else:
                car.start_shoot()
        elif isinstance(action, (tuple, list)) and len(action) > 1 and action[0] == "shoot_aim":
            car.start_shoot(aim_angle=action[1])
        elif action:
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
        if not car.dead and car.airtime <= 0.0:
            _apply_oil(car)
        if not car.dead:
            _apply_ramps(car)
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
            # Celebratory star burst when crossing finish line
            for c_col in ((255, 230, 80), (80, 205, 255), (255, 120, 180)):
                spawn_particles(car.x, car.y, 8, 110, c_col, 0.6)
            if getattr(car, "is_player", False) and not getattr(car, "is_remote", False) \
                    and lap < TOTAL_LAPS - 1:
                play("lap")
            # oil hazards appear on random laps (host/single-player owns the world)
            if NET_ROLE != "client" and random.random() < OIL_SPAWN_CHANCE:
                drop_oil(random.randint(2, 4))
    # one impact sound per frame, for the hardest hit (a landed bash already made its own)
    loud = max(cars, key=lambda c: c.impact, default=None)
    if loud is not None and not getattr(loud, "bash_sounded", False):
        if loud.impact > 180:
            play_at("crash", loud.x, loud.y)
        elif loud.impact > 80:
            play_at("bump", loud.x, loud.y, min(1.0, loud.impact / 180.0 + 0.3))
    for c in cars:
        c.bash_sounded = False
    _pack_pacing(cars)
    _update_draft(cars, dt)
    _update_boxes(dt, cars)
    _update_cones(dt, cars)
    _update_destructibles(dt, cars)
    _update_tires(cars)
    _update_particles(dt)
    _update_debris(dt)
    _update_fx(dt)
    _update_projectiles(dt, cars)
    update_banner(dt)

def _update_drift(car, dt):
    speed = math.hypot(car.vx, car.vy)
    turning = abs(car.steer_angle) > 0.08
    if car.drift and speed > DRIFT_MIN_SPEED and turning:
        before = car.drift_charge / DRIFT_MAX_CHARGE
        car.drift_charge = min(DRIFT_MAX_CHARGE, car.drift_charge + DRIFT_CHARGE_RATE * dt)
        after = car.drift_charge / DRIFT_MAX_CHARGE
        if getattr(car, "is_player", False) and not getattr(car, "is_remote", False):
            if before < 0.5 <= after:           # sparks turn orange
                play("drift_tick1")
            elif before < 0.9 <= after:         # ... and blue: full charge
                play("drift_tick2")
    if car.was_drifting and not car.drift:      # released
        if car.drift_charge >= DRIFT_MIN_CHARGE:
            f = min(1.0, car.drift_charge / DRIFT_MAX_CHARGE)
            car.boost_time = max(car.boost_time, DRIFT_BOOST_TIME * f)
            rad = math.radians(car.angle)
            car.vx += math.cos(rad) * DRIFT_BOOST_KICK * f
            car.vy += math.sin(rad) * DRIFT_BOOST_KICK * f
            bcol = (90, 215, 255) if f >= 0.9 else (255, 180, 50)
            play_at("drift_boost_max" if f >= 0.9 else "drift_boost", car.x, car.y,
                    1.0 if getattr(car, "is_player", False) else 0.6)
            spawn_particles(car.x - math.cos(rad) * CAR_HL, car.y - math.sin(rad) * CAR_HL, int(22 * f), 130, bcol, 0.6)
            spawn_particles(car.x - math.cos(rad) * CAR_HL, car.y - math.sin(rad) * CAR_HL, int(10 * f), 90, (230, 245, 255), 0.4)
            if getattr(car, "is_player", False) and not getattr(car, "is_remote", False):
                trigger_banner("DRIFT BOOST!", (255, 235, 70), sub="MINI-TURBO", dur=1.5)
        car.drift_charge = 0.0
    car.was_drifting = car.drift

def _spawn_car_fx(car):
    # surface dust off-road, boost flames, and the drift smoke that tints as the charge builds
    speed = math.hypot(car.vx, car.vy)
    off = 0.5 * (car.off_f + car.off_r)
    rad = math.radians(car.angle)
    c, s = math.cos(rad), math.sin(rad)
    bx, by = car.x - c * CAR_HL, car.y - s * CAR_HL
    if off > 0.2 and speed > 50 and random.random() < 0.75:
        if CURRENT_TILESET == "frost_pass":
            col = (235, 245, 255) if random.random() < 0.6 else (165, 190, 206)
        elif CURRENT_TILESET == "canyon_sand":
            col = (218, 177, 99) if random.random() < 0.5 else (180, 120, 60)
        elif CURRENT_TILESET == "harvest_mud":
            col = (110, 76, 48) if random.random() < 0.5 else (80, 52, 32)
        elif CURRENT_TILESET == "neon_night":
            col = (0, 240, 255) if random.random() < 0.5 else (255, 0, 180)
        else:
            col = (115, 175, 75) if off > 0.5 else (195, 140, 95)
        spawn_particles(bx, by, 2, 45, col, 0.45)   # kicked-up dust/grass
    if car.drift and speed > DRIFT_MIN_SPEED:
        f = min(1.0, car.drift_charge / DRIFT_MAX_CHARGE)
        for side in (-1, 1):
            tx = car.x - c * AXLE_REAR - s * side * WHEEL_Y
            ty = car.y - s * AXLE_REAR + c * side * WHEEL_Y
            if CURRENT_TILESET == "neon_night":
                col = (0, 240, 255) if random.random() < 0.5 else (255, 0, 180)
                cnt = 2 if f < 0.6 else 3
            elif f < 0.5:
                col = (245, 245, 250) if random.random() < 0.7 else (255, 215, 130)
                cnt = 2
            elif f < 0.9:
                col = (255, 170, 45) if random.random() < 0.7 else (255, 235, 90)
                cnt = 2
            else:
                col = (85, 215, 255) if random.random() < 0.7 else (210, 245, 255)
                cnt = 3
            spawn_particles(tx, ty, cnt, 65, col, 0.45)
    if car.boost_time > 0:
        for side in (-1, 1):
            tx = car.x - c * CAR_HL - s * side * 4.5
            ty = car.y - s * CAR_HL + c * side * 4.5
            b_col = (255, 145, 35) if random.random() < 0.6 else (255, 225, 80)
            spawn_particles(tx, ty, 2, 85, b_col, 0.38)
    if car.impact > 40:        # sparks on a scrape / collision
        spk_cnt = min(int(car.impact / 12), 22)
        spk_col = (255, 245, 160) if random.random() < 0.5 else (255, 195, 60)
        spawn_particles(car.x, car.y, spk_cnt, 150, spk_col, 0.4)
    # animated dust puffs kicked up when sliding / drifting / running on the grass
    drifting = car.drift and speed > DRIFT_MIN_SPEED
    if (drifting or car.slip_r > SKID_SLIP * 1.4 or (off > 0.3 and speed > 90)) \
            and not car.dead:
        side = random.choice((-1, 1))
        dx = car.x - c * AXLE_REAR - s * side * WHEEL_Y
        dy = car.y - s * AXLE_REAR + c * side * WHEEL_Y
        if random.random() < 0.35:
            spawn_fx(dx, dy, "dust1" if random.random() < 0.5 else "dust2", random.uniform(13, 19))
        if drifting and random.random() < 0.7:
            spawn_tire_smoke(dx, dy, count=2, speed=45.0)

def _update_draft(cars, dt):
    # tuck in close behind another kart, pointed roughly the same way -> slipstream kicks in
    n = len(cars)
    for a in cars:
        best = 0.0
        if not a.dead:
            rad = math.radians(a.angle)
            fx, fy = math.cos(rad), math.sin(rad)
            for b in cars:
                if b is a or b.dead:
                    continue
                dx, dy = wrap_delta(b.x, a.x), wrap_delta(b.y, a.y)   # a - b: points back from b to a
                dist = math.hypot(dx, dy)
                if dist < 4.0 or dist > DRAFT_RANGE:
                    continue
                # is b roughly ahead of a, and is a lined up behind it (not beside)?
                ahead = (-dx * fx - dy * fy) / dist     # +1 = b dead ahead of a
                if ahead < DRAFT_CONE:
                    continue
                strength = ahead * (1.0 - dist / DRAFT_RANGE)
                best = max(best, strength)
        old_draft = a.draft
        a.draft += (best - a.draft) * min(1.0, (DRAFT_RISE if best > a.draft else DRAFT_FALL) * dt)
        if getattr(a, "is_player", False) and not getattr(a, "is_remote", False):
            if old_draft < 0.82 and a.draft >= 0.82:
                trigger_banner("SLIPSTREAM!", (70, 215, 255), sub="DRAFT BOOST ACTIVE", dur=1.6)
                play("slipstream")

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
    if BOT_AGGRESSION != "Chill":
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

    lane_goal = 0.0 if BOT_AGGRESSION == "Chill" else bot.lane_target
    if target is not None and bot.reverse_time <= 0:
        _, t_lat, _ = track_coords(target.x, target.y, idx)
        aggr = min(1.0, bot.aggression * (1.6 if target.uid == bot.grudge else 1.0))
        if BOT_AGGRESSION == "Demolition":
            aggr = 1.0
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
        # fire a projectile at a rival lined up ahead and out of bash range
        if action is None and bot.proj_cd <= 0 and 40 < tfx < 300 and abs(tfy) < 24:
            if rnd.random() < aggr * 1.6 * dt:
                action = "shoot"
        # sabotage rivals with cones or oil slicks
        if action is None:
            if bot.item == "cone" or (bot.sabotage_cd <= 0 and rnd.random() < aggr * 0.35 * dt):
                if 35 < tfx < 240 and abs(tfy) < 28:
                    action = "cone"
                elif -140 < tfx < -20 and abs(tfy) < 32:
                    action = "drop_cone"
            elif bot.item == "oil" or (bot.sabotage_cd <= 0 and rnd.random() < aggr * 0.35 * dt):
                if -150 < tfx < -15 and abs(tfy) < 35:
                    action = "oil"

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
        self.trauma_x = 0.0
        self.trauma_y = 0.0
        self.trauma_vx = 0.0
        self.trauma_vy = 0.0
        self.zoom = ZOOM
        self.target_zoom = ZOOM
        self.override_zoom = None
        self.lead_x = 0.0
        self.lead_y = 0.0
        self.sway_t = 0.0           # cinematic handheld-sway clock
        rad = -math.radians(self.angle + 90)
        self.cos_c, self.sin_c = math.cos(rad), math.sin(rad)

    def update(self, dt, car):
        # Dynamic look-ahead camera or centered camera
        if DYNAMIC_LOOK_AHEAD and not car.dead:
            target_lx = (car.vx / max(1.0, MAX_SPEED)) * 52.0
            target_ly = (car.vy / max(1.0, MAX_SPEED)) * 52.0
        else:
            target_lx = 0.0
            target_ly = 0.0
        self.lead_x += (target_lx - self.lead_x) * min(1.0, dt * 3.5)
        self.lead_y += (target_ly - self.lead_y) * min(1.0, dt * 3.5)
        self.x = (car.x + self.lead_x) % WORLD
        self.y = (car.y + self.lead_y) % WORLD
        speed = math.hypot(car.vx, car.vy)

        # Dynamic Speed & Boost Zoom (FOV dilation)
        if getattr(self, "override_zoom", None) is not None:
            self.target_zoom = self.override_zoom
        else:
            target_z = ZOOM
            if getattr(car, "boost_time", 0.0) > 0.0:
                target_z = ZOOM * 0.85      # hard punch-out on boost for a speed rush
            elif getattr(car, "draft", 0.0) > 0.7 or speed > 225.0:
                target_z = ZOOM * 0.90      # ease back when drafting / flat out
            elif getattr(car, "drift", False):
                target_z = ZOOM * 1.09      # whip in tight on drift
            elif speed < 50.0:
                target_z = ZOOM * 1.04
            self.target_zoom = target_z
        z_spd = 3.2 if self.target_zoom < self.zoom else 4.2   # snappier, more cinematic dilation
        self.zoom += (self.target_zoom - self.zoom) * min(1.0, dt * z_spd)

        # 3. Rotational follow
        t_rot = min(CAM_ROT_SMOOTH * dt, 1)
        target = car.angle
        if speed > 60:
            w = min(1.0, (speed - 60) / 120) * CAM_VEL_FOLLOW
            target = lerp_angle(car.angle, math.degrees(math.atan2(car.vy, car.vx)), w)
        self.angle = lerp_angle(self.angle, target, t_rot)

        # 4. Directional Camera Trauma (Damped Spring Physics)
        # Instead of uniform random noise jitter, kick the camera in the actual vector direction
        # of the impact force, decaying with damped spring physics.
        imp = getattr(car, "impact", 0.0)
        if imp > 0.0:
            ivx = getattr(car, "impact_vx", 0.0)
            ivy = getattr(car, "impact_vy", 0.0)
            rad_cam = -math.radians(self.angle + 90)
            cos_c, sin_c = math.cos(rad_cam), math.sin(rad_cam)
            if abs(ivx) > 0.01 or abs(ivy) > 0.01:
                skx = ivx * cos_c - ivy * sin_c
                sky = ivx * sin_c + ivy * cos_c
                smag = math.hypot(skx, sky)
                if smag > 0.01:
                    kick = min(300.0, imp * 1.45)
                    self.trauma_vx += (skx / smag) * kick
                    self.trauma_vy += (sky / smag) * kick
            else:
                c_rad = math.radians(car.angle)
                fx, fy = math.cos(c_rad), math.sin(c_rad)
                skx = fx * cos_c - fy * sin_c
                sky = fx * sin_c + fy * cos_c
                self.trauma_vx += skx * min(230.0, imp)
                self.trauma_vy += sky * min(230.0, imp)

        sub_dt = min(dt, 0.05)
        k_spring = 145.0
        c_damp = 14.0       # a touch bouncier so big hits wobble longer (more cinematic)
        ax = -k_spring * self.trauma_x - c_damp * self.trauma_vx
        ay = -k_spring * self.trauma_y - c_damp * self.trauma_vy
        self.trauma_vx += ax * sub_dt
        self.trauma_vy += ay * sub_dt
        self.trauma_x += self.trauma_vx * sub_dt
        self.trauma_y += self.trauma_vy * sub_dt

        # High-frequency shudder: hits, plus a continuous rumble from speed / grass / boost
        self.shake = min(1.0, max(0.0, self.shake - dt * 2.8) + imp / SHAKE_IMPULSE)
        speed_frac = min(1.0, speed / MAX_SPEED)
        offroad = 0.5 * (getattr(car, "off_f", 0.0) + getattr(car, "off_r", 0.0))
        ambient = 0.0
        if not car.dead:
            ambient += offroad * (0.4 + 0.6 * speed_frac)          # bouncing over the grass
            if getattr(car, "boost_time", 0.0) > 0.0:
                ambient += 0.55                                    # boost kick-in rumble
            ambient += max(0.0, speed_frac - 0.72) * 1.8           # top-speed buzz
        rumble = SHAKE_PX * (0.22 * self.shake * self.shake + 0.5 * min(1.2, ambient))
        rx = random.uniform(-rumble, rumble)
        ry = random.uniform(-rumble, rumble)

        # Handheld cinematic sway: a slow lissajous drift so the frame always breathes a little
        self.sway_t = getattr(self, "sway_t", 0.0) + dt
        sway_amp = SHAKE_PX * 0.18 * (0.5 + 0.5 * speed_frac)
        sx = math.sin(self.sway_t * 1.7) * sway_amp
        sy = math.cos(self.sway_t * 1.3) * sway_amp * 0.6

        scale = SHAKE_SCALE
        self.ox = (self.trauma_x + rx + sx) * scale
        self.oy = (self.trauma_y + ry + sy) * scale
        rad_f = -math.radians(self.angle + 90)
        self.cos_c, self.sin_c = math.cos(rad_f), math.sin(rad_f)

    def to_screen(self, wx, wy):
        dx, dy = wrap_delta(self.x, wx), wrap_delta(self.y, wy)
        c = getattr(self, "cos_c", None)
        if c is not None:
            s = self.sin_c
        else:
            rad = -math.radians(self.angle + 90)
            c, s = math.cos(rad), math.sin(rad)
        z = getattr(self, "zoom", ZOOM)
        return (W / 2 + (dx * c - dy * s) * z + self.ox,
                H / 2 + (dx * s + dy * c) * z + self.oy)

    def to_world(self, sx, sy):
        z = getattr(self, "zoom", ZOOM)
        px = (sx - W / 2 - self.ox) / z
        py = (sy - H / 2 - self.oy) / z
        c = getattr(self, "cos_c", None)
        if c is not None:
            s = self.sin_c
        else:
            rad = -math.radians(self.angle + 90)
            c, s = math.cos(rad), math.sin(rad)
        dx = px * c + py * s
        dy = -px * s + py * c
        return (self.x + dx) % WORLD, (self.y + dy) % WORLD


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

# =================================================================================================
# debris, sparks & tire smoke (cinematic dynamic fx)
# =================================================================================================
DEBRIS = []  # [x, y, vx, vy, life, max_life, kind, col, p1, p2, rot, vrot]
MAX_DEBRIS = 400

def spawn_wood_splinters(x, y, count=12, speed=160.0):
    WOOD_COLS = ((195, 145, 95), (150, 100, 60), (225, 185, 125), (115, 75, 45))
    for _ in range(count):
        if len(DEBRIS) >= MAX_DEBRIS:
            break
        ang = random.uniform(0, math.tau)
        spd = random.uniform(0.35, 1.0) * speed
        vx, vy = math.cos(ang) * spd, math.sin(ang) * spd
        ttl = random.uniform(0.5, 0.9)
        col = random.choice(WOOD_COLS)
        w = random.uniform(1.8, 3.2)
        h = random.uniform(5.0, 9.5)
        rot = random.uniform(0, 360)
        vrot = random.uniform(-650, 650)
        DEBRIS.append([x % WORLD, y % WORLD, vx, vy, ttl, ttl, "wood", col, w, h, rot, vrot])

def spawn_sparks(x, y, count=16, speed=220.0, normal=None):
    SPARK_COLS = ((255, 255, 220), (255, 225, 80), (255, 180, 40), (255, 130, 20))
    for _ in range(count):
        if len(DEBRIS) >= MAX_DEBRIS:
            break
        if normal is not None:
            nx, ny = normal
            base_ang = math.atan2(ny, nx)
            ang = base_ang + random.uniform(-1.25, 1.25)
        else:
            ang = random.uniform(0, math.tau)
        spd = random.uniform(0.4, 1.0) * speed
        vx, vy = math.cos(ang) * spd, math.sin(ang) * spd
        ttl = random.uniform(0.2, 0.45)
        col = random.choice(SPARK_COLS)
        length = random.uniform(3.5, 7.5)
        DEBRIS.append([x % WORLD, y % WORLD, vx, vy, ttl, ttl, "spark", col, 1.5, length, 0.0, 0.0])

def spawn_tire_smoke(x, y, count=2, speed=35.0):
    SMOKE_COLS = ((235, 235, 240), (210, 210, 215), (185, 185, 190))
    for _ in range(count):
        if len(DEBRIS) >= MAX_DEBRIS:
            break
        ang = random.uniform(0, math.tau)
        spd = random.uniform(0.2, 0.8) * speed
        vx, vy = math.cos(ang) * spd, math.sin(ang) * spd
        ttl = random.uniform(0.4, 0.75)
        col = random.choice(SMOKE_COLS)
        init_r = random.uniform(3.5, 6.0)
        max_r = random.uniform(12.0, 18.0)
        DEBRIS.append([x % WORLD, y % WORLD, vx, vy, ttl, ttl, "smoke", col, init_r, max_r, 0.0, 0.0])

def _update_debris(dt):
    keep = []
    for d in DEBRIS:
        d[4] -= dt
        if d[4] <= 0:
            continue
        kind = d[6]
        d[0] = (d[0] + d[2] * dt) % WORLD
        d[1] = (d[1] + d[3] * dt) % WORLD
        if kind == "wood":
            d[2] *= max(0.0, 1.0 - 3.8 * dt)
            d[3] *= max(0.0, 1.0 - 3.8 * dt)
            d[10] += d[11] * dt
        elif kind == "spark":
            d[2] *= max(0.0, 1.0 - 6.0 * dt)
            d[3] *= max(0.0, 1.0 - 6.0 * dt)
        elif kind == "smoke":
            d[2] *= max(0.0, 1.0 - 2.5 * dt)
            d[3] *= max(0.0, 1.0 - 2.5 * dt)
        keep.append(d)
    DEBRIS[:] = keep

FX_FPS = 20.0       # animation speed of one-shot sprite effects
MAX_FX = 200

def spawn_fx(x, y, name, world_w, dur=None, rot=None):
    frames = FX_FRAMES.get(name)
    if not frames or len(FX) >= MAX_FX:
        return
    if dur is None:
        dur = len(frames) / FX_FPS
    if rot is None:
        rot = random.uniform(0, 360)
    FX.append([x % WORLD, y % WORLD, name, 0.0, dur, world_w, rot])

def _update_fx(dt):
    keep = [f for f in FX if (f.__setitem__(3, f[3] + dt) or f[3] < f[4])]
    FX[:] = keep

def _fx_frame(name, frame, w):
    frames = FX_FRAMES.get(name)
    if not frames:
        return None
    frame = max(0, min(len(frames) - 1, frame))
    key = (name, frame, w)
    img = _FX_CACHE.get(key)
    if img is None:
        src = frames[frame]
        h = max(2, round(w * src.get_height() / src.get_width()))
        img = pygame.transform.smoothscale(src, (w, h))
        _FX_CACHE[key] = img
    return img

# ---- projectiles & oil slicks -------------------------------------------------------
PROJECTILES = []    # [x, y, vx, vy, life, owner_uid]
OIL = []            # [x, y, r] oil slicks on the track

def spawn_projectile(x, y, vx, vy, owner_uid):
    PROJECTILES.append([x % WORLD, y % WORLD, vx, vy, PROJ_LIFE, owner_uid])

def _update_projectiles(dt, cars):
    keep = []
    for p in PROJECTILES:
        p[4] -= dt
        if p[4] <= 0:
            continue
        p[0] = (p[0] + p[2] * dt) % WORLD
        p[1] = (p[1] + p[3] * dt) % WORLD
        hit = False
        for car in cars:
            if car.uid == p[5] or car.dead:
                continue
            dx, dy = wrap_delta(p[0], car.x), wrap_delta(p[1], car.y)
            if dx * dx + dy * dy <= (CAR_BOUND + PROJ_R) ** 2:
                sp = math.hypot(p[2], p[3]) or 1.0
                car.vx += p[2] / sp * PROJ_KNOCK
                car.vy += p[3] / sp * PROJ_KNOCK
                car.omega += random.uniform(-1.5, 1.5)
                car.stagger = STAGGER_TIME
                car.flash = 0.25
                car.hit_flash = HIT_FLASH
                car.last_hit_by = p[5]
                car.grudge, car.grudge_time = p[5], 5.0
                car.impact = max(car.impact, PROJ_KNOCK * 1.4)
                spawn_particles(p[0], p[1], 16, 150, (255, 210, 90), 0.4)
                spawn_fx(p[0], p[1], "fire1", 20, dur=0.3)
                play_at("proj_hit", p[0], p[1])
                car.bash_sounded = True
                hit = True
                break
        if not hit:
            keep.append(p)
    PROJECTILES[:] = keep

def make_oil_track_sprite(width, length):
    # Generates a pixel art oil track sprite of requested width and length from the 48x48 oil_track_tiles.
    # Sprite orientation is vertical (height = length, width = width), with tapered caps and organic side lobes.
    if not OIL_TILES:
        surf = pygame.Surface((width, length), pygame.SRCALPHA)
        pygame.draw.ellipse(surf, (27, 26, 40, 230), (0, 0, width, length))
        return surf

    surf = pygame.Surface((width, length), pygame.SRCALPHA)
    cap_h = min(16, max(4, length // 3))
    mid_h = max(1, length - 2 * cap_h)

    if width <= 20:
        # Narrow streak / single line of oil
        top_s = pygame.transform.scale(OIL_TILES["top"], (width, cap_h))
        bot_s = pygame.transform.scale(OIL_TILES["bot"], (width, cap_h))
        mid_s = pygame.transform.scale(OIL_TILES["center"], (width, mid_h))
        surf.blit(top_s, (0, 0))
        surf.blit(mid_s, (0, cap_h))
        surf.blit(bot_s, (0, length - cap_h))
    else:
        # Multi-column / 9-slice oil track with side lobes and center fill
        cap_w = min(16, max(4, width // 3))
        mid_w = max(1, width - 2 * cap_w)
        top_s = pygame.transform.scale(OIL_TILES["top"], (mid_w, cap_h))
        bot_s = pygame.transform.scale(OIL_TILES["bot"], (mid_w, cap_h))
        surf.blit(top_s, (cap_w, 0))
        surf.blit(bot_s, (cap_w, length - cap_h))
        left_s = pygame.transform.scale(OIL_TILES["left"], (cap_w, mid_h))
        right_s = pygame.transform.scale(OIL_TILES["right"], (cap_w, mid_h))
        surf.blit(left_s, (0, cap_h))
        surf.blit(right_s, (width - cap_w, cap_h))
        center_s = pygame.transform.scale(OIL_TILES["center"], (mid_w, mid_h))
        surf.blit(center_s, (cap_w, cap_h))

    return surf

def _get_oil_sprite(width, length):
    key = (width, length)
    if key not in _OIL_SPRITE_CACHE:
        _OIL_SPRITE_CACHE[key] = make_oil_track_sprite(width, length)
    return _OIL_SPRITE_CACHE[key]

def _get_oil_zoom_sprite(width, length, zw, zl):
    key = (width, length, zw, zl)
    if key not in _OIL_ZOOM_CACHE:
        base = _get_oil_sprite(width, length)
        _OIL_ZOOM_CACHE[key] = pygame.transform.scale(base, (zw, zl))
    return _OIL_ZOOM_CACHE[key]

def is_obstacle_pos_clear(x, y, min_dist=28.0, check_boxes=True, check_cones=True,
                           check_destruct=True, check_tires=True, check_ramps=True, check_oil=False):
    """Ensures tires, vases, cones, boxes, and props do not overlap each other on the track."""
    min_dist_sq = min_dist * min_dist
    if check_boxes and "BOXES" in globals():
        for b in BOXES:
            dx = wrap_delta(x, b["x"])
            dy = wrap_delta(y, b["y"])
            if dx * dx + dy * dy < min_dist_sq:
                return False
    if check_cones and "CONES" in globals():
        for c in CONES:
            dx = wrap_delta(x, c["x"])
            dy = wrap_delta(y, c["y"])
            if dx * dx + dy * dy < min_dist_sq:
                return False
    if check_destruct and "DESTRUCTIBLES" in globals():
        for d in DESTRUCTIBLES:
            dx = wrap_delta(x, d["x"])
            dy = wrap_delta(y, d["y"])
            if dx * dx + dy * dy < min_dist_sq:
                return False
    if check_tires and "TIRES" in globals():
        for tp in TIRES:
            dx = wrap_delta(x, tp["x"])
            dy = wrap_delta(y, tp["y"])
            if dx * dx + dy * dy < min_dist_sq:
                return False
    if check_ramps and "RAMPS" in globals():
        for rp in RAMPS:
            dx = wrap_delta(x, rp["x"])
            dy = wrap_delta(y, rp["y"])
            if dx * dx + dy * dy < (min_dist + 16.0) ** 2:
                return False
    if check_oil and "OIL" in globals():
        for o in OIL:
            dx = wrap_delta(x, o[0])
            dy = wrap_delta(y, o[1])
            if dx * dx + dy * dy < min_dist_sq:
                return False
    return True

def drop_oil(n=1, rng=None):
    if ROAD_LEN <= 1.0:
        return
    r = rng if rng is not None else random
    for _ in range(n):
        s = r.uniform(0, ROAD_LEN)
        lat = r.uniform(-1, 1) * ROAD_WIDTH * 0.38
        x, y, heading = road_pose(s, lat)
        ox, oy = x % WORLD, y % WORLD
        if not is_obstacle_pos_clear(ox, oy, min_dist=30.0, check_boxes=True, check_cones=True, check_destruct=True, check_tires=True, check_ramps=True):
            continue

        preset = r.choices(["narrow", "medium", "wide", "large_pool"], weights=[25, 30, 15, 30])[0]
        if preset == "narrow":
            w = r.choice([14, 16, 18, 20])
            l = r.choice([48, 64, 80, 96])
        elif preset == "medium":
            w = r.choice([24, 28, 32, 36])
            l = r.choice([40, 52, 68, 84, 100])
        elif preset == "wide":
            w = r.choice([40, 44, 48])
            l = r.choice([48, 64, 80, 96, 112])
        else:  # large_pool: substantial wide oil body / pool instead of single straight line
            w = r.choice([56, 64, 72, 80, 88])
            l = r.choice([56, 68, 76, 88, 96])

        angle = heading + r.uniform(-15.0, 15.0)
        max_r = max(l, w) * 0.5
        OIL.append([ox, oy, l, w, angle, max_r])

    if len(OIL) > OIL_MAX:
        del OIL[:len(OIL) - OIL_MAX]

def _apply_oil(car):
    # a kart whose centre is on an oil track loses grip and fishtails
    for item in OIL:
        ox, oy = item[0], item[1]
        length = item[2]
        width = item[3] if len(item) > 3 else length
        angle = item[4] if len(item) > 4 else 0.0

        max_r = max(length, width) * 0.55
        dx, dy = wrap_delta(ox, car.x), wrap_delta(oy, car.y)
        if dx * dx + dy * dy > max_r * max_r:
            continue

        rad = math.radians(angle)
        cos_a, sin_a = math.cos(rad), math.sin(rad)
        lx = dx * cos_a + dy * sin_a
        ly = -dx * sin_a + dy * cos_a
        hl = max(1.0, length * 0.5)
        hw = max(1.0, width * 0.5)
        if (lx / hl) ** 2 + (ly / hw) ** 2 <= 1.0:
            car.stagger = max(car.stagger, 0.18)
            car.omega += random.uniform(-0.6, 0.6)
            if not getattr(car, "on_oil", False):
                play_at("oil_slip", car.x, car.y)
            car.on_oil = True
            return
    car.on_oil = False

def _apply_ramps(car):
    # drive through a ramp zone while grounded -> launched: a forward kick plus a short
    # airborne window where off-road grass and oil can't touch you
    if car.airtime > 0.0:
        return
    for rp in RAMPS:
        dx, dy = wrap_delta(rp["x"], car.x), wrap_delta(rp["y"], car.y)
        max_r = max(rp["l"], rp["w"]) * 0.6
        if dx * dx + dy * dy > max_r * max_r:
            continue
        rad = math.radians(rp["angle"])
        cos_a, sin_a = math.cos(rad), math.sin(rad)
        lx = dx * cos_a + dy * sin_a
        ly = -dx * sin_a + dy * cos_a
        hl, hw = max(1.0, rp["l"] * 0.5), max(1.0, rp["w"] * 0.5)
        if (lx / hl) ** 2 + (ly / hw) ** 2 <= 1.0:
            car_rad = math.radians(car.angle)
            car.vx += math.cos(car_rad) * RAMP_KICK
            car.vy += math.sin(car_rad) * RAMP_KICK
            car.airtime = RAMP_AIR_TIME
            spawn_particles(car.x, car.y, 10, 100, (210, 210, 220), 0.4)
            play_at("ramp_launch", car.x, car.y)
            return

RAMP_KINDS = ("wood",)   # dirt ramp removed per request

def spawn_test_ramps():
    del RAMPS[:]
    if ROAD_LEN <= 1.0:
        return
    for i, frac in enumerate((0.25,)):
        s = ROAD_LEN * frac
        x, y, heading = road_pose(s)
        kind = RAMP_KINDS[i % len(RAMP_KINDS)]
        RAMPS.append({"x": x, "y": y, "angle": heading, "w": RAMP_WIDTH, "l": RAMP_LEN, "kind": kind})

def draw_ramps(screen, cam):
    # sprite-stack ramps (assets/ramps/*_stack.png via ramps.py)
    for rp in RAMPS:
        ramps.draw(screen, cam, rp.get("kind", "wood"), rp["x"], rp["y"], rp["angle"])

TIRE_KINDS = ("tires1", "tires2", "tires3")
TIRE_R = 18.0            # collision radius, roughly the drawn pile's footprint
TIRE_RESTITUTION = 0.45  # a stacked tyre pile gives more than a fence, less than a cone

def spawn_turn_tire_barriers(rng=None):
    """Detects sharpest turn crash zones and places a small protective tire barrier cluster on the outside shoulder."""
    del TIRES[:]
    if not ROAD or ROAD_LEN <= 1.0 or len(ROAD) < 6:
        return
    r = rng if rng is not None else random
    n = len(ROAD)

    # 1. Identify turn zones based on track curvature
    zones = []
    cur_zone = None
    for i in range(n):
        t1 = ROAD_T[i]
        t2 = ROAD_T[(i + 1) % n]
        ang1 = math.atan2(t1[1], t1[0])
        ang2 = math.atan2(t2[1], t2[0])
        d_ang = (ang2 - ang1 + math.pi) % (2 * math.pi) - math.pi
        s = ROAD_S[i]
        if abs(d_ang) > 0.008:
            # d_ang > 0 = turning left -> centrifugal drift to right (side = -1.0)
            # d_ang < 0 = turning right -> centrifugal drift to left (side = 1.0)
            side = -1.0 if d_ang > 0 else 1.0
            if cur_zone is not None and cur_zone["side"] == side:
                cur_zone["end_s"] = s
                cur_zone["count"] += 1
                cur_zone["max_curv"] = max(cur_zone["max_curv"], abs(d_ang))
            else:
                if cur_zone and cur_zone["count"] >= 3:
                    zones.append(cur_zone)
                cur_zone = {"start_s": s, "end_s": s, "side": side, "count": 1, "max_curv": abs(d_ang)}
        else:
            if cur_zone and cur_zone["count"] >= 3:
                zones.append(cur_zone)
            cur_zone = None
    if cur_zone and cur_zone["count"] >= 3:
        zones.append(cur_zone)

    if not zones:
        return

    # Select only the top 2-3 sharpest corners with the highest curvature (avoid too many tires)
    zones.sort(key=lambda z: z.get("max_curv", 0.0), reverse=True)
    sharp_zones = zones[:3]

    # Place a small, tidy cluster of 2 to 3 tires at each chosen corner
    for z in sharp_zones:
        start_s = z["start_s"]
        end_s = z["end_s"]
        side = z["side"]
        mid_s = (start_s + (end_s - start_s) % ROAD_LEN * 0.5) % ROAD_LEN
        for step_i in (-1, 0, 1):
            ts = (mid_s + step_i * 22.0) % ROAD_LEN
            lat = side * (ROAD_WIDTH * 0.38)
            x, y, heading = road_pose(ts, lat)
            pos_x, pos_y = x % WORLD, y % WORLD
            # The tire barrier must sit firmly on the road surface, never in the dirt buffer or against the fence
            if dist_to_dirt(pos_x, pos_y, 400.0) > 0.0:
                continue
            if not is_obstacle_pos_clear(pos_x, pos_y, min_dist=28.0, check_tires=True):
                continue
            TIRES.append({
                "x": pos_x,
                "y": pos_y,
                "angle": heading + r.uniform(-12, 12),
                "kind": r.choice(TIRE_KINDS),
                "wobble": 0.0,
            })

spawn_test_tires = spawn_turn_tire_barriers

def draw_tires(screen, cam):
    for tp in TIRES:
        wox = 0.0
        if tp.get("wobble", 0.0) > 0.0:
            wox = math.sin(tp["wobble"] * 40.0) * 3.0 / ZOOM
        ramps.draw(screen, cam, tp["kind"], tp["x"] + wox, tp["y"], tp["angle"])

def draw_trees(screen, cam):
    # sprite-stack trees at the grid cells _bake_bushes picked; angle 0 keeps the baked-in
    # sunlight lined up with the fence/kart shadows, same as the flat sprites did
    if not TREE_STACK_SEQ:
        return
    n = len(TREE_STACK_SEQ)
    for gx, gy in TREES:
        idx = (gx * 73856093 ^ gy * 19349663 ^ MAP_SEED) % n
        x, y = gx * TILE + TILE / 2, gy * TILE + TILE / 2
        ramps.draw(screen, cam, TREE_STACK_SEQ[idx], x, y, 0.0)

def _update_tires(cars):
    # Rubber bouncy tire barriers:
    # When colliding with a tire barrier, cars do not die or lose hearts.
    # Depending on impact speed, the tire pushes / bounces the car back onto the track.
    if not TIRES:
        return
    min_dist = TIRE_R + CAR_HW
    for tp in TIRES:
        if tp.get("wobble", 0.0) > 0.0:
            tp["wobble"] = max(0.0, tp["wobble"] - 0.016)

        for car in cars:
            dx, dy = wrap_delta(tp["x"], car.x), wrap_delta(tp["y"], car.y)
            dist_sq = dx * dx + dy * dy
            if dist_sq >= min_dist * min_dist:
                continue
            dist = max(0.001, math.sqrt(dist_sq))
            nx, ny = dx / dist, dy / dist
            pen = min_dist - dist

            # 1. Heart protection & life preservation (no death, no heart loss from tires)
            car.tire_bounce_grace = 1.2
            car.heart_cooldown = max(car.heart_cooldown, 1.8)
            if car.hearts < 1.0:
                car.hearts = 1.0
            car.dead = False

            # 2. Determine inward direction toward the track centerline
            s_tp, lat_tp, tidx = track_coords(tp["x"], tp["y"])
            rx, ry, _ = road_pose(s_tp, 0.0)
            in_dx = wrap_delta(tp["x"], rx)
            in_dy = wrap_delta(tp["y"], ry)
            in_dist = max(0.001, math.hypot(in_dx, in_dy))
            ix, iy = in_dx / in_dist, in_dy / in_dist

            # 3. Blend collision normal with inward track normal
            bx = 0.35 * nx + 0.65 * ix
            by = 0.35 * ny + 0.65 * iy
            b_mag = max(0.001, math.hypot(bx, by))
            bx /= b_mag
            by /= b_mag

            # 4. Measure impact speed
            v_mag = math.hypot(car.vx, car.vy)
            vn = car.vx * nx + car.vy * ny
            v_impact = max(abs(vn), v_mag * 0.75, 45.0)

            # 5. Rubbery bouncy push back toward the track
            bounce_v = min(360.0, max(110.0, v_impact * 1.3))
            car.vx = bx * bounce_v
            car.vy = by * bounce_v

            # 6. Reorient car slightly toward track tangent
            tx, ty = ROAD_T[tidx]
            track_deg = math.degrees(math.atan2(ty, tx))
            ang_err = (track_deg - car.angle + 180) % 360 - 180
            car.omega = max(-2.0, min(2.0, car.omega * 0.2 + ang_err * 0.03))

            # 7. Push out of penetration
            car.x = (car.x + bx * (pen + 4.0)) % WORLD
            car.y = (car.y + by * (pen + 4.0)) % WORLD

            # Invariant fence guard: strictly guarantee kart stays inside fence
            fence_lim = FENCE_OFFSET * TILE - 2.0
            cur_d = dist_to_dirt(car.x, car.y, 400.0)
            if cur_d > fence_lim:
                car.x = (car.x + ix * (cur_d - fence_lim + 1.0)) % WORLD
                car.y = (car.y + iy * (cur_d - fence_lim + 1.0)) % WORLD

            # 8. Feedback (particles, sound, wobble)
            tp["wobble"] = 0.35
            car.impact = min(40.0, max(10.0, v_impact * 0.25))
            if v_impact > 30.0:
                spawn_particles(car.x, car.y, min(int(v_impact / 8), 12), 100, (40, 42, 48), 0.4)
            if v_impact > 25.0:
                play_at("tire_hit", tp["x"], tp["y"], min(1.0, 0.4 + v_impact / 180.0))
            break

def draw_oil(screen, cam):
    for item in OIL:
        ox, oy = item[0], item[1]
        length = item[2]
        width = item[3] if len(item) > 3 else length
        angle = item[4] if len(item) > 4 else 0.0

        sx0, sy0 = cam.to_screen(ox, oy)
        bound = int(max(length, width) * ZOOM) + 16
        if sx0 < -bound or sx0 > W + bound or sy0 < -bound or sy0 > H + bound:
            continue

        zw = max(2, round(width * ZOOM))
        zl = max(2, round(length * ZOOM))
        zoom_spr = _get_oil_zoom_sprite(width, length, zw, zl)
        if zoom_spr is None:
            continue

        rad = math.radians(angle)
        sxf, syf = cam.to_screen(ox + math.cos(rad) * 10, oy + math.sin(rad) * 10)
        measured_rot = -math.degrees(math.atan2(syf - sy0, sxf - sx0))
        rot_img = pygame.transform.rotate(zoom_spr, measured_rot + 90)
        screen.blit(rot_img, rot_img.get_rect(center=(round(sx0), round(sy0))))

def draw_projectiles(screen, cam):
    for x, y, vx, vy, life, owner in PROJECTILES:
        sx, sy = cam.to_screen(x, y)
        if sx < -20 or sx > W + 20 or sy < -20 or sy > H + 20:
            continue
        r = max(2, int(PROJ_R * ZOOM))
        pygame.draw.circle(screen, (255, 235, 150), (int(sx), int(sy)), r + 2)
        pygame.draw.circle(screen, (255, 120, 40), (int(sx), int(sy)), r)
        pygame.draw.circle(screen, (255, 255, 255), (int(sx), int(sy)), max(1, r // 2))

def draw_fx(screen, cam):
    for x, y, name, age, dur, world_w, rot in FX:
        frames = FX_FRAMES.get(name)
        if not frames:
            continue
        sx, sy = cam.to_screen(x, y)
        if sx < -60 or sx > W + 60 or sy < -60 or sy > H + 60:
            continue
        nf = len(frames)
        fi = min(nf - 1, int(age / dur * nf))
        w = max(4, int(world_w * ZOOM))
        img = _fx_frame(name, fi, w)
        if img is None:
            continue
        if rot:
            img = pygame.transform.rotate(img, rot)
        frac = age / dur
        if frac > 0.72:                 # fade the last stretch so it dissolves rather than pops off
            img = img.copy()
            img.set_alpha(int(255 * max(0.0, 1 - (frac - 0.72) / 0.28)))
        screen.blit(img, img.get_rect(center=(sx, sy)))

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
        bx, by = x % WORLD, y % WORLD
        if not is_obstacle_pos_clear(bx, by, min_dist=28.0, check_boxes=True, check_tires=True, check_ramps=True):
            continue
        BOXES.append({"x": bx, "y": by, "kind": "mystery",
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
    elif kind == "cone":
        car.item = "cone"
    elif kind == "oil":
        car.item = "oil"
    car.flash = max(car.flash, 0.25)
    # exhaust pumps fire on pickup: a short burst of flame puffs out the back
    rad = math.radians(car.angle)
    c, s = math.cos(rad), math.sin(rad)
    for _ in range(3):
        ex = car.x - c * CAR_HL + random.uniform(-5, 5)
        ey = car.y - s * CAR_HL + random.uniform(-5, 5)
        spawn_fx(ex, ey, "fire1" if random.random() < 0.5 else "fire2",
                 random.uniform(18, 26), dur=0.38)
    if getattr(car, "is_player", True) and not getattr(car, "is_remote", False):
        play({"boost": "pickup_boost", "heart": "pickup_heart", "bash": "pickup_bash"}.get(kind, "pickup_item"))
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
                if ITEM_RULE == "none":
                    continue
                elif ITEM_RULE == "kinetic":
                    kind = random.choice(["boost", "bash"])
                elif ITEM_RULE == "hazards":
                    kind = random.choice(["cone", "oil"])
                else:
                    kind = random.choice(POWERUP_KINDS)
                give_powerup(car, kind)
                b["timer"] = BOX_RESPAWN
                spawn_particles(b["x"], b["y"], 24, 140, BOX_COLORS.get("mystery", (45, 145, 255)), 0.65)
                if NET_ROLE == "host":
                    BOX_EVENTS.append((idx, slot, kind))
                break

def apply_box_event(idx, kind):
    # a client marks a box as taken + plays the effect; the recipient's own powerup is
    # applied separately (only the local player applies it to its own car)
    if 0 <= idx < len(BOXES):
        b = BOXES[idx]
        b["timer"] = BOX_RESPAWN
        spawn_particles(b["x"], b["y"], 24, 140, BOX_COLORS.get("mystery", (45, 145, 255)), 0.65)

def spawn_traffic_cones(rng=None):
    del CONES[:]
    if ROAD_LEN <= 1.0:
        return
    r = rng if rng is not None else random
    # Place cones along road borders / corner apexes / chicanes
    num_clusters = r.randint(5, 8)
    for _ in range(num_clusters):
        s = r.uniform(0, ROAD_LEN)
        side = r.choice([-1.0, 1.0])
        cluster_len = r.choice([2, 3])
        for step_i in range(cluster_len):
            cs = (s + step_i * 22.0) % ROAD_LEN
            lat = side * ROAD_WIDTH * 0.44
            cx, cy, _ = road_pose(cs, lat)
            pos_x, pos_y = cx % WORLD, cy % WORLD
            if not is_obstacle_pos_clear(pos_x, pos_y, min_dist=28.0, check_boxes=True, check_cones=True, check_tires=True, check_ramps=True):
                continue
            CONES.append({
                "x": pos_x,
                "y": pos_y,
                "base_x": pos_x,
                "base_y": pos_y,
                "vx": 0.0,
                "vy": 0.0,
                "angle": 0.0,
                "vrot": 0.0,
                "knocked": False,
                "timer": 0.0,
            })

def _update_cones(dt, cars):
    if not CONES:
        return
    r_cone = 13.0
    min_dist = r_cone + CAR_HW
    for c in CONES:
        if c["knocked"]:
            c["x"] = (c["x"] + c["vx"] * dt) % WORLD
            c["y"] = (c["y"] + c["vy"] * dt) % WORLD
            c["angle"] += c["vrot"] * dt
            c["vx"] *= 0.90
            c["vy"] *= 0.90
            c["vrot"] *= 0.88
            c["timer"] -= dt
            spd_sq = c["vx"] * c["vx"] + c["vy"] * c["vy"]
            if spd_sq > 50.0 * 50.0:
                for car in cars:
                    if c.get("owner_uid") == car.uid and c["timer"] > 5.5:
                        continue
                    dx = wrap_delta(c["x"], car.x)
                    dy = wrap_delta(c["y"], car.y)
                    if dx * dx + dy * dy < (r_cone + CAR_HW) ** 2:
                        sp = math.sqrt(spd_sq)
                        car.vx += (c["vx"] / sp) * 150.0
                        car.vy += (c["vy"] / sp) * 150.0
                        car.omega += random.choice([-1, 1]) * 1.8
                        car.stagger = max(car.stagger, 0.35)
                        car.impact = max(car.impact, 110.0)
                        spawn_particles(c["x"], c["y"], 12, 100, (255, 140, 30), 0.4)
                        play_at("cone_smack", c["x"], c["y"])
                        c["vx"] *= -0.3
                        c["vy"] *= -0.3
                        break
            if c["timer"] <= 0.0:
                if c.get("thrown", False):
                    c["dead"] = True
                else:
                    c["x"], c["y"] = c["base_x"], c["base_y"]
                    c["vx"] = c["vy"] = c["angle"] = c["vrot"] = 0.0
                    c["knocked"] = False
        else:
            for car in cars:
                dx = wrap_delta(c["x"], car.x)
                dy = wrap_delta(c["y"], car.y)
                dist_sq = dx * dx + dy * dy
                if dist_sq < min_dist * min_dist:
                    dist = max(0.001, math.sqrt(dist_sq))
                    nx, ny = dx / dist, dy / dist
                    pen = min_dist - dist
                    # Positional push: physically separate car and cone
                    car.x = (car.x + nx * pen * 0.45) % WORLD
                    car.y = (car.y + ny * pen * 0.45) % WORLD
                    c["x"] = (c["x"] - nx * pen * 0.55) % WORLD
                    c["y"] = (c["y"] - ny * pen * 0.55) % WORLD

                    # Velocity response along collision normal
                    rel_vx = car.vx - c["vx"]
                    rel_vy = car.vy - c["vy"]
                    vn = rel_vx * nx + rel_vy * ny
                    if vn < 0:
                        j = -(1.0 + 0.55) * vn
                        # Push back and deflect car
                        car.vx += nx * (j * 0.22)
                        car.vy += ny * (j * 0.22)
                        car.omega += (-dy * nx + dx * ny) * 0.002
                        car.impact = max(car.impact, 85.0)
                        # Knock cone away with high momentum
                        c["vx"] -= nx * (j * 1.35) + random.uniform(-25, 25)
                        c["vy"] -= ny * (j * 1.35) + random.uniform(-25, 25)
                        c["vrot"] = random.choice([-1, 1]) * random.uniform(360, 720)
                        c["knocked"] = True
                        c["timer"] = 6.0
                        spawn_particles(c["x"], c["y"], 8, 90, (255, 140, 30), 0.35)
                        play_at("cone_hit", c["x"], c["y"])
                    break
    if any(c.get("dead") for c in CONES):
        CONES[:] = [c for c in CONES if not c.get("dead", False)]

def throw_traffic_cone(car, forward=False):
    rad = math.radians(car.angle)
    c, s = math.cos(rad), math.sin(rad)
    if forward:
        cx = (car.x + c * (CAR_HL + 16.0)) % WORLD
        cy = (car.y + s * (CAR_HL + 16.0)) % WORLD
        car_spd = math.hypot(car.vx, car.vy)
        cone_spd = car_spd + 420.0
        cvx = c * cone_spd + car.vx * 0.2
        cvy = s * cone_spd + car.vy * 0.2
        CONES.append({
            "x": cx,
            "y": cy,
            "base_x": cx,
            "base_y": cy,
            "vx": cvx,
            "vy": cvy,
            "angle": car.angle,
            "vrot": random.choice([-1, 1]) * random.uniform(500, 900),
            "knocked": True,
            "timer": 6.0,
            "thrown": True,
            "owner_uid": car.uid,
        })
        spawn_particles(cx, cy, 10, 80, (255, 140, 30), 0.4)
        play_at("cone_throw", cx, cy)
    else:
        cx = (car.x - c * (CAR_HL + 20.0)) % WORLD
        cy = (car.y - s * (CAR_HL + 20.0)) % WORLD
        CONES.append({
            "x": cx,
            "y": cy,
            "base_x": cx,
            "base_y": cy,
            "vx": 0.0,
            "vy": 0.0,
            "angle": car.angle,
            "vrot": 0.0,
            "knocked": False,
            "timer": 15.0,
            "thrown": True,
            "owner_uid": car.uid,
        })
        spawn_particles(cx, cy, 8, 60, (255, 140, 30), 0.3)
        play_at("cone_drop", cx, cy)
    return True

def spill_oil(car):
    rad = math.radians(car.angle)
    c, s = math.cos(rad), math.sin(rad)
    ox = (car.x - c * (CAR_HL + 20.0)) % WORLD
    oy = (car.y - s * (CAR_HL + 20.0)) % WORLD
    w = random.choice([28, 36, 44])
    l = random.choice([48, 64, 80])
    angle = car.angle + random.uniform(-10.0, 10.0)
    max_r = max(l, w) * 0.5
    OIL.append([ox, oy, l, w, angle, max_r])
    if len(OIL) > OIL_MAX + 12:
        del OIL[:len(OIL) - (OIL_MAX + 12)]
    spawn_particles(ox, oy, 12, 50, (35, 35, 40), 0.5)
    play_at("oil_spill", ox, oy)
    return True

def spawn_destructibles(rng=None):
    del DESTRUCTIBLES[:]
    if ROAD_LEN <= 1.0 or not DESTRUCT_SURF:
        return
    r = rng if rng is not None else random
    kinds = [k for k in ("barrel", "box", "vase") if k in DESTRUCT_SURF]
    if not kinds:
        return
    num_clusters = r.randint(6, 10)
    for _ in range(num_clusters):
        s = r.uniform(0, ROAD_LEN)
        side = r.choice([-1.0, 1.0])
        cluster_len = r.choice([2, 3])
        cluster_kind = r.choice(kinds)
        spacing = r.uniform(20.0, 26.0)
        for step_i in range(cluster_len):
            cs = (s + step_i * spacing) % ROAD_LEN
            lat = side * ROAD_WIDTH * 0.44
            dx_off = r.uniform(-3.0, 3.0)
            dy_off = r.uniform(-3.0, 3.0)
            cx, cy, _ = road_pose(cs, lat)
            pos_x = (cx + dx_off) % WORLD
            pos_y = (cy + dy_off) % WORLD
            if not is_obstacle_pos_clear(pos_x, pos_y, min_dist=28.0, check_boxes=True, check_cones=True, check_destruct=True, check_tires=True, check_ramps=True):
                continue
            k = cluster_kind if r.random() < 0.65 else r.choice(kinds)
            DESTRUCTIBLES.append({
                "x": pos_x,
                "y": pos_y,
                "type": k,
                "destroyed": False,
                "wobble": 0.0,
                "respawn_timer": 0.0,
            })

def _update_destructibles(dt, cars):
    if not DESTRUCTIBLES or not DESTRUCT_SURF:
        return
    for d in DESTRUCTIBLES:
        if d["destroyed"]:
            d["respawn_timer"] -= dt
            if d["respawn_timer"] <= 0.0:
                d["destroyed"] = False
                d["wobble"] = 0.0
            continue

        if d["wobble"] > 0:
            d["wobble"] = max(0.0, d["wobble"] - dt)

        r_prop = 21.0 if d["type"] in ("barrel", "box") else 14.0
        min_car_dist = r_prop + CAR_HW

        # 1. Car collisions
        for car in cars:
            dx = wrap_delta(d["x"], car.x)
            dy = wrap_delta(d["y"], car.y)
            dist_sq = dx * dx + dy * dy
            if dist_sq < min_car_dist * min_car_dist:
                dist = max(0.001, math.sqrt(dist_sq))
                car_spd = math.hypot(car.vx, car.vy)
                if car_spd > 60.0 or car.bash_time > 0 or car.boost_time > 0:
                    d["destroyed"] = True
                    d["respawn_timer"] = 12.0
                    fx_w = 64 if d["type"] in ("barrel", "box") else 42
                    spawn_fx(d["x"], d["y"], f"{d['type']}_break", fx_w, dur=0.35, rot=0.0)
                    part_col = (180, 140, 90) if d["type"] == "box" else ((150, 95, 60) if d["type"] == "barrel" else (210, 130, 90))
                    spawn_particles(d["x"], d["y"], 18, 140, part_col, 0.5)
                    spawn_wood_splinters(d["x"], d["y"], 16, 170.0)
                    play_at("break_vase" if d["type"] == "vase" else "break_wood", d["x"], d["y"])
                    car.vx *= 0.88
                    car.vy *= 0.88
                    car.impact = max(car.impact, 95.0)
                    car.impact_vx = -car.vx * 0.4
                    car.impact_vy = -car.vy * 0.4
                    break
                else:
                    nx, ny = dx / dist, dy / dist
                    pen = min_car_dist - dist
                    car.x = (car.x + nx * pen * 0.5) % WORLD
                    car.y = (car.y + ny * pen * 0.5) % WORLD
                    car.vx *= 0.55
                    car.vy *= 0.55
                    d["wobble"] = 0.35
                    play_at("prop_bump", d["x"], d["y"])
                    break

        if d["destroyed"]:
            continue

        # 2. Knocked cone collisions
        for c in CONES:
            if c["knocked"] and (c["vx"] * c["vx"] + c["vy"] * c["vy"] > 40.0 * 40.0):
                dx = wrap_delta(d["x"], c["x"])
                dy = wrap_delta(d["y"], c["y"])
                if dx * dx + dy * dy < (r_prop + 14.0) ** 2:
                    d["destroyed"] = True
                    d["respawn_timer"] = 12.0
                    fx_w = 64 if d["type"] in ("barrel", "box") else 42
                    spawn_fx(d["x"], d["y"], f"{d['type']}_break", fx_w, dur=0.35, rot=0.0)
                    part_col = (180, 140, 90) if d["type"] == "box" else ((150, 95, 60) if d["type"] == "barrel" else (210, 130, 90))
                    spawn_particles(d["x"], d["y"], 18, 140, part_col, 0.5)
                    play_at("break_vase" if d["type"] == "vase" else "break_wood", d["x"], d["y"])
                    c["vx"] *= -0.5
                    c["vy"] *= -0.5
                    break

        if d["destroyed"]:
            continue

        # 3. Projectile collisions
        for p in PROJECTILES:
            if p[4] <= 0:
                continue
            dx = wrap_delta(d["x"], p[0])
            dy = wrap_delta(d["y"], p[1])
            if dx * dx + dy * dy < (r_prop + PROJ_R) ** 2:
                d["destroyed"] = True
                d["respawn_timer"] = 12.0
                fx_w = 64 if d["type"] in ("barrel", "box") else 42
                spawn_fx(d["x"], d["y"], f"{d['type']}_break", fx_w, dur=0.35, rot=0.0)
                part_col = (180, 140, 90) if d["type"] == "box" else ((150, 95, 60) if d["type"] == "barrel" else (210, 130, 90))
                spawn_particles(d["x"], d["y"], 18, 140, part_col, 0.5)
                play_at("break_vase" if d["type"] == "vase" else "break_wood", d["x"], d["y"])
                p[4] = 0.0
                break

DESTRUCT_STACK_NAMES = {"box": "crate", "barrel": "barrel", "vase": "vase"}

def draw_destructibles(screen, cam):
    if not DESTRUCTIBLES:
        return
    for d in DESTRUCTIBLES:
        if d["destroyed"]:
            continue
        name = DESTRUCT_STACK_NAMES.get(d["type"])
        if name is None:
            continue
        # wobble is a little screen-space shake; approximate it in world space pre-zoom
        wox = 0.0
        if d.get("wobble", 0.0) > 0.0:
            wox = math.sin(d["wobble"] * 30.0) * 3.0 / ZOOM
        ramps.draw(screen, cam, name, d["x"] + wox, d["y"], 0.0)

def lap_of(car):
    # laps completed since the start line; progress is px driven along the loop
    if ROAD_LEN <= 1.0:
        return 0
    return max(0, int(car.progress / ROAD_LEN))

# ---- multiplayer car sync ----------------------------------------------------------
_NET_SNAP = ("vx", "vy", "omega", "steer_angle", "flash", "bash_time", "hit_flash",
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
ZOOM = 1.68         # camera zoom; >1 shows less of the world, bigger karts
ZOOM_MIN = 1.2      # slider ends: more of the track in view ...
ZOOM_MAX = 2.4      # ... to tight and zoomed on the kart

def set_zoom(v):
    # slider 0..1 -> ZOOM; rebuilds the pre-scaled ground so draw_ground stays fast
    global ZOOM
    ZOOM = ZOOM_MIN + (ZOOM_MAX - ZOOM_MIN) * max(0.0, min(1.0, v))
    if GROUND_SURF is not None:
        _build_zoomed_ground()

def zoom_frac():
    return (ZOOM - ZOOM_MIN) / (ZOOM_MAX - ZOOM_MIN)
# chunk is in *zoomed-ground* pixels and sized to still cover the screen once rotated. Using a
# ground that's pre-scaled by ZOOM lets us rotate() each frame (fast) instead of rotozoom() (slow).
_CHUNK = int(math.hypot(W, H)) + 6 * TILE
_chunk_surf = None
_overlay = None

def draw_ground(screen, cam):
    # Grass everywhere, then the part of the (pre-zoomed) baked map around the camera, rotated.
    global _chunk_surf
    screen.fill(GRASS_COLOR)
    if GROUND_Z is None:
        return
    if _chunk_surf is None:
        # plain (no per-pixel alpha) for a fast rotate(); the chunk over-covers the screen, so
        # rotate's black corner padding always falls outside the visible area
        _chunk_surf = pygame.Surface((_CHUNK, _CHUNK)).convert()
    ox, oy = GROUND_ORIGIN
    left = math.floor((cam.x - ox) * ZOOM - _CHUNK / 2)   # top-left in zoomed-ground pixels
    top = math.floor((cam.y - oy) * ZOOM - _CHUNK / 2)
    _chunk_surf.fill(GRASS_COLOR)
    _chunk_surf.blit(GROUND_Z, (-left, -top))             # clipped to the overlap
    rot = pygame.transform.rotate(_chunk_surf, cam.angle + 90)
    # chunk centre back in world coords, mapped to screen (to_screen already applies ZOOM)
    wcx = (left + _CHUNK / 2) / ZOOM + ox
    wcy = (top + _CHUNK / 2) / ZOOM + oy
    sx, sy = cam.to_screen(wcx, wcy)
    screen.blit(rot, rot.get_rect(center=(round(sx), round(sy))))

def _get_overlay():
    global _overlay
    if _overlay is None:
        _overlay = pygame.Surface((W, H), pygame.SRCALPHA)
    _overlay.fill((0, 0, 0, 0))
    return _overlay

def draw_trails(screen, cars, cam):
    # Tyre tracks remain visible for 13s, then smoothly fade into the ground
    for car in cars:
        for seg in car.trail:
            if len(seg) == 7:
                x0, y0, x1, y1, life, width, is_grass = seg
            elif len(seg) == 3:
                x0, y0, life = seg
                x1, y1 = x0 + 1, y0 + 1
                width, is_grass = 6, False
            else:
                continue

            # Fast distance culling before screen projection
            if abs(wrap_delta(cam.x, x0)) > 420 or abs(wrap_delta(cam.y, y0)) > 420:
                continue

            sx0, sy0 = cam.to_screen(x0, y0)
            sx1, sy1 = cam.to_screen(x1, y1)

            # Viewport culling with margin
            if (min(sx0, sx1) <= W + 20 and max(sx0, sx1) >= -20 and
                min(sy0, sy1) <= H + 20 and max(sy0, sy1) >= -20):
                f = life / TRAIL_LIFE
                base_col = SKID_GRASS_COLOR if is_grass else SKID_ROAD_COLOR
                ground_col = GRASS_COLOR if is_grass else DIRT_COLOR
                # In the last 35% of its 13s life, smoothly fade into the ground
                if f < 0.35:
                    blend = max(0.0, f / 0.35)
                    col = (
                        int(ground_col[0] + (base_col[0] - ground_col[0]) * blend),
                        int(ground_col[1] + (base_col[1] - ground_col[1]) * blend),
                        int(ground_col[2] + (base_col[2] - ground_col[2]) * blend),
                    )
                else:
                    col = base_col
                p0 = (round(sx0), round(sy0))
                p1 = (round(sx1), round(sy1))
                pygame.draw.line(screen, col, p0, p1, width)
                if width >= 5:
                    pygame.draw.circle(screen, col, p1, width // 2)

def _get_particle_sprite(color, size, alpha_step):
    key = (color[0], color[1], color[2], size, alpha_step)
    surf = _PARTICLE_CACHE.get(key)
    if surf is None:
        scaled = pygame.transform.smoothscale(PARTICLE_RAW, (size, size)).copy()
        scaled.fill((color[0], color[1], color[2], 255), special_flags=pygame.BLEND_RGB_MULT)
        if alpha_step < 4:
            alpha = max(35, int(255 * (alpha_step + 1) / 5.0))
            a_surf = pygame.Surface((size, size), pygame.SRCALPHA)
            a_surf.fill((255, 255, 255, alpha))
            scaled.blit(a_surf, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        surf = scaled
        _PARTICLE_CACHE[key] = surf
    return surf

def draw_particles(screen, cam):
    if not PARTICLES:
        return
    for x, y, _, _, life, max_life, col in PARTICLES:
        sx, sy = cam.to_screen(x, y)
        if -8 <= sx <= W + 8 and -8 <= sy <= H + 8:
            f = max(0.0, min(1.0, life / max_life)) if max_life > 0 else 0.0
            # Scale down to ~1/6th car size (~5px) shrinking to ~2px
            size = max(2, min(5, int(2 + round(f * 3))))
            alpha_step = max(0, min(4, int(f * 4.99)))
            if PARTICLE_RAW is not None:
                sp = _get_particle_sprite(col, size, alpha_step)
                screen.blit(sp, (int(round(sx - size * 0.5)), int(round(sy - size * 0.5))))
            else:
                s = 2 if f < 0.5 else 3
                pygame.draw.rect(screen, col, (int(round(sx - s * 0.5)), int(round(sy - s * 0.5)), s, s))

def draw_debris(screen, cam):
    if not DEBRIS:
        return
    z = getattr(cam, "zoom", ZOOM)
    for x, y, vx, vy, life, max_life, kind, col, p1, p2, rot, _ in DEBRIS:
        sx, sy = cam.to_screen(x, y)
        if not (-40 <= sx <= W + 40 and -40 <= sy <= H + 40):
            continue
        f = max(0.0, min(1.0, life / max_life)) if max_life > 0 else 0.0
        if kind == "wood":
            w = max(1.5, p1 * z)
            h = max(3.0, p2 * z * f)
            surf = pygame.Surface((int(w + 4), int(h + 4)), pygame.SRCALPHA)
            pygame.draw.rect(surf, (30, 20, 10), (0, 0, int(w + 2), int(h + 2)))
            pygame.draw.rect(surf, col, (1, 1, int(max(1, w)), int(max(1, h))))
            rot_s = pygame.transform.rotate(surf, rot)
            screen.blit(rot_s, rot_s.get_rect(center=(int(round(sx)), int(round(sy)))))
        elif kind == "spark":
            spd = math.hypot(vx, vy)
            ang = math.atan2(vy, vx) if spd > 1.0 else 0.0
            rad_cam = -math.radians(cam.angle + 90)
            sc_ang = ang + rad_cam
            slen = max(2.5, min(14.0, (p2 * f + spd * 0.02) * z))
            x2 = sx - math.cos(sc_ang) * slen
            y2 = sy - math.sin(sc_ang) * slen
            pygame.draw.line(screen, col, (int(round(sx)), int(round(sy))), (int(round(x2)), int(round(y2))), max(1, int(1.5 * z)))
        elif kind == "smoke":
            curr_r = p1 + (p2 - p1) * (1.0 - f)
            r = int(round(curr_r * z))
            if r <= 1:
                continue
            alpha = int(135 * f)
            if alpha > 0:
                s_surf = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
                pygame.draw.circle(s_surf, (col[0], col[1], col[2], alpha), (r + 1, r + 1), r)
                screen.blit(s_surf, (int(round(sx - r - 1)), int(round(sy - r - 1))))

KART_BODY = [(14, -4), (14, 4), (9, 7), (-12, 7), (-14, 5), (-14, -5), (-12, -7), (9, -7)]
CABIN_BODY = [(6, -4), (7, 0), (6, 4), (-6, 4), (-6, -4)]    # cockpit, sits on the top slice
STACK_LAYERS = 7        # stacked slices faking height (sprite stacking)
STACK_LIFT = 1          # px each slice is drawn above the one below

def _shade(col, f):
    return (int(col[0] * f), int(col[1] * f), int(col[2] * f))

_CAR_SHADOW_SURF = None

def draw_car_shadow(screen, car, cam):
    global _CAR_SHADOW_SURF
    sx, sy = cam.to_screen(car.x, car.y)
    if not (-80 <= sx <= W + 80 and -80 <= sy <= H + 80):
        return

    rad = math.radians(car.angle)
    c, s = math.cos(rad), math.sin(rad)

    def ground_pt(lx, ly, off_h=0.0):
        wx = car.x + lx * c - ly * s + SUN_DIR_X * off_h
        wy = car.y + lx * s + ly * c + SUN_DIR_Y * off_h
        return cam.to_screen(wx, wy)

    shadow_pts_body = [ground_pt(lx, ly, CAR_SHADOW_DIST) for lx, ly in KART_BODY]
    shadow_pts_base = [ground_pt(lx, ly, 0.5) for lx, ly in KART_BODY]

    all_pts = shadow_pts_body + shadow_pts_base
    min_x = math.floor(min(p[0] for p in all_pts)) - 4
    max_x = math.ceil(max(p[0] for p in all_pts)) + 4
    min_y = math.floor(min(p[1] for p in all_pts)) - 4
    max_y = math.ceil(max(p[1] for p in all_pts)) + 4
    sw, sh = max_x - min_x, max_y - min_y
    if sw <= 0 or sh <= 0 or min_x > W or max_x < 0 or min_y > H or max_y < 0:
        return

    if _CAR_SHADOW_SURF is None or _CAR_SHADOW_SURF.get_width() < sw or _CAR_SHADOW_SURF.get_height() < sh:
        _CAR_SHADOW_SURF = pygame.Surface((max(160, sw), max(160, sh)), pygame.SRCALPHA)
    else:
        _CAR_SHADOW_SURF.fill((0, 0, 0, 0), (0, 0, sw, sh))

    local_base = [(p[0] - min_x, p[1] - min_y) for p in shadow_pts_base]
    local_body = [(p[0] - min_x, p[1] - min_y) for p in shadow_pts_body]

    pygame.draw.polygon(_CAR_SHADOW_SURF, CAR_SHADOW_COLOR, local_base)
    pygame.draw.polygon(_CAR_SHADOW_SURF, CAR_SHADOW_COLOR, local_body)
    for i in range(len(KART_BODY)):
        j = (i + 1) % len(KART_BODY)
        quad = [local_base[i], local_base[j], local_body[j], local_body[i]]
        pygame.draw.polygon(_CAR_SHADOW_SURF, CAR_SHADOW_COLOR, quad)

    for ax, steer in ((AXLE_FRONT, car.steer_angle), (-AXLE_REAR, 0.0)):
        cw, sw_ = math.cos(steer), math.sin(steer)
        for side in (-1, 1):
            wy = side * WHEEL_Y
            w_pts = [ground_pt(ax + wl * cw - ww * sw_, wy + wl * sw_ + ww * cw, 1.0)
                     for wl, ww in ((3.5, 2.0), (3.5, -2.0), (-3.5, -2.0), (-3.5, 2.0))]
            pygame.draw.polygon(_CAR_SHADOW_SURF, CAR_SHADOW_COLOR, [(p[0] - min_x, p[1] - min_y) for p in w_pts])

    screen.blit(_CAR_SHADOW_SURF, (min_x, min_y), (0, 0, sw, sh))

CAR_SPRITE_W = 42       # on-screen width of the 36px racer slice in world px (before ZOOM)
CAR_STACK_LIFT = 1.34   # px each slice is lifted above the one below (before ZOOM)

def _car_layers(tint=None):
    # scaled slices for the car stack at the current zoom, cached.
    # Authentic sprite stack colors are preserved across all players and bots.
    if CAR_STACK is None:
        return None
    w = max(6, int(CAR_SPRITE_W * ZOOM))
    if tint is None:
        scaled = _CARSCALE_CACHE.get(w)
        if scaled is None:
            scaled = [pygame.transform.scale(l, (w, w)) for l in CAR_STACK]
            _CARSCALE_CACHE[w] = scaled
        return scaled
    key = (tint, w)
    cached = _CARTINT_CACHE.get(key)
    if cached is None:
        scaled = _CARSCALE_CACHE.get(w)
        if scaled is None:
            scaled = [pygame.transform.scale(l, (w, w)) for l in CAR_STACK]
            _CARSCALE_CACHE[w] = scaled
        if tint in ("dead", (150, 150, 155)):
            cached = []
            for l in scaled:
                t = l.copy()
                t.fill((140, 140, 150, 255), special_flags=pygame.BLEND_RGB_MULT)
                cached.append(t)
        elif tint in ("bash", (255, 255, 255)):
            cached = []
            for l in scaled:
                t = l.copy()
                t.fill((80, 80, 80, 0), special_flags=pygame.BLEND_RGB_ADD)
                cached.append(t)
        elif tint in ("hit", (255, 70, 70)):
            cached = []
            for l in scaled:
                t = l.copy()
                t.fill((100, 20, 20, 0), special_flags=pygame.BLEND_RGB_ADD)
                cached.append(t)
        else:
            cached = scaled
        _CARTINT_CACHE[key] = cached
    return cached

_CAR_ROT_CACHE = {}

def draw_car(screen, car, cam):
    if CAR_STACK is None:
        _draw_car_vector(screen, car, cam)
        return
    rad = math.radians(car.angle)
    c, s = math.cos(rad), math.sin(rad)
    sx0, sy0 = cam.to_screen(car.x, car.y)
    if car.dead:
        tint = (150, 150, 155)
    elif car.bash_time > 0:
        tint = (255, 255, 255)                  # bashing -> flash white
    elif car.hit_flash > 0:
        tint = (255, 70, 70)                    # got bashed / hit a wall -> red
    else:
        tint = None
    # forward direction on screen (accounts for the rotating camera)
    sxf, syf = cam.to_screen(car.x + c, car.y + s)
    rot_deg = int(round(-math.degrees(math.atan2(syf - sy0, sxf - sx0)))) % 360
    z = getattr(cam, "zoom", ZOOM)
    z_key = round(z, 2)
    key = (tint, rot_deg, z_key)
    cached = _CAR_ROT_CACHE.get(key)
    if cached is None:
        layers = _car_layers(tint)
        lift = max(1, int(round(CAR_STACK_LIFT * z)))
        n = len(layers)
        rotated = [pygame.transform.rotate(lay, rot_deg) for lay in layers]
        rw, rh = rotated[0].get_size()
        cw, ch = rw, rh + (n - 1) * lift
        final_s = pygame.Surface((cw, ch), pygame.SRCALPHA)
        for k, img in enumerate(rotated):
            final_s.blit(img, (0, (n - 1 - k) * lift))
        cached = (final_s, cw // 2, rh // 2 + (n - 1) * lift)
        _CAR_ROT_CACHE[key] = cached
    surf, off_x, off_y = cached
    screen.blit(surf, (int(sx0 - off_x), int(sy0 - off_y)))

def _draw_car_vector(screen, car, cam):
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
    lit = car.flash > 0 or car.bash_time > 0 or car.hit_flash > 0
    if car.dead:
        base_col = (90, 90, 95)                 # eliminated karts go grey
    elif car.bash_time > 0:
        base_col = (255, 255, 255)              # this kart is bashing -> white
    elif car.hit_flash > 0:
        base_col = (235, 45, 45)                # got bashed / hit a wall -> red
    else:
        base_col = car.color
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

def _text_outlined(font, text, color, outline=(15, 15, 20), out_color=None):
    # text with a 1px dark outline so it stays readable with no background box
    if out_color is not None:
        outline = out_color
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
    if box.get("kind", "mystery") == "mystery" and ramps.has("mystery_box"):
        # 2.5D sprite stack: hovers, bobs and slowly turns; the ground shadow shrinks as it rises
        hover = BOX_HOVER + bob
        k = 1.0 - 0.25 * (hover / (BOX_HOVER + BOX_FLOAT_AMP))
        sw, sh = int(BOX_SIZE * 1.05 * k), int(BOX_SIZE * 0.5 * k)
        shadow = pygame.Surface((sw, sh), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (10, 12, 22, 95), shadow.get_rect())
        screen.blit(shadow, shadow.get_rect(center=(int(sx), int(sy + BOX_SIZE * 0.12))))
        spin = math.degrees(box["phase"]) * BOX_SPIN / BOX_FLOAT_SPEED
        ramps.draw(screen, cam, "mystery_box", box["x"], box["y"], spin, hover)
        return
    r = BOX_SIZE // 2
    cy = sy + bob
    rect = pygame.Rect(int(sx - r), int(cy - r), BOX_SIZE, BOX_SIZE)
    kind = box.get("kind", "mystery")
    box_col = BOX_COLORS.get(kind, (45, 145, 255))
    pygame.draw.rect(screen, box_col, rect, border_radius=8)
    pygame.draw.rect(screen, (255, 255, 255), rect, 2, border_radius=8)
    q = get_font(30).render(BOX_LETTER.get(kind, "?"), True, (255, 255, 255))
    screen.blit(q, q.get_rect(center=rect.center))

def draw_boxes(screen, cam):
    for box in BOXES:
        if box["timer"] <= 0:
            draw_box(screen, box, cam)

def draw_cones(screen, cam):
    if not CONES:
        return
    shadow_on = SHADER_SETTINGS.get("shadows", "ON") == "ON"
    dx_c = round(SUN_DIR_X * 9)
    dy_c = round(SUN_DIR_Y * 9)
    csw, csh = CONE_SHADOW.get_size() if CONE_SHADOW is not None else (0, 0)
    for c in CONES:
        sx, sy = cam.to_screen(c["x"], c["y"])
        if not (-40 <= sx <= W + 40 and -40 <= sy <= H + 40):
            continue
        if shadow_on and CONE_SHADOW is not None and not c["knocked"]:
            screen.blit(CONE_SHADOW, (round(sx - csw // 2 + dx_c), round(sy - csh // 2 + dy_c - 1)))

        # always the sprite-stack cone, standing or tumbling after a knock/throw, so it
        # stays upright and correct from every camera angle instead of flattening out
        ramps.draw(screen, cam, "cone", c["x"], c["y"], c["angle"])

# ---- shaders and post-processing ----------------------------------------------------
SHADER_PRESETS = ["NONE", "CRT", "CYBERPUNK", "NOIR", "CINEMATIC", "SUNSET", "ACTION", "VHS"]
FOG_OPTIONS = ["OFF", "LOW", "MEDIUM", "HIGH"]
CRT_OPTIONS = ["OFF", "LOW", "MED", "HIGH"]
VIGNETTE_OPTIONS = ["OFF", "ON"]
SHADOWS_OPTIONS = ["OFF", "ON"]

SHADER_SETTINGS = {
    "preset": "CINEMATIC",
    "fog": "MEDIUM",
    "crt": "OFF",
    "vignette": "ON",
    "shadows": "ON",
}

FOG_LEVEL_DENSITY = {"OFF": 0.0, "LOW": 0.33, "MEDIUM": 0.55, "HIGH": 0.9}
FOG_DENSITY = FOG_LEVEL_DENSITY["MEDIUM"]   # 0..1, the real knob the slider drives

def _sync_fog_density_from_level():
    global FOG_DENSITY
    FOG_DENSITY = FOG_LEVEL_DENSITY.get(SHADER_SETTINGS.get("fog", "MEDIUM"), 0.55)

def set_fog_density(v):
    # slider 0..1; 0 = no fog. Keeps the fog label roughly in sync for the preset display.
    global FOG_DENSITY
    FOG_DENSITY = max(0.0, min(1.0, v))
    label = "OFF" if FOG_DENSITY < 0.02 else min(
        ("LOW", "MEDIUM", "HIGH"), key=lambda k: abs(FOG_LEVEL_DENSITY[k] - FOG_DENSITY))
    SHADER_SETTINGS["fog"] = label
    update_shader_preset_label()
    _rebuild_shader_surface()

_SHADER_SURF = None
_FOG_SURF = None
_GRADE_MULT = None      # full-frame colour-grade: blitted with BLEND_RGB_MULT (tints/darkens)
_GRADE_ADD = None       # then BLEND_RGB_ADD (lifts shadows toward a hue)
_GRAIN_FRAMES = None
_GRAIN_I = 0

# preset -> (multiply colour, add colour); None = untouched. This is what actually makes the
# presets look different -- a real colour wash over the whole frame, not just fog + vignette.
GRADE = {
    "NONE":      (None, None),
    "CRT":       ((224, 226, 236), (6, 4, 12)),
    "CYBERPUNK": ((150, 168, 255), (30, 6, 46)),    # cold blue cast, magenta lift
    "NOIR":      ((176, 180, 192), (8, 9, 14)),      # cool near-grey, crushed
    "CINEMATIC": ((226, 220, 206), (10, 12, 20)),    # teal shadows, warm mids
    "SUNSET":    ((255, 194, 146), (42, 14, 2)),     # golden-hour wash
    "ACTION":    ((255, 236, 214), (34, 14, 4)),     # punchy warm high-contrast
    "VHS":       ((198, 206, 216), (12, 8, 20)),     # washed cool tape look
}
GRAIN_PRESETS = {"CINEMATIC", "NOIR", "SUNSET", "CYBERPUNK", "ACTION", "VHS"}

def _build_grain():
    global _GRAIN_FRAMES
    tw, th = 300, 200
    rnd = random.Random(1234)
    frames = []
    for _ in range(4):
        t = pygame.Surface((tw, th), pygame.SRCALPHA)
        for _ in range((tw * th) // 6):
            v = rnd.randint(0, 255)
            t.set_at((rnd.randrange(tw), rnd.randrange(th)), (v, v, v, rnd.randint(0, 20)))
        frames.append(pygame.transform.scale(t, (W, H)))   # blocky upscale = film-ish grain
    _GRAIN_FRAMES = frames

def _rebuild_shader_surface():
    global _SHADER_SURF, _FOG_SURF, _GRADE_MULT, _GRADE_ADD
    # colour grade applies regardless of fog/crt/vignette, so build it first
    gm, ga = GRADE.get(SHADER_SETTINGS.get("preset", "NONE"), (None, None))
    if gm is not None and gm != (255, 255, 255):
        _GRADE_MULT = pygame.Surface((W, H)); _GRADE_MULT.fill(gm)
    else:
        _GRADE_MULT = None
    if ga is not None and any(ga):
        _GRADE_ADD = pygame.Surface((W, H)); _GRADE_ADD.fill(ga)
    else:
        _GRADE_ADD = None

    fog_on = FOG_DENSITY > 0.02
    crt_level = SHADER_SETTINGS.get("crt", "OFF")
    vig_level = SHADER_SETTINGS.get("vignette", "ON")

    if not fog_on and crt_level == "OFF" and vig_level == "OFF":
        _SHADER_SURF = None
        _FOG_SURF = None
        return

    surf = pygame.Surface((W, H), pygame.SRCALPHA)

    # 1. Fog Layer -- alpha scales continuously with FOG_DENSITY
    if fog_on:
        tint_a = int(4 + 30 * FOG_DENSITY)
        puff_a = int(6 + 40 * FOG_DENSITY)
        fog_layer = pygame.Surface((W, H), pygame.SRCALPHA)
        fog_layer.fill((210, 222, 235, tint_a))
        for x, y, rad in [
            (int(W * 0.25), int(H * 0.28), 260),
            (int(W * 0.65), int(H * 0.62), 320),
            (int(W * 0.85), int(H * 0.32), 240),
            (int(W * 0.38), int(H * 0.82), 280),
        ]:
            m = pygame.Surface((rad * 2, rad * 2), pygame.SRCALPHA)
            for r in range(rad, 0, -8):
                fa = int(puff_a * ((1.0 - r / rad) ** 1.5))
                if fa > 0:
                    pygame.draw.circle(m, (220, 232, 245, fa), (rad, rad), r)
            fog_layer.blit(m, (x - rad, y - rad))
        surf.blit(fog_layer, (0, 0))
        _FOG_SURF = fog_layer
    else:
        _FOG_SURF = None

    # 2. Vignette Layer
    if vig_level == "ON":
        cx, cy = W / 2, H / 2
        max_dist = math.hypot(cx, cy)
        vig = pygame.Surface((W, H), pygame.SRCALPHA)
        for r in range(int(max_dist), int(max_dist * 0.35), -8):
            norm = (r - max_dist * 0.35) / (max_dist * 0.65)
            alpha = int(45 * (norm ** 1.8))
            pygame.draw.circle(vig, (8, 12, 20, alpha), (int(cx), int(cy)), r)
        surf.blit(vig, (0, 0))

    # 3. CRT Scanlines Layer
    if crt_level != "OFF":
        alpha = 18 if crt_level == "SUBTLE" else 38
        crt = pygame.Surface((W, H), pygame.SRCALPHA)
        for y in range(0, H, 2):
            pygame.draw.line(crt, (0, 0, 0, alpha), (0, y), (W, y))
        surf.blit(crt, (0, 0))

    _SHADER_SURF = surf

def apply_shader_preset(preset):
    if preset in ("NONE", "OFF"):
        SHADER_SETTINGS["preset"] = "NONE"
        SHADER_SETTINGS["fog"] = "OFF"
        SHADER_SETTINGS["crt"] = "OFF"
        SHADER_SETTINGS["vignette"] = "OFF"
        SHADER_SETTINGS["shadows"] = "OFF"
    elif preset in ("CRT", "RETRO CRT"):
        SHADER_SETTINGS["preset"] = "CRT"
        SHADER_SETTINGS["fog"] = "OFF"
        SHADER_SETTINGS["crt"] = "HIGH"
        SHADER_SETTINGS["vignette"] = "ON"
        SHADER_SETTINGS["shadows"] = "ON"
    elif preset == "CYBERPUNK":
        SHADER_SETTINGS["preset"] = "CYBERPUNK"
        SHADER_SETTINGS["fog"] = "LOW"
        SHADER_SETTINGS["crt"] = "LOW"
        SHADER_SETTINGS["vignette"] = "ON"
        SHADER_SETTINGS["shadows"] = "ON"
    elif preset == "NOIR":
        SHADER_SETTINGS["preset"] = "NOIR"
        SHADER_SETTINGS["fog"] = "LOW"
        SHADER_SETTINGS["crt"] = "OFF"
        SHADER_SETTINGS["vignette"] = "ON"
        SHADER_SETTINGS["shadows"] = "ON"
    elif preset == "CINEMATIC":
        SHADER_SETTINGS["preset"] = "CINEMATIC"
        SHADER_SETTINGS["fog"] = "MEDIUM"
        SHADER_SETTINGS["crt"] = "OFF"
        SHADER_SETTINGS["vignette"] = "ON"
        SHADER_SETTINGS["shadows"] = "ON"
    elif preset == "SUNSET":
        SHADER_SETTINGS["preset"] = "SUNSET"
        SHADER_SETTINGS["fog"] = "MEDIUM"
        SHADER_SETTINGS["crt"] = "OFF"
        SHADER_SETTINGS["vignette"] = "ON"
        SHADER_SETTINGS["shadows"] = "ON"
    elif preset == "ACTION":
        SHADER_SETTINGS["preset"] = "ACTION"
        SHADER_SETTINGS["fog"] = "OFF"
        SHADER_SETTINGS["crt"] = "OFF"
        SHADER_SETTINGS["vignette"] = "ON"
        SHADER_SETTINGS["shadows"] = "ON"
    elif preset == "VHS":
        SHADER_SETTINGS["preset"] = "VHS"
        SHADER_SETTINGS["fog"] = "LOW"
        SHADER_SETTINGS["crt"] = "MED"
        SHADER_SETTINGS["vignette"] = "ON"
        SHADER_SETTINGS["shadows"] = "ON"
    _sync_fog_density_from_level()
    _rebuild_shader_surface()

def update_shader_preset_label():
    for p in SHADER_PRESETS:
        test = {}
        if p == "NONE":
            test = {"fog": "OFF", "crt": "OFF", "vignette": "OFF", "shadows": "OFF"}
        elif p == "CRT":
            test = {"fog": "OFF", "crt": "HIGH", "vignette": "ON", "shadows": "ON"}
        elif p == "CYBERPUNK":
            test = {"fog": "LOW", "crt": "LOW", "vignette": "ON", "shadows": "ON"}
        elif p == "NOIR":
            test = {"fog": "LOW", "crt": "OFF", "vignette": "ON", "shadows": "ON"}
        elif p == "CINEMATIC":
            test = {"fog": "MEDIUM", "crt": "OFF", "vignette": "ON", "shadows": "ON"}
        elif p == "SUNSET":
            test = {"fog": "MEDIUM", "crt": "OFF", "vignette": "ON", "shadows": "ON"}
        elif p == "ACTION":
            test = {"fog": "OFF", "crt": "OFF", "vignette": "ON", "shadows": "ON"}
        elif p == "VHS":
            test = {"fog": "LOW", "crt": "MED", "vignette": "ON", "shadows": "ON"}
        if test and all(SHADER_SETTINGS.get(k) == v for k, v in test.items()):
            SHADER_SETTINGS["preset"] = p
            return
    SHADER_SETTINGS["preset"] = "CUSTOM"

def set_shader_option(key, val):
    SHADER_SETTINGS[key] = val
    if key == "fog":
        _sync_fog_density_from_level()
    update_shader_preset_label()
    _rebuild_shader_surface()

def set_shader_settings(d):
    if not isinstance(d, dict):
        return
    for k in ("fog", "crt", "vignette", "shadows"):
        if k in d:
            SHADER_SETTINGS[k] = d[k]
    if "fog_density" in d:
        try:
            globals()["FOG_DENSITY"] = max(0.0, min(1.0, float(d["fog_density"])))
        except (TypeError, ValueError):
            _sync_fog_density_from_level()
    else:
        _sync_fog_density_from_level()
    if "preset" in d:
        SHADER_SETTINGS["preset"] = d["preset"]
    else:
        update_shader_preset_label()
    _rebuild_shader_surface()

def draw_shaders(screen):
    global _SHADER_SURF, _GRAIN_I
    preset = SHADER_SETTINGS.get("preset", "NONE")
    wants = (preset in GRADE and GRADE[preset] != (None, None)) or \
        any(SHADER_SETTINGS.get(k) != "OFF" for k in ("fog", "crt", "vignette"))
    if _SHADER_SURF is None and _GRADE_MULT is None and wants:
        _rebuild_shader_surface()
    # 1. colour grade the whole frame, 2. lay fog/vignette/scanlines on top, 3. film grain
    if _GRADE_MULT is not None:
        screen.blit(_GRADE_MULT, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
    if _GRADE_ADD is not None:
        screen.blit(_GRADE_ADD, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
    if _SHADER_SURF is not None:
        screen.blit(_SHADER_SURF, (0, 0))
    if preset in GRAIN_PRESETS:
        if _GRAIN_FRAMES is None:
            _build_grain()
        _GRAIN_I = (_GRAIN_I + 1) % len(_GRAIN_FRAMES)
        screen.blit(_GRAIN_FRAMES[_GRAIN_I], (0, 0))

def draw_fog(screen):
    draw_shaders(screen)

def draw_world(screen, cam, cars):
    draw_ground(screen, cam)
    draw_trees(screen, cam)
    draw_oil(screen, cam)
    draw_ramps(screen, cam)
    draw_trails(screen, cars, cam)
    draw_destructibles(screen, cam)
    draw_cones(screen, cam)
    draw_boxes(screen, cam)
    draw_tires(screen, cam)
    if SHADER_SETTINGS.get("shadows", "ON") == "ON":
        for car in cars:
            draw_car_shadow(screen, car, cam)
    for car in cars:
        draw_car(screen, car, cam)
    draw_projectiles(screen, cam)
    draw_particles(screen, cam)
    draw_debris(screen, cam)
    draw_fx(screen, cam)
    draw_shaders(screen)
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
        name = c.name                      # the player's row is marked yellow (blue is menu-only)
        color = (255, 210, 70) if c is player else (235, 235, 235)
        pygame.draw.circle(screen, c.color, (x + 6, yc + 8), 4)
        pygame.draw.circle(screen, (255, 255, 255), (x + 6, yc + 8), 4, 1)
        screen.blit(_text_outlined(font, f"P{i + 1}", color), (x + 12, yc))
        tx = x + 34
        flag = get_flag(c.flag, 11) if c.flag else None
        if flag:
            screen.blit(flag, (tx, yc + 4))
            pygame.draw.rect(screen, (30, 30, 30), (tx, yc + 4, flag.get_width(), flag.get_height()), 1)
            tx += flag.get_width() + 3
        screen.blit(_text_outlined(font, name, (170, 110, 110) if c.dead else color), (tx, yc))
        if c.dead:
            tag = _text_outlined(font, "DNF", (235, 80, 80))
        else:
            tag = _text_outlined(font, f"L{min(lap_of(c) + 1, TOTAL_LAPS)}", (185, 200, 180))
        screen.blit(tag, tag.get_rect(topright=(x + w - 6, yc)))

    # the player's lap count, x / y, under the board
    cur = min(lap_of(player) + 1, TOTAL_LAPS)
    if cur >= TOTAL_LAPS and TOTAL_LAPS > 1:
        lap_s = _text_outlined(get_font(26), "FINAL LAP", (255, 80, 80))
    else:
        lap_s = _text_outlined(get_font(26), f"LAP {cur}/{TOTAL_LAPS}", (255, 210, 70))
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

def draw_hud(screen, car, font=None, cars=None, hud_opacity=1.0):
    if hud_opacity <= 0.02:
        return
    if hud_opacity >= 0.98:
        target_s = screen
    else:
        target_s = pygame.Surface((W, H), pygame.SRCALPHA)

    draw_hearts(target_s, car.hearts)
    if getattr(car, "item", None) is not None:
        ix, iy = 20, 52
        item_label = "CONE" if car.item == "cone" else "OIL SLICK"
        key_hint = "[F/C]" if car.item == "cone" else "[F/V]"
        panel = pygame.Surface((132, 26), pygame.SRCALPHA)
        panel.fill((20, 24, 32, 210))
        border_col = (255, 140, 30) if car.item == "cone" else (180, 180, 200)
        pygame.draw.rect(panel, border_col, (0, 0, 132, 26), 1)
        target_s.blit(panel, (ix, iy))
        hud_f = get_font(18)
        lbl = _text_outlined(hud_f, f"{key_hint} {item_label}", (255, 235, 120))
        target_s.blit(lbl, (ix + 6, iy + 4))

    # Flashing wrong-way warning banner
    if getattr(car, "wrong_way", False) and not car.dead:
        flash = (int(time.time() * 5) % 2 == 0)
        ww_f = get_font(26)
        warn_col = (255, 65, 65) if flash else (255, 220, 50)
        lbl = _text_outlined(ww_f, "WRONG WAY!", warn_col, (15, 15, 20), 3)
        r = lbl.get_rect(center=(W // 2, 75))
        bg_rect = r.inflate(28, 10)
        bg = pygame.Surface(bg_rect.size, pygame.SRCALPHA)
        bg.fill((25, 12, 12, 215 if flash else 165))
        pygame.draw.rect(bg, warn_col, bg.get_rect(), 2, border_radius=6)
        target_s.blit(bg, bg_rect.topleft)
        target_s.blit(lbl, r)

    if cars is not None:
        draw_leaderboard(target_s, cars, car)
        draw_minimap(target_s, cars, car)

    if target_s is not screen:
        target_s.set_alpha(int(255 * max(0.0, min(1.0, hud_opacity))))
        screen.blit(target_s, (0, 0))

# =================================================================================================
# cinematic letterbox & animated callout banners
# =================================================================================================
def draw_letterbox(screen, height):
    h = int(round(height))
    if h <= 0:
        return
    h = min(H // 2, h)
    # Top bar
    pygame.draw.rect(screen, (8, 9, 12), (0, 0, W, h))
    pygame.draw.line(screen, (45, 52, 65), (0, h - 1), (W, h - 1), 1)
    # Bottom bar
    pygame.draw.rect(screen, (8, 9, 12), (0, H - h, W, h))
    pygame.draw.line(screen, (45, 52, 65), (0, H - h), (W, H - h), 1)

ACTIVE_BANNER = None

def trigger_banner(text, color=(255, 230, 70), sub="", dur=1.8):
    global ACTIVE_BANNER
    ACTIVE_BANNER = {
        "text": text,
        "color": color,
        "sub": sub,
        "dur": max(0.5, dur),
        "timer": max(0.5, dur),
    }

def update_banner(dt):
    global ACTIVE_BANNER
    if ACTIVE_BANNER is not None:
        ACTIVE_BANNER["timer"] -= dt
        if ACTIVE_BANNER["timer"] <= 0.0:
            ACTIVE_BANNER = None

def draw_callout_banner(screen):
    global ACTIVE_BANNER
    if ACTIVE_BANNER is None:
        return
    b = ACTIVE_BANNER
    dur, timer = b["dur"], b["timer"]
    if timer <= 0:
        return
    elapsed = dur - timer

    # 1. Scale-Bounce animation during entrance (0..0.24s)
    scale = 1.0
    if elapsed < 0.24:
        prog = elapsed / 0.24
        bounce = math.cos(prog * math.pi * 2.0) * math.exp(-prog * 4.5)
        scale = 1.0 + 0.65 * bounce
    elif timer < 0.25:
        scale = 1.0 - (0.25 - timer) * 0.35

    # 2. Alpha calculation
    alpha = 255
    if timer < 0.25:
        alpha = int(255 * max(0.0, timer / 0.25))

    cy = int(H * 0.25)
    rw = int(W * 0.72)
    rh = 50
    rx = (W - rw) // 2
    ry = cy - rh // 2

    # Ribbon background
    ribbon = pygame.Surface((rw, rh), pygame.SRCALPHA)
    r_alpha = int(215 * (alpha / 255.0))
    ribbon.fill((12, 16, 24, r_alpha))
    border_col = (b["color"][0], b["color"][1], b["color"][2], r_alpha)
    pygame.draw.line(ribbon, border_col, (0, 0), (rw, 0), 2)
    pygame.draw.line(ribbon, border_col, (0, rh - 1), (rw, rh - 1), 2)
    screen.blit(ribbon, (rx, ry))

    # 3. Main typography with scale-bounce and motion blur
    f_main = get_font(34)
    main_surf = _text_outlined(f_main, b["text"], b["color"], outline=(10, 10, 15))

    # Motion blur / ghost trails during entrance slam
    if elapsed < 0.24:
        ghost_prog = 1.0 - (elapsed / 0.24)
        g_alpha = int(90 * ghost_prog)
        if g_alpha > 0:
            for g_offset in (-18 * ghost_prog, 18 * ghost_prog):
                g_surf = _text_outlined(f_main, b["text"], (255, 255, 255), outline=(20, 20, 30))
                g_surf.set_alpha(g_alpha)
                screen.blit(g_surf, g_surf.get_rect(center=(W / 2 + g_offset, cy - (8 if b["sub"] else 0))))

    # Scaled main text blit
    if abs(scale - 1.0) > 0.02:
        tw = max(1, int(main_surf.get_width() * scale))
        th = max(1, int(main_surf.get_height() * scale))
        scaled_text = pygame.transform.smoothscale(main_surf, (tw, th))
    else:
        scaled_text = main_surf
    if alpha < 255:
        scaled_text.set_alpha(alpha)
    screen.blit(scaled_text, scaled_text.get_rect(center=(W / 2, cy - (8 if b["sub"] else 0))))

    # Subtext (if any)
    if b["sub"]:
        f_sub = get_font(18)
        sub_surf = _text_outlined(f_sub, b["sub"].upper(), (230, 235, 245), outline=(15, 15, 20))
        if alpha < 255:
            sub_surf.set_alpha(alpha)
        screen.blit(sub_surf, sub_surf.get_rect(center=(W / 2, cy + 14)))
