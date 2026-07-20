#!/usr/bin/env python3
"""Generates all JSON assets/data and PNG textures for the Swordsmith mod.

Pure stdlib (struct + zlib): no Pillow required. Idempotent — safe to re-run.
Usage: python3 tools/gen_assets.py [--montage OUTPUT.png]
"""
import json
import os
import struct
import sys
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(ROOT, "src", "main", "resources")
ASSETS = os.path.join(RES, "assets", "swordsmith")
DATA = os.path.join(RES, "data")


# --------------------------------------------------------------------------
# PNG writing
# --------------------------------------------------------------------------

def write_png(path, pixels):
    """pixels: list of rows, each row a list of (r, g, b, a) tuples."""
    h = len(pixels)
    w = len(pixels[0])
    raw = b"".join(
        b"\x00" + b"".join(struct.pack("4B", *px) for px in row)
        for row in pixels
    )

    def chunk(tag, data):
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 9))
           + chunk(b"IEND", b""))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(png)


def blank(w=16, h=16):
    return [[(0, 0, 0, 0)] * w for _ in range(h)]


def noise(x, y, seed, k):
    v = (x * 73856093) ^ (y * 19349663) ^ (seed * 83492791)
    return ((v >> 7) ^ (v >> 3)) % k


def clamp(v):
    return max(0, min(255, int(v)))


def shade(c, d):
    return (clamp(c[0] + d), clamp(c[1] + d), clamp(c[2] + d), 255)


def scale(pixels, factor):
    out = []
    for row in pixels:
        srow = []
        for px in row:
            srow.extend([px] * factor)
        for _ in range(factor):
            out.append(list(srow))
    return out


# --------------------------------------------------------------------------
# Item sprite pipeline
# --------------------------------------------------------------------------

def form_pass(px, prot=None):
    """Directional form lighting: silhouette pixels facing up/left get
    brighter, those facing down/right get darker — instant pixel-art depth."""
    def opaque(x, y):
        return 0 <= x < 16 and 0 <= y < 16 and px[y][x][3] > 0

    out = [row[:] for row in px]
    for y in range(16):
        for x in range(16):
            if px[y][x][3] == 0 or (prot and prot[y][x]):
                continue
            r, g, b, a = px[y][x]
            if not opaque(x + 1, y) or not opaque(x, y + 1):
                out[y][x] = (clamp(r * 0.62), clamp(g * 0.62), clamp(b * 0.62), a)
            elif not opaque(x - 1, y) or not opaque(x, y - 1):
                out[y][x] = (clamp(r * 1.18), clamp(g * 1.18), clamp(b * 1.18), a)
    return out


def sprite(grid, palette, protect="", checker=""):
    assert len(grid) == 16, "grid must have 16 rows, has %d" % len(grid)
    px = blank()
    prot = [[False] * 16 for _ in range(16)]
    for y, row in enumerate(grid):
        assert len(row) == 16, "row %d must have 16 chars, has %d: %r" % (y, len(row), row)
        for x, ch in enumerate(row):
            if ch == ".":
                continue
            c = palette[ch]
            if ch in checker and (x + y) % 2 == 0:
                px[y][x] = shade(c, 9)
            else:
                px[y][x] = (c[0], c[1], c[2], 255)
            if ch in protect:
                prot[y][x] = True
    return form_pass(px, prot)


# --------------------------------------------------------------------------
# Item sprites (16x16 grids; '.' = transparent)
# --------------------------------------------------------------------------

DOTS = "................"

BLADE = [
    DOTS,
    "..............e.",
    ".............eb.",
    "............ebd.",
    "...........ebd..",
    "..........ebd...",
    ".........ebd....",
    "........ebd.....",
    ".......ebd......",
    "......ebd.......",
    ".....ebd........",
    "....ebd.........",
    "...ebd..........",
    "..tt............",
    ".tt.............",
    DOTS,
]

CRACK_PIXELS = {(11, 5), (10, 6), (10, 7), (9, 8)}
CRACKED = [
    "".join("k" if (x, y) in CRACK_PIXELS else ch for x, ch in enumerate(row))
    for y, row in enumerate(BLADE)
]

PREFORM = [
    DOTS,
    DOTS,
    DOTS,
    "...........bd...",
    "..........bd....",
    ".........bd.....",
    "........bd......",
    ".......bd.......",
    "......bd........",
    ".....bd.........",
    "....bd..........",
    "...bd...........",
    "..bd............",
    DOTS,
    DOTS,
    DOTS,
]

BILLET = [
    DOTS,
    DOTS,
    DOTS,
    DOTS,
    DOTS,
    ".........hbd....",
    "........hbbd....",
    ".......hbbd.....",
    "......hbbd......",
    ".....hbbd.......",
    "....hbbd........",
    "....bbd.........",
    DOTS,
    DOTS,
    DOTS,
    DOTS,
]

BLOOM = [
    DOTS,
    DOTS,
    DOTS,
    "....rrgg........",
    "...rgggggr......",
    "..rggghgggr.....",
    ".rgghggggggr....",
    ".rggggghgggr....",
    ".rghgggggghr....",
    "..rggghggggr....",
    "..rggggghgr.....",
    "...rrgggrr......",
    ".....rrr........",
    DOTS,
    DOTS,
    DOTS,
]

GUARD = [
    DOTS,
    DOTS,
    DOTS,
    DOTS,
    DOTS,
    "......GGGG......",
    ".....GGGGGG.....",
    "..gGGGGhhGGGGg..",
    "..gGGGGhhGGGGg..",
    ".....GGGGGG.....",
    "......gggg......",
    DOTS,
    DOTS,
    DOTS,
    DOTS,
    DOTS,
]

GRIP = [
    DOTS,
    "......cccc......",
    "......HHHH......",
    "......hHHH......",
    "......HhHH......",
    "......HHhH......",
    "......HHHh......",
    "......hHHH......",
    "......HhHH......",
    "......HHhH......",
    "......HHHh......",
    "......hHHH......",
    "......HhHH......",
    "......HHHH......",
    "......cccc......",
    DOTS,
]

POMMEL = [
    DOTS,
    DOTS,
    DOTS,
    DOTS,
    DOTS,
    "......PPPP......",
    ".....PWWPPP.....",
    "....PPPkkPPP....",
    "....PPPkkPPP....",
    ".....PPPPPp.....",
    "......pppp......",
    DOTS,
    DOTS,
    DOTS,
    DOTS,
    DOTS,
]

HAMMER = [
    DOTS,
    ".........MMMMMM.",
    ".........MWMMMm.",
    ".........MMMMMm.",
    ".........mmmmmm.",
    ".........Hh.....",
    "........Hh......",
    ".......Hh.......",
    "......Hh........",
    ".....Hh.........",
    "....Hh..........",
    "...Hh...........",
    "..Hh............",
    DOTS,
    DOTS,
    DOTS,
]

BELLOWS = [
    DOTS,
    "..............m.",
    ".............m..",
    "...........BB...",
    "..........BLLB..",
    ".........BLLLB..",
    "........BLLLB...",
    ".......BLLLB....",
    "......BLLLB.....",
    ".....BLLLB......",
    "....BLLB........",
    "...BBBB.........",
    "...S.S..........",
    "..S.S...........",
    DOTS,
    DOTS,
]

SWORD = [
    DOTS,
    "..............e.",
    ".............eb.",
    "............ebd.",
    "...........ebd..",
    "..........ebd...",
    ".........ebd....",
    "....GG..ebd.....",
    ".....GGebd......",
    "......GG........",
    ".....HHGG.......",
    "....Hh..GG......",
    "...Hh...........",
    "..PP............",
    "..pp............",
    DOTS,
]


def tongs_pixels():
    """Tongs drawn procedurally: an X of two 2px arms crossing at a riveted
    pivot, jaws curling together upper-right, handles spread lower-left."""
    px = blank()
    steel = (126, 130, 140)

    def put(x, y, c=steel):
        if 0 <= x < 16 and 0 <= y < 16:
            px[y][x] = (c[0], c[1], c[2], 255)

    def seg(x0, y0, x1, y1):
        steps = max(abs(x1 - x0), abs(y1 - y0), 1)
        for i in range(steps + 1):
            x = round(x0 + (x1 - x0) * i / steps)
            y = round(y0 + (y1 - y0) * i / steps)
            put(x, y)
            put(x + 1, y)

    seg(7, 8, 12, 2)    # upper jaw arm
    seg(7, 8, 13, 5)    # lower jaw arm
    seg(7, 8, 2, 12)    # upper handle
    seg(7, 8, 4, 14)    # lower handle
    # The jaw tips curl toward each other around the work.
    put(14, 3)
    put(14, 4)
    rivet = (58, 60, 68)
    put(7, 8, rivet)
    put(8, 8, rivet)
    return form_pass(px)


STEEL = {"G": (162, 168, 182), "H": (139, 92, 50), "h": (100, 65, 34),
         "P": (174, 180, 192), "p": (114, 119, 130)}

ITEM_SPRITES = {
    "iron_bloom": {"grid": BLOOM, "palette": {"g": (142, 134, 124), "r": (124, 92, 66), "h": (56, 50, 44)},
                   "checker": "g"},
    "steel_billet": {"grid": BILLET, "palette": {"h": (206, 209, 216), "b": (141, 143, 150), "d": (84, 86, 93)},
                     "protect": "h", "checker": "b"},
    "blade_preform": {"grid": PREFORM, "palette": {"b": (154, 156, 162), "d": (92, 94, 101)},
                      "checker": "b"},
    "rough_blade": {"grid": BLADE, "palette": {"e": (196, 198, 204), "b": (142, 144, 150),
                                               "d": (84, 86, 94), "t": (70, 70, 76)},
                    "protect": "e", "checker": "b"},
    "cracked_blade": {"grid": CRACKED, "palette": {"e": (196, 198, 204), "b": (142, 144, 150),
                                                   "d": (84, 86, 94), "t": (70, 70, 76), "k": (26, 26, 30)},
                      "protect": "e", "checker": "b"},
    "quenched_blade": {"grid": BLADE, "palette": {"e": (168, 177, 196), "b": (109, 116, 136),
                                                  "d": (56, 60, 78), "t": (52, 52, 62)},
                       "protect": "e", "checker": "b"},
    "tempered_blade": {"grid": BLADE, "palette": {"e": (224, 206, 140), "b": (122, 133, 168),
                                                  "d": (64, 70, 102), "t": (52, 52, 62)},
                       "protect": "e", "checker": "b"},
    "sharp_blade": {"grid": BLADE, "palette": {"e": (248, 250, 253), "b": (203, 208, 219),
                                               "d": (112, 118, 136), "t": (70, 70, 76)},
                    "protect": "e", "checker": "b"},
    "sword_guard": {"grid": GUARD, "palette": {"G": (172, 178, 190), "g": (116, 122, 134), "h": (38, 40, 46)}},
    "sword_grip": {"grid": GRIP, "palette": {"c": (154, 160, 172), "H": (139, 92, 50), "h": (96, 62, 33)},
                   "checker": "H"},
    "sword_pommel": {"grid": POMMEL, "palette": {"P": (174, 180, 192), "W": (226, 230, 238),
                                                 "k": (43, 45, 51), "p": (114, 119, 130)},
                     "protect": "W"},
    "smithing_hammer": {"grid": HAMMER, "palette": {"M": (124, 128, 138), "W": (196, 200, 210),
                                                    "m": (76, 80, 90), "H": (139, 92, 50), "h": (100, 65, 34)},
                        "protect": "W"},
    "smithing_tongs": {"proc": tongs_pixels},
    "bellows": {"grid": BELLOWS, "palette": {"m": (144, 148, 156), "B": (112, 76, 42),
                                             "L": (200, 154, 100), "S": (100, 65, 34)},
                "checker": "L"},
    "forged_steel_sword": {"grid": SWORD,
                           "palette": dict(STEEL, **{"e": (248, 250, 253), "b": (205, 210, 221),
                                                     "d": (118, 124, 141)}),
                           "protect": "e", "checker": "b"},
}


def build_item(name):
    spec = ITEM_SPRITES[name]
    if "proc" in spec:
        return spec["proc"]()
    return sprite(spec["grid"], spec["palette"], spec.get("protect", ""), spec.get("checker", ""))


# --------------------------------------------------------------------------
# Block textures (procedural)
# --------------------------------------------------------------------------

def tex_stone(seed, base):
    px = blank()
    for y in range(16):
        for x in range(16):
            px[y][x] = shade(base, noise(x, y, seed, 17) - 8)
    return px


def tex_forge_side():
    base = (121, 116, 109)
    mortar = (86, 82, 76)
    px = blank()
    for y in range(16):
        for x in range(16):
            row = y // 4
            offset = 0 if row % 2 == 0 else 4
            if y % 4 == 3 or (x + offset) % 8 == 7:
                c = mortar
            else:
                c = base
            c = shade(c, noise(x, y, 11, 13) - 6)
            if y < 4:  # soot near the mouth
                c = (clamp(c[0] * 0.55), clamp(c[1] * 0.55), clamp(c[2] * 0.55), 255)
            px[y][x] = c
    return px


def tex_forge_top(lit):
    px = tex_stone(21, (121, 116, 109))
    for y in range(16):
        for x in range(16):
            if 2 <= x <= 13 and 2 <= y <= 13:
                if lit:
                    dx = x - 7.5
                    dy = y - 7.5
                    d = (dx * dx + dy * dy) ** 0.5
                    t = max(0.0, min(1.0, 1.0 - (d - 1.5) / 5.5))
                    r = 60 + t * 195
                    g = 28 + t * 172
                    b = 16 + t * 74
                    c = (clamp(r), clamp(g), clamp(b), 255)
                    if noise(x, y, 33, 19) == 0:
                        c = (255, 240, 180, 255)
                    elif noise(x, y, 37, 13) == 0 and t < 0.55:
                        c = (46, 36, 30, 255)  # charred coal poking through
                else:
                    c = shade((40, 35, 30), noise(x, y, 44, 15) - 7)
                    if noise(x, y, 55, 11) == 0:
                        c = (62, 52, 42, 255)
                px[y][x] = c
    return px


def tex_anvil_body():
    px = blank()
    for y in range(16):
        for x in range(16):
            c = shade((70, 71, 76), noise(x, y, 66, 11) - 5)
            if x in (0, 15) or y in (0, 15):
                c = shade((55, 56, 60), noise(x, y, 67, 7) - 3)
            if y > 11:
                c = shade((c[0] - 8, c[1] - 8, c[2] - 8), 0)
            px[y][x] = c
    return px


def tex_anvil_top():
    px = blank()
    for y in range(16):
        for x in range(16):
            if x in (0, 15) or y in (0, 15):
                c = shade((52, 53, 57), noise(x, y, 71, 7) - 3)
            elif 3 <= x <= 12 and 3 <= y <= 12:
                c = shade((104, 105, 112), noise(x, y, 72, 11) - 5)
            else:
                c = shade((86, 87, 93), noise(x, y, 73, 11) - 5)
            px[y][x] = c
    # A working anvil has a square hardy hole and a round pritchel hole...
    for hx, hy in ((11, 6), (12, 6), (11, 7), (12, 7)):
        px[hy][hx] = (38, 39, 43, 255)
    px[7][3] = (44, 45, 49, 255)
    # ...and years of hammer scars.
    for sx, sy in ((5, 5), (6, 9), (8, 4), (9, 10), (4, 8), (7, 7)):
        px[sy][sx] = shade((122, 123, 130), noise(sx, sy, 74, 9) - 4)
    return px


def tex_planks(seed, base, seam, vertical):
    px = blank()
    for y in range(16):
        for x in range(16):
            k = x if vertical else y
            c = seam if k % 4 == 3 else base
            c = shade(c, noise(x, y, seed, 15) - 7)
            px[y][x] = c
    return px


def tex_barrel_side():
    px = tex_planks(81, (122, 84, 48), (86, 58, 32), vertical=True)
    for y in (2, 3, 12, 13):
        for x in range(16):
            c = (118, 122, 128) if y in (2, 12) else (92, 96, 102)
            if x % 5 == 2 and y in (2, 12):
                c = (152, 156, 162)
            px[y][x] = (c[0], c[1], c[2], 255)
    return px


def tex_barrel_top(water):
    px = tex_planks(82, (122, 84, 48), (86, 58, 32), vertical=False)
    for y in range(16):
        for x in range(16):
            if 2 <= x <= 13 and 2 <= y <= 13:
                if water:
                    c = shade((63, 118, 228), noise(x, y, 83, 13) - 6)
                    if (x + y) % 5 == 0:
                        c = (90, 142, 240, 255)
                    if noise(x, y, 84, 23) == 0:
                        c = (165, 205, 255, 255)
                else:
                    c = shade((44, 33, 22), noise(x, y, 85, 11) - 5)
                px[y][x] = c
    return px


def tex_whetstone_wheel():
    px = blank()
    cx, cy, rx, ry = 7.5, 5.5, 6.0, 5.0
    for y in range(16):
        for x in range(16):
            dx = (x - cx) / rx
            dy = (y - cy) / ry
            d = dx * dx + dy * dy
            if d > 1.0:
                continue
            if d > 0.68:
                c = shade((106, 106, 100), noise(x, y, 91, 9) - 4)
            elif abs(x - 8) <= 1 and abs(y - 6) <= 1:
                c = (74, 58, 38, 255)
            else:
                c = shade((142, 142, 134), noise(x, y, 92, 13) - 6)
            px[y][x] = c
    return px


BLOCK_TEXTURES = {
    "forge_side": tex_forge_side,
    "forge_top_lit": lambda: tex_forge_top(True),
    "forge_top_off": lambda: tex_forge_top(False),
    "forge_bottom": lambda: tex_stone(12, (108, 104, 99)),
    "anvil_body": tex_anvil_body,
    "anvil_top": tex_anvil_top,
    "quenching_barrel_side": tex_barrel_side,
    "quenching_barrel_top_water": lambda: tex_barrel_top(True),
    "quenching_barrel_top_empty": lambda: tex_barrel_top(False),
    "quenching_barrel_bottom": lambda: tex_planks(86, (104, 72, 40), (76, 52, 28), vertical=False),
    "whetstone_base": lambda: tex_planks(87, (110, 78, 46), (80, 56, 32), vertical=False),
    "whetstone_rim": lambda: tex_stone(93, (122, 122, 116)),
    "whetstone_wheel": tex_whetstone_wheel,
}


# --------------------------------------------------------------------------
# Forge GUI texture (vanilla-styled panel, 256x256)
# --------------------------------------------------------------------------

GUI_BG = (198, 198, 198, 255)
GUI_WHITE = (255, 255, 255, 255)
GUI_SHADOW = (85, 85, 85, 255)
GUI_BLACK = (0, 0, 0, 255)
SLOT_BG = (139, 139, 139, 255)
SLOT_DARK = (55, 55, 55, 255)


def rect(px, x0, y0, w, h, c):
    for y in range(y0, y0 + h):
        for x in range(x0, x0 + w):
            px[y][x] = c


def gui_panel(px, x0, y0, w, h):
    """Classic dialog: black outline, white top-left bevel, dark bottom-right."""
    rect(px, x0, y0, w, h, GUI_BG)
    for x in range(x0 + 1, x0 + w - 1):
        px[y0][x] = GUI_BLACK
        px[y0 + h - 1][x] = GUI_BLACK
    for y in range(y0 + 1, y0 + h - 1):
        px[y][x0] = GUI_BLACK
        px[y][x0 + w - 1] = GUI_BLACK
    for x in range(x0 + 1, x0 + w - 2):
        px[y0 + 1][x] = GUI_WHITE
        px[y0 + h - 2][x] = GUI_SHADOW
    for y in range(y0 + 1, y0 + h - 2):
        px[y][x0 + 1] = GUI_WHITE
        px[y][x0 + w - 2] = GUI_SHADOW
    px[y0 + 1][x0 + w - 2] = GUI_BG
    px[y0 + h - 2][x0 + 1] = GUI_BG
    for cx, cy in ((x0, y0), (x0 + w - 1, y0), (x0, y0 + h - 1), (x0 + w - 1, y0 + h - 1)):
        px[cy][cx] = (0, 0, 0, 0)


def gui_inset(px, x0, y0, w, h, fill=SLOT_BG):
    """Recessed area: dark top-left, white bottom-right (slot look)."""
    rect(px, x0, y0, w, h, fill)
    for x in range(x0, x0 + w - 1):
        px[y0][x] = SLOT_DARK
    for y in range(y0, y0 + h - 1):
        px[y][x0] = SLOT_DARK
    for x in range(x0 + 1, x0 + w):
        px[y0 + h - 1][x] = GUI_WHITE
    for y in range(y0 + 1, y0 + h):
        px[y][x0 + w - 1] = GUI_WHITE
    px[y0][x0 + w - 1] = fill
    px[y0 + h - 1][x0] = fill


GUI_FLAME = [
    "......f......",
    "......f......",
    ".....fff.....",
    ".....fff.....",
    "....fffff....",
    "....fffff....",
    "...fffffff...",
    "...ffyyyff...",
    "..ffyyyyyff..",
    "..fyyywyyyf..",
    "..fyywwwyyf..",
    "...fywwwyf...",
    "....fffff....",
]


def draw_flame(px, ox, oy, silhouette):
    lit = {"f": (255, 138, 20, 255), "y": (255, 200, 40, 255), "w": (255, 240, 160, 255)}
    for y, row in enumerate(GUI_FLAME):
        assert len(row) == 13
        for x, ch in enumerate(row):
            if ch == ".":
                continue
            px[oy + y][ox + x] = (118, 118, 118, 255) if silhouette else lit[ch]


def draw_arrow(px, ox, oy, silhouette):
    color = (118, 118, 118, 255) if silhouette else (232, 232, 232, 255)
    for x in range(0, 15):
        for y in range(4, 9):
            px[oy + y][ox + x] = color
    for c in range(14, 22):
        half = round((21 - c) * 6 / 7)
        for y in range(6 - half, 6 + half + 1):
            px[oy + y][ox + c] = color


def gauge_y(temp):
    return 70 - round(54 * (temp - 20) / 1280.0)


def tex_gui_forge():
    px = blank(256, 256)
    gui_panel(px, 0, 0, 176, 166)

    # Slots: workpiece, fuel, player inventory, hotbar.
    gui_inset(px, 79, 34, 18, 18)
    gui_inset(px, 27, 52, 18, 18)
    for row in range(3):
        for col in range(9):
            gui_inset(px, 7 + col * 18, 83 + row * 18, 18, 18)
    for col in range(9):
        gui_inset(px, 7 + col * 18, 141, 18, 18)

    # Thermometer housing with graduations and colored zone ticks.
    gui_inset(px, 147, 13, 13, 59, fill=(30, 30, 34, 255))
    for gy in (26, 39, 52, 65):
        for gx in range(149, 158):
            px[gy][gx] = (48, 48, 54, 255)
    zones = [
        (gauge_y(400), gauge_y(150), (111, 168, 220, 255)),   # temper band
        (gauge_y(720) - 1, gauge_y(720) + 1, (230, 145, 56, 255)),  # forging line
        (gauge_y(950), gauge_y(780), (204, 65, 37, 255)),     # quench band
        (gauge_y(1150) - 1, gauge_y(1150) + 1, (255, 217, 102, 255)),  # smelt line
    ]
    for y0, y1, color in zones:
        for y in range(min(y0, y1), max(y0, y1) + 1):
            px[y][161] = color
            px[y][162] = color

    # Fuel flame silhouette and bellows blast channel.
    draw_flame(px, 28, 35, silhouette=True)
    gui_inset(px, 48, 57, 26, 7, fill=(30, 30, 34, 255))

    # Progress arrow silhouette.
    draw_arrow(px, 103, 36, silhouette=True)

    # Ghost icons: a faint blade in the workpiece slot, coal in the fuel slot.
    for i in range(10):
        px[38 + i][91 - i] = (122, 122, 122, 255)
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            if dx * dx + dy * dy <= 5:
                px[60 + dy][35 + dx] = (117, 117, 117, 255)

    # Sprite region: lit flame, blast fill, lit arrow.
    draw_flame(px, 176, 0, silhouette=False)
    for x in range(24):
        k = x / 23.0
        c = (clamp(156 + k * 68), clamp(199 + k * 41), 255, 255)
        for y in range(5):
            px[16 + y][176 + x] = c
    draw_arrow(px, 176, 24, silhouette=False)
    return px


# --------------------------------------------------------------------------
# JSON assets
# --------------------------------------------------------------------------

def J(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent="\t", ensure_ascii=False)
        f.write("\n")


def gen_blockstates():
    bs = os.path.join(ASSETS, "blockstates")
    J(os.path.join(bs, "forge.json"), {"variants": {
        "lit=false": {"model": "swordsmith:block/forge"},
        "lit=true": {"model": "swordsmith:block/forge_lit"},
    }})
    J(os.path.join(bs, "quenching_barrel.json"), {"variants": {
        "filled=false": {"model": "swordsmith:block/quenching_barrel_empty"},
        "filled=true": {"model": "swordsmith:block/quenching_barrel_filled"},
    }})
    for name, model in (("smithing_anvil", "swordsmith:block/smithing_anvil"),
                        ("whetstone", "swordsmith:block/whetstone")):
        J(os.path.join(bs, name + ".json"), {"variants": {
            "facing=north": {"model": model},
            "facing=east": {"model": model, "y": 90},
            "facing=south": {"model": model, "y": 180},
            "facing=west": {"model": model, "y": 270},
        }})


def gen_block_models():
    mb = os.path.join(ASSETS, "models", "block")
    J(os.path.join(mb, "forge.json"), {"parent": "minecraft:block/cube_bottom_top", "textures": {
        "top": "swordsmith:block/forge_top_off",
        "side": "swordsmith:block/forge_side",
        "bottom": "swordsmith:block/forge_bottom",
    }})
    J(os.path.join(mb, "forge_lit.json"), {"parent": "minecraft:block/cube_bottom_top", "textures": {
        "top": "swordsmith:block/forge_top_lit",
        "side": "swordsmith:block/forge_side",
        "bottom": "swordsmith:block/forge_bottom",
    }})
    J(os.path.join(mb, "smithing_anvil.json"), {"parent": "minecraft:block/template_anvil", "textures": {
        "particle": "swordsmith:block/anvil_body",
        "body": "swordsmith:block/anvil_body",
        "top": "swordsmith:block/anvil_top",
    }})
    for suffix, top in (("empty", "swordsmith:block/quenching_barrel_top_empty"),
                        ("filled", "swordsmith:block/quenching_barrel_top_water")):
        J(os.path.join(mb, "quenching_barrel_%s.json" % suffix), {
            "parent": "minecraft:block/cube_bottom_top",
            "textures": {
                "top": top,
                "side": "swordsmith:block/quenching_barrel_side",
                "bottom": "swordsmith:block/quenching_barrel_bottom",
            }})
    J(os.path.join(mb, "whetstone.json"), {
        "parent": "minecraft:block/block",
        "textures": {
            "particle": "swordsmith:block/whetstone_rim",
            "base": "swordsmith:block/whetstone_base",
            "wheel": "swordsmith:block/whetstone_wheel",
            "rim": "swordsmith:block/whetstone_rim",
        },
        "elements": [
            {
                "from": [0, 0, 0], "to": [16, 7, 16],
                "faces": {
                    "down": {"texture": "#base", "cullface": "down"},
                    "up": {"texture": "#base"},
                    "north": {"texture": "#base", "cullface": "north"},
                    "south": {"texture": "#base", "cullface": "south"},
                    "west": {"texture": "#base", "cullface": "west"},
                    "east": {"texture": "#base", "cullface": "east"},
                },
            },
            {
                "from": [6, 5, 2], "to": [10, 15, 14],
                "faces": {
                    "up": {"texture": "#rim"},
                    "down": {"texture": "#rim"},
                    "north": {"texture": "#rim"},
                    "south": {"texture": "#rim"},
                    "west": {"texture": "#wheel", "uv": [2, 1, 14, 11]},
                    "east": {"texture": "#wheel", "uv": [2, 1, 14, 11]},
                },
            },
        ],
    })


def gen_item_models():
    mi = os.path.join(ASSETS, "models", "item")
    handheld = {"smithing_hammer", "forged_steel_sword"}
    for name in ITEM_SPRITES:
        J(os.path.join(mi, name + ".json"), {
            "parent": "minecraft:item/handheld" if name in handheld else "minecraft:item/generated",
            "textures": {"layer0": "swordsmith:item/" + name},
        })
    J(os.path.join(mi, "forge.json"), {"parent": "swordsmith:block/forge"})
    J(os.path.join(mi, "smithing_anvil.json"), {"parent": "swordsmith:block/smithing_anvil"})
    J(os.path.join(mi, "quenching_barrel.json"), {"parent": "swordsmith:block/quenching_barrel_empty"})
    J(os.path.join(mi, "whetstone.json"), {"parent": "swordsmith:block/whetstone"})


def gen_recipes():
    rd = os.path.join(DATA, "swordsmith", "recipe")

    def shaped(name, pattern, key, result, count=1, category="misc"):
        J(os.path.join(rd, name + ".json"), {
            "type": "minecraft:crafting_shaped",
            "category": category,
            "pattern": pattern,
            "key": key,
            "result": {"id": result, "count": count},
        })

    iron = {"item": "minecraft:iron_ingot"}
    nugget = {"item": "minecraft:iron_nugget"}
    stick = {"item": "minecraft:stick"}
    planks = {"tag": "minecraft:planks"}
    leather = {"item": "minecraft:leather"}

    shaped("smithing_hammer", ["II", "IS", " S"], {"I": iron, "S": stick},
           "swordsmith:smithing_hammer", category="equipment")
    shaped("smithing_tongs", ["I I", " I ", "S S"], {"I": iron, "S": stick},
           "swordsmith:smithing_tongs", category="equipment")
    shaped("bellows", ["PPP", "LLL", "PPP"], {"P": planks, "L": leather},
           "swordsmith:bellows", category="equipment")
    shaped("forge", ["SSS", "S S", "SSS"], {"S": {"item": "minecraft:stone_bricks"}},
           "swordsmith:forge", category="building")
    shaped("smithing_anvil", ["III", " I ", "III"], {"I": iron},
           "swordsmith:smithing_anvil", category="building")
    shaped("quenching_barrel", ["P P", "P P", "PPP"], {"P": planks},
           "swordsmith:quenching_barrel", category="building")
    shaped("whetstone", ["CC", "PP"], {"C": {"item": "minecraft:smooth_stone"}, "P": planks},
           "swordsmith:whetstone", category="building")
    shaped("sword_guard", ["NIN"], {"N": nugget, "I": iron}, "swordsmith:sword_guard")
    shaped("sword_grip", ["L", "S", "L"], {"L": leather, "S": stick}, "swordsmith:sword_grip")
    J(os.path.join(rd, "sword_pommel.json"), {
        "type": "minecraft:crafting_shapeless",
        "category": "misc",
        "ingredients": [iron, nugget],
        "result": {"id": "swordsmith:sword_pommel", "count": 1},
    })


def gen_loot_tables():
    ld = os.path.join(DATA, "swordsmith", "loot_table", "blocks")
    for name in ("forge", "smithing_anvil", "quenching_barrel", "whetstone"):
        J(os.path.join(ld, name + ".json"), {
            "type": "minecraft:block",
            "pools": [{
                "rolls": 1.0,
                "bonus_rolls": 0.0,
                "entries": [{"type": "minecraft:item", "name": "swordsmith:" + name}],
                "conditions": [{"condition": "minecraft:survives_explosion"}],
            }],
            "random_sequence": "swordsmith:blocks/" + name,
        })


def gen_tags():
    td = os.path.join(DATA, "minecraft", "tags", "block", "mineable")
    J(os.path.join(td, "pickaxe.json"), {"replace": False, "values": [
        "swordsmith:forge", "swordsmith:smithing_anvil", "swordsmith:whetstone"]})
    J(os.path.join(td, "axe.json"), {"replace": False, "values": [
        "swordsmith:quenching_barrel"]})


def gen_advancements():
    ad = os.path.join(DATA, "swordsmith", "advancement", "smithing")

    def adv(name, icon, parent, frame="task", hidden=False, background=None,
            announce=True, toast=True):
        display = {
            "icon": {"id": icon},
            "title": {"translate": "advancement.swordsmith.%s.title" % name},
            "description": {"translate": "advancement.swordsmith.%s.desc" % name},
            "frame": frame,
            "show_toast": toast,
            "announce_to_chat": announce,
            "hidden": hidden,
        }
        if background:
            display["background"] = background
        obj = {
            "display": display,
            "criteria": {"has_item": {
                "trigger": "minecraft:inventory_changed",
                "conditions": {"items": [{"items": [icon]}]},
            }},
        }
        if parent:
            obj["parent"] = "swordsmith:smithing/" + parent
        J(os.path.join(ad, name + ".json"), obj)

    adv("root", "swordsmith:smithing_hammer", None,
        background="minecraft:textures/gui/advancements/backgrounds/stone.png",
        announce=False, toast=False)
    adv("iron_bloom", "swordsmith:iron_bloom", "root", frame="goal")
    adv("steel_billet", "swordsmith:steel_billet", "iron_bloom")
    adv("rough_blade", "swordsmith:rough_blade", "steel_billet")
    adv("cracked_blade", "swordsmith:cracked_blade", "rough_blade", hidden=True)
    adv("quenched_blade", "swordsmith:quenched_blade", "rough_blade", frame="goal")
    adv("tempered_blade", "swordsmith:tempered_blade", "quenched_blade")
    adv("sharp_blade", "swordsmith:sharp_blade", "tempered_blade")
    adv("forged_steel_sword", "swordsmith:forged_steel_sword", "sharp_blade", frame="challenge")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def gen_textures():
    for name in ITEM_SPRITES:
        write_png(os.path.join(ASSETS, "textures", "item", name + ".png"), build_item(name))
    for name, fn in BLOCK_TEXTURES.items():
        write_png(os.path.join(ASSETS, "textures", "block", name + ".png"), fn())
    write_png(os.path.join(ASSETS, "textures", "gui", "forge.png"), tex_gui_forge())
    # Mod icon: the sword, scaled up.
    write_png(os.path.join(ASSETS, "icon.png"), scale(build_item("forged_steel_sword"), 8))


def gen_montage(path):
    names = list(ITEM_SPRITES.keys())
    blocks = list(BLOCK_TEXTURES.keys())
    cols = 5
    cell = 18
    rows_items = (len(names) + cols - 1) // cols
    rows_blocks = (len(blocks) + cols - 1) // cols
    w = cols * cell + 2
    h = (rows_items + rows_blocks) * cell + 6
    bg = (42, 42, 48, 255)
    canvas = [[bg] * w for _ in range(h)]

    def paste(px, ox, oy):
        for y in range(16):
            for x in range(16):
                p = px[y][x]
                if p[3] > 0:
                    canvas[oy + y][ox + x] = p

    for i, name in enumerate(names):
        paste(build_item(name), 2 + (i % cols) * cell, 2 + (i // cols) * cell)
    yoff = rows_items * cell + 6
    for i, name in enumerate(blocks):
        paste(BLOCK_TEXTURES[name](), 2 + (i % cols) * cell, yoff + (i // cols) * cell)
    write_png(path, scale(canvas, 6))


def main():
    gen_blockstates()
    gen_block_models()
    gen_item_models()
    gen_recipes()
    gen_loot_tables()
    gen_tags()
    gen_advancements()
    gen_textures()
    if "--montage" in sys.argv:
        gen_montage(sys.argv[sys.argv.index("--montage") + 1])
    if "--gui-preview" in sys.argv:
        gui = tex_gui_forge()
        crop = [row[:176] for row in gui[:166]]
        write_png(sys.argv[sys.argv.index("--gui-preview") + 1], scale(crop, 3))
    print("assets generated OK")


if __name__ == "__main__":
    main()
