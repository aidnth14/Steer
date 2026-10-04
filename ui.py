"""Steer UI kit: the menus' look, in one place.

Everything is drawn from flat palette colours with filled rectangles (no fonts, no images, no
anti-aliasing), so the menus are pixel-crisp at 600x400 and identical on every machine.

  text(...)                 the Steer pixel face (5x7, bold or regular, any whole-number size)
  logo(px)                  the STEER logo: slanted, gold-to-red, speed streaks
  slab / panel / keycap     the building blocks
  draw_menu(...)            the title / pause menu (also the Singleplayer / Multiplayer stack)
  draw_settings(...)        the tabbed settings screen
  menu_layout / settings_* where everything sits, so main.py can hit-test the same rects

Colours come from the Steer palette (TASTE.md). Rule of thumb on these screens:
red = selected, gold = values and emphasis, white = text, steel = secondary text.
"""
import math
import pygame

# ---------------------------------------------------------------------------------- palette
INK = (16, 18, 28)
NIGHT = (23, 21, 36)
NIGHT2 = (34, 32, 52)
SLATE = (62, 59, 101)
ASPHALT_D = (41, 46, 58)
STEEL = (100, 109, 128)
STEEL_L = (165, 190, 206)
WHITE = (240, 248, 255)
GOLD = (246, 205, 72)
AMBER = (243, 168, 51)
ORANGE = (228, 110, 22)
RED = (236, 39, 63)
RED_HI = (242, 18, 19)
CRIMSON = (172, 40, 71)
WINE = (107, 38, 67)
GREEN = (62, 155, 72)
GREEN_HI = (138, 231, 65)
BLUE = (51, 136, 222)
CYAN = (54, 197, 244)
PALE = (247, 243, 183)
CLEAR = (0, 0, 0, 0)


def _a(c, a):
    return (c[0], c[1], c[2], a)


# ---------------------------------------------------------------------------------- the face
# 5x7 glyphs ('#' = ink). Lower case is drawn as upper case.
_G = {
    "A": ".###.|#...#|#...#|#####|#...#|#...#|#...#", "B": "####.|#...#|#...#|####.|#...#|#...#|####.",
    "C": ".###.|#...#|#....|#....|#....|#...#|.###.", "D": "####.|#...#|#...#|#...#|#...#|#...#|####.",
    "E": "#####|#....|#....|####.|#....|#....|#####", "F": "#####|#....|#....|####.|#....|#....|#....",
    "G": ".###.|#...#|#....|#.###|#...#|#...#|.####", "H": "#...#|#...#|#...#|#####|#...#|#...#|#...#",
    "I": "###|.#.|.#.|.#.|.#.|.#.|###", "J": "..###|...#.|...#.|...#.|#..#.|#..#.|.##..",
    "K": "#...#|#..#.|#.#..|##...|#.#..|#..#.|#...#", "L": "#....|#....|#....|#....|#....|#....|#####",
    "M": "#...#|##.##|#.#.#|#.#.#|#...#|#...#|#...#", "N": "#...#|##..#|#.#.#|#..##|#...#|#...#|#...#",
    "O": ".###.|#...#|#...#|#...#|#...#|#...#|.###.", "P": "####.|#...#|#...#|####.|#....|#....|#....",
    "Q": ".###.|#...#|#...#|#...#|#.#.#|#..#.|.##.#", "R": "####.|#...#|#...#|####.|#.#..|#..#.|#...#",
    "S": ".####|#....|#....|.###.|....#|....#|####.", "T": "#####|..#..|..#..|..#..|..#..|..#..|..#..",
    "U": "#...#|#...#|#...#|#...#|#...#|#...#|.###.", "V": "#...#|#...#|#...#|#...#|#...#|.#.#.|..#..",
    "W": "#...#|#...#|#...#|#.#.#|#.#.#|##.##|#...#", "X": "#...#|#...#|.#.#.|..#..|.#.#.|#...#|#...#",
    "Y": "#...#|#...#|.#.#.|..#..|..#..|..#..|..#..", "Z": "#####|....#|...#.|..#..|.#...|#....|#####",
    "0": ".###.|#...#|#..##|#.#.#|##..#|#...#|.###.", "1": "..#..|.##..|..#..|..#..|..#..|..#..|.###.",
    "2": ".###.|#...#|....#|...#.|..#..|.#...|#####", "3": "####.|....#|....#|.###.|....#|....#|####.",
    "4": "...#.|..##.|.#.#.|#..#.|#####|...#.|...#.", "5": "#####|#....|####.|....#|....#|#...#|.###.",
    "6": ".###.|#....|#....|####.|#...#|#...#|.###.", "7": "#####|....#|...#.|..#..|.#...|.#...|.#...",
    "8": ".###.|#...#|#...#|.###.|#...#|#...#|.###.", "9": ".###.|#...#|#...#|.####|....#|....#|.###.",
    ".": ".|.|.|.|.|.|#", ",": ".|.|.|.|.|#|#", "!": "#|#|#|#|#|.|#", "'": "#|#|.|.|.|.|.",
    ":": ".|#|.|.|.|#|.", "-": "....|....|....|####|....|....|....", "?": ".###.|#...#|....#|...#.|..#..|.....|..#..",
    "/": "....#|...#.|...#.|..#..|.#...|.#...|#....", "·": ".|.|.|#|.|.|.", " ": "...|...|...|...|...|...|...",
    "<": "...#|..#.|.#..|#...|.#..|..#.|...#", ">": "#...|.#..|..#.|...#|..#.|.#..|#...",
    "@": ".###.|#...#|#.###|#.#.#|#.###|#....|.####", "(": ".#|#.|#.|#.|#.|#.|.#", ")": "#.|.#|.#|.#|.#|.#|#.",
    "_": ".....|.....|.....|.....|.....|.....|#####", "+": ".....|..#..|..#..|#####|..#..|..#..|.....",
    "%": "##..#|##..#|...#.|..#..|.#...|#..##|#..##", "=": "....|....|####|....|####|....|....",
    "#": ".#.#.|.#.#.|#####|.#.#.|#####|.#.#.|.#.#.", "&": ".##..|#..#.|.##..|.#...|#.#.#|#..#.|.##.#",
    "↑": "..#..|.###.|#.#.#|..#..|..#..|..#..|..#..", "↓": "..#..|..#..|..#..|..#..|#.#.#|.###.|..#..",
    "←": ".....|..#..|.#...|#####|.#...|..#..|.....", "→": ".....|..#..|...#.|#####|...#.|..#..|.....",
    "◀": "...#|..##|.###|####|.###|..##|...#", "▶": "#...|##..|###.|####|###.|##..|#...",
    "⏎": "....#|....#|..#.#|.##.#|#####|.##..|..#..", "≡": ".....|#####|.....|#####|.....|#####|.....",
    "✓": ".....|....#|...##|#.##.|###..|.#...|.....", "×": ".....|#...#|.#.#.|..#..|.#.#.|#...#|.....",
}
_GLYPH_ROWS = {k: [[c == "#" for c in r] for r in v.split("|")] for k, v in _G.items()}


def _mask(text, bold=False, gap=1):
    rows = [[] for _ in range(7)]
    for n, ch in enumerate(text.upper()):
        g = _GLYPH_ROWS.get(ch) or _GLYPH_ROWS["?"]
        if n:
            for r in rows:
                r.extend([False] * gap)
        for i in range(7):
            bits = g[i]
            if bold:
                bits = bits + [False]
                bits = [bits[j] or (j > 0 and bits[j - 1]) for j in range(len(bits))]
            rows[i].extend(bits)
    return rows


def _dilate(m):
    h, w = len(m), len(m[0]) if m else 0
    out = [[False] * (w + 2) for _ in range(h + 2)]
    for y in range(h):
        for x in range(w):
            if m[y][x]:
                for dy in (0, 1, 2):
                    row = out[y + dy]
                    row[x] = row[x + 1] = row[x + 2] = True
    return out


def _pad(m, n=1):
    w = len(m[0]) if m else 0
    blank = [False] * (w + 2 * n)
    return [blank[:] for _ in range(n)] + [[False] * n + r + [False] * n for r in m] + [blank[:] for _ in range(n)]


def _paint(surf, mask, ox, oy, px, color):
    # one fill per horizontal run: fast enough to build sprites, and pixel exact
    for r, row in enumerate(mask):
        c = color[min(r, len(color) - 1)] if isinstance(color, list) else color
        x, n = 0, len(row)
        while x < n:
            if row[x]:
                x0 = x
                while x < n and row[x]:
                    x += 1
                surf.fill(c, (ox + x0 * px, oy + r * px, (x - x0) * px, px))
            else:
                x += 1


_CACHE = {}


def text(s, px=2, color=WHITE, bold=False, shadow=True, outline=False):
    """The Steer pixel face as a Surface. px = size of one font pixel on screen (1, 2, 3...)."""
    key = ("t", s, px, color if not isinstance(color, list) else tuple(color), bold, shadow, outline)
    img = _CACHE.get(key)
    if img is not None:
        return img
    m = _mask(s, bold)
    if outline:
        edge = _dilate(m)
        m = _pad(m)
    else:
        edge = None
    h, w = len(m), len(m[0]) if m and m[0] else 1
    sh = 1 if shadow else 0
    img = pygame.Surface(((w + sh) * px, (h + sh) * px), pygame.SRCALPHA)
    img.fill(CLEAR)
    if shadow:
        _paint(img, edge or m, px, px, px, _a(INK, 170))
    if edge:
        _paint(img, edge, 0, 0, px, INK)
    _paint(img, m, 0, 0, px, color)
    _CACHE[key] = img
    return img


def text_w(s, px=2, bold=False):
    m = _mask(s, bold)
    return len(m[0]) * px if m and m[0] else 0


def put(surf, img, x, y, anchor="topleft"):
    """Blit with an anchor: topleft, midleft, center, midright, topright, bottomleft, bottomright,
    midtop, midbottom."""
    w, h = img.get_width(), img.get_height()
    if "right" in anchor:
        x -= w
    elif anchor in ("center", "midtop", "midbottom"):
        x -= w // 2
    if anchor.startswith("bottom") or anchor == "midbottom":
        y -= h
    elif anchor.startswith("mid") and anchor not in ("midtop", "midbottom") or anchor == "center":
        y -= h // 2
    surf.blit(img, (int(x), int(y)))
    return pygame.Rect(int(x), int(y), w, h)


# ---------------------------------------------------------------------------------- the logo
def logo(px=3):
    """STEER, slanted like it's doing 300: gold-to-red, with speed streaks and a lit top edge."""
    key = ("logo", px)
    if key in _CACHE:
        return _CACHE[key]
    m = _mask("STEER", bold=True)
    m = [[b for b in row for _ in (0, 1)] for row in m for _ in (0, 1)]       # 2x: 14 rows tall
    h = len(m)
    streak = [[False] * 12 for _ in range(h)]
    for r, ln in ((3, 10), (6, 7), (9, 11), (12, 6)):
        for x in range(12 - ln, 12):
            streak[r][x] = True
    m = [streak[r] + [False, False] + m[r] for r in range(h)]
    w = len(m[0])
    slant = (h - 1) // 2
    m = [[False] * ((h - 1 - r) // 2) + m[r] + [False] * (slant - (h - 1 - r) // 2) for r in range(h)]
    body = _pad(m)
    edge = _dilate(m)
    H, W = len(edge), len(edge[0])
    ramp = [WHITE, PALE, GOLD, GOLD, AMBER, AMBER, AMBER, ORANGE, ORANGE, (189, 81, 17), RED, RED,
            CRIMSON, WINE, WINE]
    img = pygame.Surface(((W + 1) * px, (H + 1) * px), pygame.SRCALPHA)
    img.fill(CLEAR)
    _paint(img, edge, px, px, px, _a(INK, 160))
    _paint(img, edge, 0, 0, px, INK)
    _paint(img, body, 0, 0, px, [ramp[0]] + ramp)
    top = [[body[y][x] and (y == 0 or not body[y - 1][x]) and y < H // 2 for x in range(W)] for y in range(H)]
    _paint(img, top, 0, 0, px, WHITE)
    _CACHE[key] = img
    return img


# ---------------------------------------------------------------------------------- blocks
def _box(w, h, face, outline=INK, hi=None, lo=None, lip=None, lip_h=3):
    """A pixel-rounded box (2 px chamfered corners) as an SRCALPHA Surface."""
    key = ("box", w, h, face, outline, hi, lo, lip, lip_h)
    s = _CACHE.get(key)
    if s is not None:
        return s
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    s.fill(CLEAR)
    s.fill(face, (2, 1, w - 4, h - 2))
    s.fill(face, (1, 2, w - 2, h - 4))
    if lip:
        s.fill(lip, (2, h - 1 - lip_h, w - 4, lip_h))
        s.fill(lip, (1, h - 1 - lip_h, w - 2, lip_h - 1))
    if hi:
        s.fill(hi, (2, 1, w - 4, 1))
    if lo:
        s.fill(lo, (2, h - 2, w - 4, 1))
    if outline:
        s.fill(outline, (2, 0, w - 4, 1))
        s.fill(outline, (2, h - 1, w - 4, 1))
        s.fill(outline, (0, 2, 1, h - 4))
        s.fill(outline, (w - 1, 2, 1, h - 4))
        for x, y in ((1, 1), (w - 2, 1), (1, h - 2), (w - 2, h - 2)):
            s.fill(outline, (x, y, 1, 1))
    _CACHE[key] = s
    return s


def panel(surf, rect, alpha=228):
    r = pygame.Rect(rect)
    surf.blit(_box(r.w, r.h, _a(NIGHT, alpha), INK, hi=_a(SLATE, 255), lo=_a(INK, 255)), r.topleft)


def slab(surf, rect, hot=False, face=None, lip=None):
    """A chunky button body. Hot = racing red with a dark lip and a finish-flag end."""
    r = pygame.Rect(rect)
    if hot:
        surf.blit(_box(r.w, r.h, face or RED, INK, hi=RED_HI, lip=lip or WINE), r.topleft)
        cw = 4                                   # chequered tail, 2 columns of 4 px squares
        x0 = r.right - 3 - cw * 2
        for j in range(2):
            for i in range((r.h - 6) // cw + 1):
                y = r.y + 2 + i * cw
                hh = min(cw, r.bottom - 5 - y)
                if hh > 0:
                    surf.fill(WHITE if (i + j) % 2 == 0 else INK, (x0 + j * cw, y, cw, hh))
    else:
        surf.blit(_box(r.w, r.h, face or _a(NIGHT2, 215), _a(INK, 230), hi=_a(SLATE, 230),
                       lip=lip or _a(INK, 200), lip_h=2), r.topleft)


def kerb_v(surf, x, y0, y1, w=5, cell=8, phase=0):
    for y in range(y0, y1, cell):
        surf.fill(RED if ((y + phase) // cell) % 2 else WHITE, (x, y, w, min(cell, y1 - y)))


def keycap(label, hot=False, wait=False):
    """A keyboard key: light cap, steel lip, ink legend. wait = gold, while rebinding."""
    key = ("cap", label, hot, wait)
    s = _CACHE.get(key)
    if s is not None:
        return s
    t = text(label, 1, INK, bold=any(ch.isalnum() for ch in label), shadow=False)
    w = max(16, t.get_width() + 9)
    h = 15
    face, lip = (GOLD, AMBER) if wait else ((WHITE, STEEL_L) if not hot else (WHITE, GOLD))
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    s.fill(CLEAR)
    s.blit(_box(w, h, face, INK, lip=lip, lip_h=3), (0, 0))
    s.blit(t, ((w - t.get_width()) // 2 + 1, 3))
    _CACHE[key] = s
    return s


_CIRCLE13 = [4, 2, 1, 1, 0, 0, 0, 0, 0, 1, 1, 2, 4]
PAD_FACE = {"A": GREEN, "B": RED, "X": BLUE, "Y": GOLD}


def pad_glyph(name):
    """Controller glyphs: A B X Y (round), LB RB LT RT (shoulder), LS, DPAD, START."""
    key = ("pad", name)
    s = _CACHE.get(key)
    if s is not None:
        return s
    if name in PAD_FACE:
        s = pygame.Surface((15, 15), pygame.SRCALPHA)
        s.fill(CLEAR)
        for y, ins in enumerate(_CIRCLE13):
            s.fill(INK, (ins, y + 1, 15 - 2 * ins, 1))
        for y, ins in enumerate(_CIRCLE13[1:-1]):
            s.fill(PAD_FACE[name], (ins + 1, y + 2, 13 - 2 * ins, 1))
        put(s, text(name, 1, INK if name == "Y" else WHITE, bold=True, shadow=False), 8, 5, "midtop")
    elif name in ("LB", "RB", "LT", "RT"):
        t = text(name, 1, WHITE, bold=True, shadow=False)
        w = t.get_width() + 10
        s = pygame.Surface((w, 15), pygame.SRCALPHA)
        s.fill(CLEAR)
        s.blit(_box(w, 15, STEEL, INK, hi=STEEL_L, lip=ASPHALT_D, lip_h=3), (0, 0))
        s.blit(t, (5, 3))
    elif name == "LS":
        s = pygame.Surface((15, 15), pygame.SRCALPHA)
        s.fill(CLEAR)
        for y, ins in enumerate(_CIRCLE13):
            s.fill(INK, (ins, y + 1, 15 - 2 * ins, 1))
        for y, ins in enumerate(_CIRCLE13[1:-1]):
            s.fill(ASPHALT_D, (ins + 1, y + 2, 13 - 2 * ins, 1))
        for y, ins in enumerate([2, 1, 0, 0, 0, 1, 2]):
            s.fill(STEEL_L, (4 + ins, 4 + y, 7 - 2 * ins, 1))
        put(s, text("L", 1, INK, bold=True, shadow=False), 8, 4, "midtop")
    elif name == "DPAD":
        s = pygame.Surface((15, 15), pygame.SRCALPHA)
        s.fill(CLEAR)
        s.fill(INK, (5, 0, 5, 15))
        s.fill(INK, (0, 5, 15, 5))
        s.fill(STEEL, (6, 1, 3, 13))
        s.fill(STEEL, (1, 6, 13, 3))
        s.fill(STEEL_L, (6, 1, 3, 1))
        s.fill(STEEL_L, (1, 6, 1, 3))
    elif name == "START":
        s = pygame.Surface((17, 13), pygame.SRCALPHA)
        s.fill(CLEAR)
        s.blit(_box(17, 13, STEEL, INK, lip=ASPHALT_D, lip_h=2), (0, 0))
        for y in (3, 5, 7):
            s.fill(WHITE, (4, y, 9, 1))
    else:
        s = keycap(name)
    _CACHE[key] = s
    return s


def glyphs(names, pad=False):
    """A row of keycaps / pad glyphs as one Surface. names: list like ["↑", "↓"] or ["A"]."""
    parts = [pad_glyph(n) if pad else keycap(n) for n in names]
    w = sum(p.get_width() for p in parts) + 2 * (len(parts) - 1)
    h = max(p.get_height() for p in parts)
    s = pygame.Surface((max(1, w), h), pygame.SRCALPHA)
    s.fill(CLEAR)
    x = 0
    for p in parts:
        s.blit(p, (x, (h - p.get_height()) // 2))
        x += p.get_width() + 2
    return s


def hint_bar(surf, items, x, y, pad=False, align="left", color=STEEL_L):
    """[keys] LABEL   [keys] LABEL ... ; items = [(["↑", "↓"], "SELECT"), ...]."""
    pieces = []
    for keys, label in items:
        g = glyphs(keys, pad)
        t = text(label, 1, color, bold=True)
        pieces.append((g, t))
    total = sum(g.get_width() + 4 + t.get_width() for g, t in pieces) + 12 * (len(pieces) - 1)
    cx = x - total if align == "right" else x
    for g, t in pieces:
        put(surf, g, cx, y, "midleft")
        cx += g.get_width() + 4
        put(surf, t, cx, y + 1, "midleft")
        cx += t.get_width() + 12
    return total


# ---------------------------------------------------------------------------------- social icons
# 11x11 original glyphs: a shop bag, a screen with a play arrow, a camera, a chat bubble
_ICONS = {
    "store": ["...#####...", "..##...##..", "..#.....#..", "###########", "##.#####.##",
              "###########", "###########", "###########", "###########", ".#########.", "..........."],
    "video": ["###########", "#.........#", "#..##.....#", "#..####...#", "#..######.#",
              "#..####...#", "#..##.....#", "#.........#", "###########", "...#####...", "..........."],
    "photo": ["...###.....", "###########", "#.........#", "#...###...#", "#..#...#..#",
              "#..#...#..#", "#...###...#", "#.........#", "###########", "...........", "..........."],
    "chat": [".#########.", "###########", "###########", "##.##.##.##", "###########",
             "###########", ".#########.", "..##.......", ".##........", "#..........", "..........."],
}
ICON_ACCENT = {"store": GOLD, "video": RED, "photo": ORANGE, "chat": BLUE}
ICON_LABEL = {"store": "STORE", "video": "VIDEOS", "photo": "PHOTOS", "chat": "COMMUNITY"}


def social_icon(kind, hot=False):
    key = ("icon", kind, hot)
    s = _CACHE.get(key)
    if s is not None:
        return s
    w = 24
    s = pygame.Surface((w, w + 2), pygame.SRCALPHA)
    s.fill(CLEAR)
    acc = ICON_ACCENT.get(kind, STEEL)
    if hot:
        s.blit(_box(w, w + 2, acc, INK, hi=WHITE, lip=_shade(acc), lip_h=3), (0, 0))
    else:
        s.blit(_box(w, w + 2, _a(NIGHT2, 225), _a(INK, 235), hi=_a(SLATE, 235), lip=_a(INK, 210), lip_h=2), (0, 0))
    rows = [[c == "#" for c in r] for r in _ICONS.get(kind, _ICONS["chat"])]
    gc = (INK if kind == "store" else WHITE) if hot else STEEL_L
    _paint(s, rows, 7, 6, 1, gc)
    _CACHE[key] = s
    return s


def _shade(c):
    return (c[0] * 6 // 10, c[1] * 6 // 10, c[2] * 6 // 10)


# ---------------------------------------------------------------------------------- animation
_anim = {}


def ease(key, target, rate=0.35):
    v = _anim.get(key, target)
    v += (target - v) * rate
    if abs(target - v) < 0.3:
        v = target
    _anim[key] = v
    return v


def _blink(period=500):
    return (pygame.time.get_ticks() // period) % 2 == 0


# ==================================================================================== MENU
MENU_X, MENU_W, MENU_H, MENU_STEP = 22, 196, 30, 36


def menu_layout(n, screen_h=400):
    """Rects of the n stacked menu buttons (bottom-left), for drawing and hit-testing."""
    y0 = screen_h - 46 - MENU_STEP * n
    return [pygame.Rect(MENU_X, y0 + i * MENU_STEP, MENU_W, MENU_H) for i in range(n)]


def social_layout(n, screen_w=600, screen_h=400):
    x = screen_w - 16 - n * 24 - (n - 1) * 6
    return [pygame.Rect(x + i * 30, screen_h - 66, 24, 26) for i in range(n)]


def _band(w, h):
    """The slanted ink band down the left with a kerb along its edge (cached)."""
    key = ("band", w, h)
    s = _CACHE.get(key)
    if s is not None:
        return s
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    s.fill(CLEAR)
    top, bot = w - 10, w - 76
    for y in range(h):
        xe = int(top + (bot - top) * y / (h - 1))
        s.fill(_a(INK, 200), (0, y, xe, 1))
        s.fill(RED if (y // 8) % 2 else WHITE, (xe, y, 5, 1))
        s.fill(INK, (xe + 5, y, 1, 1))
    _CACHE[key] = s
    return s


def draw_menu(surf, items, sel, mouse=(-1, -1), tag=None, chip=None, credit=None,
              socials=(), pad=False, hints=True):
    """The title / pause menu.
    items   : button labels, top to bottom
    sel     : highlighted index
    tag     : a line under the logo (e.g. "DRIFT · BASH · WIN" or "LAP 2/3 · 4TH")
    chip    : a small gold label above the tag (e.g. "PAUSED"), or None
    credit  : bottom-right line, e.g. "MADE BY @YOU · V1.2.0"
    socials : icon kinds for the bottom-right row: "store", "video", "photo", "chat"
    Returns {"buttons": [Rect...], "socials": [Rect...]}."""
    W, H = surf.get_size()
    surf.blit(_band(300, H), (0, 0))
    lg = logo(3)
    put(surf, lg, 14, 18)
    ty = 18 + lg.get_height() + 4
    if chip:
        ct = text(chip, 1, INK, bold=True, shadow=False)
        cw = ct.get_width() + 10
        surf.blit(_box(cw, 13, GOLD, INK, lip=AMBER, lip_h=2), (22, ty))
        surf.blit(ct, (27, ty + 3))
        ty += 18
    if tag:
        put(surf, text(tag, 1, STEEL_L, bold=True), 23, ty)

    rects = menu_layout(len(items), H)
    for i, (label, r) in enumerate(zip(items, rects)):
        hot = i == sel
        dx = ease(("menu", i, label), 10 if hot else 0)
        rr = r.move(int(dx), 0)
        slab(surf, rr, hot)
        t = text(label, 2, WHITE if hot else STEEL_L, bold=True)
        put(surf, t, rr.x + 14, rr.centery - 1, "midleft")
        if hot:
            put(surf, text("▶", 2, GOLD, bold=False), rr.x - 14, rr.centery - 1, "midleft")

    if hints:
        items_h = [(["DPAD"] if pad else ["↑", "↓"], "SELECT"), (["A"] if pad else ["⏎"], "OK")]
        hint_bar(surf, items_h, 22, H - 22, pad=pad)

    srects = social_layout(len(socials), W, H)
    hover_label = None
    for kind, r in zip(socials, srects):
        hot = r.collidepoint(mouse)
        surf.blit(social_icon(kind, hot), (r.x, r.y - (2 if hot else 0)))
        if hot:
            hover_label = (ICON_LABEL.get(kind, kind.upper()), r)
    if hover_label:
        lbl, r = hover_label
        t = text(lbl, 1, WHITE, bold=True, outline=True, shadow=False)
        put(surf, t, min(W - 8 - t.get_width() // 2, r.centerx), r.y - 6, "midbottom")
    if credit:
        put(surf, text(credit, 1, WHITE, bold=True, outline=True, shadow=False), W - 14, H - 14, "bottomright")
    return {"buttons": rects, "socials": srects}


# ==================================================================================== SETTINGS
PANEL = pygame.Rect(16, 76, 568, 276)
ROW_H = 24
CTRL_W = 232
SLIDER_W = 160
TAB_Y, TAB_H = 46, 26
BACK = pygame.Rect(494, 360, 90, 30)
KB_COL = pygame.Rect(PANEL.x + 6, PANEL.y + 6, 318, PANEL.h - 12)
PAD_COL = pygame.Rect(PANEL.x + 332, PANEL.y + 6, PANEL.w - 338, PANEL.h - 12)
KB_ROW_H = 24


def tab_layout(tabs):
    x = 16 + 22
    out = []
    for t in tabs:
        w = text_w(t, 2) + 22
        out.append(pygame.Rect(x, TAB_Y, w, TAB_H))
        x += w + 4
    return out


def row_rect(i, controls=False, n_rows=None):
    if controls:
        num_non_binds = max(0, (n_rows or 0) - 9)
        if num_non_binds > 0 and i < num_non_binds:
            return pygame.Rect(PAD_COL.x + 4, PAD_COL.y + 24 + i * 24, PAD_COL.w - 8, 22)
        bind_idx = i - num_non_binds if num_non_binds > 0 else i
        return pygame.Rect(KB_COL.x, KB_COL.y + 22 + bind_idx * KB_ROW_H, KB_COL.w, KB_ROW_H - 2)
    rh = ROW_H if (n_rows is not None and n_rows >= 10) else 26
    return pygame.Rect(PANEL.x + 6, PANEL.y + 6 + i * rh, PANEL.w - 12, rh - 2)


def ctrl_rect(i, n_rows=None, controls=False):
    r = row_rect(i, controls, n_rows)
    if controls:
        return pygame.Rect(r.x + r.w // 2, r.y, r.w // 2, r.h)
    return pygame.Rect(r.right - 12 - CTRL_W, r.y, CTRL_W, r.h)


def slider_track(i, n_rows=None):
    c = ctrl_rect(i, n_rows)
    return pygame.Rect(c.x, c.centery - 6, SLIDER_W, 12)


def _slider(surf, r, frac, hot, val_label=None):
    frac = max(0.0, min(1.0, frac))
    segs, sw = 20, r.w // 20
    fill_px = frac * segs * sw
    for k in range(segs):
        x = r.x + k * sw
        f = max(0.0, min(1.0, (fill_px - k * sw) / (sw - 1)))
        surf.fill(INK, (x, r.y, sw - 1, r.h))
        surf.fill(ASPHALT_D, (x, r.y + 1, sw - 1, r.h - 2))
        fw = int(round(f * (sw - 1)))
        if fw > 0:
            surf.fill(GOLD if hot else AMBER, (x, r.y + 1, fw, r.h - 2))
            surf.fill(AMBER if hot else ORANGE, (x, r.bottom - 4, fw, 3))
            surf.fill(PALE if hot else GOLD, (x, r.y + 1, fw, 1))
    kx = r.x + int(fill_px) - 2
    kx = max(r.x - 2, min(r.x + segs * sw - 3, kx))
    surf.fill(INK, (kx - 1, r.y - 4, 6, r.h + 8))
    surf.fill(WHITE if hot else STEEL_L, (kx, r.y - 3, 4, r.h + 6))
    disp = val_label if val_label is not None else f"{int(round(frac * 100))}"
    put(surf, text(disp, 2, WHITE if hot else STEEL_L), r.x + segs * sw + 10, r.centery, "midleft")


def _toggle(surf, c, on, hot):
    w, h = 34, 16
    x, y = c.x, c.centery - h // 2
    if on:
        surf.blit(_box(w, h, GREEN, INK, hi=GREEN_HI, lip=(38, 92, 66), lip_h=2), (x, y))
        surf.blit(_box(14, 12, WHITE, INK, lip=STEEL_L, lip_h=2), (x + w - 16, y + 2))
    else:
        surf.blit(_box(w, h, ASPHALT_D, INK, lip=INK, lip_h=2), (x, y))
        surf.blit(_box(14, 12, STEEL, INK, lip=ASPHALT_D, lip_h=2), (x + 2, y + 2))
    put(surf, text("ON" if on else "OFF", 2, WHITE if hot or on else STEEL),
        x + w + 10, c.centery, "midleft")


def _cycle(surf, c, value, hot):
    ac = GOLD if hot else STEEL
    put(surf, text("◀", 2, ac, shadow=True), c.x, c.centery, "midleft")
    put(surf, text("▶", 2, ac, shadow=True), c.right, c.centery, "midright")
    put(surf, text(str(value), 2, WHITE if hot else STEEL_L), c.centerx, c.centery, "center")


def key_label(name):
    """pygame.key.name() -> a short legend for a keycap."""
    n = (name or "?").lower()
    table = {"left shift": "L SHIFT", "right shift": "R SHIFT", "left ctrl": "L CTRL",
             "right ctrl": "R CTRL", "left alt": "L ALT", "right alt": "R ALT", "return": "ENTER",
             "up": "↑", "down": "↓", "left": "←", "right": "→", "backspace": "BKSP",
             "escape": "ESC", "caps lock": "CAPS", "space": "SPACE", "tab": "TAB"}
    return table.get(n, n.upper()[:8])


PAD_ROWS = [("STEER", ["LS", "DPAD"]), ("BASH LEFT", ["LB"]), ("BASH RIGHT", ["RB"]),
            ("RAM", ["A"]), ("DRIFT (HOLD)", ["B"]), ("SHOOT / ITEM", ["X"]), ("PAUSE", ["START"])]


def draw_settings(surf, tabs, tab, rows, sel, mouse=(-1, -1), awaiting=None, pad=False,
                  pad_rows=PAD_ROWS, title="SETTINGS", chip=None, device_name=None):
    """The tabbed settings screen.
    tabs : tab names; tab = active index
    rows : the active tab's rows, dicts with
           kind  "slider" (value 0..1) | "toggle" (value bool) | "cycle" (value str) | "bind" (value key legend)
           label, value, help, and for binds "id" (compared with `awaiting`)
    sel  : highlighted row index
    The CONTROLS tab is any tab whose rows are all binds: keyboard on the left, the gamepad map
    (pad_rows) on the right."""
    W, H = surf.get_size()
    put(surf, text(title, 3, WHITE, bold=True), 16, 12)
    if chip:
        ct = text(chip, 1, INK, bold=True, shadow=False)
        cw = ct.get_width() + 10
        surf.blit(_box(cw, 13, GOLD, INK, lip=AMBER, lip_h=2), (W - 16 - cw, 18))
        surf.blit(ct, (W - 16 - cw + 5, 21))

    # tabs, with the switch keys either side
    trs = tab_layout(tabs)
    put(surf, glyphs(["LB"] if pad else ["Q"], pad), 16, TAB_Y + TAB_H // 2, "midleft")
    put(surf, glyphs(["RB"] if pad else ["E"], pad), trs[-1].right + 6, TAB_Y + TAB_H // 2, "midleft")
    for i, (name, r) in enumerate(zip(tabs, trs)):
        on = i == tab
        hov = r.collidepoint(mouse) and not on
        if on:
            surf.blit(_box(r.w, r.h + 4, RED, INK, hi=RED_HI, lip=WINE, lip_h=3), (r.x, r.y))
        else:
            slab(surf, r, False, face=_a(SLATE, 230) if hov else None)
        put(surf, text(name, 2, WHITE if on or hov else STEEL_L), r.centerx, r.centery - (0 if on else 1), "center")

    panel(surf, PANEL)
    controls = bool(rows) and (all(r.get("kind") == "bind" for r in rows) or (len(tabs) > tab and tabs[tab] == "CONTROLS"))
    help_text = ""

    if controls:
        bind_rows = [r for r in rows if r.get("kind") == "bind"]
        non_binds = [r for r in rows if r.get("kind") != "bind"]

        put(surf, text("KEYBOARD", 1, GOLD, bold=True), KB_COL.x + 10, KB_COL.y + 6)
        for i, row in enumerate(bind_rows):
            g_idx = i + len(non_binds)
            r = row_rect(g_idx, True, len(rows))
            hot = g_idx == sel
            if hot:
                y = ease(("srow", tabs[tab]), r.y)
                surf.fill(_a(SLATE, 255), (r.x, int(y), r.w, r.h))
                surf.fill(GOLD, (r.x, int(y), 3, r.h))
                help_text = row.get("help", "")
            put(surf, text(row["label"], 2, WHITE if hot else STEEL_L), r.x + 12, r.centery, "midleft")
            waiting = awaiting is not None and awaiting == row.get("id")
            if waiting:
                cap = keycap("...", wait=True) if _blink(300) else keycap("...", wait=False)
                put(surf, cap, r.right - 10, r.centery, "midright")
                put(surf, text("PRESS A KEY", 1, GOLD, bold=True), r.right - 18 - cap.get_width(), r.centery, "midright")
            else:
                put(surf, keycap(str(row["value"]), hot=hot), r.right - 10, r.centery, "midright")

        surf.fill(_a(SLATE, 200), (PAD_COL.x - 5, PAD_COL.y + 4, 1, PAD_COL.h - 8))
        put(surf, text("GAMEPAD & INPUT", 1, GOLD, bold=True), PAD_COL.x + 6, PAD_COL.y + 6)
        dev_lbl = str(device_name) if device_name else ("GAMEPAD DETECTED" if pad else "KEYBOARD & MOUSE")
        put(surf, text(dev_lbl, 1, STEEL_L, bold=True), PAD_COL.right - 8, PAD_COL.y + 7, "topright")

        for g_idx, row in enumerate(non_binds):
            r = row_rect(g_idx, True, len(rows))
            hot = g_idx == sel
            if hot:
                surf.fill(_a(SLATE, 255), (r.x, r.y, r.w, r.h))
                surf.fill(GOLD, (r.x, r.y, 3, r.h))
                help_text = row.get("help", "")
            put(surf, text(row["label"], 2, WHITE if hot else STEEL_L), r.x + 8, r.centery, "midleft")
            ctrl_box = pygame.Rect(r.right - 110, r.y, 106, r.h)
            if row["kind"] == "toggle":
                _toggle(surf, ctrl_box, bool(row["value"]), hot)
            elif row["kind"] == "cycle":
                _cycle(surf, ctrl_box, row["value"], hot)
            elif row["kind"] == "slider":
                _slider(surf, pygame.Rect(ctrl_box.x, ctrl_box.centery - 5, 70, 10), row["value"], hot, row.get("val_label"))

        if non_binds:
            div_y = PAD_COL.y + 24 + len(non_binds) * 24 + 4
            surf.fill(_a(SLATE, 160), (PAD_COL.x + 6, div_y, PAD_COL.w - 12, 1))
            pad_start_y = div_y + 4
        else:
            pad_start_y = PAD_COL.y + 24

        for i, (lbl, gl) in enumerate(pad_rows):
            y = pad_start_y + i * 20 + 8
            if y < PAD_COL.bottom - 8:
                put(surf, text(lbl, 2, STEEL_L), PAD_COL.x + 6, y, "midleft")
                put(surf, glyphs(gl, pad=True), PAD_COL.right - 8, y, "midright")
        if awaiting is not None:
            help_text = "PRESS THE NEW KEY · ESC CANCELS"
    else:
        n_rows = len(rows)
        for i, row in enumerate(rows):
            r = row_rect(i, False, n_rows)
            hot = i == sel
            if hot:
                y = ease(("srow", tabs[tab]), r.y)
                surf.fill(_a(SLATE, 255), (r.x, int(y), r.w, r.h))
                surf.fill(GOLD, (r.x, int(y), 3, r.h))
                help_text = row.get("help", "")
            put(surf, text(row["label"], 2, WHITE if hot else STEEL_L), r.x + 12, r.centery, "midleft")
            c = ctrl_rect(i, n_rows)
            k = row["kind"]
            if k == "slider":
                _slider(surf, slider_track(i, n_rows), row["value"], hot, row.get("val_label"))
            elif k == "toggle":
                _toggle(surf, c, bool(row["value"]), hot)
            elif k == "cycle":
                _cycle(surf, c, row["value"], hot)

    # footer: what the highlighted thing does, the keys, and Back
    if help_text:
        put(surf, text(help_text, 1, WHITE, bold=True), 18, 364)
    if controls:
        hints = [(["DPAD"] if pad else ["↑", "↓"], "SELECT"), (["A"] if pad else ["⏎"], "CHANGE/REBIND"),
                 (["B"] if pad else ["ESC"], "BACK")]
    else:
        hints = [(["DPAD"] if pad else ["↑", "↓"], "SELECT"), ([] if pad else ["←", "→"], "CHANGE"),
                 (["B"] if pad else ["ESC"], "BACK")]
        if pad:
            hints[1] = (["DPAD"], "CHANGE")
    hint_bar(surf, hints, 18, 385, pad=pad)
    bh = BACK.collidepoint(mouse)
    slab(surf, BACK, bh)
    put(surf, text("BACK", 2, WHITE if bh else STEEL_L, bold=True), BACK.x + 14, BACK.centery - 1, "midleft")
    return {"tabs": trs, "back": BACK}


def hit_row(pos, n, controls=False):
    for i in range(n):
        if row_rect(i, controls, n).collidepoint(pos):
            return i
    return None


# ==================================================================================== RESULTS
BRONZE = (185, 127, 86)
RES_PANEL = pygame.Rect(16, 66, 568, 270)
RES_ROW_H = 29


def results_buttons(labels):
    """Rects of the results screen's buttons (right-aligned along the bottom)."""
    out, x = [], 584
    for lbl in reversed(labels):
        w = text_w(lbl, 2, bold=True) + 30
        x -= w
        out.insert(0, pygame.Rect(x, 352, w, 34))
        x -= 8
    return out


def _pos_badge(pos):
    face, txt, lip = {1: (GOLD, INK, AMBER), 2: (STEEL_L, INK, STEEL), 3: (BRONZE, INK, (117, 83, 56))}.get(
        pos, (_a(NIGHT2, 255), WHITE, INK))
    s = pygame.Surface((34, 20), pygame.SRCALPHA)
    s.fill(CLEAR)
    s.blit(_box(34, 20, face, INK, lip=lip, lip_h=3), (0, 0))
    put(s, text(f"P{pos}", 2 if pos < 10 else 1, txt, bold=True, shadow=False), 17, 9, "center")
    return s


def _chip(label, face, fg=INK, lip=None):
    t = text(label, 1, fg, bold=True, shadow=False)
    s = pygame.Surface((t.get_width() + 8, 13), pygame.SRCALPHA)
    s.fill(CLEAR)
    s.blit(_box(s.get_width(), 13, face, INK, lip=lip or _shade(face), lip_h=2), (0, 0))
    s.blit(t, (4, 3))
    return s


def draw_results(surf, title, rows, t=10.0, sub=None, chip=None, footer=None, buttons=("MENU",),
                 sel=0, mouse=(-1, -1), pad=False, status_col=False):
    """The finish board.
    rows : finishing order, dicts with name, flag (Surface or None), gap (seconds behind the winner,
           0 for the winner, None if unknown), laps_down (whole laps behind: shows "+1 LAP"),
           best (best lap, s; 0 = none), out (eliminated),
           you (the player), fastest (holds the fastest lap of the race)
    t    : seconds since the board opened (rows slide in one after another)
    sub  : line under the title; chip: gold tag top right; footer: line bottom left
    status_col : battle / elimination: the GAP column becomes STATUS (WINNER / OUT)
    Returns the button rects."""
    W, H = surf.get_size()
    put(surf, text(title, 3, WHITE, bold=True), 16, 12)
    if sub:
        put(surf, text(sub, 1, STEEL_L, bold=True), 18, 44)
    if chip:
        c = _chip(chip, GOLD, lip=AMBER)
        put(surf, c, W - 16, 18, "topright")
    # a chequered strip along the top of the board
    for i in range(0, RES_PANEL.w - 4, 6):
        for j in range(2):
            surf.fill(WHITE if (i // 6 + j) % 2 == 0 else INK,
                      (RES_PANEL.x + 2 + i, RES_PANEL.y - 12 + j * 6, min(6, RES_PANEL.w - 4 - i), 6))
    panel(surf, RES_PANEL)

    x_pos, x_flag, x_name = RES_PANEL.x + 10, RES_PANEL.x + 52, RES_PANEL.x + 74
    x_gap, x_best = RES_PANEL.x + 420, RES_PANEL.right - 14
    hy = RES_PANEL.y + 10
    for lbl, x, anc in (("POS", x_pos, "topleft"), ("DRIVER", x_flag, "topleft"),
                        ("STATUS" if status_col else "GAP", x_gap, "topright"), ("BEST LAP", x_best, "topright")):
        put(surf, text(lbl, 1, STEEL, bold=True), x, hy, anc)
    surf.fill(_a(SLATE, 255), (RES_PANEL.x + 6, hy + 12, RES_PANEL.w - 12, 1))

    y0 = RES_PANEL.y + 28
    surf.set_clip(RES_PANEL.inflate(-4, -4))      # rows slide in from the right, inside the board
    for i, r in enumerate(rows[:8]):
        k = max(0.0, min(1.0, (t - 0.15 - i * 0.07) / 0.35))
        if k <= 0.0:
            continue
        dx = int((1 - k) ** 3 * 320)
        y = y0 + i * RES_ROW_H
        band = pygame.Rect(RES_PANEL.x + 6 + dx, y, RES_PANEL.w - 12, RES_ROW_H - 3)
        if r.get("you"):
            surf.fill(_a(SLATE, 255), band)
            surf.fill(RED, (band.x, band.y, 3, band.h))
        elif i % 2 == 0:
            surf.fill(_a(NIGHT2, 150), band)
        cy = band.centery
        surf.blit(_pos_badge(i + 1), (x_pos + dx, cy - 10))
        fl = r.get("flag")
        if fl is not None:
            fr = put(surf, fl, x_flag + dx, cy, "midleft")
            surf.fill(INK, (fr.x - 1, fr.y - 1, fr.w + 2, 1))
            surf.fill(INK, (fr.x - 1, fr.bottom, fr.w + 2, 1))
            surf.fill(INK, (fr.x - 1, fr.y, 1, fr.h))
            surf.fill(INK, (fr.right, fr.y, 1, fr.h))
        name_c = GOLD if r.get("you") else (STEEL if r.get("out") else WHITE)
        nr = put(surf, text(r["name"][:12], 2, name_c), x_name + dx, cy, "midleft")
        if r.get("you"):
            put(surf, _chip("YOU", RED, WHITE, WINE), nr.right + 6, cy, "midleft")
        # gap / status
        if r.get("out"):
            g = text("OUT", 2, RED)
        elif i == 0:
            g = text("WINNER", 2, GOLD, bold=True)
        elif status_col:
            g = text("SURVIVED", 2, STEEL_L)
        elif r.get("laps_down", 0) >= 1:
            n = r["laps_down"]
            g = text(f"+{n} LAP" + ("S" if n > 1 else ""), 2, STEEL_L)
        elif r.get("gap") is None:
            g = text("--", 2, STEEL)
        else:
            gs = r["gap"]
            g = text(f"+{int(gs // 60)}:{gs % 60:05.2f}" if gs >= 60 else f"+{gs:.2f}", 2, WHITE)
        put(surf, g, x_gap + dx, cy, "midright")
        # best lap; the race's fastest lap gets a cyan time and an FL tag
        best = r.get("best") or 0.0
        if best > 0:
            m, sec = int(best // 60), best - 60 * int(best // 60)
            bt = f"{m}:{sec:06.3f}" if m else f"{sec:.3f}"
        else:
            bt = "--.---"
        fast = r.get("fastest") and best > 0
        br = put(surf, text(bt, 2, CYAN if fast else (STEEL_L if best > 0 else STEEL)), x_best + dx, cy, "midright")
        if fast:
            put(surf, _chip("FL", CYAN, INK, BLUE), br.x - 6, cy, "midright")
    surf.set_clip(None)

    if footer:
        put(surf, text(footer, 1, WHITE, bold=True), 18, 357)
    hint_bar(surf, [(["DPAD"] if pad else ["←", "→"], "SELECT"), (["A"] if pad else ["⏎"], "OK")],
             18, 377, pad=pad)
    rects = results_buttons(list(buttons))
    for i, (lbl, r) in enumerate(zip(buttons, rects)):
        hot = i == sel or r.collidepoint(mouse)
        slab(surf, r, hot)
        put(surf, text(lbl, 2, WHITE if hot else STEEL_L, bold=True), r.x + 12, r.centery - 1, "midleft")
    return rects
