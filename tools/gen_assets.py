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


def from_grid(grid, palette):
    assert len(grid) == 16, "grid must have 16 rows, has %d" % len(grid)
    px = blank()
    for y, row in enumerate(grid):
        assert len(row) == 16, "row %d must have 16 chars, has %d: %r" % (y, len(row), row)
        for x, ch in enumerate(row):
            if ch == ".":
                continue
            c = palette[ch]
            px[y][x] = (c[0], c[1], c[2], 255)
    return px


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

TONGS = [
    DOTS,
    DOTS,
    DOTS,
    "............TT..",
    "...........T.T..",
    "..........T.T...",
    ".........T.T....",
    "........T.T.....",
    ".......TRT......",
    "......T.T.......",
    ".....T.T........",
    "....T.T.........",
    "...T.T..........",
    "....T...........",
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

STEEL = {"G": (158, 164, 178), "H": (133, 88, 48), "h": (96, 62, 33),
         "P": (170, 176, 188), "p": (112, 117, 128)}

ITEM_SPRITES = {
    "iron_bloom": (BLOOM, {"g": (140, 132, 122), "r": (122, 90, 64), "h": (58, 52, 46)}),
    "steel_billet": (BILLET, {"h": (200, 203, 210), "b": (139, 141, 148), "d": (88, 90, 97)}),
    "blade_preform": (PREFORM, {"b": (150, 152, 158), "d": (96, 98, 105)}),
    "rough_blade": (BLADE, {"e": (184, 186, 192), "b": (142, 144, 150), "d": (93, 95, 102), "t": (74, 74, 80)}),
    "cracked_blade": (CRACKED, {"e": (184, 186, 192), "b": (142, 144, 150), "d": (93, 95, 102),
                                "t": (74, 74, 80), "k": (28, 28, 32)}),
    "quenched_blade": (BLADE, {"e": (154, 163, 181), "b": (109, 116, 136), "d": (63, 67, 86), "t": (58, 58, 68)}),
    "tempered_blade": (BLADE, {"e": (217, 201, 143), "b": (125, 136, 168), "d": (74, 80, 112), "t": (58, 58, 68)}),
    "sharp_blade": (BLADE, {"e": (244, 246, 250), "b": (201, 206, 217), "d": (122, 128, 145), "t": (74, 74, 80)}),
    "sword_guard": (GUARD, {"G": (168, 174, 186), "g": (112, 118, 130), "h": (40, 42, 48)}),
    "sword_grip": (GRIP, {"c": (150, 156, 168), "H": (133, 88, 48), "h": (92, 60, 32)}),
    "sword_pommel": (POMMEL, {"P": (170, 176, 188), "W": (220, 224, 232), "k": (45, 47, 53), "p": (112, 117, 128)}),
    "smithing_hammer": (HAMMER, {"M": (120, 124, 134), "W": (190, 194, 204), "m": (78, 82, 92),
                                 "H": (133, 88, 48), "h": (96, 62, 33)}),
    "smithing_tongs": (TONGS, {"T": (120, 124, 134), "R": (70, 73, 82)}),
    "bellows": (BELLOWS, {"m": (140, 144, 152), "B": (110, 74, 40), "L": (196, 150, 96), "S": (96, 62, 33)}),
    "forged_steel_sword": (SWORD, dict(STEEL, **{"e": (244, 246, 250), "b": (203, 208, 219), "d": (124, 130, 147)})),
}


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


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def gen_textures():
    for name, (grid, palette) in ITEM_SPRITES.items():
        write_png(os.path.join(ASSETS, "textures", "item", name + ".png"), from_grid(grid, palette))
    for name, fn in BLOCK_TEXTURES.items():
        write_png(os.path.join(ASSETS, "textures", "block", name + ".png"), fn())
    # Mod icon: the sword, scaled up.
    sword = from_grid(*ITEM_SPRITES["forged_steel_sword"])
    write_png(os.path.join(ASSETS, "icon.png"), scale(sword, 8))


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
        paste(from_grid(*ITEM_SPRITES[name]), 2 + (i % cols) * cell, 2 + (i // cols) * cell)
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
    gen_textures()
    if "--montage" in sys.argv:
        gen_montage(sys.argv[sys.argv.index("--montage") + 1])
    print("assets generated OK")


if __name__ == "__main__":
    main()
