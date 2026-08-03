#!/usr/bin/env python3
"""Worked example: an elaborate fennec fox mob, model + texture from code.

Demonstrates every core technique of the skill in one small mob:
  * quadruped archetype blocked out from anatomy-patterns numbers
  * secondary masses EMBEDDED into the body (head, chest fluff, thighs)
  * tertiary detail: tiered snout taper, brow via texture, paw shading
  * segment_chain tail with per-segment bend + taper
  * zero-thickness planes (cheek fur) with alpha-serrated edges
  * bone-rotation micro-tilts on the signature ears
  * mirror UV sharing (left limbs reuse right-limb texture)
  * palette with hue-shifted shades, counter-shading, AO, seeded noise
  * all UV rects taken from uv_map() — never hardcoded

Run:  python3 build_fennec.py          (writes fennec.geo.json + fennec.png)
Then: python3 ../../scripts/validate_geo.py fennec.geo.json --texture fennec.png
      python3 ../../scripts/render_geo.py fennec.geo.json --texture fennec.png \
              -o fennec_preview.png --scale 10
"""
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
from geo_builder import Model, segment_chain  # noqa: E402

from PIL import Image  # noqa: E402

OUT = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- 1. MODEL
# Fennec: small desert fox. Wolf-calibration quadruped scaled down
# (vanilla-calibration.md), total height ~14 units + ears ≈ 0.85 block.

m = Model("geometry.fennec", texture_size=(64, 64))
m.bone("root", pivot=(0, 0, 0))

body = m.bone("body", parent="root", pivot=(0, 7, 2))
body.cube(origin=(-3, 4, -4), size=(6, 5, 9))                 # primary mass
# chest fluff: embedded, hangs 1 below and pokes 1.5 ahead of the body
body.cube(origin=(-2.5, 3, -5.5), size=(5, 3, 3), inflate=0.25)

head = m.bone("head", parent="body", pivot=(0, 7, -4))        # pivot = neck base
head.cube(origin=(-2.5, 6, -8), size=(5, 4, 4))               # embeds 0 z? -8..-4
head.cube(origin=(-1.5, 6.5, -10), size=(3, 2, 2))            # snout tier
# cheek fur: zero-thickness planes, angled out, alpha-serrated in texture
head.plane(origin=(-3.5, 6, -7.5), size=(0, 2, 3),
           rotation=(0, 12, 0), pivot=(-2.5, 7, -6))
head.plane(origin=(3.5, 6, -7.5), size=(0, 2, 3),
           rotation=(0, -12, 0), pivot=(2.5, 7, -6))

# signature giant ears: own bones (they animate), micro-tilted outward
ear_r = m.bone("ear_right", parent="head", pivot=(-1.5, 10, -5.5),
               rotation=(0, 0, 12))
ear_r.cube(origin=(-3, 9.5, -6), size=(3, 5, 1))
ear_l = m.bone("ear_left", parent="head", pivot=(1.5, 10, -5.5),
               rotation=(0, 0, -12))

# legs: right side first, then pack UVs, then mirror-share onto left side.
# Pivot |x| = 2.25 puts the outer leg face 0.25 OUTSIDE the body side plane
# (x=±3) — flush faces would z-fight (validate_geo would flag it).
def leg(name, px, pz):
    b = m.bone(name, parent="root", pivot=(px, 5, pz))
    b.cube(origin=(px - 1, 0, pz - 1), size=(2, 5, 2))
    return b

leg_fr = leg("leg_front_right", -2.25, -2.5)
leg_br = leg("leg_back_right", -2.25, 3)
# haunch on the back leg (secondary mass, offset 0.4 off the body side)
leg_br.cube(origin=(-3.4, 3, 1.4), size=(2, 4, 4))

m.pack_uv()   # resolve UVs now so left parts can pin-share the right rects

ear_l.cube(origin=(0, 9.5, -6), size=(3, 5, 1),
           uv=ear_r.cubes[0].uv, mirror=True)
for src, name, px, pz in ((leg_fr, "leg_front_left", 2.25, -2.5),
                          (leg_br, "leg_back_left", 2.25, 3)):
    b = m.bone(name, parent="root", pivot=(px, 5, pz))
    b.cube(origin=(px - 1, 0, pz - 1), size=(2, 5, 2),
           uv=src.cubes[0].uv, mirror=True)
# mirrored haunch for the left back leg
m["leg_back_left"].cube(origin=(1.4, 3, 1.4), size=(2, 4, 4),
                        uv=leg_br.cubes[1].uv, mirror=True)

# tail: 3-segment chain curling upward. Sub-unit taper via inflate_step
# keeps every size integer (fractional sizes smear box UV).
segment_chain(m, "tail", m["body"], start=(0, 7.5, 5),
              direction=(0, 0, 1), seg_size=(3, 3, 3), count=3,
              bend_deg=(-14, 0, 0), inflate_step=-0.25)

geo_path = os.path.join(OUT, "fennec.geo.json")
m.save(geo_path)
print(m.stats())

# -------------------------------------------------------------- 2. TEXTURE
# Palette: sand fur, 5 steps, shadows hue-shifted toward red-brown,
# highlight toward yellow (texturing.md). Accents: cream, dark rim, eyes.
BASE = (227, 203, 164, 255)
LIGHT = (242, 224, 191, 255)
SHAD = (198, 168, 128, 255)
DARK = (156, 124, 91, 255)
CREAM = (247, 240, 224, 255)
CREAM_SH = (229, 216, 191, 255)
RIM = (94, 71, 51, 255)        # ear rims, tail tip
NOSE = (43, 35, 32, 255)
EYE = (36, 29, 24, 255)

img = Image.new("RGBA", m.texture_size, (0, 0, 0, 0))
px = img.load()
rng = random.Random(11)         # seeded => deterministic texture

uv = m.uv_map()                 # {bone: [ {face: (x,y,w,h)} per cube ]}


def fill(rect, color):
    x, y, w, h = rect
    for j in range(y, y + h):
        for i in range(x, x + w):
            px[i, j] = color


def noise(rect, colors, density):
    x, y, w, h = rect
    for j in range(y, y + h):
        for i in range(x, x + w):
            if rng.random() < density:
                px[i, j] = rng.choice(colors)


def bottom_rows(rect, n, color):
    x, y, w, h = rect
    for j in range(max(y, y + h - n), y + h):
        for i in range(x, x + w):
            px[i, j] = color


def fur(cube_faces, base=BASE, belly=CREAM):
    """Standard fur treatment: counter-shaded, noisy, AO-free (engine shades)."""
    for f, r in cube_faces.items():
        if f == "down":
            fill(r, belly)
            noise(r, [CREAM_SH], 0.15)
        elif f == "up":
            fill(r, base)
            noise(r, [SHAD, DARK], 0.22)      # back stripe scatter
        else:
            fill(r, base)
            noise(r, [SHAD], 0.12)
            noise(r, [LIGHT], 0.05)


# body ------------------------------------------------------------------
fur(uv["body"][0])
for f, r in uv["body"][1].items():            # chest fluff: cream all over
    fill(r, CREAM)
    noise(r, [CREAM_SH], 0.2)

# head ------------------------------------------------------------------
faces = uv["head"][0]
fur(faces, belly=CREAM)
n = faces["north"]                            # the face (5x4)
fill(n, BASE)
x, y, w, h = n
for i in range(w):                            # cream muzzle-side cheeks
    px[x + i, y + h - 1] = CREAM
px[x + 1, y + 1] = EYE; px[x + 1, y + 2] = EYE          # eyes 1x2, wide-set
px[x + 3, y + 1] = EYE; px[x + 3, y + 2] = EYE
px[x + 1, y] = DARK; px[x + 3, y] = DARK                # brow shadow px
# snout tier
sn = uv["head"][1]
fur(sn, belly=CREAM)
ns = sn["north"]                              # snout tip (3x2)
fill(ns, CREAM)
px[ns[0] + 1, ns[1]] = NOSE                   # nose
px[ns[0] + 1, ns[1] + 1] = DARK               # mouth line
up = sn["up"]
fill(up, BASE)
px[up[0] + 1, up[1] + up[3] - 1] = DARK       # nose bridge shadow

# cheek fur planes: cream, outer edge serrated via alpha
for ci in (2, 3):
    for f, r in uv["head"][ci].items():
        fill(r, CREAM)
        rx, ry, rw, rh = r
        for j in range(rh):                   # jagged tips on the outer column
            if j % 2 == 0:
                px[rx + rw - 1, ry + j] = (0, 0, 0, 0)

# ears (left mirrors right) --------------------------------------------
ear = uv["ear_right"][0]
for f, r in ear.items():
    fill(r, SHAD)                             # backs/edges darker than body
    noise(r, [DARK], 0.15)
en = ear["north"]                             # inner ear (3x5)
fill(en, CREAM)
x, y, w, h = en
for j in range(h):                            # dark rim, left+top+right
    px[x, y + j] = RIM
    px[x + w - 1, y + j] = RIM
for i in range(w):
    px[x + i, y] = RIM
px[x + 1, y + h - 1] = CREAM_SH               # inner shading at the base

# legs (left mirrors right) --------------------------------------------
for bone, cube_i in (("leg_front_right", 0), ("leg_back_right", 0)):
    f = uv[bone][cube_i]
    fur(f)
    for name, r in f.items():
        if name != "up":
            bottom_rows(r, 1, CREAM)          # cream paws
f = uv["leg_back_right"][1]                   # haunch
fur(f)

# tail: base color, tip segment cream (real fennec) with dark cap ------
for i, bone in enumerate(("tail_0", "tail_1", "tail_2")):
    f = uv[bone][0]
    fur(f)
    if bone == "tail_2":
        for name, r in f.items():
            fill(r, CREAM)
            noise(r, [CREAM_SH], 0.2)
        # dark cap on the very tip (south face + last rows of sides)
        fill(f["south"], RIM)
        for name in ("east", "west", "up", "down"):
            rx, ry, rw, rh = f[name]
            for i2 in range(rx + rw - 1, rx + rw):
                for j2 in range(ry, ry + rh):
                    px[i2, j2] = RIM

tex_path = os.path.join(OUT, "fennec.png")
img.save(tex_path)
print(f"wrote {geo_path}\nwrote {tex_path}")
